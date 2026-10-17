# Security Policy

## Scope

VoiceBridge AI is an **educational prototype** demonstrating conversational AI techniques.
It is not a production financial service and does not process real financial data, store
personally identifiable information (PII), or connect to any bank or lender.

## What this project does handle

- User-typed or speech-recognised text (processed server-side and logged locally)
- An optional OpenAI-compatible API key stored in a local `.env` file (never sent to the browser)
- Conversation transcripts written to `logs/transcripts.jsonl` on the local machine

Credentials shared by a user in chat (e.g., SSNs, card numbers) are detected and **redacted**
before being written to the log. The redaction is best-effort and not a substitute for proper
data handling in production systems.

## Reporting a vulnerability

If you find a security issue (e.g., a way to extract the API key from the server, bypass the
output safety checks, or inject data into the log), please report it **privately**:

1. **Do not** open a public GitHub issue.
2. Email `ojusgupta004@gmail.com` with the subject line `[VoiceBridge AI Security]`.
3. Include a description, reproduction steps, and the potential impact.

You will receive a response within 7 days. Because this is a prototype with no production
deployment, the goal is to fix and document the issue rather than apply a CVE.

## Supported versions

Only the latest commit on `main` is supported. There are no versioned releases at this time.
