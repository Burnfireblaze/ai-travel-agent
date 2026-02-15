# Setup & Environment

## Prerequisites

- Python **3.11+**
- [Ollama](https://ollama.com/) installed and running locally

Optional (recommended for better memory retrieval):
- `sentence-transformers` (installed via extras or `requirements.txt`)

## Install (recommended)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,embeddings]"
```

## Install (minimal, requirements.txt)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure `.env`

Copy the example and edit as needed:

```bash
cp .env.example .env
```

Key variables:

- `OLLAMA_BASE_URL`: Ollama server (default `http://localhost:11434`)
- `OLLAMA_MODEL`: model used for the whole run (intent + planning + synthesis)
- `EMBEDDING_MODEL`: sentence-transformers model name (default `all-MiniLM-L6-v2`)
- `CHROMA_PERSIST_DIR`: persistent Chroma directory (default `./data/chroma_persistent`)
- `RUNTIME_DIR`: where logs/metrics/artifacts are written (default `./runtime`)

## Pull models in Ollama

At minimum, pull the configured model:

```bash
ollama pull qwen2.5:7b-instruct
```

If you change `OLLAMA_MODEL`, pull that name instead.

## Run

```bash
ai-travel-agent
```

Outputs:

- Logs: `runtime/logs/app.jsonl`, `runtime/logs/app.log`
- Metrics: `runtime/metrics/metrics.jsonl`
- Artifacts (ICS): `runtime/artifacts/*.ics`

## Chroma (Memory) Storage

This repo uses two Chroma collections:

- **Persistent** (disk): stored under `CHROMA_PERSIST_DIR` (default `./data/chroma_persistent`)
  - Chroma will create a SQLite DB and related files in that folder.
- **Session** (in-memory): stored in RAM via Chroma `EphemeralClient`
  - Cleared when the process exits.

## Resetting Memory (Optional)

- Delete `CHROMA_PERSIST_DIR` to wipe persistent memory.
- The session store resets automatically per process run (or via `MemoryStore.reset_session()`).
