from __future__ import annotations

import os
import logging
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

logger = logging.getLogger("inercia.config")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class UpworkSearchFilters:
    categories: list[str]
    experience_levels: list[str]
    job_types: list[str]
    budget_min: Optional[float]
    budget_max: Optional[float]
    hourly_rate_min: Optional[float]
    hourly_rate_max: Optional[float]
    hours_per_week: list[str]
    project_lengths: list[str]
    client_history: list[str]
    client_location: str
    proposals: list[str]
    max_connects: int


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
    login_debug_port: int
    floor_hourly_rate: float
    floor_fixed_rate: float
    allow_upwork_network: bool
    scheduler_interval_min_minutes: int
    scheduler_interval_max_minutes: int
    blacklist_keywords: list[str]
    upwork_search_filters: UpworkSearchFilters
    portfolio_attachments: list[Path]


DEFAULT_BLACKLIST_KEYWORDS: tuple[str, ...] = (
    "wordpress",
    "wix",
    "shopify",
    "squarespace",
    "bigcommerce",
    "elementor",
    "divi",
    "webflow",
    "woocommerce",
    "magento",
    "prestashop",
    "joomla",
    "drupal",
    "godaddy",
    "weebly",
    "php developer",
    "theme customization",
    "plugin development",
)

DEFAULT_UPWORK_SEARCH_FILTERS = UpworkSearchFilters(
    categories=[],
    experience_levels=["Intermediate", "Expert"],
    job_types=["Hourly", "Fixed"],
    budget_min=None,
    budget_max=None,
    hourly_rate_min=None,
    hourly_rate_max=None,
    hours_per_week=[],
    project_lengths=[],
    client_history=[],
    client_location="",
    proposals=[],
    max_connects=16,
)

DEFAULT_SETTING_VALUES: dict[str, str] = {
    "GEMINI_API_KEY": "",
    "OPENCODE_API_KEY": "",
    "OPENCODE_BASE_URL": "https://opencode.ai/zen/go/v1/chat/completions",
    "OPENCODE_COPYWRITER_MODEL": "kimi-k2.6",
    "OPENCODE_USER_AGENT": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "UPWORK_SESSION_DIR": ".upwork-session",
    "DB_PATH": "inercia.db",
    "DAILY_PROPOSAL_CAP": "12",
    "WS_PORT": "9741",
    "LOGIN_DEBUG_PORT": "9742",
    "FLOOR_HOURLY_RATE": "35",
    "FLOOR_FIXED_RATE": "50",
    "ALLOW_UPWORK_NETWORK": "false",
    "SCHEDULER_INTERVAL_MIN_MINUTES": "5",
    "SCHEDULER_INTERVAL_MAX_MINUTES": "15",
    "blacklist_keywords": json.dumps(list(DEFAULT_BLACKLIST_KEYWORDS)),
    "upwork_search_filters": json.dumps(asdict(DEFAULT_UPWORK_SEARCH_FILTERS)),
    "portfolio_attachments": "[]",
}

RUNTIME_SETTING_KEYS: tuple[str, ...] = tuple(DEFAULT_SETTING_VALUES)


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


def _read_session_values(db_path: Path) -> dict[str, str]:
    if not db_path.exists():
        return {}
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            rows = conn.execute("SELECT key, value FROM sessions;").fetchall()
    except sqlite3.Error as exc:
        logger.debug("Skipping DB settings overrides from %s: %s", db_path, exc)
        return {}
    return {str(key): str(value) for key, value in rows}


def _get_value(
    name: str,
    env_file_values: Mapping[str, str],
    session_values: Mapping[str, str],
    default: str,
) -> str:
    return session_values.get(name, os.environ.get(name, env_file_values.get(name, default)))


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


