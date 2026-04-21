"""Unit tests for workspace path safety and file I/O."""

from unittest.mock import patch

import pytest

from prism.iris.sdk.workspace import (
    workspace_root,
    resolve_safe,
    save_content,
    load_content,
    validate_doc_name,
)


class TestWorkspaceRoot:
    def test_raises_when_not_configured(self):
        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", ""):
            with pytest.raises(RuntimeError, match="not configured"):
                workspace_root()

    def test_returns_resolved_path(self, tmp_path):
        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", str(tmp_path)):
            assert workspace_root() == tmp_path.resolve()


class TestResolveSafe:
    def test_resolves_within_workspace(self, tmp_path):
        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", str(tmp_path)):
            result = resolve_safe("MyApp.Person.cls")
            assert result == tmp_path / "MyApp.Person.cls"

    def test_resolves_nested_path(self, tmp_path):
        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", str(tmp_path)):
            result = resolve_safe("subdir/MyApp.Person.cls")
            assert result == tmp_path / "subdir" / "MyApp.Person.cls"

    def test_blocks_parent_traversal(self, tmp_path):
        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", str(tmp_path)):
            with pytest.raises(ValueError, match="escapes workspace"):
                resolve_safe("../etc/passwd")

    def test_blocks_absolute_path_disguised(self, tmp_path):
        with patch("prism.iris.sdk.workspace.IRIS_WORKSPACE", str(tmp_path)):
            with pytest.raises(ValueError, match="escapes workspace"):
                resolve_safe("foo/../../etc/passwd")


class TestSaveAndLoadContent:
    def test_roundtrip(self, tmp_path):
        lines = ["Class MyApp.Hello", "{", "}", ""]
        file_path = tmp_path / "MyApp.Hello.cls"
        save_content(file_path, lines)
        loaded = load_content(file_path)
        assert loaded == lines

    def test_creates_parent_dirs(self, tmp_path):
        file_path = tmp_path / "deep" / "nested" / "file.cls"
        save_content(file_path, ["line1", "line2"])
        assert file_path.exists()
        assert load_content(file_path) == ["line1", "line2"]

    def test_empty_lines(self, tmp_path):
        file_path = tmp_path / "empty.cls"
        save_content(file_path, [""])
        assert load_content(file_path) == [""]

    def test_load_missing_file(self, tmp_path):
        missing = tmp_path / "NoSuch.cls"
        with pytest.raises(FileNotFoundError, match="Write the file"):
            load_content(missing)


class TestValidateDocName:
    @pytest.mark.parametrize(
        "name",
        [
            "MyApp.Person.cls",
            "Test.MCPPerson.cls",
            "My.Deep.Package.Name.cls",
            "Utils.mac",
            "MyInclude.inc",
            "Routine.int",
            "Legacy.bas",
            "%Library.String.cls",
            "%SYS.Task.cls",
            "Test.BPL.bpl",
            "Test.DTL.dtl",
            "Schema.hl7",
        ],
    )
    def test_valid_names(self, name):
        validate_doc_name(name)  # should not raise

    @pytest.mark.parametrize(
        "name,reason",
        [
            ("", "empty"),
            ("NoExtension", "no dot/extension"),
            (".cls", "starts with dot"),
            ("My App.cls", "space in name"),
            ("../etc/passwd", "path traversal"),
            ("my-app.cls", "hyphen in segment"),
            ("123.cls", "starts with number"),
            ("MyApp.", "trailing dot, no extension"),
            ("MyApp.Person.CLS", "uppercase extension"),
        ],
    )
    def test_invalid_names(self, name, reason):
        with pytest.raises(ValueError, match="Invalid document name"):
            validate_doc_name(name)
