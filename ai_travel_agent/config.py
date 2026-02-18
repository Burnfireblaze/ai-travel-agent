from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    ollama_base_url: str
    ollama_model: str
    groq_api_key: str
    groq_model: str
    embedding_model: str
    chroma_persist_dir: Path
    user_id: str
    runtime_dir: Path
    log_level: str
    max_graph_iters: int
    eval_threshold: float
    max_tool_retries: int

    # Fault injection flags
    simulate_tool_timeout: bool = False
    simulate_bad_retrieval: bool = False
    failure_seed: int = 42


def load_settings() -> Settings:
    load_dotenv(override=False)

    runtime_dir = Path(os.getenv("RUNTIME_DIR", "./runtime"))
    chroma_persist_dir = Path(os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_persistent"))
    llm_provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

    return Settings(
        llm_provider=llm_provider,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        chroma_persist_dir=chroma_persist_dir,
        user_id=os.getenv("USER_ID", "local_user"),
        runtime_dir=runtime_dir,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        max_graph_iters=int(os.getenv("MAX_GRAPH_ITERS", "20")),
        eval_threshold=float(os.getenv("EVAL_THRESHOLD", "3.5")),
        max_tool_retries=int(os.getenv("MAX_TOOL_RETRIES", "1")),
        simulate_tool_timeout=os.getenv("SIMULATE_TOOL_TIMEOUT", "false").lower() == "true",
        simulate_bad_retrieval=os.getenv("SIMULATE_BAD_RETRIEVAL", "false").lower() == "true",
        failure_seed=int(os.getenv("FAILURE_SEED", "42")),
    )
