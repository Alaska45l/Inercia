from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Final, Optional

from inercia.cv.profiles import CVProfile, get_upwork_profile

logger = logging.getLogger("inercia.cv.builder")

TEMPLATE_DIR: Final[Path] = Path(__file__).parent / "templates"
TEMPLATE_PATH: Final[Path] = TEMPLATE_DIR / "cv_upwork.typ"
COMPILE_TIMEOUT_S: Final[float] = 30.0
KEYWORDS_FALLBACK: Final[tuple[str, ...]] = (
    "Python",
    "Playwright",
    "SvelteKit",
    "Tauri",
    "Security Research",
    "SQLite",
)


class CVCompilationError(Exception):
    pass


async def _verify_typst() -> None:
    typst_path = await asyncio.to_thread(shutil.which, "typst")
    if typst_path is None:
        raise CVCompilationError("typst CLI is not available in PATH")


def _escape_typst_text(value: str) -> str:
    replacements = {
        "\\": "\\\\",
        "#": "\\#",
        "[": "\\[",
        "]": "\\]",
        "$": "\\$",
        "@": "\\@",
    }
    escaped = value
    for original, replacement in replacements.items():
        escaped = escaped.replace(original, replacement)
    return escaped


def _format_typst_string_array(values: list[str]) -> str:
    escaped = [value.replace("\\", "\\\\").replace('"', r"\"") for value in values]
    return ", ".join(f'"{value}"' for value in escaped)


def _format_bullets(values: tuple[str, ...]) -> str:
    return "\n".join(f"- {_escape_typst_text(value)}" for value in values)


def normalize_keywords(keywords: list[str], limit: int = 10) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for keyword in keywords:
        cleaned = " ".join(keyword.strip().split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            normalized.append(cleaned)
            seen.add(key)
        if len(normalized) >= limit:
            break
    if normalized:
        return normalized
    return list(KEYWORDS_FALLBACK)


def render_cv_source(
    keywords: list[str],
    profile: Optional[CVProfile] = None,
) -> str:
    selected_profile = profile or get_upwork_profile()
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    values = {
        "NAME": _escape_typst_text(selected_profile.contact["name"]),
        "TITLE": _escape_typst_text(selected_profile.title),
        "LOCATION": _escape_typst_text(selected_profile.contact["location"]),
        "EMAIL": _escape_typst_text(selected_profile.contact["email"]),
        "LINKEDIN": _escape_typst_text(selected_profile.contact["linkedin"]),
        "PORTFOLIO": _escape_typst_text(selected_profile.contact["portfolio"]),
        "GITHUB": _escape_typst_text(selected_profile.contact["github"]),
        "SUMMARY": _escape_typst_text(selected_profile.summary),
        "KEYWORDS": _format_typst_string_array(normalize_keywords(keywords)),
        "PROJECTS": _format_bullets(selected_profile.projects),
        "SKILLS": _format_bullets(selected_profile.skills),
        "EDUCATION": _format_bullets(selected_profile.education),
        "CERTIFICATIONS": _format_bullets(selected_profile.certifications),
    }
    rendered = template
    for marker, value in values.items():
        rendered = rendered.replace("{{ " + marker + " }}", value)
    return rendered


async def compile_cv_pdf(
    keywords: list[str],
    profile: Optional[CVProfile] = None,
) -> bytes:
    await _verify_typst()
    rendered = await asyncio.to_thread(render_cv_source, keywords, profile)
    with tempfile.TemporaryDirectory(prefix="inercia_cv_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        typ_path = tmp_path / "cv_upwork.typ"
        pdf_path = tmp_path / "cv_upwork.pdf"
        await asyncio.to_thread(typ_path.write_text, rendered, "utf-8")
        proc = await asyncio.create_subprocess_exec(
            "typst",
            "compile",
            str(typ_path),
            str(pdf_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=COMPILE_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise CVCompilationError("typst compile timed out") from exc
        if proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            raise CVCompilationError(f"typst compile failed: {stderr_text or stdout_text}")
        if not pdf_path.exists():
            raise CVCompilationError("typst compile finished without producing a PDF")
        pdf_bytes = await asyncio.to_thread(pdf_path.read_bytes)
    logger.info("Compiled Upwork CV | bytes=%d | keywords=%s", len(pdf_bytes), ", ".join(normalize_keywords(keywords)))
    return pdf_bytes


__all__ = ["CVCompilationError", "compile_cv_pdf", "normalize_keywords", "render_cv_source"]
