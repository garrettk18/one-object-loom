# AGENTS.md

## What this is
Single-file Python script (`ool.py`) — a single-branch auto-iterative text generator using Ollama. No build system, no tests, no lint/typecheck config.

## Setup & run
```
.venv\scripts\activate          # Windows; use .venv/bin/activate on Unix
python -m pip install ollama    # or: uv pip install ollama
ollama pull phi3                # or any model
python ool.py                   # starts interactive session
```

## Architecture
- **One file**: `ool.py` is the entire app
- **Flow**: interactive setup prompts → seed chat → infinite loop appending continuation phrases to conversation history
- **Logging**: writes `loom-<session-name>.log` at `logging.INFO`
- **Dependencies**: only `ollama` Python package; requires local Ollama server running

## Pending refactor
The user wants the session logic extracted into its own object class. Currently all session state (conversation history, model, prompts, iteration counter, previous text) lives in module-level globals inside `ool.py`. When refactoring:
- Create a `Session` (or similar) class that owns: model name, system prompt, user message, continuation phrase, conversation_history, ITER, PREVIOUS_TEXT
- Keep the interactive prompt collection either as a classmethod or a separate builder/factory
- Preserve existing behavior: repeat detection with variation phrases, error handling, logging to file
- Do not change the external CLI UX (same prompts, same log file format, same Ctrl+C exit behavior)
