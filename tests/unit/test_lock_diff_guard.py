from pathlib import Path

from scripts.lock_diff_guard import find_divergent_packages

BASE = '''version = "1"
[[package]]
name = "fastmcp"
version = "3.4.7"
source = { registry = "https://pypi.org/simple" }
requires-python = ">=3.9"
[[package]]
name = "mkdocs-material"
version = "9.7.7"
source = { registry = "https://pypi.org/simple" }
'''

HEAD_DIVERGENT = '''version = "1"
[[package]]
name = "fastmcp"
version = "4.0.0"
source = { registry = "https://pypi.org/simple" }
requires-python = ">=3.9"
[[package]]
name = "mkdocs-material"
version = "9.7.7"
source = { registry = "https://pypi.org/simple" }
'''

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
