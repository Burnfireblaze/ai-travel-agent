from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


def _workspace_root() -> Path:
    configured = os.getenv("AURA_REPO_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def _default_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "aura_policy.yml"


@dataclass(frozen=True)
class AuraBridgeConfig:
    enabled: bool = False
    policy_path: Path = field(default_factory=_default_policy_path)
    host: str = "localhost"
    port: int = 3100
    service_name: str = "ai-travel-agent"
    timeout_s: float = 2.0


@dataclass
class _AuraBridgeState:
    config: AuraBridgeConfig = field(default_factory=AuraBridgeConfig)
    client: Any | None = None
    init_error: str | None = None


_STATE = _AuraBridgeState()


def configure_aura(
    *,
    enabled: bool,
    policy_path: Path | None = None,
    host: str = "localhost",
    port: int = 3100,
    service_name: str = "ai-travel-agent",
    timeout_s: float = 2.0,
) -> None:
    _STATE.config = AuraBridgeConfig(
        enabled=enabled,
        policy_path=(policy_path or _default_policy_path()).resolve(),
        host=host,
        port=port,
        service_name=service_name,
        timeout_s=timeout_s,
    )
    _STATE.client = None
    _STATE.init_error = None


def _build_client():
    workspace_root = _workspace_root()
    workspace_root_str = str(workspace_root)
    if workspace_root_str not in sys.path:
        sys.path.insert(0, workspace_root_str)

    from aura_core.aura import Aura
    from aura_core.config.config import validate_policy_config
    from aura_core.config.policy_schema import PolicyConfig
    from aura_core.logstore.store import LokiLogStore

    with _STATE.config.policy_path.open("r", encoding="utf-8") as f:
        raw_policy = yaml.safe_load(f)

    policy_config = PolicyConfig(**raw_policy)
    validate_policy_config(policy_config)

    store = LokiLogStore(
        {
            "host": _STATE.config.host,
            "port": _STATE.config.port,
            "service_name": _STATE.config.service_name,
            "timeout_s": _STATE.config.timeout_s,
        }
    )
    store.require_ready()
    return Aura(store, policy_config)


def _ensure_client():
    if not _STATE.config.enabled:
        return None

    if _STATE.client is not None:
        return _STATE.client

    if _STATE.init_error is not None:
        return None

    try:
        _STATE.client = _build_client()
    except Exception as exc:
        if "Loki is not ready" in str(exc):
            return None
        _STATE.init_error = str(exc)
        return None

    return _STATE.client


def capture_event(record: Mapping[str, Any]) -> bool:
    client = _ensure_client()
    if client is None:
        return False

    try:
        client.capture(json.dumps(record))
    except Exception:
        return False

    return True


def get_active_ruleset() -> str:
    client = _ensure_client()
    if client is None:
        return "general"
    return client.policy_manager.active_ruleset


def is_detailed_logging_enabled() -> bool:
    return get_active_ruleset() != "general"


def get_aura_status() -> dict[str, Any]:
    return {
        "enabled": _STATE.config.enabled,
        "policy_path": str(_STATE.config.policy_path),
        "active_ruleset": get_active_ruleset(),
        "init_error": _STATE.init_error,
    }
