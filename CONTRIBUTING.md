# Contributing to VoiceBridge AI

Thank you for your interest. This is an educational prototype — contributions that improve clarity,
correctness, or test coverage are especially welcome.

## Setup

```bash
git clone https://github.com/OjusGupta/VoiceBridge-AI-.git
cd VoiceBridge-AI-
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

To also run the optional browser end-to-end tests or the legacy Streamlit UI:

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
```

## Running the tests

```bash
pytest -q           # all 130 backend tests; ~24 s
pytest -v tests/test_safety.py   # single module
```

The test suite never writes to the real `logs/` directory — it uses temporary directories via `conftest.py`.

## Running the server

```bash
uvicorn server:app --port 8000 --reload
# Open http://localhost:8000 in Chrome or Edge
```

## Style guide

- **Python**: follow the existing code style (PEP 8, `from __future__ import annotations`, type hints on all public functions).
- **Docstrings**: use the existing single-line or Google-style docstrings; do not mix styles.
- **Tests**: every new behaviour in `src/` should have a corresponding test in `tests/`.
- **No secrets**: never commit `.env`, API keys, or real personal data.
- **No application-behaviour changes** without a test and a clear explanation.

## What is out of scope

- Real financial decisions, rate calculations, or bank integrations.
- Server-side speech-to-text (the README explains why this is intentionally absent).
- Production deployment infrastructure.

## Submitting a PR

1. Fork the repo and create a branch: `git checkout -b fix/my-fix`
2. Make your changes and run `pytest -q` — all tests must pass.
3. Push and open a PR against `main`. Fill in the PR template.
