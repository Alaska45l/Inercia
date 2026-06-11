<div align="center">
  <h1>Inercia v0.3.0</h1>
  <p><strong>Autonomous Upwork Proposal Pipeline with AI Scoring, Cover Letter Generation & Human-in-the-Loop Approval</strong></p>

  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/LangGraph-StateGraph-1C3C3C?style=flat-square&logo=python&logoColor=white" alt="LangGraph">
  <img src="https://img.shields.io/badge/Gemini-2.5_Flash_%7C_Pro-4285F4?style=flat-square&logo=google&logoColor=white" alt="Gemini API">
  <img src="https://img.shields.io/badge/Playwright-Persistent_Profile-2EAD33?style=flat-square&logo=playwright&logoColor=white" alt="Playwright">
  <img src="https://img.shields.io/badge/Tauri_v2-Svelte_5-FFC131?style=flat-square&logo=tauri&logoColor=black" alt="Tauri v2">
  <img src="https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite WAL">
  <img src="https://img.shields.io/badge/Typst-Dynamic_CV-239BBE?style=flat-square&logo=typst&logoColor=white" alt="Typst">
</div>

---

Inercia is an autonomous Upwork job application system. It collects listings via RSS or a user-consented Playwright browser profile, runs a 4-node AI pipeline (extraction → ROI scoring → cover letter generation → self-reflection critic), compiles keyword-injected CVs with Typst, fills out the Apply form, and presents everything in a Tauri desktop dashboard where you accept or reject each proposal before it's submitted.

## <img src="https://api.iconify.design/material-symbols/lightbulb.svg?color=%23007acc" width="24" height="24" align="center"> Why Inercia? (Architecture & Philosophy)

Inercia was born from the realization that freelancing platforms are a credit-burning machine. Upwork charges connects per proposal, and most AI-powered applier bots out there blast generic cover letters at everything — burning your budget on WordPress gigs and $20 fixed-price projects.

