# Legacy: Streamlit UI

This directory contains the original Streamlit-based user interface for VoiceBridge AI.

**Status: Superseded — not maintained, not tested.**

The primary interface is now the FastAPI + plain HTML/CSS/JS frontend in `frontend/` and `server.py`.
To run the main application, see the [Quick start](../README.md#quick-start) section.

## Why it is kept

The Streamlit app demonstrates an alternative UI architecture and may be useful for reference.
It is **not tested** in the CI pipeline and may break if dependencies drift.

## Running it (at your own risk)

```bash
pip install -r requirements-dev.txt   # includes streamlit
streamlit run legacy/streamlit_app.py
```

Streamlit must be started from the **project root** (one level above `legacy/`) so that imports from `src/`, `prompts/`, and `evaluation/` resolve correctly.
