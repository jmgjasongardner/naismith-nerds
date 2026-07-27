# CLAUDE.md — Naismith Nerds

> **WHAT / WHY / HOW documentation for the Naismith Nerds basketball analytics ecosystem**

---

## 1. Project Overview

**Naismith Nerds** is a personal, end‑to‑end basketball analytics platform designed to:

* Collect and standardize pickup basketball game data
* Store and evolve that data over time
* Generate player‑level and lineup‑level metrics (RAPM‑style, win probability, etc.)
* Expose results via a lightweight web application
* Serve as both a living analytics lab and a professional portfolio artifact

The project intentionally mirrors real‑world data engineering + modeling + deployment workflows, but is scoped to be:

* Fast
* Cheap
* Maintainable by a single developer
* Easy to iterate on as the dataset grows

This file exists to help **Claude (or any LLM)** quickly understand how the system is structured, what tools are used, and how changes should be made without breaking assumptions.

---

## 2. Core Design Philosophy

### 2.1 Guiding Principles

* **Simple > clever**
* **Explicit > implicit**
* **Reproducible > optimized** (until optimization is needed)
* **Static artifacts over dynamic infra when possible**

The system avoids unnecessary complexity (Spark, Airflow, Kubernetes, etc.) and instead focuses on:

* Clear scripts
* Deterministic transformations
* Version‑controlled logic
* Small, composable components

### 2.2 What This Is *Not*

* Not a real‑time analytics system
* Not a multi‑tenant SaaS
* Not a heavy frontend framework
* Not a monolithic Jupyter notebook

---

## 3. Software Stack

### 3.1 Programming Languages

* **Python 3.11+** — primary language for ETL, modeling, and backend
* **HTML / CSS / JavaScript** — frontend rendering and interactivity
* **SQL (DuckDB dialect)** — local analytical queries

### 3.2 Core Python Libraries

* **polars (>=0.20)** — primary dataframe engine
* **duckdb** — embedded analytical database
* **pandas** — limited use (mostly I/O interop)
* **scikit‑learn** — modeling (ridge regression, CV, etc.)
* **numpy** — numerical utilities
* **flask** — web server
* **jinja2** — HTML templating
* **python‑dotenv** — environment variable loading

### 3.3 Dependency Management

* **pdm** is the primary dependency manager
* `pdm.lock` is the source of truth
* `requirements.txt` exists *only* for compatibility (e.g. GitHub Actions, Render)

---

## 4. Repository Structure

```
naismith_nerds/
│
├── collective_bball/           # Analytics + modeling code
│   ├── eda_main.py             # Exploratory analysis
│   ├── rapm_model_main.py      # Player impact modeling
│   ├── win_prob_log_reg.py     # Win probability model
│   ├── funs/                   # Reusable helper functions
│   │   ├── io.py
│   │   ├── transforms.py
│   │   ├── modeling.py
│   │   └── validation.py
│   └── __init__.py
│
├── flask_app/                  # Web application
│   ├── app.py                  # Flask entry point
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── index.html
│   │   ├── player.html
│   │   └── base.html
│   ├── static/
│   │   ├── css/
│   │   ├── js/
│   │   └── player_pics/
│   └── utility_imports/        # JS helpers (tooltips, etc.)
│
├── data/                       # Local data artifacts (gitignored)
│   ├── raw/
│   ├── processed/
│   └── temp/
│
├── scripts/                    # One‑off or scheduled scripts
│
├── .env                        # Local secrets (gitignored)
├── CLAUDE.md                   # This file
├── pyproject.toml
├── pdm.lock
└── requirements.txt
```

---

## 5. Data Sources

### 5.1 Primary Input: Excel

The **source of truth** for game data is an Excel workbook that contains:

* Game date
* Court / run identifier
* Team A players (A1–A5)
* Team B players (B1–B5)
* Score / winner
* Optional metadata (fatigue, first possession, etc.)

Excel is used intentionally because:

* Data is manually collected real-time when playing basketball
* Non‑technical collaborators can edit it
* Validation can happen visually

