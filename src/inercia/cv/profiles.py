from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CVProfile:
    code: str
    title: str
    summary: str
    projects: tuple[str, ...]
    skills: tuple[str, ...]
    contact: dict[str, str]
    education: tuple[str, ...]
    certifications: tuple[str, ...]


CV_Upwork: CVProfile = CVProfile(
    code="CV_Upwork",
    title="Software Developer & Security Researcher",
    summary=(
        "Alaska Elaina Gonzalez, Mar del Plata, Argentina. Builds Go/SvelteKit systems, "
        "Rust/Tauri desktop tools, Python automation, and security research workflows."
    ),
    projects=(
        "INVARIANT SYSTEM: forensic platform with Go/Fiber, PostgreSQL, SvelteKit, Rust/Tauri, Python tooling, and security controls.",
        "Independent security research: responsible disclosure of a critical IDOR/BOLA issue in a large e-commerce platform.",
        "Freelance IT and automation work: Python scripts, Linux/Windows hardening, troubleshooting, and repeatable technical documentation.",
    ),
    skills=(
        "Python",
        "asyncio",
        "Playwright",
        "SQLite",
        "Go",
        "SvelteKit",
        "Svelte 5",
        "TypeScript",
        "Rust",
        "Tauri",
        "PostgreSQL",
        "Linux",
        "Pentesting",
        "OWASP Top 10",
        "Burp Suite",
        "Cloudflare",
    ),
    contact={
        "name": "Alaska Elaina Gonzalez",
        "location": "Mar del Plata, Buenos Aires, Argentina",
        "email": "AlaskaGonzalez@outlook.com",
        "linkedin": "linkedin.com/in/alaska45l",
        "portfolio": "alaska45l.github.io",
        "github": "github.com/alaska45l",
    },
    education=(
        "Licenciatura en Física - UNMDP, 2025-Presente",
        "TU en Desarrollo de Aplicaciones Informáticas, Ciclo Básico - UNICEN, 2022-2024",
    ),
    certifications=(
        "Técnica IT Nivel II",
        "Programación Multilenguaje - Mastermind",
        "Cambridge B2 English - First Certificate",
    ),
)

CV_UPWORK: CVProfile = CV_Upwork


def get_upwork_profile() -> CVProfile:
    return CV_Upwork


__all__ = ["CVProfile", "CV_UPWORK", "CV_Upwork", "get_upwork_profile"]
