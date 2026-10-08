# FinCrime Balance Migration & Reconciliation Platform

MVP implementation of the *FICrime Balance Migration & Reconciliation Platform* BRD: automated
Level 1/2/3 reconciliation of migrated financial-crime data, a business-rules engine, exception
workflow, role-based sign-off, AI-assisted root-cause analysis and regulator-ready reports.

| Layer    | Technology |
|----------|------------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Recharts |
| Backend  | FastAPI, SQLAlchemy 2, Pandas, PyArrow |
| Database | PostgreSQL (docker-compose) or SQLite (local default) |
| Reports  | ReportLab (PDF), OpenPyXL (Excel), ZIP audit pack with SHA-256 manifest |
| AI       | Azure OpenAI or Anthropic Claude when configured; deterministic grounded engine otherwise |
| Auth     | JWT bearer tokens with RBAC (Entra ID / OIDC can replace the local login) |

## Features

- **Domains**: customer, account, balance, transaction, AML, KYC, sanctions, audit.
- **Reconciliation levels**: L1 control totals (counts, balance/debit/credit sums, risk counts),
  L2 record matching (matched / mismatched / missing in target / missing in source / duplicates),
  L3 field-by-field comparison with numeric variance.
- **Rules engine** (no arbitrary code): `RECONCILIATION`, `THRESHOLD`, `PERCENTAGE_THRESHOLD`,
  `COMPLIANCE`, `COMPLETENESS`; managed in *Administration → Business rules*.
- **Exceptions**: missing / unexpected / duplicate records, balance variance, mapping issues, AML
  validation failures and rule failures, with severity and a classified root cause
  (source, transformation, load, mapping, missing records, data quality).
  Workflow `DETECTED → ASSIGNED → INVESTIGATING → RESOLVED → CLOSED` with mandatory owner,
  mandatory resolution comment and four-eyes closure. Status is preserved across re-runs.
- **Sign-off**: Finance, AML, Compliance and Operations areas; approval is blocked while open
  CRITICAL exceptions exist in that area.
- **Dashboards**: Executive, Finance, AML, Compliance, plus L1/L2/L3 heatmap and exception trend.
- **Reconciliation split view**: source vs target side by side with highlighted differences.
- **Reports**: Business reconciliation, Migration summary, Compliance, Management summary (PDF),
  Detailed mismatch (Excel), Audit pack (ZIP: reports, exception log, workflow history, approval
  log, audit log, evidence JSON, SHA-256 manifest).
- **AI assistant**: answers “Why did reconciliation fail?”, “Show accounts with highest mismatch.”,
  “Which AML cases failed migration?”, “Show root cause of balance variance.” and per-domain
  questions from database facts; per-exception explanation with recommended action.
- **Data ingestion**: synthetic demo data generator, file upload (CSV, TXT/PSV/TSV, Parquet, JSON)
  and read-only SQL extraction through SQLAlchemy URLs (PostgreSQL, SQL Server, Oracle, DB2,
  Snowflake, Azure SQL, Databricks with the matching driver installed) and MongoDB (`pymongo`).
- **Audit log** of every login, run, reconciliation, transition, sign-off, report and AI query.

## Roles

| User (password `Passw0rd!`) | Role | Highlights |
|---|---|---|
| `admin` | Administrator | everything, users, rules |
| `analyst` | Business Analyst | runs, exceptions, Operations sign-off |
| `finance` | Finance User | run reconciliation, balance/transaction exceptions, Finance sign-off |
| `compliance` | Compliance User | AML/KYC/sanctions exceptions, AML & Compliance sign-off |
| `auditor` | Auditor | read-only, audit log, audit pack |

Change `JWT_SECRET` and the seeded passwords before any shared deployment.

## Run with Docker

```bash
docker compose up --build
# UI  http://localhost:3000   API docs http://localhost:8000/docs
```

## Run locally

```bash
# backend
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env            # optional
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (proxies /api to BACKEND_URL, default http://localhost:8000)
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

Three demo migration runs are seeded on first start (`SEED_DEMO_DATA=true`).

## Tests and checks

```bash
cd backend && .venv/bin/pytest && .venv/bin/ruff check app tests
cd frontend && npm run typecheck && npm run lint && npm run build
```

## Loading your own data

1. *Migration Runs → New run* (untick synthetic data).
2. *Load data*: upload one file per domain and side (source / target), or extract with a SQL query.
   Columns must include the domain key (`customer_id`, `account_id`, `txn_id`, `case_id`,
   `match_id`, `record_id`) and the compared fields shown in the dialog.
3. *Run reconciliation*, then review exceptions, sign off and generate reports.

## Project layout

```
backend/app
  constants.py        domains, compared fields, enums
  models.py           SQLAlchemy models
  security.py         JWT, password hashing, RBAC
  routers/            REST API (auth, runs, recon, exceptions, rules, reports, ai, dashboard, admin)
  services/
    recon_engine.py   L1/L2/L3 reconciliation (Pandas)
    rules_engine.py   business rules
    root_cause.py     root-cause heuristics
    recon_service.py  orchestration and persistence
    workflow.py       exception state machine
    signoff.py        business sign-off
    reporting.py      PDF / Excel / audit pack
    ai.py             assistant and explanations
    connectors.py     file, SQL and MongoDB ingestion
    seed.py           synthetic data with injected defects
frontend/src
  app/(app)/          dashboards, runs, reconciliation, exceptions, reports, assistant, admin
  components/         layout shell, UI kit, charts
  lib/                API client, session, hooks
```

## Not in this MVP

Live Databricks/PySpark execution, Kafka/Service Bus eventing, Camunda/Temporal workflow,
Entra ID SSO and Azure infrastructure-as-code are not wired up; the service boundaries
(`connectors.py`, `recon_engine.py`, `workflow.py`, `security.py`) are where they plug in.
