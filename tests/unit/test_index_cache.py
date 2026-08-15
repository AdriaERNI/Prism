"""Unit tests for the SQLite index-cache persistence layer.

Uses a temp directory for the DB file (patched via ``_db_path``) so tests
never touch the real user-data cache. Pure local — no IRIS needed.
"""

from unittest.mock import patch

from prism.iris.indexing import cache

SAMPLE = {"classes": [{"name": "A"}, {"name": "B"}], "degree": {"A": 1}}


class TestIndexCache:
    """Round-trip put/get/fresh/status/remove over a temp SQLite DB."""

    def _patch_db(self, tmp_path):
        return patch.object(cache, "_db_path", lambda: tmp_path / "index_cache.db")

    def test_put_get_roundtrip(self, tmp_path):
        with self._patch_db(tmp_path):
            cache.cache_put("USER", "prefix:A", "fp1", SAMPLE)
            out = cache.cache_get("USER", "prefix:A")
        assert out == SAMPLE

    def test_get_missing(self, tmp_path):
        with self._patch_db(tmp_path):
            assert cache.cache_get("USER", "nope") is None

    def test_freshness_exact(self, tmp_path):
        with self._patch_db(tmp_path):
            cache.cache_put("USER", "prefix:A", "fp1", SAMPLE)
            assert cache.cache_is_fresh("USER", "prefix:A", "fp1")
            assert not cache.cache_is_fresh("USER", "prefix:A", "fp2")
            # different namespace -> not fresh
            assert not cache.cache_is_fresh("SYS", "prefix:A", "fp1")

    def test_load_fresh_misses_stale(self, tmp_path):
        with self._patch_db(tmp_path):
            cache.cache_put("USER", "prefix:A", "fp1", SAMPLE)
            assert cache.cache_load("USER", "prefix:A", "fp1") == SAMPLE
            assert cache.cache_load("USER", "prefix:A", "fp-changed") is None

    def test_put_replaces_old_fingerprint(self, tmp_path):
        with self._patch_db(tmp_path):
            cache.cache_put("USER", "prefix:A", "fp1", SAMPLE)
            cache.cache_put("USER", "prefix:A", "fp2", {"classes": []})
            assert not cache.cache_is_fresh("USER", "prefix:A", "fp1")
            assert cache.cache_is_fresh("USER", "prefix:A", "fp2")

    def test_status_reports_classes_and_age(self, tmp_path):
        with self._patch_db(tmp_path):
            cache.cache_put("USER", "prefix:A", "fp1", SAMPLE)
            entries = cache.cache_status("USER", "prefix:A")
        assert len(entries) == 1
        assert entries[0]["namespace"] == "USER"
        assert entries[0]["target"] == "prefix:A"
        assert entries[0]["classes"] == 2  # from cached data
        assert entries[0]["age_seconds"] >= 0

    def test_status_filters_by_namespace(self, tmp_path):
        with self._patch_db(tmp_path):
            cache.cache_put("USER", "prefix:A", "fp1", SAMPLE)
            cache.cache_put("SYS", "prefix:A", "fp1", SAMPLE)
            assert len(cache.cache_status("USER")) == 1
            assert len(cache.cache_status()) == 2

    def test_remove(self, tmp_path):
        with self._patch_db(tmp_path):
            cache.cache_put("USER", "prefix:A", "fp1", SAMPLE)
            cache.cache_remove("USER", "prefix:A")
            assert cache.cache_get("USER", "prefix:A") is None

    def test_tolerant_of_corrupt_json(self, tmp_path):
        with self._patch_db(tmp_path):
            conn = cache._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO index_cache (namespace, target, fingerprint, built_at, data) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("USER", "bad", "fp", 0.0, "{not json"),
                )
                conn.commit()
            finally:
                conn.close()
            assert cache.cache_get("USER", "bad") is None
            entries = cache.cache_status("USER", "bad")
            assert entries[0]["classes"] == 0
