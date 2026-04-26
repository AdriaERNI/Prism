"""Unit tests for the debugging feature: DBGP protocol, session management, API helpers, and tool gating."""

import base64
import time
from unittest.mock import AsyncMock, MagicMock, patch
from xml.etree.ElementTree import Element, SubElement

import httpx
import pytest

from prism.iris.sdk.dbgp import DbgpError, _check_error, _parse_dbgp_response
from prism.iris.sdk.debug_session import DebugSession, SessionManager
from prism.settings import settings
from prism.iris.api.debugger import (
    _context_name,
    _parse_breakpoint_list,
    _parse_location,
    _parse_property,
    _status_to_state,
    attach_session,
    list_processes,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _mock_conn():
    """Create a mock DbgpConnection with async close."""
    conn = MagicMock()
    conn.close = AsyncMock()
    return conn


# ── 1. DBGP protocol parsing ─────────────────────────────────────────


class TestParseDbgpResponse:
    """Tests for _parse_dbgp_response."""

    def test_plain_xml(self):
        xml = '<response command="status" status="break" reason="ok"/>'
        elem = _parse_dbgp_response(xml)
        assert elem.tag == "response"
        assert elem.get("status") == "break"

    def test_iris_length_base64_framed(self):
        """IRIS sends DBGP responses as 'length|base64(xml)'. Verify the
        parser decodes the base64 payload and extracts the XML element."""
        xml = '<response command="step_into" status="break"/>'
        b64 = base64.b64encode(xml.encode("iso-8859-1")).decode()
        framed = f"{len(b64)}|{b64}"
        elem = _parse_dbgp_response(framed)
        assert elem.tag == "response"
        assert elem.get("command") == "step_into"

    def test_iris_framing_with_init(self):
        """The very first message from IRIS is an <init> packet using the
        same 'length|base64(xml)' framing. Confirm it parses correctly."""
        xml = '<init appid="AtelierDebugger" idekey="Atelier" session="123"/>'
        b64 = base64.b64encode(xml.encode("iso-8859-1")).decode()
        framed = f"{len(b64)}|{b64}"
        elem = _parse_dbgp_response(framed)
        assert elem.tag == "init"
        assert elem.get("appid") == "AtelierDebugger"

    def test_namespace_prefixed_tags(self):
        xml = (
            '<response xmlns="urn:debugger_protocol_v1" command="status" status="running">'
            '<message filename="test.cls" lineno="5"/>'
            "</response>"
        )
        elem = _parse_dbgp_response(xml)
        assert "response" in elem.tag
        assert elem.get("status") == "running"

    def test_xml_declaration_prefix(self):
        xml = '<?xml version="1.0" encoding="UTF-8"?><init appid="123" idekey="test"/>'
        elem = _parse_dbgp_response(xml)
        assert "init" in elem.tag
        assert elem.get("appid") == "123"

    def test_whitespace_stripped(self):
        xml = '  <response status="break"/>  '
        elem = _parse_dbgp_response(xml)
        assert elem.get("status") == "break"


class TestCheckError:
    """Tests for _check_error."""

    def test_raises_on_error_response(self):
        root = Element("response")
        err = SubElement(root, "error", code="100")
        msg = SubElement(err, "message")
        msg.text = "command parse error"

        with pytest.raises(DbgpError, match="DBGP error 100"):
            _check_error(root)

    def test_raises_on_namespaced_error(self):
        root = Element("response")
        err = SubElement(root, "{urn:debugger_protocol_v1}error", code="200")
        msg = SubElement(err, "{urn:debugger_protocol_v1}message")
        msg.text = "unimplemented command"

        with pytest.raises(DbgpError) as exc_info:
            _check_error(root)
        assert exc_info.value.code == 200

    def test_passes_on_clean_response(self):
        root = Element("response", command="step_into", status="break")
        _check_error(root)  # Should not raise

    def test_error_with_missing_message_text(self):
        root = Element("response")
        err = SubElement(root, "error", code="5")
        SubElement(err, "message")  # Empty text

        with pytest.raises(DbgpError, match="Unknown error"):
            _check_error(root)

    def test_dbgp_error_attributes(self):
        root = Element("response")
        err = SubElement(root, "error", code="302")
        msg = SubElement(err, "message")
        msg.text = "can not get property"

        with pytest.raises(DbgpError) as exc_info:
            _check_error(root)
        assert exc_info.value.code == 302
        assert "302" in str(exc_info.value)
        assert "can not get property" in str(exc_info.value)


# ── 2. Session manager ───────────────────────────────────────────────


class TestDebugSession:
    """Tests for the DebugSession data class."""

    def test_session_attributes(self):
        conn = _mock_conn()
        session = DebugSession(conn, "Main^MyRoutine", "USER")
        assert session.target == "Main^MyRoutine"
        assert session.namespace == "USER"
        assert session.state == "starting"
        assert len(session.id) == 12
        assert session.conn is conn

    def test_touch_resets_idle_timer(self):
        conn = _mock_conn()
        session = DebugSession(conn, "target", None)
        before = session.last_active
        # Simulate time passing
        session.last_active -= 10
        session.touch()
        assert session.last_active >= before

    def test_is_expired(self):
        conn = _mock_conn()
        session = DebugSession(conn, "target", None)
        assert not session.is_expired
        # Force expiry by backdating last_active
        with patch.object(settings, "iris_debug_idle_timeout", 0):
            # Even with timeout=0, idle_seconds is very small right after creation
            session.last_active = time.monotonic() - 1
            assert session.is_expired


class TestSessionManager:
    """Tests for SessionManager lifecycle operations."""

    async def test_create_session(self):
        mgr = SessionManager(max_sessions=2)
        conn = _mock_conn()
        session = await mgr.create(conn, "##class(Pkg.Cls).Run()", "USER")
        assert session.target == "##class(Pkg.Cls).Run()"
        assert session.namespace == "USER"
        assert session.state == "starting"
        assert session.id in [s["session_id"] for s in mgr.active_sessions]

    async def test_get_retrieves_and_touches(self):
        mgr = SessionManager(max_sessions=2)
        conn = _mock_conn()
        session = await mgr.create(conn, "target", None)
        # Backdate the last_active
        session.last_active -= 100
        old_active = session.last_active

        retrieved = mgr.get(session.id)
        assert retrieved is session
        assert retrieved.last_active > old_active

    async def test_get_raises_for_missing_id(self):
        mgr = SessionManager(max_sessions=2)
        with pytest.raises(KeyError, match="No active debug session"):
            mgr.get("nonexistent")

    async def test_get_raises_for_expired_session(self):
        mgr = SessionManager(max_sessions=2)
        conn = _mock_conn()
        session = await mgr.create(conn, "target", None)
        # Force expiry
        with patch.object(settings, "iris_debug_idle_timeout", 0):
            session.last_active = time.monotonic() - 1
            with pytest.raises(KeyError, match="expired"):
                mgr.get(session.id)

    async def test_close_removes_session(self):
        mgr = SessionManager(max_sessions=2)
        conn = _mock_conn()
        session = await mgr.create(conn, "target", None)
        result = await mgr.close(session.id)
        assert result is True
        conn.close.assert_awaited_once()

        with pytest.raises(KeyError):
            mgr.get(session.id)

    async def test_close_nonexistent_returns_false(self):
        mgr = SessionManager(max_sessions=2)
        result = await mgr.close("nope")
        assert result is False

    async def test_max_sessions_limit(self):
        mgr = SessionManager(max_sessions=1)
        conn1 = _mock_conn()
        await mgr.create(conn1, "target1", None)

        conn2 = _mock_conn()
        with pytest.raises(RuntimeError, match="Maximum concurrent debug sessions"):
            await mgr.create(conn2, "target2", None)

    async def test_max_sessions_allows_after_close(self):
        mgr = SessionManager(max_sessions=1)
        conn1 = _mock_conn()
        session = await mgr.create(conn1, "target1", None)
        await mgr.close(session.id)

        conn2 = _mock_conn()
        session2 = await mgr.create(conn2, "target2", None)
        assert session2.target == "target2"

    async def test_close_all(self):
        mgr = SessionManager(max_sessions=5)
        conns = [_mock_conn() for _ in range(3)]
        for i, conn in enumerate(conns):
            await mgr.create(conn, f"target{i}", None)

        count = await mgr.close_all()
        assert count == 3
        assert mgr.active_sessions == []
        for c in conns:
            c.close.assert_awaited_once()


# ── 3. API helpers ────────────────────────────────────────────────────


class TestStatusToState:
    """Tests for _status_to_state mapping."""

    def test_break(self):
        assert _status_to_state("break") == "break"

    def test_stopping(self):
        assert _status_to_state("stopping") == "ended"

    def test_stopped(self):
        assert _status_to_state("stopped") == "ended"

    def test_running(self):
        assert _status_to_state("running") == "running"

    def test_empty_string(self):
        assert _status_to_state("") == "unknown"

    def test_unknown_status(self):
        assert _status_to_state("starting") == "starting"


class TestParseLocation:
    """Tests for _parse_location."""

    def test_location_from_attributes(self):
        elem = Element("response", filename="MyApp.Utils.cls", lineno="42")
        loc = _parse_location(elem)
        assert loc["filename"] == "MyApp.Utils.cls"
        assert loc["line"] == 42

    def test_location_from_message_child(self):
        elem = Element("response")
        SubElement(
            elem,
            "{urn:debugger_protocol_v1}message",
            filename="Pkg.Cls.cls",
            lineno="10",
        )
        loc = _parse_location(elem)
        assert loc["filename"] == "Pkg.Cls.cls"
        assert loc["line"] == 10

    def test_location_from_plain_message_child(self):
        elem = Element("response")
        SubElement(elem, "message", filename="test.mac", lineno="3")
        loc = _parse_location(elem)
        assert loc["filename"] == "test.mac"
        assert loc["line"] == 3

    def test_empty_response(self):
        elem = Element("response")
        loc = _parse_location(elem)
        assert loc == {}


class TestParseProperty:
    """Tests for _parse_property."""

    def test_simple_value(self):
        elem = Element("property", name="x", fullname="x", type="string")
        elem.text = "hello"
        result = _parse_property(elem)
        assert result["name"] == "x"
        assert result["type"] == "string"
        assert result["value"] == "hello"

    def test_base64_encoded_value(self):
        elem = Element(
            "property", name="data", fullname="data", type="string", encoding="base64"
        )
        elem.text = base64.b64encode(b"decoded value").decode("ascii")
        result = _parse_property(elem)
        assert result["value"] == "decoded value"

    def test_no_value(self):
        elem = Element("property", name="obj", fullname="obj", type="object")
        result = _parse_property(elem)
        assert "value" not in result
        assert result["type"] == "object"

    def test_nested_children(self):
        parent = Element(
            "property", name="obj", fullname="obj", type="object", numchildren="1"
        )
        child = SubElement(
            parent, "property", name="prop", fullname="obj.prop", type="int"
        )
        child.text = "42"
        result = _parse_property(parent)
        assert result["num_children"] == 1
        assert len(result["children"]) == 1
        assert result["children"][0]["name"] == "obj.prop"
        assert result["children"][0]["value"] == "42"

    def test_fullname_preferred_over_name(self):
        elem = Element("property", name="short", fullname="long.name", type="string")
        elem.text = "val"
        result = _parse_property(elem)
        assert result["name"] == "long.name"

    def test_name_fallback_when_no_fullname(self):
        elem = Element("property", name="x", type="int")
        elem.text = "5"
        result = _parse_property(elem)
        assert result["name"] == "x"


class TestParseBreakpointList:
    """Tests for _parse_breakpoint_list."""

    def test_parses_breakpoints(self):
        root = Element("response", command="breakpoint_list")
        SubElement(
            root,
            "breakpoint",
            id="1",
            type="line",
            state="enabled",
            filename="Pkg.Cls.cls",
            lineno="10",
            function="Method",
            hit_count="3",
        )
        SubElement(
            root,
            "breakpoint",
            id="2",
            type="conditional",
            state="disabled",
            filename="Other.cls",
            lineno="20",
            function="Run",
            hit_count="0",
        )

        bps = _parse_breakpoint_list(root)
        assert len(bps) == 2
        assert bps[0]["id"] == "1"
        assert bps[0]["type"] == "line"
        assert bps[0]["state"] == "enabled"
        assert bps[0]["filename"] == "Pkg.Cls.cls"
        assert bps[0]["lineno"] == 10
        assert bps[0]["method"] == "Method"
        assert bps[0]["hit_count"] == 3
        assert bps[1]["id"] == "2"
        assert bps[1]["state"] == "disabled"

    def test_empty_breakpoint_list(self):
        root = Element("response", command="breakpoint_list")
        bps = _parse_breakpoint_list(root)
        assert bps == []

    def test_ignores_non_breakpoint_children(self):
        root = Element("response")
        SubElement(
            root,
            "breakpoint",
            id="1",
            type="line",
            state="enabled",
            filename="f",
            lineno="1",
            function="m",
            hit_count="0",
        )
        SubElement(root, "other", id="ignore")
        bps = _parse_breakpoint_list(root)
        assert len(bps) == 1

    def test_namespaced_breakpoint_tags(self):
        root = Element("response")
        SubElement(
            root,
            "{urn:debugger_protocol_v1}breakpoint",
            id="1",
            type="line",
            state="enabled",
            filename="x.cls",
            lineno="5",
            function="Go",
            hit_count="1",
        )
        bps = _parse_breakpoint_list(root)
        assert len(bps) == 1
        assert bps[0]["id"] == "1"


class TestContextName:
    """Tests for _context_name mapping."""

    def test_private(self):
        assert _context_name(0) == "private"

    def test_public(self):
        assert _context_name(1) == "public"

    def test_class(self):
        assert _context_name(2) == "class"

    def test_unknown(self):
        assert _context_name(99) == "context_99"


# ── 4. Tool gating ───────────────────────────────────────────────────


class TestToolGating:
    """Debug tools are conditionally registered based on IRIS_DEBUG_ENABLED."""

    async def test_debug_tools_not_registered_when_disabled(self):
        from fastmcp import Client

        from prism.mcp.server import create_mcp

        with patch.object(settings, "iris_debug_enabled", False):
            import prism.mcp as tools_pkg

            orig_skip = tools_pkg._SKIP_MODULES.copy()
            tools_pkg._SKIP_MODULES.add("debugger")
            try:
                mcp = create_mcp()
                client = Client(mcp)
                async with client:
                    tools = await client.list_tools()
                    names = {t.name for t in tools}
                    assert "debug_start" not in names
                    assert "debug_step" not in names
                    assert "debug_inspect" not in names
                    assert "debug_variables" not in names
                    assert "debug_stack" not in names
                    assert "debug_breakpoints" not in names
                    assert "debug_stop" not in names
                    assert "debug_list_processes" not in names
                    assert "debug_attach" not in names
            finally:
                tools_pkg._SKIP_MODULES = orig_skip

    async def test_debug_tools_registered_when_enabled(self):
        from fastmcp import Client

        from prism.mcp.server import create_mcp

        with patch.object(settings, "iris_debug_enabled", True):
            import prism.mcp as tools_pkg

            orig_skip = tools_pkg._SKIP_MODULES.copy()
            tools_pkg._SKIP_MODULES.discard("debugger")
            try:
                mcp = create_mcp()
                client = Client(mcp)
                async with client:
                    tools = await client.list_tools()
                    names = {t.name for t in tools}
                    assert "debug_start" in names
                    assert "debug_step" in names
                    assert "debug_inspect" in names
                    assert "debug_variables" in names
                    assert "debug_stack" in names
                    assert "debug_breakpoints" in names
                    assert "debug_stop" in names
                    assert "debug_list_processes" in names
                    assert "debug_attach" in names
            finally:
                tools_pkg._SKIP_MODULES = orig_skip


# ── 5. Process listing and attach ────────────────────────────────────


def _mock_httpx_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestListProcesses:
    """Tests for list_processes API function."""

    async def test_list_processes_basic(self):
        json_data = {
            "result": {
                "content": [
                    {
                        "pid": 1234,
                        "namespace": "USER",
                        "routine": "Main^MyApp",
                        "state": "RUN",
                        "device": "/dev/null",
                    },
                    {
                        "pid": 5678,
                        "namespace": "%SYS",
                        "routine": "CONTROL",
                        "state": "HANG",
                        "device": "",
                    },
                ]
            }
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_httpx_response(json_data))

        with patch("prism.iris.api.debugger.client", return_value=mock_client):
            result = await list_processes(system=False)

        assert len(result) == 2
        assert result[0]["pid"] == 1234
        assert result[0]["namespace"] == "USER"
        assert result[0]["routine"] == "Main^MyApp"
        assert result[0]["state"] == "RUN"
        assert result[0]["device"] == "/dev/null"
        assert result[1]["pid"] == 5678

    async def test_list_processes_empty(self):
        json_data = {"result": {"content": []}}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_httpx_response(json_data))

        with patch("prism.iris.api.debugger.client", return_value=mock_client):
            result = await list_processes()

        assert result == []

    async def test_list_processes_system_param(self):
        json_data = {"result": {"content": []}}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_httpx_response(json_data))

        with patch("prism.iris.api.debugger.client", return_value=mock_client):
            await list_processes(system=True)

        # Verify the system=1 param was passed
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["system"] == "1"

    async def test_list_processes_system_false_param(self):
        json_data = {"result": {"content": []}}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_httpx_response(json_data))

        with patch("prism.iris.api.debugger.client", return_value=mock_client):
            await list_processes(system=False)

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["system"] == "0"

    async def test_list_processes_missing_fields(self):
        """Processes with missing fields should use defaults."""
        json_data = {"result": {"content": [{"pid": 999}]}}
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_httpx_response(json_data))

        with patch("prism.iris.api.debugger.client", return_value=mock_client):
            result = await list_processes()

        assert result[0]["pid"] == 999
        assert result[0]["namespace"] == ""
        assert result[0]["routine"] == ""
        assert result[0]["state"] == ""
        assert result[0]["device"] == ""


