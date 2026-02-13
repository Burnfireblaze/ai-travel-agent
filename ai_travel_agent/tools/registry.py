from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


ToolFn = Callable[..., Mapping[str, Any]]


@dataclass
class ToolRegistry:
    tools: dict[str, ToolFn] = field(default_factory=dict)

    def register(self, name: str, fn: ToolFn) -> None:
        self.tools[name] = fn

    def call(self, name: str, **kwargs: Any) -> Mapping[str, Any]:
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        return self.tools[name](**kwargs)

