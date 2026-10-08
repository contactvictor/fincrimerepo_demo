"""Synthetic, deterministic demo data with injected migration defects."""
import copy
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from ..constants import Role
from ..models import (
    ExceptionHistory, MigrationRun, ReconException, Rule, SignOff, SourceRecord, TargetRecord, User,
)
from ..security import hash_password
from .recon_service import run_reconciliation

FIRST = ["James", "Olivia", "Liam", "Emma", "Noah", "Ava", "Arjun", "Mia", "Chen", "Sofia", "Omar",
         "Isla", "Lucas", "Amara", "Mateo", "Priya", "Ethan", "Zara", "Kenji", "Leah"]
LAST = ["Smith", "Patel", "Nguyen", "Garcia", "Okafor", "Kowalski", "Rossi", "Khan", "Murphy",
        "Schmidt", "Silva", "Cohen", "Tanaka", "Dubois", "Ibrahim", "Johansson"]
COUNTRIES = ["GB", "US", "DE", "FR", "IN", "AE", "SG", "NG", "BR", "CH"]

DEMO_USERS = [
    ("admin", "Alex Admin", Role.ADMIN.value),
    ("analyst", "Bianca Analyst", Role.ANALYST.value),
    ("finance", "Femi Finance", Role.FINANCE.value),
    ("compliance", "Carla Compliance", Role.COMPLIANCE.value),
    ("auditor", "Arthur Auditor", Role.AUDITOR.value),
]
DEMO_PASSWORD = "Passw0rd!"

DEFAULT_RULES = [
    *[(f"{d.title()} record count reconciles", "RECONCILIATION", d, {"metric": "record_count"}, "CRITICAL")
      for d in ["customer", "account", "balance", "transaction", "aml", "kyc", "sanctions", "audit"]],
    ("Transaction debit totals reconcile", "RECONCILIATION", "transaction", {"metric": "debit_total"}, "CRITICAL"),
    ("Transaction credit totals reconcile", "RECONCILIATION", "transaction", {"metric": "credit_total"}, "CRITICAL"),
    ("Open sanctions matches reconcile", "RECONCILIATION", "sanctions", {"metric": "open_matches"}, "CRITICAL"),
    ("Current balance variance <= 0", "THRESHOLD", "balance",
     {"field": "current_balance", "measure": "total_abs_variance", "operator": "<=", "value": 0}, "CRITICAL"),
    ("Ledger balance variance <= 0", "THRESHOLD", "balance",
     {"field": "ledger_balance", "measure": "total_abs_variance", "operator": "<=", "value": 0}, "CRITICAL"),
    ("Closing balance variance <= 0", "THRESHOLD", "balance",
     {"field": "closing_balance", "measure": "total_abs_variance", "operator": "<=", "value": 0}, "HIGH"),
    *[(f"{d.title()} mismatch % below 0.01%", "PERCENTAGE_THRESHOLD", d, {"max_mismatch_pct": 0.01}, "HIGH")
      for d in ["customer", "account", "balance", "transaction"]],
    ("High-risk AML cases keep risk ratings", "COMPLIANCE", "aml",
     {"filter_field": "risk_rating", "filter_values": ["HIGH"], "required_fields": ["risk_rating", "risk_score"]},
     "CRITICAL"),
    ("High-risk customers keep KYC classification", "COMPLIANCE", "kyc",
     {"filter_field": "risk_classification", "filter_values": ["HIGH"],
      "required_fields": ["risk_classification"]}, "CRITICAL"),
    ("PEP flags migrated", "COMPLIANCE", "kyc",
     {"filter_field": "pep_flag", "filter_values": ["true"], "required_fields": ["pep_flag"]}, "CRITICAL"),
    ("Open sanctions matches stay open", "COMPLIANCE", "sanctions",
     {"filter_field": "match_status", "filter_values": ["OPEN"], "required_fields": ["match_status"]}, "CRITICAL"),
    *[(f"{d.title()} mandatory fields populated", "COMPLETENESS", d, {}, "HIGH")
      for d in ["customer", "account", "balance", "transaction", "aml", "kyc", "sanctions", "audit"]],
]


def _d(rng: random.Random, start: date, span_days: int) -> str:
    return (start + timedelta(days=rng.randint(0, span_days))).isoformat()