### 5.2 Pulling Data from Excel

Typical flow:

1. Excel file is saved locally and pushed to Github (this is bad practice and should change!)
2. Python script reads Excel using `polars.read_excel()` or `pandas.read_excel()`
3. Columns are normalized to canonical names
4. Types are enforced (dates, ints, categoricals)
5. Output is written to DuckDB or Parquet

No Excel formulas are relied on downstream — Excel is **input only**.
Note: Until May 2025, OneDrive provided a downloadable link to access the file without pushing to Github,
but this functionality is broken and a new process is needed since .xlsx shouldbe gitignored

---

## 6. Data Storage

### 6.1 DuckDB

* Local file‑based database (`.duckdb`)
* Used for:

  * Player ratings over time
  * Game‑level fact tables
  * Lightweight joins

DuckDB is preferred because:

* Zero setup
* SQL + dataframe friendly
* Excellent performance for this scale
* The problem is that DuckDB file is only updated locally, and not when run in production

---

## 7. Modeling Layer

### 7.1 Player Impact (RAPM‑Style)

* Ridge regression
* Player dummy variables
* Team context captured implicitly
* Alpha tuned via k‑fold CV

Key goals:

* Stability over interpretability
* Reasonable out‑of‑sample behavior
* Extendable to interactions later

### 7.2 Win Probability Model

* Logistic regression
* Inputs:

  * Player ratings
  * Score margin
  * Possession indicators

Outputs are used for:

* Post‑game evaluation
* Hypothetical lineup simulations

---

## 8. Web Application

### 8.1 Flask

* Single Flask app
* No Blueprints (intentionally)
* Routes map directly to pages

Examples:

* `/` — leaderboard
* `/player/<name>` — player detail page

### 8.2 Templates

* Jinja2
* Minimal logic
* Data passed as pre‑shaped dictionaries/lists

All heavy computation happens **before** rendering.

### 8.3 Frontend Interactivity

* Tables currently don't scroll correctly with ideal frozen first header row and column
* Functionality is needed correctly in both mobile and web
* Filtering and sorting done client‑side
* JS kept small and explicit

---

## 9. Deployment

### 9.1 Hosting Platform

* **Fly.io** — app `naismith-nerds`, region `iad`, 1 shared CPU / 1 GB
* Custom domain `naismith-nerds.com` (+ `www`), certs managed by Fly
* Deployed by GitHub Actions on push to `main` (`.github/workflows/fly-deploy.yml`)

(An older `render.yaml` and `Procfile` remain in the repo but are not what runs.)

### 9.2 Persistent volume

A Fly volume `naismith_data` is mounted at `/data` (`NN_DATA_DIR`). It holds the
state that must survive deploys:

```
/data
  bball_database.duckdb   ratings history since Jan 2025, seeded from the repo copy
  onedrive_token.json     rotating OneDrive refresh token
  GameResults.xlsm        last workbook successfully fetched, used as a fallback
  artifacts/              prebuilt parquet the app boots from
```

Paths are resolved in `collective_bball/paths.py`. Never hard-code them.

### 9.3 Environment Variables

Fly secrets:

* `CLIENT_ID`, `TENANT_ID` — Microsoft app registration
* `REFRESH_TOKEN` — seed only; once `/data/onedrive_token.json` exists it wins
* `UPLOAD_PASSWORD` — guards `/upload` and `/admin/refresh`

Optional: `REFRESH_INTERVAL_SECONDS` (default 1800), `DISABLE_AUTO_REFRESH`,
`LOG_LEVEL`.

## 10. Scheduling & Automation

`flask_app/refresh.py` runs a background thread that polls OneDrive every 30
minutes, hashes the workbook, and rebuilds only when the bytes changed. The
rebuild happens off the request path; when it finishes, `DataStore.swap()`
atomically replaces the served dataset. No redeploy, no downtime.

Polling rather than a wall-clock cron is deliberate: the Fly machine suspends
when idle, and a suspended machine does not fire a "run at 06:00" timer.

