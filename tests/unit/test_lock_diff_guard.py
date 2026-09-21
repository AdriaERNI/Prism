from pathlib import Path

from scripts.lock_diff_guard import find_divergent_packages

BASE = """version = "1"
[[package]]
name = "fastmcp"
version = "3.4.7"
source = { registry = "https://pypi.org/simple" }
requires-python = ">=3.9"
[[package]]
name = "mkdocs-material"
version = "9.7.7"
source = { registry = "https://pypi.org/simple" }
"""

HEAD_DIVERGENT = """version = "1"
[[package]]
name = "fastmcp"
version = "4.0.0"
source = { registry = "https://pypi.org/simple" }
requires-python = ">=3.9"
[[package]]
name = "mkdocs-material"
version = "9.7.7"
source = { registry = "https://pypi.org/simple" }
"""

HEAD_UNION = BASE  # identical text -> no divergence


def test_flags_divergent(tmp_path: Path) -> None:
    a = tmp_path / "main.lock"
    b = tmp_path / "head.lock"
    a.write_text(BASE, encoding="utf-8")
    b.write_text(HEAD_DIVERGENT, encoding="utf-8")
    assert find_divergent_packages(str(a), str(b)) == ["fastmcp"]


def test_passes_on_identical(tmp_path: Path) -> None:
    a = tmp_path / "main.lock"
    b = tmp_path / "head.lock"
    a.write_text(BASE, encoding="utf-8")
    b.write_text(HEAD_UNION, encoding="utf-8")
    assert find_divergent_packages(str(a), str(b)) == []


def test_empty_when_no_overlap(tmp_path: Path) -> None:
    a = tmp_path / "main.lock"
    b = tmp_path / "head.lock"
    a.write_text(BASE, encoding="utf-8")
    b.write_text('version = "1"\n', encoding="utf-8")
    assert find_divergent_packages(str(a), str(b)) == []


def test_flags_dependency_list_divergence(tmp_path: Path) -> None:
    """Full-block comparison: a changed dependency list must be flagged even
    when version and source are identical."""
    base = 'version = "1"\n[[package]]\nname = "fastmcp"\nversion = "3.4.7"\nsource = { registry = "https://pypi.org/simple" }\ndependencies = ["pydantic>=2.0"]\n'
    head = 'version = "1"\n[[package]]\nname = "fastmcp"\nversion = "3.4.7"\nsource = { registry = "https://pypi.org/simple" }\ndependencies = ["pydantic>=2.5"]\n'
    a = tmp_path / "main.lock"
    b = tmp_path / "head.lock"
    a.write_text(base, encoding="utf-8")
    b.write_text(head, encoding="utf-8")
    assert find_divergent_packages(str(a), str(b)) == ["fastmcp"]


def test_new_package_on_one_side_is_not_flagged(tmp_path: Path) -> None:
    """Packages present in only one lock are not overlapping hunks."""
    head = BASE + '[[package]]\nname = "extra-pkg"\nversion = "1.0.0"\n'
    a = tmp_path / "main.lock"
    b = tmp_path / "head.lock"
    a.write_text(BASE, encoding="utf-8")
    b.write_text(head, encoding="utf-8")
    assert find_divergent_packages(str(a), str(b)) == []
