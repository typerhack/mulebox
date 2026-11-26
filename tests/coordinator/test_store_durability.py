"""The store commits so that a power cut keeps what the coordinator answered (design.md, Sudden
power loss). The suite runs with NORMAL (tests/conftest.py); here the real setting is used."""

from pathlib import Path

from mulebox.coordinator import store as st


def test_a_commit_is_synced_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "SYNCHRONOUS", "FULL")
    with st.Store(tmp_path / "queue.db").open() as store, store.write() as conn:
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_the_shipped_setting_is_full():
    assert '\nSYNCHRONOUS = "FULL"\n' in Path(st.__file__).read_text(encoding="utf-8")
