"""Tests for the chatbot skills loader (prism.chatbot.skills)."""

from __future__ import annotations

from prism.chatbot.skills import list_skills, load_skills


class TestLoadSkills:
    """Tests for load_skills() — loading markdown files into a prompt string."""

    def test_none_path_returns_empty(self):
        assert load_skills(None) == ""

    def test_empty_string_returns_empty(self):
        assert load_skills("") == ""

    def test_nonexistent_path_returns_empty(self, tmp_path):
        assert load_skills(str(tmp_path / "nonexistent")) == ""

    def test_empty_directory_returns_empty(self, tmp_path):
        assert load_skills(str(tmp_path)) == ""

    def test_single_md_file(self, tmp_path):
        (tmp_path / "guide.md").write_text("# How to query\nUse execute_sql.")
        result = load_skills(str(tmp_path))
        assert "## Skill: guide" in result
        assert "Use execute_sql." in result
        assert result.startswith("# Skills")

    def test_multiple_md_files(self, tmp_path):
        (tmp_path / "sql.md").write_text("SQL guide content")
        (tmp_path / "docs.md").write_text("Docs guide content")
        result = load_skills(str(tmp_path))
        assert "## Skill: sql" in result
        assert "## Skill: docs" in result
        assert "SQL guide content" in result
        assert "Docs guide content" in result

    def test_nested_directories(self, tmp_path):
        (tmp_path / "advanced").mkdir()
        (tmp_path / "advanced" / "debug.md").write_text("Debug guide")
        (tmp_path / "basic.md").write_text("Basic guide")
        result = load_skills(str(tmp_path))
        assert "## Skill: advanced/debug" in result
        assert "## Skill: basic" in result

    def test_empty_md_file_skipped(self, tmp_path):
        (tmp_path / "empty.md").write_text("")
        (tmp_path / "content.md").write_text("Some content")
        result = load_skills(str(tmp_path))
        assert "## Skill: empty" not in result
        assert "## Skill: content" in result

    def test_whitespace_only_md_file_skipped(self, tmp_path):
        (tmp_path / "ws.md").write_text("   \n  \n")
        result = load_skills(str(tmp_path))
        assert result == ""

    def test_non_md_files_ignored(self, tmp_path):
        (tmp_path / "readme.txt").write_text("Not a skill")
        (tmp_path / "data.json").write_text("{}")
        result = load_skills(str(tmp_path))
        assert result == ""

    def test_path_object_accepted(self, tmp_path):
        (tmp_path / "skill.md").write_text("Skill content")
        result = load_skills(tmp_path)
        assert "## Skill: skill" in result

    def test_header_present(self, tmp_path):
        (tmp_path / "s.md").write_text("content")
        result = load_skills(str(tmp_path))
        assert "# Skills" in result
        assert "skill files that provide guidance" in result

    def test_unreadable_file_skipped(self, tmp_path):
        """File that raises OSError should be skipped, not crash."""
        (tmp_path / "good.md").write_text("Good content")
        # Create a file and then make it unreadable (skip on Windows/root)
        import os
        import sys

        bad_file = tmp_path / "bad.md"
        bad_file.write_text("Bad content")
        if sys.platform != "win32" and os.geteuid() != 0:
            os.chmod(bad_file, 0o000)
            try:
                result = load_skills(str(tmp_path))
                assert "## Skill: good" in result
                assert "## Skill: bad" not in result
            finally:
                os.chmod(bad_file, 0o644)


class TestListSkills:
    """Tests for list_skills() — metadata listing."""

    def test_none_path_returns_empty_list(self):
        assert list_skills(None) == []

    def test_empty_string_returns_empty_list(self):
        assert list_skills("") == []

    def test_nonexistent_path_returns_empty_list(self, tmp_path):
        assert list_skills(str(tmp_path / "nope")) == []

    def test_empty_directory_returns_empty_list(self, tmp_path):
        assert list_skills(str(tmp_path)) == []

    def test_single_skill(self, tmp_path):
        (tmp_path / "guide.md").write_text("Content here")
        skills = list_skills(str(tmp_path))
        assert len(skills) == 1
        assert skills[0]["name"] == "guide"
        assert "guide.md" in skills[0]["path"]
        assert "bytes" in skills[0]["size"]

    def test_multiple_skills_sorted(self, tmp_path):
        (tmp_path / "zebra.md").write_text("Z")
        (tmp_path / "alpha.md").write_text("A")
        skills = list_skills(str(tmp_path))
        assert len(skills) == 2
        # Sorted by name
        assert skills[0]["name"] == "alpha"
        assert skills[1]["name"] == "zebra"

    def test_nested_skill_names(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.md").write_text("Nested")
        skills = list_skills(str(tmp_path))
        assert len(skills) == 1
        assert skills[0]["name"] == "sub/nested"

    def test_non_md_files_excluded(self, tmp_path):
        (tmp_path / "skill.md").write_text("Skill")
        (tmp_path / "notes.txt").write_text("Notes")
        (tmp_path / "data.json").write_text("{}")
        skills = list_skills(str(tmp_path))
        assert len(skills) == 1
        assert skills[0]["name"] == "skill"

    def test_path_object_accepted(self, tmp_path):
        (tmp_path / "s.md").write_text("content")
        skills = list_skills(tmp_path)
        assert len(skills) == 1