Manual trigger:

```bash
curl -X POST https://naismith-nerds.com/admin/refresh -d "password=$UPLOAD_PASSWORD"
curl https://naismith-nerds.com/admin/status
```

## 11. Development Workflow

Normal case: **edit the Excel in OneDrive and do nothing else.** The site picks
it up within 30 minutes. Partial rows (missing a date, missing any of the ten
players, missing a score) are skipped until complete.

To rebuild locally:

```bash
python -m collective_bball.main            # freshest available source
python -m collective_bball.main --local    # the workbook committed to the repo
flask --app flask_app.app run --port 5055
```

One-time OneDrive setup (needed again only if the grant is fully revoked):

```bash
python -m collective_bball.utils.onedrive_client
```

## 11b. Architecture: build vs serve

The single most important structural rule.

**Build** (`collective_bball/artifacts.py::build`) reads the workbook, fits the
ridge model and renders charts. It needs pandas, openpyxl, scikit-learn and
plotly, and takes ~9 seconds. It runs from the CLI or on the refresh thread.

**Serve** (`flask_app/app.py`) loads prebuilt parquet and starts in under a
second. It must never import the modeling stack at module scope, directly or
transitively. `collective_bball/main.py` used to run the whole pipeline at
import time, which cost 37 seconds on every boot; do not reintroduce that.

Data flow:

```
OneDrive workbook
  -> validate_games_data()      skip incomplete rows
  -> build()                    clean, RAPM, spreads, win prob, charts
  -> save()                     parquet + meta.json, staged then swapped in
  -> load()                     what the app holds in memory
  -> DataStore.swap()           atomic handover, version += 1
```

`DataStore.version` keys every derived cache (API payloads, avatar list, the
classic home page), so one swap invalidates all of them.

## 11c. The classic site

`/classic` serves the original site Jason built solo before any agentic coding.
Templates live in `flask_app/templates/legacy/`, styled by the untouched
`static/css/styles.css` and `static/js/*.js`. Routes are in
`flask_app/legacy_views.py`.

The exact pre-agentic source is pinned at the git tag `v1-solo-build`.

Do not refactor the legacy templates, stylesheet or scripts to share code with
the new site, and do not "fix" them. Preserving them unchanged is the point.
They are fed live data, so they stay current.

## 11d. Front end

No build step, no jQuery, no DataTables. Server renders a small shell; tables
fetch JSON per tab from `/api/table/<name>` and render themselves.

* `static/css/nn.css` — design system. Dark default, light via
  `prefers-color-scheme` and a `data-theme` override. Components read custom
  properties; never hard-code a color.
* `static/js/nn-table.js` — sorting, filtering, CSV export, and virtualized
  rows so only what is near the viewport is in the DOM.
* `static/js/nn-app.js` — theme, tabs, search.
* `static/js/nn-teams.js` — Team Builder.
* `flask_app/columns.py` — labels, types, tooltips and rounding, in one place.

Why it matters: the old home page shipped 66 MB of HTML in one document and
took 8.8 seconds to render. It is now 16 KB.

## 12. Conventions & Preferences

* Polars `group_by()` over `over()`
* Avoid loops where possible
* Explicit typing in Python functions
* Deterministic outputs
* No hidden magic

---

## 13. Future Extensions

### 13.1 Short-term

* Fixing the UI so that the Team Builder page correctly picks players
* Allow for correct sizing of tables in mobile and web with headers
* Take in data and auto-upload to rebuild without pushing Excel to GitHub

### 13.2 Long-term
* A full Apple and Google Play store app to pull in this data
* A different method to update data than Excel, more of a form type
* User-authentication so that users can create their own accounts to upload data

---

## 14. Final Notes for LLMs

When modifying this repo:

* Respect existing structure
* Do not introduce unnecessary frameworks
* Prefer clarity over abstraction
* Ask before changing storage assumptions

This project is meant to **grow slowly and deliberately**.

---

**End of CLAUDE.md**
