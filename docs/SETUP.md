# Setup & Environment

## Prerequisites

- Python **3.11+**
- [Ollama](https://ollama.com/) installed and running locally **or** a free Groq API key

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

- `LLM_PROVIDER`: `ollama` (default) or `groq`
- `OLLAMA_BASE_URL`: Ollama server (default `http://localhost:11434`)
- `OLLAMA_MODEL`: model used for the whole run (intent + planning + synthesis)
- `GROQ_API_KEY`: required when `LLM_PROVIDER=groq`
- `GROQ_MODEL`: Groq model name (default `llama-3.1-8b-instant`)
- `AMADEUS_CLIENT_ID`: Amadeus API key (optional; enables Top‑5 live flights/hotels)
- `AMADEUS_CLIENT_SECRET`: Amadeus API secret (optional)
- `AMADEUS_BASE_URL`: Amadeus base URL (default `https://test.api.amadeus.com`)
- `EMBEDDING_MODEL`: sentence-transformers model name (default `all-MiniLM-L6-v2`)
- `CHROMA_PERSIST_DIR`: persistent Chroma directory (default `./data/chroma_persistent`)
- `RUNTIME_DIR`: where logs/metrics/artifacts are written (default `./runtime`)

## Pull models in Ollama

At minimum, pull the configured model:

```bash
ollama pull qwen2.5:7b-instruct
```

If you change `OLLAMA_MODEL`, pull that name instead.

## Use Groq (free API mode)

Set the provider and key in `.env`:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

## Enable Top‑5 Live Flights/Hotels (Optional)

Amadeus provides a free tier suitable for development/testing. Add to `.env`:

```bash
AMADEUS_CLIENT_ID=your_id
AMADEUS_CLIENT_SECRET=your_secret
AMADEUS_BASE_URL=https://test.api.amadeus.com
```

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
