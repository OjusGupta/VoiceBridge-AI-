"""VoiceBridge AI — Transcript logger module.

Logs each conversation turn to JSONL files for later analysis.
Provides methods to read and clear logs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from src.config import Config
from src.schemas import TurnRecord


class TranscriptLogger:
    """Logs conversation turns to local JSONL files.

    Each session's turns are appended to a single log file.
    No real personal information is collected.
    """

    def __init__(self, log_dir: Optional[str] = None) -> None:
        self._log_dir = Path(log_dir or Config.LOG_DIR)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_file(self) -> Path:
        """Path to the main transcript log file."""
        return self._log_dir / "transcripts.jsonl"

    def log_turn(self, record: TurnRecord) -> None:
        """Append a turn record to the log file.

        Args:
            record: The TurnRecord to log.
        """
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")
        except Exception:
            pass  # Fail silently — logging should not crash the app

    def read_all_turns(self) -> list[dict]:
        """Read all logged turns from the transcript file.

        Returns:
            List of turn dictionaries.
        """
        turns = []
        if not self.log_file.exists():
            return turns
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        turns.append(json.loads(line))
        except Exception:
            pass
        return turns

    def read_session_turns(self, session_id: str) -> list[dict]:
        """Read turns for a specific session.

        Args:
            session_id: The session ID to filter by.

        Returns:
            List of turn dictionaries for that session.
        """
        return [t for t in self.read_all_turns() if t.get("session_id") == session_id]

    def get_all_session_ids(self) -> list[str]:
        """Get a list of unique session IDs in the log.

        Returns:
            Sorted list of unique session IDs.
        """
        ids = set()
        for turn in self.read_all_turns():
            sid = turn.get("session_id")
            if sid:
                ids.add(sid)
        return sorted(ids)

    def clear_logs(self) -> bool:
        """Delete all transcript logs.

        Returns:
            True if cleared successfully, False otherwise.
        """
        try:
            if self.log_file.exists():
                self.log_file.unlink()
            return True
        except Exception:
            return False

    def get_turn_count(self) -> int:
        """Return total number of logged turns."""
        return len(self.read_all_turns())