def _parse_optional_float(name: str, value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return _parse_float(name, str(value), 0)


def _parse_string_list(name: str, value: str, fallback: list[str]) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON list for %s; using defaults", name)
        return fallback
    if not isinstance(parsed, list):
        return fallback
    return [str(item).strip() for item in parsed if str(item).strip()]


def _parse_search_filters(value: str) -> UpworkSearchFilters:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        logger.warning("Invalid upwork_search_filters JSON; using defaults")
        return DEFAULT_UPWORK_SEARCH_FILTERS
    if not isinstance(parsed, dict):
        return DEFAULT_UPWORK_SEARCH_FILTERS
    defaults = asdict(DEFAULT_UPWORK_SEARCH_FILTERS)
    merged = {**defaults, **parsed}
    max_connects = merged.get("max_connects", 16)
    if max_connects is None or max_connects == "":
        max_connects = 16
    return UpworkSearchFilters(
        categories=[str(item) for item in merged.get("categories", []) if str(item).strip()],
        experience_levels=[str(item) for item in merged.get("experience_levels", []) if str(item).strip()],
        job_types=[str(item) for item in merged.get("job_types", []) if str(item).strip()],
        budget_min=_parse_optional_float("budget_min", merged.get("budget_min")),
        budget_max=_parse_optional_float("budget_max", merged.get("budget_max")),
        hourly_rate_min=_parse_optional_float("hourly_rate_min", merged.get("hourly_rate_min")),
        hourly_rate_max=_parse_optional_float("hourly_rate_max", merged.get("hourly_rate_max")),
        hours_per_week=[str(item) for item in merged.get("hours_per_week", []) if str(item).strip()],
        project_lengths=[str(item) for item in merged.get("project_lengths", []) if str(item).strip()],
        client_history=[str(item) for item in merged.get("client_history", []) if str(item).strip()],
        client_location=str(merged.get("client_location", "") or "").strip(),
        proposals=[str(item) for item in merged.get("proposals", []) if str(item).strip()],
        max_connects=_parse_int("max_connects", str(max_connects), 0),
    )


def get_settings(env_path: Optional[Path] = None, db_path: Optional[Path] = None) -> Settings:
    selected_env_path = env_path or DEFAULT_ENV_PATH
    env_file_values = _read_env_file(selected_env_path)
    bootstrap_db_path = db_path or _resolve_project_path(
        os.environ.get("DB_PATH", env_file_values.get("DB_PATH", DEFAULT_SETTING_VALUES["DB_PATH"]))
    )
    session_values = _read_session_values(bootstrap_db_path)

    def value(name: str) -> str:
        return _get_value(name, env_file_values, session_values, DEFAULT_SETTING_VALUES[name])

    search_filters = _parse_search_filters(value("upwork_search_filters"))
    scheduler_interval_min_minutes = _parse_int(
        "SCHEDULER_INTERVAL_MIN_MINUTES",
        value("SCHEDULER_INTERVAL_MIN_MINUTES"),
        1,
    )
    scheduler_interval_max_minutes = _parse_int(
        "SCHEDULER_INTERVAL_MAX_MINUTES",
        value("SCHEDULER_INTERVAL_MAX_MINUTES"),
        1,
    )
    if scheduler_interval_min_minutes > scheduler_interval_max_minutes:
        scheduler_interval_max_minutes = scheduler_interval_min_minutes

    return Settings(
        gemini_api_key=value("GEMINI_API_KEY"),
        opencode_api_key=value("OPENCODE_API_KEY"),
        opencode_base_url=value("OPENCODE_BASE_URL"),
        opencode_copywriter_model=value("OPENCODE_COPYWRITER_MODEL"),
        opencode_user_agent=value("OPENCODE_USER_AGENT"),
        upwork_session_dir=_resolve_project_path(value("UPWORK_SESSION_DIR")),
        db_path=_resolve_project_path(value("DB_PATH")),
        daily_proposal_cap=_parse_int(
            "DAILY_PROPOSAL_CAP",
            value("DAILY_PROPOSAL_CAP"),
            1,
        ),
        ws_port=_parse_int("WS_PORT", value("WS_PORT"), 1),
        login_debug_port=_parse_int("LOGIN_DEBUG_PORT", value("LOGIN_DEBUG_PORT"), 1),
        floor_hourly_rate=_parse_float(
            "FLOOR_HOURLY_RATE",
            value("FLOOR_HOURLY_RATE"),
            0,
        ),
        floor_fixed_rate=_parse_float(
            "FLOOR_FIXED_RATE",
            value("FLOOR_FIXED_RATE"),
            0,
        ),
        allow_upwork_network=_parse_bool(
            "ALLOW_UPWORK_NETWORK",
            value("ALLOW_UPWORK_NETWORK"),
        ),
        scheduler_interval_min_minutes=scheduler_interval_min_minutes,
        scheduler_interval_max_minutes=scheduler_interval_max_minutes,
        blacklist_keywords=_parse_string_list(
            "blacklist_keywords",
            value("blacklist_keywords"),
            list(DEFAULT_BLACKLIST_KEYWORDS),
        ),
        upwork_search_filters=search_filters,
        portfolio_attachments=[
            _resolve_project_path(path)
            for path in _parse_string_list("portfolio_attachments", value("portfolio_attachments"), [])
        ],
    )


class _LazySettings:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_settings(), name)

    def __repr__(self) -> str:
        return repr(get_settings())


settings = _LazySettings()

__all__ = [
    "DEFAULT_BLACKLIST_KEYWORDS",
    "DEFAULT_SETTING_VALUES",
    "DEFAULT_UPWORK_SEARCH_FILTERS",
    "RUNTIME_SETTING_KEYS",
    "Settings",
    "UpworkSearchFilters",
    "get_settings",
    "settings",
]
