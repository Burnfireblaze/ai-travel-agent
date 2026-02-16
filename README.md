# AI Travel Agent

AI travel agent built with **LangGraph** + **LangChain**, with **Chroma** memory (persistent + in-memory), plus **step-aware logging** and **run metrics**.

## Requirements

- Python 3.11+
- Ollama running locally (`OLLAMA_BASE_URL` default: `http://localhost:11434`) **or** a free Groq API key
- A chat model pulled in Ollama (default: `qwen2.5:7b-instruct`) or a Groq model (default: `llama-3.1-8b-instant`)
- (Optional) Amadeus free tier keys for **Top‑5 live flights/hotels**

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,embeddings]"
cp .env.example .env
```

## Run

```bash
ai-travel-agent
```

## Documentation

See:
- `docs/SETUP.md` for installation + environment setup
- `docs/PROMPTS.md` for example prompts
- `docs/ARCHITECTURE.md` for a full architecture walkthrough (graph flow, memory, tools, logging, metrics, evaluation)

Options:
- `--log-level INFO|DEBUG`
- `--runtime-dir ./runtime`
- `--verbose`

## LLM Providers

By default the app uses **local Ollama**. To use a **free API** instead:

```bash
# .env
LLM_PROVIDER=groq
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.1-8b-instant
```

To switch back to local:

```bash
LLM_PROVIDER=ollama
```

## Live Top‑5 Flights/Hotels (Optional)

If you want actual **Top‑5 results** (not just provider links), add Amadeus keys:

```bash
AMADEUS_CLIENT_ID=your_id
AMADEUS_CLIENT_SECRET=your_secret
AMADEUS_BASE_URL=https://test.api.amadeus.com
```

Artifacts:
- Logs: `runtime/logs/app.jsonl` and `runtime/logs/app.log`
- Metrics: `runtime/metrics/metrics.jsonl`
- Calendar export: `runtime/artifacts/*.ics`

## Notes

- This MVP **does not book** flights/hotels. It produces a plan, deep links, and an `.ics` itinerary export.
- Weather and other network tools degrade gracefully if offline.

## Evaluation

Each run is evaluated with:
- Hard gates (must pass): assumptions coverage, no fabricated prices, valid links, valid ICS, safety disclaimer
- Rubric scores (0–5): relevance, feasibility, completeness, specificity, coherence

The final evaluation is included in `runtime/metrics/metrics.jsonl` for each run.
