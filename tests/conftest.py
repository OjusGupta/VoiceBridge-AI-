"""Isolate every test from the real transcript log (tests used to append to logs/transcripts.jsonl)."""
import pytest
from src.config import Config


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(Config, "RESULTS_DIR", str(tmp_path / "results"))