After reviewing the existing open-source solutions ([kaymen99/upwork-ai-jobs-applier](https://github.com/kaymen99/upwork-ai-jobs-applier)), I found good ideas but critical weaknesses: fragile Playwright configs, LLM-based scoring (hallucination-prone), and no economic filtering. On the other hand, my own [jobbot](https://github.com/alaska45l/jobbot) had a battle-tested Producer-Consumer engine and deterministic scoring — but no Upwork integration.

Inercia fuses the best of both under a strict technical philosophy:

* **ROI Over Volume:** Every job is scored deterministically (no LLM) using a Jaccard skill overlap, client spending history, hire rate, and connect cost. Jobs below the ROI threshold are instantly blacklisted — your connects are investments, not lottery tickets.
* **Kill List:** WordPress, Wix, Shopify, Squarespace, Joomla, Drupal, and 10 more keywords trigger an instant `roi = -100`. Zero connects wasted on credit-killing gigs.
* **Human-in-the-Loop:** The bot *never* clicks Submit. It fills out the entire Apply form, then stops. You review the proposal in a glassmorphism Tauri UI and click Accept or Reject. Your account, your final call.
* **Critic Self-Reflection:** A 2-iteration critic node catches AI-typical openings ("I am writing to express my interest..."), enforces a 150-word cap, and rewrites robotic phrases before the proposal reaches you.
* **Manual Session Reuse:** A separate local Chromium profile stores the user's own Upwork session after manual login. The app verifies page state before live scraping and does not store credentials in code.
* **Dynamic CVs (Typst):** Each proposal gets a freshly compiled PDF with the job's exact keywords injected into the Typst template, optimized for Upwork's compact format.

---

## <img src="https://api.iconify.design/material-symbols/layers-outline.svg?color=%23007acc" width="24" height="24" align="center"> Architecture & Features

* **Dual Orchestration Layer:** The Producer-Consumer pipeline (`asyncio.Queue`, sentinel pattern, backpressure) handles scraping. LangGraph's `StateGraph` handles the AI pipeline. They run independently — scraping is I/O-bound, AI is compute-bound.
* **4-Node LangGraph Pipeline:** `Extractor` (Gemini Flash → structured JSON) → `Investor` (deterministic ROI, no LLM) → `Copywriter` (Gemini Pro → 150-word cover letter) → `Critic` (Gemini Flash → self-reflection, max 2 rewrites).
* **Offline-First Design:** Every LLM node has a deterministic fallback. If `GEMINI_API_KEY` is not set, the full pipeline still runs with hardcoded logic — perfect for development and testing.
* **RSS + Playwright Hybrid:** Job discovery via Upwork's RSS feed in offline/dev mode, plus optional user-consented Playwright browsing for authenticated search and job details.
* **WebSocket API:** Python API server on `ws://127.0.0.1:{WS_PORT}` pushes `ProposalReady` events directly to the Tauri frontend in real-time.
* **Daily Proposal Cap:** Hardcoded limit of 12 proposals/day, enforced at pipeline level before each job is processed.
* **Connects Tracking:** Every approval logs connects spent to the `connects_log` table. The UI shows a circular progress tracker with remaining balance.

---

## <img src="https://api.iconify.design/material-symbols/folder-open-outline.svg?color=%23007acc" width="24" height="24" align="center"> Project Structure

```
inercia/
├── pyproject.toml                    # Package metadata, dependencies, entry points
├── .env.example                      # Environment variable template
├── README.md
├── src/
│   └── inercia/
│       ├── __init__.py               # Package root, version = "0.1.0"
│       ├── __main__.py               # CLI: python -m inercia
│       ├── config.py                 # Settings from .env (Gemini key, DB path, caps)
│       ├── core/
│       │   ├── orchestrator.py       # Producer-Consumer pipeline (asyncio.Queue)
│       │   ├── scheduler.py          # Periodic scan loop
│       │   └── state.py              # Shared EstadoBot dataclass, thread-safe snapshot
│       ├── scraper/
│       │   ├── engine.py             # Playwright context setup and resource controls
│       │   ├── feed.py               # Upwork RSS parser (no browser)
│       │   ├── job_detail.py         # Job page → Markdown extraction
│       │   └── selectors.py          # All Upwork CSS/XPath selectors (centralized)
│       ├── ai/
│       │   ├── graph.py              # LangGraph StateGraph (4 nodes + conditional edges)
│       │   ├── llm.py                # Gemini SDK wrapper (retry, token tracking, fallback)
│       │   ├── prompts.py            # System prompts (extractor, copywriter, critic)
│       │   ├── schemas.py            # Pydantic models (JobDetail, ROIScore, CoverLetter, ...)
│       │   └── nodes/
│       │       ├── extractor.py      # Node 1: Markdown → structured JobDetail
│       │       ├── investor.py       # Node 2: Deterministic ROI scoring (no LLM)
│       │       ├── copywriter.py     # Node 3: Cover letter + screening Q&A
│       │       └── critic.py         # Node 4: Self-reflection, max 2 rewrites
│       ├── cv/
│       │   ├── builder.py            # Async Typst compilation with keyword injection
│       │   ├── profiles.py           # CV_Upwork profile with real professional data
│       │   └── templates/
│       │       └── cv_upwork.typ     # Compact, skills-forward Typst template
│       ├── applicator/
│       │   ├── apply_flow.py         # Upwork Apply form navigation (stops before Submit)
│       │   ├── session.py            # Persistent Playwright session (user_data_dir)
│       │   └── rate_calculator.py    # Bid rate computation (hourly/fixed + floor rates)
│       ├── db/
│       │   ├── manager.py            # SQLite WAL, context manager, CRUD operations
│       │   ├── models.py             # Dataclasses for DB rows
│       │   └── schema.sql            # DDL: jobs, proposals, connects_log, sessions
│       └── api/
│           ├── server.py             # WebSocket server (ws://127.0.0.1:{WS_PORT})
│           └── protocol.py           # JSON message types (ProposalReady, UserApproved, ...)
├── src-tauri/
│   ├── src/main.rs                   # Tauri app: Python sidecar lifecycle
│   ├── Cargo.toml
│   └── tauri.conf.json
└── ui/                               # Svelte 5 frontend
    ├── src/
    │   ├── App.svelte                # Main layout: sidebar + proposal feed
    │   ├── app.css                   # Dark theme, Inter font, glassmorphism
    │   └── lib/
    │       ├── components/
    │       │   ├── ProposalCard.svelte
    │       │   ├── ApprovalBar.svelte
    │       │   ├── ConnectsTracker.svelte
    │       │   ├── StatsPanel.svelte
    │       │   └── FilterChips.svelte
    │       └── stores/
    │           └── proposals.ts      # Svelte store fed by WebSocket
    ├── package.json
    ├── svelte.config.js
    ├── tsconfig.json
    └── vite.config.ts
```

---

## <img src="https://api.iconify.design/material-symbols/settings-outline.svg?color=%23007acc" width="24" height="24" align="center"> Installation

### 1. Clone and create virtual environment

```bash
git clone https://github.com/alaska45l/inercia.git
cd inercia
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
# Production
pip install -e .

# Playwright browsers
playwright install chromium
```

### 3. Environment Variables (`.env`)

Copy the template and fill in your credentials:

```bash
cp .env.example .env
```

```env
# Gemini API (required for AI pipeline)
GEMINI_API_KEY="your-gemini-api-key"

# Upwork session directory (Playwright persistent context)
UPWORK_SESSION_DIR=".upwork-session"

# Database path
DB_PATH="inercia.db"

# Safety limits
DAILY_PROPOSAL_CAP=12
FLOOR_HOURLY_RATE=35
FLOOR_FIXED_RATE=50

# WebSocket API port
WS_PORT=9741

# Login browser DevTools port
LOGIN_DEBUG_PORT=9742

# Live Upwork browsing is opt-in. Offline mock scraping works without this.
ALLOW_UPWORK_NETWORK=false
```

### 4. External System Dependencies

* **Typst:** Required for dynamic CV compilation.

    ```bash
    # Option 1: Cargo
    cargo install typst-cli

    # Option 2: Precompiled binary
    # https://github.com/typst/typst/releases

    # Verify
    typst --version
    ```

* **Rust + Tauri v2:** Required for the desktop UI.

    ```bash
    # Install Rust
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

    # Install Tauri CLI
    cargo install tauri-cli

    # Install UI dependencies
    cd ui && npm install --include=dev
    ```

### 5. Upwork Session (One-Time Manual Login)

Inercia does **not** automate Upwork login. You must log in once manually to create the persistent session:

```bash
# Open a visible browser with the session dir
python -c "
import asyncio
from playwright.async_api import async_playwright

async def login():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context('.upwork-session', headless=False)
        page = await ctx.new_page()
        await page.goto('https://www.upwork.com/ab/account-security/login')
        input('Log in manually, then press Enter here...')
        await ctx.close()

asyncio.run(login())
"
```

After login, the `.upwork-session/` directory stores your cookies. All subsequent Playwright sessions reuse them.

---

## <img src="https://api.iconify.design/material-symbols/terminal.svg?color=%23007acc" width="24" height="24" align="center"> Usage

The system is operated via `python -m inercia` with subcommands.

### Initialize Database

```bash
python -m inercia init-db
```

### Phase 1: Scrape Jobs

```bash
# Offline (mock RSS — for development)
python -m inercia scrape "python developer"

# Live (authenticated Playwright session for search and job details)
python -m inercia scrape "python developer" --allow-network
python -m inercia scrape "svelte rust tauri" --allow-network
```

### Phase 2: AI Pipeline

Process all scraped jobs through the 4-node LangGraph pipeline:

```bash
python -m inercia process
python -m inercia process --limit 5
```

This runs: Extract → Score ROI → Generate Cover Letter → Critic Review → Save to DB.

Jobs below the ROI threshold are automatically blacklisted. Proposals that pass are saved with status `pending`.

### Phase 3: Start the Approval Server

```bash
# Start WebSocket API (Python backend)
python -m inercia api

# In another terminal: start the Tauri desktop app
cd src-tauri && cargo tauri dev

# Or standalone Svelte dev server (without Tauri shell)
cd ui && npm run dev
```

The Tauri app spawns the Python sidecar automatically when launched via `cargo tauri dev`.

---

## <img src="https://api.iconify.design/material-symbols/science-outline.svg?color=%23007acc" width="24" height="24" align="center"> LangGraph Pipeline

The AI pipeline is a `StateGraph` with 4 nodes and conditional edges:

```
                    ┌──────────────┐
                    │  Extractor   │  Gemini 2.5 Flash
                    │  (Node 1)    │  Markdown → JobDetail (Pydantic)
                    └──────┬───────┘
                           │
                    ┌──────▼──────┐
                    │  Investor    │  Pure Python (no LLM)
                    │  (Node 2)    │  ROI scoring + blacklist check
                    └──────┬───────┘
                           │
                   ┌───────┴───────┐
                   │               │
            roi < 6.0        roi ≥ 6.0
                   │               │
            ┌──────▼─────┐ ┌──────▼───────┐
            │ BLACKLISTED │ │  Copywriter  │  Gemini 2.5 Pro
            │   (END)     │ │  (Node 3)    │  Cover letter + Q&A
            └─────────────┘ └──────┬───────┘
                                   │
                            ┌──────▼──────┐
                            │   Critic     │  Gemini 2.5 Flash
                            │  (Node 4)    │  Self-reflection
                            └──────┬───────┘
                                   │
                          ┌────────┴────────┐
                          │                 │
                    approved=true    approved=false
                     (or attempt≥2)   (attempt<2)
                          │                 │
                   ┌──────▼─────┐   ┌──────▼───────┐
                   │   READY     │   │  Copywriter  │
                   │   (END)     │   │  (retry)     │
                   └─────────────┘   └──────────────┘
```

### ROI Scoring Formula (Node 2 — Investor)

```python
roi  = 40 × skill_overlap      # Jaccard: job_skills ∩ my_skills / union
roi -= 20 × (connects / 16)    # Normalized connect cost penalty
roi += 20 × min(spent/10000, 1) # Client spending history
roi += 10 × hire_rate           # Client hire rate (0–1)
roi += 10 × min(reviews/20, 1)  # Social proof

# Kill signals
if blacklist_keyword_found: roi = -100
if fixed_budget < $50:      roi -= 50
if hourly_rate < $15/hr:    roi -= 50
```

**Threshold:** `roi ≥ 6.0` → pass to Copywriter. Below → instant blacklist.

### Blacklisted Keywords

```
wordpress, wix, shopify, squarespace, bigcommerce, elementor, divi,
webflow, woocommerce, magento, prestashop, joomla, drupal,
php developer, theme customization, plugin development
```

---

## <img src="https://api.iconify.design/material-symbols/database.svg?color=%23007acc" width="24" height="24" align="center"> Database

All data is stored in `inercia.db` (SQLite, WAL mode, STRICT tables). Four tables:

| Table | Purpose |
| :--- | :--- |
| `jobs` | Scraped job listings with ROI scores and lifecycle status |
| `proposals` | Generated cover letters, bid rates, critic notes, approval status |
| `connects_log` | Connect spend/refund tracking with timestamps |
| `sessions` | Key-value store for runtime state (e.g. total connects balance) |

```sql
-- Check today's activity
SELECT COUNT(*) FROM proposals WHERE status = 'submitted' AND date(submitted_at) = date('now');

-- View pending proposals
SELECT j.title, p.roi_score, p.connects_cost, p.status
FROM proposals p JOIN jobs j ON j.id = p.job_id
WHERE p.status = 'pending'
ORDER BY p.roi_score DESC;

-- Reset for a fresh run
DELETE FROM proposals;
UPDATE jobs SET status = 'new' WHERE status != 'blacklisted';
```

---

## <img src="https://api.iconify.design/material-symbols/list-alt-outline.svg?color=%23007acc" width="24" height="24" align="center"> CLI Reference

| Command | Description |
| :--- | :--- |
| `python -m inercia` | Print version and config status |
| `python -m inercia init-db` | Initialize SQLite database with schema |
| `python -m inercia scrape <query>` | Scrape Upwork RSS for a search query |
| `python -m inercia scrape <query> --allow-network` | Live scrape (real Upwork requests) |
| `python -m inercia process` | Run AI pipeline on unprocessed jobs |
| `python -m inercia process --limit N` | Limit to N jobs per run |
| `python -m inercia api` | Start WebSocket server on configured port |
| `python -m inercia api --host 0.0.0.0` | Bind to all interfaces |
| `python -m inercia api --port 8080` | Override WebSocket port |

---

## <img src="https://api.iconify.design/material-symbols/build-outline.svg?color=%23007acc" width="24" height="24" align="center"> Tech Stack

| Layer | Technology |
| :--- | :--- |
| Language | Python 3.11+ |
| Async | `asyncio` (Producer-Consumer, `Queue`, `Event`, sentinels) |
| AI Orchestration | LangGraph `StateGraph` (4 nodes, conditional edges) |
| LLM | Gemini 2.5 Flash (extraction, critic), Gemini 2.5 Pro (copywriting) |
| LLM SDK | `google-genai` with Pydantic structured output |
| Browser | Playwright Chromium (persistent user profile, explicit waits, resource controls) |
| Database | SQLite3 (WAL mode, `STRICT` tables, foreign keys) |
| CV Compiler | Typst CLI (keyword-injected `.typ` templates) |
| Desktop UI | Tauri v2 + Svelte 5 + TypeScript |
| Styling | Dark theme, Inter font, glassmorphism, CSS-only |
| Realtime | WebSockets (`websockets` library, bidirectional JSON protocol) |
| Validation | Pydantic v2 (schemas for all LLM I/O) |

---

## <img src="https://api.iconify.design/material-symbols/warning-outline.svg?color=%23f5a84f" width="24" height="24" align="center"> Safety & Limitations

* **No automated login.** You must log into Upwork manually once. The bot reuses the persistent session.
* **No automated Submit.** The bot fills out the Apply form and stops. You approve via the UI.
* **No stealth or protection bypass.** The browser automation does not bypass CAPTCHA, MFA, access controls, rate limits, or bot detection.
* **Daily cap enforced.** The pipeline refuses to process more than 12 proposals/day (configurable in `.env`).
* **Upwork selectors are volatile.** Upwork's SPA (React) changes DOM structure frequently. All selectors are centralized in `scraper/selectors.py` for easy updates.
* **Connects are real money.** The ROI calculator is conservative by design. Tune `FLOOR_HOURLY_RATE` and `FLOOR_FIXED_RATE` in `.env` to match your minimum acceptable rates.

---

<div align="center">
  <sub>Proposals generated with Inercia · <a href="https://github.com/alaska45l/inercia">github.com/alaska45l/inercia</a></sub>
</div>
