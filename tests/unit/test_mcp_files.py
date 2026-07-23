"""Tests for MCP file tools (prism.mcp.files).

Tests verify:
- File reading with path traversal protection
- Binary file detection
- Directory listing
- Error handling for missing files and missing workspace
- File truncation for large files
"""

from __future__ import annotations

import json


from prism.mcp.files import _is_binary, _truncate_content, list_files, read_file


class TestIsBinary:
    """Tests for binary file detection."""

    def test_text_file_not_binary(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        assert _is_binary(f) is False

    def test_binary_file_detected(self, tmp_path):
        f = tmp_path / "binary.dat"
        f.write_bytes(b"\x00\x01\x02\x03\x04\x05")
        assert _is_binary(f) is True

    def test_empty_file_not_binary(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert _is_binary(f) is False

    def test_unicode_text_not_binary(self, tmp_path):
        f = tmp_path / "unicode.txt"
        f.write_text("héllo wörld — 日本語", encoding="utf-8")
        assert _is_binary(f) is False


class TestTruncateContent:
    """Tests for content truncation."""

    def test_short_content_unchanged(self):
        assert _truncate_content("short") == "short"

    def test_long_content_truncated(self):
        text = "x" * 200_000
        result = _truncate_content(text)
        assert len(result) < len(text)
        assert "truncated" in result

    def test_truncates_at_line_boundary(self):
        lines = [f"line {i} " + "x" * 100 for i in range(2000)]
        text = "\n".join(lines)
        result = _truncate_content(text)
        assert "truncated" in result


class TestReadFile:
    """Tests for the read_file MCP tool."""

    async def test_read_text_file(self, tmp_path, monkeypatch):
        """Should read a text file from the workspace."""
        f = tmp_path / "hello.txt"
        f.write_text("Hello, World!")

        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await read_file(path="hello.txt")
        assert result["content"] == "Hello, World!"
        assert result["size"] == 13
        assert result["lines"] == 1
        assert result["truncated"] is False
        assert "hello.txt" in result["path"]

    async def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        """Path traversal should be rejected."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await read_file(path="../../../etc/passwd")
        assert (
            result["error"] is not None
            or "escapes" in result.get("error", "")
            or result["content"] == ""
        )

    async def test_missing_file_returns_error(self, tmp_path, monkeypatch):
        """Missing file should return an error, not crash."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await read_file(path="nonexistent.txt")
        assert result["content"] == ""
        assert "not found" in result["error"].lower()
        assert result["size"] == 0

    async def test_no_workspace_returns_error(self, monkeypatch):
        """Without IRIS_WORKSPACE, should return an error."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", "")
        result = await read_file(path="test.txt")
        assert result["content"] == ""
        assert "IRIS_WORKSPACE" in result["error"]

    async def test_directory_returns_error(self, tmp_path, monkeypatch):
        """Reading a directory should return an error."""
        (tmp_path / "subdir").mkdir()
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await read_file(path="subdir")
        assert result["content"] == ""
        assert "directory" in result["error"].lower()

    async def test_binary_file_rejected(self, tmp_path, monkeypatch):
        """Binary files should be detected and rejected."""
        f = tmp_path / "binary.dat"
        f.write_bytes(b"\x00\x01\x02\x03\x04\x05")
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await read_file(path="binary.dat")
        assert result["content"] == ""
        assert result.get("is_binary") is True
        assert "binary" in result["error"].lower()

    async def test_json_file_read(self, tmp_path, monkeypatch):
        """Should read JSON files."""
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"key": "value"}, indent=2))
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await read_file(path="config.json")
        assert '"key": "value"' in result["content"]
        assert result["size"] > 0

    async def test_nested_path(self, tmp_path, monkeypatch):
        """Should read files in nested directories."""
        sub = tmp_path / "src" / "app"
        sub.mkdir(parents=True)
        f = sub / "main.py"
        f.write_text("print('hello')")
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await read_file(path="src/app/main.py")
        assert result["content"] == "print('hello')"
        assert "src/app/main.py" in result["path"]

    async def test_large_file_truncated(self, tmp_path, monkeypatch):
        """Large files should be truncated."""
        f = tmp_path / "large.txt"
        f.write_text("x" * 200_000)
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await read_file(path="large.txt")
        assert result["truncated"] is True
        assert "truncated" in result["content"]


class TestListFiles:
    """Tests for the list_files MCP tool."""

    async def test_list_root_directory(self, tmp_path, monkeypatch):
        """Should list files in the workspace root."""
        (tmp_path / "file1.py").write_text("x")
        (tmp_path / "file2.py").write_text("y")
        (tmp_path / "subdir").mkdir()
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await list_files()
        assert result["count"] >= 3
        names = [f["name"] for f in result["files"]]
        assert "file1.py" in names
        assert "file2.py" in names
        assert "subdir" in names

    async def test_list_with_glob_pattern(self, tmp_path, monkeypatch):
        """Should filter by glob pattern."""
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("y")
        (tmp_path / "c.txt").write_text("z")
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await list_files(pattern="*.py")
        names = [f["name"] for f in result["files"]]
        assert "a.py" in names
        assert "b.py" in names
        assert "c.txt" not in names

    async def test_list_subdirectory(self, tmp_path, monkeypatch):
        """Should list contents of a subdirectory."""
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "main.py").write_text("x")
        (sub / "utils.py").write_text("y")
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await list_files(path="src")
        assert result["count"] == 2
        names = [f["name"] for f in result["files"]]
        assert "main.py" in names
        assert "utils.py" in names

    async def test_list_no_workspace_error(self, monkeypatch):
        """Without workspace, should return an error."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", "")
        result = await list_files()
        assert result["count"] == 0
        assert "IRIS_WORKSPACE" in result["error"]

    async def test_list_path_traversal_blocked(self, tmp_path, monkeypatch):
        """Path traversal in list_files should be rejected."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await list_files(path="../../../etc")
        assert result["count"] == 0
        assert result["error"] is not None

    async def test_list_missing_path(self, tmp_path, monkeypatch):
        """Listing a nonexistent path should return an error."""
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await list_files(path="nonexistent")
        assert result["count"] == 0
        assert "not found" in result["error"].lower()

    async def test_list_shows_is_dir_flag(self, tmp_path, monkeypatch):
        """File entries should indicate directories vs files."""
        (tmp_path / "file.txt").write_text("x")
        (tmp_path / "dir").mkdir()
        monkeypatch.setattr("prism.settings.settings.iris_workspace", str(tmp_path))
        result = await list_files()
        dirs = [f for f in result["files"] if f["is_dir"]]
        files = [f for f in result["files"] if not f["is_dir"]]
        assert any(f["name"] == "dir" for f in dirs)
        assert any(f["name"] == "file.txt" for f in files)
