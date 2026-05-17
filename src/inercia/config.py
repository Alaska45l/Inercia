from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

logger = logging.getLogger("inercia.config")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    opencode_api_key: str
    opencode_base_url: str
    opencode_copywriter_model: str
    opencode_user_agent: str
    upwork_session_dir: Path
    db_path: Path
    daily_proposal_cap: int
    ws_port: int
    floor_hourly_rate: float
    floor_fixed_rate: float
    allow_upwork_network: bool


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            logger.debug("Ignoring malformed .env line: %s", raw_line)
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value
    return values


def _get_value(name: str, env_file_values: Mapping[str, str], default: str) -> str:
    return os.environ.get(name, env_file_values.get(name, default))


def _resolve_project_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _parse_int(name: str, value: str, minimum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return parsed


def _parse_float(name: str, value: str, minimum: float) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    return parsed


def _parse_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean.")


def get_settings(env_path: Optional[Path] = None) -> Settings:
    selected_env_path = env_path or DEFAULT_ENV_PATH
    env_file_values = _read_env_file(selected_env_path)

    return Settings(
        gemini_api_key=_get_value("GEMINI_API_KEY", env_file_values, ""),
        opencode_api_key=_get_value("OPENCODE_API_KEY", env_file_values, ""),
        opencode_base_url=_get_value(
            "OPENCODE_BASE_URL",
            env_file_values,
            "https://opencode.ai/zen/go/v1/chat/completions",
        ),
        opencode_copywriter_model=_get_value("OPENCODE_COPYWRITER_MODEL", env_file_values, "kimi-k2.6"),
        opencode_user_agent=_get_value(
            "OPENCODE_USER_AGENT",
            env_file_values,
            (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        ),
        upwork_session_dir=_resolve_project_path(
            _get_value("UPWORK_SESSION_DIR", env_file_values, ".upwork-session")
        ),
        db_path=_resolve_project_path(_get_value("DB_PATH", env_file_values, "inercia.db")),
        daily_proposal_cap=_parse_int(
            "DAILY_PROPOSAL_CAP",
            _get_value("DAILY_PROPOSAL_CAP", env_file_values, "12"),
            1,
        ),
        ws_port=_parse_int("WS_PORT", _get_value("WS_PORT", env_file_values, "9741"), 1),
        floor_hourly_rate=_parse_float(
            "FLOOR_HOURLY_RATE",
            _get_value("FLOOR_HOURLY_RATE", env_file_values, "35"),
            0,
        ),
        floor_fixed_rate=_parse_float(
            "FLOOR_FIXED_RATE",
            _get_value("FLOOR_FIXED_RATE", env_file_values, "50"),
            0,
        ),
        allow_upwork_network=_parse_bool(
            "ALLOW_UPWORK_NETWORK",
            _get_value("ALLOW_UPWORK_NETWORK", env_file_values, "false"),
        ),
    )


settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