def generate_source(rng: random.Random, n_customers: int, id_offset: int = 0) -> dict[str, list[dict]]:
    customers, accounts, balances, txns, aml, kyc, sanctions, audit = ([] for _ in range(8))
    acc_seq = txn_seq = 0
    for i in range(1, n_customers + 1):
        cid = f"C{id_offset + i:06d}"
        customers.append({
            "customer_id": cid, "full_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
            "status": rng.choices(["ACTIVE", "DORMANT", "CLOSED"], [85, 10, 5])[0],
            "segment": rng.choice(["RETAIL", "SME", "CORPORATE", "PRIVATE"]),
            "country": rng.choice(COUNTRIES), "relationship_id": f"R{id_offset + (i + 1) // 2:06d}",
            "date_of_birth": _d(rng, date(1950, 1, 1), 18000),
        })
        risk = rng.choices(["LOW", "MEDIUM", "HIGH"], [70, 22, 8])[0]
        kyc.append({
            "customer_id": cid, "kyc_status": rng.choices(["VERIFIED", "PENDING", "EXPIRED"], [85, 10, 5])[0],
            "risk_classification": risk, "pep_flag": rng.random() < 0.04,
            "tax_id": f"TX{rng.randint(10**7, 10**8 - 1)}", "documents_count": rng.randint(1, 6),
            "last_review_date": _d(rng, date(2023, 1, 1), 600),
        })
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            acc_seq += 1
            aid = f"A{id_offset * 3 + acc_seq:07d}"
            accounts.append({
                "account_id": aid, "customer_id": cid,
                "account_type": rng.choice(["CURRENT", "SAVINGS", "LOAN", "CARD", "TERM_DEPOSIT"]),
                "status": rng.choices(["ACTIVE", "DORMANT", "CLOSED", "FROZEN"], [85, 8, 5, 2])[0],
                "currency": rng.choice(["GBP", "GBP", "EUR", "USD"]),
                "open_date": _d(rng, date(2005, 1, 1), 6500),
            })
            opening = round(rng.uniform(-2000, 250000), 2)
            credits = debits = 0.0
            for _ in range(rng.randint(2, 6)):
                txn_seq += 1
                direction = rng.choice(["DEBIT", "CREDIT"])
                amount = round(rng.uniform(5, 15000), 2)
                status = rng.choices(["POSTED", "PENDING", "REVERSED"], [90, 6, 4])[0]
                if status == "POSTED":
                    credits += amount if direction == "CREDIT" else 0
                    debits += amount if direction == "DEBIT" else 0
                txns.append({"txn_id": f"T{id_offset * 15 + txn_seq:08d}", "account_id": aid,
                             "direction": direction, "amount": amount, "status": status,
                             "txn_date": _d(rng, date(2024, 1, 1), 270)})
            closing = round(opening + credits - debits, 2)
            blocked = round(rng.choice([0, 0, 0, rng.uniform(10, 5000)]), 2)
            balances.append({
                "account_id": aid, "opening_balance": opening, "closing_balance": closing,
                "current_balance": closing, "ledger_balance": closing, "blocked_balance": blocked,
                "available_balance": round(closing - blocked, 2),
            })
    for i in range(1, max(10, n_customers // 3) + 1):
        c = rng.choice(customers)
        rating = rng.choices(["LOW", "MEDIUM", "HIGH"], [45, 35, 20])[0]
        score = {"LOW": rng.randint(5, 39), "MEDIUM": rng.randint(40, 74), "HIGH": rng.randint(75, 99)}[rating]
        aml.append({
            "case_id": f"CASE{id_offset + i:06d}", "customer_id": c["customer_id"],
            "alert_type": rng.choice(["STRUCTURING", "RAPID_MOVEMENT", "HIGH_RISK_JURISDICTION",
                                      "UNUSUAL_CASH", "TRADE_BASED_ML"]),
            "risk_rating": rating, "risk_score": score,
            "case_status": rng.choice(["OPEN", "UNDER_REVIEW", "ESCALATED", "CLOSED"]),
            "sar_filed": rating == "HIGH" and rng.random() < 0.5, "watchlist_match": rng.random() < 0.15,
            "case_notes": f"Analyst review {rng.randint(1000, 9999)}: {rng.choice(['pattern confirmed', 'no further action', 'escalated to MLRO', 'awaiting RFI'])}",
        })
    for i in range(1, max(6, n_customers // 7) + 1):
        c = rng.choice(customers)
        status = rng.choice(["OPEN", "CLOSED", "CLOSED"])
        sanctions.append({
            "match_id": f"SM{id_offset + i:06d}", "customer_id": c["customer_id"],
            "list_name": rng.choice(["OFAC SDN", "UN Consolidated", "EU Consolidated", "HMT"]),
            "match_status": status, "screening_score": round(rng.uniform(70, 100), 1),
            "finding": "UNDER_INVESTIGATION" if status == "OPEN" else rng.choice(["FALSE_POSITIVE", "TRUE_MATCH"]),
        })
    for i in range(1, max(10, n_customers // 2) + 1):
        created = date(2022, 1, 1) + timedelta(days=rng.randint(0, 900))
        audit.append({
            "record_id": f"AUD{id_offset + i:07d}", "entity": rng.choice(["CUSTOMER", "ACCOUNT", "CASE", "KYC"]),
            "created_date": created.isoformat(),
            "updated_date": (created + timedelta(days=rng.randint(0, 300))).isoformat(),
            "user_id": f"U{rng.randint(100, 160)}",
            "workflow_state": rng.choice(["APPROVED", "PENDING_APPROVAL", "REJECTED"]),
            "approved_by": f"U{rng.randint(200, 220)}",
        })
    return {"customer": customers, "account": accounts, "balance": balances, "transaction": txns,
            "aml": aml, "kyc": kyc, "sanctions": sanctions, "audit": audit}


def inject_defects(rng: random.Random, source: dict[str, list[dict]], level: float) -> dict[str, list[dict]]:
    tgt = copy.deepcopy(source)

    def n(base: int) -> int:
        return int(round(base * level))

    def pick(domain: str, count: int, predicate=None) -> list[dict]:
        pool = [r for r in tgt[domain] if predicate is None or predicate(r)]
        return rng.sample(pool, min(count, len(pool)))

    def drop(domain: str, count: int, predicate=None) -> None:
        victims = {id(r) for r in pick(domain, count, predicate)}
        tgt[domain] = [r for r in tgt[domain] if id(r) not in victims]

    # Customers
    drop("customer", n(3))
    for r in pick("customer", n(4), lambda r: r["status"] == "ACTIVE"):
        r["status"] = "A"
    for r in pick("customer", n(3)):
        r["full_name"] = r["full_name"].upper() + " "
    for r in pick("customer", n(2)):
        y, m, d = r["date_of_birth"].split("-")
        r["date_of_birth"] = f"{d}/{m}/{y}"
    for r in pick("customer", n(1)):
        tgt["customer"].append(dict(r))
    # Accounts
    drop("account", n(2))
    for r in pick("account", n(3), lambda r: r["account_type"] == "SAVINGS"):
        r["account_type"] = "SAV"
    if n(1):
        extra = dict(tgt["account"][0])
        extra["account_id"] = "A9999999"
        tgt["account"].append(extra)
    # Balances
    drop("balance", n(2))
    for r in pick("balance", n(3), lambda r: abs(r["current_balance"]) > 100):
        r["current_balance"] = round(r["current_balance"] * 100, 2)
    for r in pick("balance", n(4)):
        r["ledger_balance"] = round(r["ledger_balance"] + rng.choice([0.01, -0.01, 0.25, -0.5]), 2)
    for r in pick("balance", n(2)):
        r["closing_balance"] = round(r["closing_balance"] + rng.choice([15250.0, -22840.5]), 2)
    for r in pick("balance", n(1), lambda r: r["blocked_balance"] > 0):
        r["blocked_balance"] = -r["blocked_balance"]
    # Transactions
    drop("transaction", n(5), lambda r: r["status"] == "PENDING")
    for r in pick("transaction", n(2)):
        r["amount"] = -r["amount"]
    for r in pick("transaction", n(1)):
        tgt["transaction"].append(dict(r))
    # AML
    for r in pick("aml", n(27)):
        r["case_notes"] = None
    for r in pick("aml", n(4), lambda r: r["risk_rating"] == "HIGH"):
        r["risk_rating"] = "MEDIUM"
    for r in pick("aml", n(3)):
        r["risk_score"] = None
    drop("aml", n(2))
    # KYC
    for r in pick("kyc", n(3), lambda r: r["pep_flag"]):
        r["pep_flag"] = False
    for r in pick("kyc", n(2)):
        r["tax_id"] = None
    for r in pick("kyc", n(4), lambda r: r["documents_count"] > 1):
        r["documents_count"] -= 1
    # Sanctions
    for r in pick("sanctions", n(2), lambda r: r["match_status"] == "OPEN"):
        r["match_status"] = "CLOSED"
    drop("sanctions", n(1))
    for r in pick("sanctions", n(2)):
        r["screening_score"] = round(r["screening_score"])
    # Audit
    for r in pick("audit", n(5)):
        r["updated_date"] = r["updated_date"].replace("-", "")
    for r in pick("audit", n(3)):
        r["approved_by"] = None
    return tgt


def load_run_data(db: Session, run_id: int, source: dict, target: dict) -> None:
    from ..constants import DOMAIN_SPECS

    for model, data in ((SourceRecord, source), (TargetRecord, target)):
        for domain, rows in data.items():
            key = DOMAIN_SPECS[domain]["key"]
            if rows:
                db.execute(insert(model), [
                    {"run_id": run_id, "domain": domain, "record_key": str(r.get(key)), "data": r}
                    for r in rows
                ])


def seed_users_and_rules(db: Session) -> None:
    if not db.scalar(select(User).limit(1)):
        for username, name, role in DEMO_USERS:
            db.add(User(username=username, full_name=name, role=role,
                        email=f"{username}@bank.example", password_hash=hash_password(DEMO_PASSWORD)))
    if not db.scalar(select(Rule).limit(1)):
        for name, category, domain, params, severity in DEFAULT_RULES:
            db.add(Rule(name=name, category=category, domain=domain, params=params, severity=severity,
                        description=f"{category.replace('_', ' ').title()} rule for {domain}"))
    db.flush()


def _simulate_workflow(db: Session, rng: random.Random, run: MigrationRun, start: datetime, days: int,
                       close_domains: set[str] | None = None) -> None:
    owners = ["analyst", "finance", "compliance"]
    for exc in db.scalars(select(ReconException).where(ReconException.run_id == run.id)):
        detected = start + timedelta(hours=rng.randint(0, days * 24))
        exc.created_at = exc.updated_at = detected
        stage = 4 if close_domains and exc.domain in close_domains else rng.choices(
            [0, 1, 2, 3, 4], [35, 20, 20, 12, 13])[0]
        status, at = "DETECTED", detected
        for target in ["ASSIGNED", "INVESTIGATING", "RESOLVED", "CLOSED"][:stage]:
            at = at + timedelta(hours=rng.randint(2, 30))
            if target == "ASSIGNED":
                exc.owner = rng.choice(owners)
            comment = "Corrected in remediation load" if target == "RESOLVED" else ""
            if target == "RESOLVED":
                exc.resolution = comment
            db.add(ExceptionHistory(exception_id=exc.id, from_status=status, to_status=target,
                                    actor="admin" if target in {"ASSIGNED", "CLOSED"} else exc.owner or "analyst",
                                    comment=comment, at=at))
            status = target
        exc.status = status
        exc.updated_at = at


def seed_demo(db: Session) -> None:
    seed_users_and_rules(db)
    if db.scalar(select(MigrationRun).limit(1)):
        return
    now = datetime.now(timezone.utc)
    plans = [
        ("Wave 1 - Retail Banking", "Oracle", "Actimize", "UAT", 400, 1.0, 21, 101),
        ("Wave 2 - Corporate & SME", "SQL Server", "SAS AML", "SIT", 250, 0.3, 10, 202),
        ("Wave 3 - Private Banking Dress Rehearsal", "DB2", "Oracle FCCM", "UAT", 150, 0.2, 1, 303),
    ]
    for idx, (name, src_sys, tgt_sys, env, size, level, days_ago, seed) in enumerate(plans):
        rng = random.Random(seed)
        created = now - timedelta(days=days_ago)
        run = MigrationRun(name=name, source_system=src_sys, target_system=tgt_sys, environment=env,
                           description=f"{src_sys} legacy FinCrime estate to {tgt_sys}",
                           created_by="admin", created_at=created, status="LOADED", progress=60.0)
        db.add(run)
        db.flush()
        source = generate_source(rng, size, id_offset=idx * 10000)
        load_run_data(db, run.id, source, inject_defects(rng, source, level))
        if idx == 2:
            run.records_processed = sum(len(v) for v in source.values())
            continue
        run_reconciliation(db, run, "admin")
        run.started_at = created
        run.completed_at = created + timedelta(hours=3)
        span = max(1, days_ago - 1)
        if idx == 1:
            _simulate_workflow(db, rng, run, created, span, close_domains={"customer", "account", "transaction", "audit"})
            db.add(SignOff(run_id=run.id, area="OPERATIONS", decision="APPROVED", actor="analyst",
                           role="analyst", comment="Operational reconciliation complete", at=now - timedelta(days=2)))
            run.signoff_status = "PARTIAL"
        else:
            _simulate_workflow(db, rng, run, created, span)
    db.flush()