class TestAttachSession:
    """Tests for attach_session API function."""

    async def test_attach_sends_pid_target(self):
        """Verify debug_target is set to PID:{pid} without namespace prefix."""
        mock_conn = MagicMock()
        mock_conn.close = AsyncMock()

        # Track all send_command calls
        break_resp = Element("response", command="step_into", status="break")
        mock_conn.send_command = AsyncMock(return_value=break_resp)

        mock_manager = MagicMock()
        mock_session = DebugSession(mock_conn, "PID:1234", "USER")
        mock_manager.create = AsyncMock(return_value=mock_session)
        mock_manager.get = MagicMock(return_value=mock_session)
        mock_manager.close = AsyncMock()

        with (
            patch(
                "prism.iris.api.debugger.DbgpConnection.connect",
                new_callable=AsyncMock,
                return_value=mock_conn,
            ),
            patch(
                "prism.iris.api.debugger.get_session_manager", return_value=mock_manager
            ),
        ):
            result = await attach_session(pid=1234, namespace="USER")

        # Verify debug_target was set with PID: prefix (no namespace prefix)
        target_call = [
            c
            for c in mock_conn.send_command.call_args_list
            if c.args[0] == "feature_set" and c.kwargs.get("n") == "debug_target"
        ]
        assert len(target_call) == 1
        assert target_call[0].kwargs["v"] == "PID:1234"

        assert result["session_id"] == mock_session.id
        assert result["state"] == "break"
        assert result["target"] == "PID:1234"

    async def test_attach_polls_until_break(self):
        """Verify the polling loop retries step_into until status is 'break'."""
        mock_conn = MagicMock()
        mock_conn.close = AsyncMock()

        running_resp = Element("response", command="step_into", status="running")
        break_resp = Element(
            "response",
            command="step_into",
            status="break",
            filename="MyApp.cls",
            lineno="10",
        )

        # stack_get response for _get_context_variables auto-detect
        stack_resp = Element("response", command="stack_get")
        SubElement(
            stack_resp,
            "stack",
            level="1",
            type="file",
            filename="MyApp.cls",
            lineno="10",
            where="Method",
            cmdbegin="10",
        )
        # context_get response (empty variables)
        context_resp = Element("response", command="context_get")

        # Attach sequence: debug_target first, then 4 feature_sets,
        # 2 runs, break, step_into polls
        mock_conn.send_command = AsyncMock(
            side_effect=[
                Element("response"),  # feature_set debug_target (first)
                Element("response"),  # feature_set max_data
                Element("response"),  # feature_set max_children
                Element("response"),  # feature_set max_depth
                Element("response"),  # feature_set step_granularity
                running_resp,  # first run (ignored by IRIS)
                running_resp,  # second run (binds debugger)
                running_resp,  # break (interrupt attempt)
                running_resp,  # step_into (poll 1)
                running_resp,  # step_into (poll 2)
                break_resp,  # step_into (poll 3) — success
                stack_resp,  # stack_get (auto-detect level)
                context_resp,  # context_get (fetch variables)
            ]
        )

        mock_manager = MagicMock()
        mock_session = DebugSession(mock_conn, "PID:42", None)
        mock_manager.create = AsyncMock(return_value=mock_session)
        mock_manager.close = AsyncMock()

        with (
            patch(
                "prism.iris.api.debugger.DbgpConnection.connect",
                new_callable=AsyncMock,
                return_value=mock_conn,
            ),
            patch(
                "prism.iris.api.debugger.get_session_manager", return_value=mock_manager
            ),
            patch("prism.iris.api.debugger.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await attach_session(pid=42)

        assert result["state"] == "break"
        assert result["location"]["filename"] == "MyApp.cls"
        assert result["location"]["line"] == 10

    async def test_attach_fails_on_stopped(self):
        """Verify attach raises when process returns 'stopped' status."""
        mock_conn = MagicMock()
        mock_conn.close = AsyncMock()

        stopped_resp = Element("response", command="step_into", status="stopped")
        mock_conn.send_command = AsyncMock(
            side_effect=[
                Element("response"),  # feature_set debug_target (sent first)
                Element("response"),  # feature_set max_data
                Element("response"),  # feature_set max_children
                Element("response"),  # feature_set max_depth
                Element("response"),  # feature_set step_granularity
                Element("response", status="running"),  # first run (ignored)
                Element("response", status="running"),  # second run (binds)
                Element("response", status="running"),  # break (interrupt)
                stopped_resp,  # step_into — process already done
            ]
        )

        mock_manager = MagicMock()
        mock_session = DebugSession(mock_conn, "PID:99", None)
        mock_manager.create = AsyncMock(return_value=mock_session)
        mock_manager.close = AsyncMock()

        with (
            patch(
                "prism.iris.api.debugger.DbgpConnection.connect",
                new_callable=AsyncMock,
                return_value=mock_conn,
            ),
            patch(
                "prism.iris.api.debugger.get_session_manager", return_value=mock_manager
            ),
            patch("prism.iris.api.debugger.asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(RuntimeError, match="Attach failed.*stopped"):
                await attach_session(pid=99)

        # Verify cleanup happened
        mock_manager.close.assert_awaited_once()

    async def test_attach_timeout(self):
        """Verify attach raises after timeout if process never reaches 'break'."""
        mock_conn = MagicMock()
        mock_conn.close = AsyncMock()

        running_resp = Element("response", command="step_into", status="running")
        mock_conn.send_command = AsyncMock(return_value=running_resp)
        # Override to return feature_set responses then always running
        call_count = 0
        original_running = running_resp

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 5:  # feature_set calls (debug_target + 4 features)
                return Element("response")
            return original_running

        mock_conn.send_command = AsyncMock(side_effect=side_effect)

        mock_manager = MagicMock()
        mock_session = DebugSession(mock_conn, "PID:77", None)
        mock_manager.create = AsyncMock(return_value=mock_session)
        mock_manager.close = AsyncMock()

        with (
            patch(
                "prism.iris.api.debugger.DbgpConnection.connect",
                new_callable=AsyncMock,
                return_value=mock_conn,
            ),
            patch(
                "prism.iris.api.debugger.get_session_manager", return_value=mock_manager
            ),
            patch("prism.iris.api.debugger.asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                await attach_session(pid=77)

    async def test_attach_cleans_up_on_connect_error(self):
        """Verify connection is closed on each attempt when errors occur."""
        mock_conn = MagicMock()
        mock_conn.close = AsyncMock()
        mock_conn.send_command = AsyncMock(side_effect=Exception("connection failed"))

        with (
            patch(
                "prism.iris.api.debugger.DbgpConnection.connect",
                new_callable=AsyncMock,
                return_value=mock_conn,
            ),
            patch("prism.iris.api.debugger.get_session_manager") as mock_get_mgr,
            patch("prism.iris.api.debugger.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_get_mgr.return_value = MagicMock()
            with pytest.raises(Exception, match="connection failed"):
                await attach_session(pid=1)

        # Connection-level errors retry 4 times, close called on each attempt
        assert mock_conn.close.await_count == 4
