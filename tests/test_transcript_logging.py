"""Tests for transcript logging and analytics."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.transcript_logger import TranscriptLogger
from src.analytics import Analytics
from src.schemas import TurnRecord


@pytest.fixture
def temp_log_dir(tmp_path):
    """Provide a temporary directory for log files."""
    return str(tmp_path)


@pytest.fixture
def logger(temp_log_dir):
    """Create a TranscriptLogger with a temp directory."""
    return TranscriptLogger(log_dir=temp_log_dir)


@pytest.fixture
def sample_turns():
    """Create sample turn records for testing."""
    return [
        TurnRecord(
            session_id="sess-001",
            turn_number=0,
            state="GREETING",
            user_message="",
            assistant_response="Hello!",
            detected_intent="GREETING",
            prompt_version="A",
            response_mode="local",
            response_time_ms=5.0,
        ),
        TurnRecord(
            session_id="sess-001",
            turn_number=1,
            state="CONSENT",
            user_message="yes",
            assistant_response="What would you like to know?",
            detected_intent="AFFIRMATIVE",
            prompt_version="A",
            response_mode="local",
            response_time_ms=3.0,
        ),
        TurnRecord(
            session_id="sess-001",
            turn_number=2,
            state="COMPLETED",
            user_message="goodbye",
            assistant_response="Thanks!",
            detected_intent="EXIT",
            prompt_version="A",
            response_mode="local",
            response_time_ms=2.0,
        ),
        TurnRecord(
            session_id="sess-002",
            turn_number=0,
            state="GREETING",
            user_message="",
            assistant_response="Hello!",
            detected_intent="GREETING",
            clarification_required=True,
            prompt_version="B",
            response_mode="local",
            response_time_ms=4.0,
        ),
    ]


class TestTranscriptLogger:
    """Test transcript logging functionality."""

    def test_log_and_read(self, logger, sample_turns):
        logger.log_turn(sample_turns[0])
        turns = logger.read_all_turns()
        assert len(turns) == 1
        assert turns[0]["session_id"] == "sess-001"

    def test_multiple_turns(self, logger, sample_turns):
        for turn in sample_turns:
            logger.log_turn(turn)
        turns = logger.read_all_turns()
        assert len(turns) == 4

    def test_read_session(self, logger, sample_turns):
        for turn in sample_turns:
            logger.log_turn(turn)
        sess_turns = logger.read_session_turns("sess-001")
        assert len(sess_turns) == 3

    def test_get_session_ids(self, logger, sample_turns):
        for turn in sample_turns:
            logger.log_turn(turn)
        ids = logger.get_all_session_ids()
        assert "sess-001" in ids
        assert "sess-002" in ids

    def test_clear_logs(self, logger, sample_turns):
        logger.log_turn(sample_turns[0])
        assert logger.get_turn_count() == 1
        success = logger.clear_logs()
        assert success
        assert logger.get_turn_count() == 0

    def test_empty_log(self, logger):
        turns = logger.read_all_turns()
        assert turns == []

    def test_turn_count(self, logger, sample_turns):
        for turn in sample_turns:
            logger.log_turn(turn)
        assert logger.get_turn_count() == 4


class TestAnalytics:
    """Test analytics computation."""

    def test_empty_analytics(self, temp_log_dir):
        logger = TranscriptLogger(log_dir=temp_log_dir)
        analytics = Analytics(logger)
        summary = analytics.compute_summary()
        assert summary["total_sessions"] == 0
        assert summary["total_turns"] == 0

    def test_summary_with_data(self, temp_log_dir, sample_turns):
        logger = TranscriptLogger(log_dir=temp_log_dir)
        for turn in sample_turns:
            logger.log_turn(turn)

        analytics = Analytics(logger)
        summary = analytics.compute_summary()

        assert summary["total_sessions"] == 2
        assert summary["total_turns"] == 4
        assert summary["completed_sessions"] == 1
        assert summary["clarification_turns"] == 1

    def test_prompt_comparison(self, temp_log_dir, sample_turns):
        logger = TranscriptLogger(log_dir=temp_log_dir)
        for turn in sample_turns:
            logger.log_turn(turn)

        analytics = Analytics(logger)
        comparison = analytics.compute_prompt_comparison()

        assert "A" in comparison
        assert "B" in comparison
        assert comparison["A"]["total_turns"] == 3
        assert comparison["B"]["total_turns"] == 1

    def test_intent_distribution(self, temp_log_dir, sample_turns):
        logger = TranscriptLogger(log_dir=temp_log_dir)
        for turn in sample_turns:
            logger.log_turn(turn)

        analytics = Analytics(logger)
        summary = analytics.compute_summary()
        dist = summary["intent_distribution"]
        assert "GREETING" in dist
        assert dist["GREETING"] == 2
