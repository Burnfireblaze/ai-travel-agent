from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FaultInjector:
    simulate_tool_timeout: bool = False
    simulate_tool_error: bool = False
    simulate_bad_retrieval: bool = False
    simulate_llm_error: bool = False
    failure_seed: int = 42
    probability: float = 1.0
    sleep_seconds: float = 5.0
    bad_retrieval_mode: str = "empty"
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.failure_seed)

    def _should_fail(self, enabled: bool) -> bool:
        if not enabled:
            return False
        return self._rng.random() < float(self.probability)

    def maybe_inject_tool_timeout(self, tool_name: str) -> None:
        if self._should_fail(self.simulate_tool_timeout):
            time.sleep(max(0.0, float(self.sleep_seconds)))
            raise TimeoutError(f"Injected tool timeout for '{tool_name}'.")

    def maybe_inject_tool_error(self, tool_name: str) -> None:
        if self._should_fail(self.simulate_tool_error):
            raise RuntimeError(f"Injected tool error for '{tool_name}'.")

    def maybe_inject_bad_retrieval(self, query: str) -> list[dict[str, Any]] | None:
        if not self._should_fail(self.simulate_bad_retrieval):
            return None
        mode = (self.bad_retrieval_mode or "empty").strip().lower()
        if mode == "garbage":
            return [
                {
                    "id": "bad_retrieval_1",
                    "text": f"Injected unrelated content for query: {query}",
                    "metadata": {"type": "injected"},
                    "distance": 0.99,
                }
            ]
        return []

    def maybe_inject_llm_error(self, stage: str) -> None:
        if self._should_fail(self.simulate_llm_error):
            raise RuntimeError(f"Injected LLM failure at stage '{stage}'.")
