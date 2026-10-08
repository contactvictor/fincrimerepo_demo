import random

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..constants import DOMAIN_SPECS, ENVIRONMENTS, SOURCE_SYSTEMS, TARGET_SYSTEMS, SignOffArea
from ..db import get_db
from ..deps import check_domain, get_run_or_404
from ..models import MigrationRun, SignOff, SourceRecord, TargetRecord, User
from ..schemas import (
    ReconcileRequest, RuleResultOut, RunCreate, RunOut, SignOffOut, SignOffRequest, SqlExtractRequest,
)
from ..security import ROLE_DOMAINS, get_current_user, require
from ..services import analytics, connectors, seed
from ..services.audit import log_action
from ..services.recon_service import run_reconciliation
from ..services.signoff import area_domains, blocking_exceptions, record_signoff

router = APIRouter(prefix="/api", tags=["migration-runs"])


@router.get("/meta")
def meta(_: User = Depends(get_current_user)):
    return {
        "source_systems": SOURCE_SYSTEMS, "target_systems": TARGET_SYSTEMS, "environments": ENVIRONMENTS,
        "domains": {d: {"key": s["key"], "fields": s["fields"], "numeric": s["numeric"]}
                    for d, s in DOMAIN_SPECS.items()},
        "signoff_areas": {a.value: area_domains(a.value) for a in SignOffArea},
        "sql_dialects": connectors.SQL_DIALECT_HINTS,
    }


@router.get("/runs", response_model=list[RunOut])
def list_runs(environment: str | None = None, db: Session = Depends(get_db),
              _: User = Depends(require("runs:read"))):
    stmt = select(MigrationRun).order_by(MigrationRun.created_at.desc())
    if environment:
        stmt = stmt.where(MigrationRun.environment == environment)
    return list(db.scalars(stmt))


@router.post("/runs", response_model=RunOut, status_code=201)
def create_run(body: RunCreate, db: Session = Depends(get_db), user: User = Depends(require("runs:write"))):
    if body.environment not in ENVIRONMENTS:
        raise HTTPException(400, f"environment must be one of {ENVIRONMENTS}")
    run = MigrationRun(name=body.name, description=body.description, source_system=body.source_system,
                       target_system=body.target_system, environment=body.environment, created_by=user.username)
    db.add(run)
    db.flush()
    if body.generate_demo_data:
        rng = random.Random(run.id * 7919)
        source = seed.generate_source(rng, body.demo_customers, id_offset=run.id * 100000)
        seed.load_run_data(db, run.id, source, seed.inject_defects(rng, source, body.defect_level))
        run.status = "LOADED"
        run.progress = 60.0
        run.records_processed = sum(len(v) for v in source.values())
    log_action(db, user.username, "RUN_CREATED", "migration_run", run.id, body.model_dump())
    db.commit()
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(require("runs:read"))):
    run = get_run_or_404(db, run_id)
    signoffs = list(db.scalars(select(SignOff).where(SignOff.run_id == run_id).order_by(SignOff.at.desc())))
    return {
        "run": RunOut.model_validate(run),
        "domains": analytics.domain_stats(db, [run_id]),
        "rule_results": [RuleResultOut.model_validate(r) for r in analytics.rule_results(db, [run_id])],
        "signoffs": [SignOffOut.model_validate(s) for s in signoffs],
        "signoff_blockers": {a.value: blocking_exceptions(db, run_id, a.value) for a in SignOffArea},
    }


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(require("runs:write"))):
    run = get_run_or_404(db, run_id)
    db.delete(run)
    log_action(db, user.username, "RUN_DELETED", "migration_run", run_id, {"name": run.name})
    db.commit()


def _store(db: Session, run: MigrationRun, domain: str, side: str, rows: list[dict], replace: bool) -> int:
    if domain not in DOMAIN_SPECS:
        raise HTTPException(400, f"Unknown domain {domain}")
    key = DOMAIN_SPECS[domain]["key"]
    missing_key = [i for i, r in enumerate(rows) if r.get(key) in (None, "")]
    if missing_key:
        raise HTTPException(400, f"{len(missing_key)} row(s) are missing the key column '{key}'")
    model = SourceRecord if side == "source" else TargetRecord
    if replace:
        db.execute(delete(model).where(model.run_id == run.id, model.domain == domain))
    db.add_all(model(run_id=run.id, domain=domain, record_key=str(r[key]), data=r) for r in rows)
    run.status = "LOADED"
    run.progress = max(run.progress, 50.0)
    return len(rows)


@router.post("/runs/{run_id}/upload")
async def upload(run_id: int, domain: str = Form(...), side: str = Form(...), replace: bool = Form(True),
                 delimiter: str | None = Form(None), file: UploadFile = File(...),
                 db: Session = Depends(get_db), user: User = Depends(require("runs:write"))):
    if side not in {"source", "target"}:
        raise HTTPException(400, "side must be 'source' or 'target'")
    run = get_run_or_404(db, run_id)
    try:
        rows = connectors.read_file(file.filename or "upload.csv", await file.read(), delimiter)
    except connectors.ConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    count = _store(db, run, domain, side, rows, replace)
    log_action(db, user.username, "DATA_UPLOADED", "migration_run", run_id,
               {"domain": domain, "side": side, "rows": count, "file": file.filename})
    db.commit()
    return {"loaded": count, "domain": domain, "side": side}


@router.post("/runs/{run_id}/extract")
def extract(run_id: int, body: SqlExtractRequest, db: Session = Depends(get_db),
            user: User = Depends(require("runs:write"))):
    run = get_run_or_404(db, run_id)
    try:
        if body.connector == "sql":
            rows = connectors.read_sql(body.url, body.query)
        else:
            rows = connectors.read_mongodb(body.url, body.database, body.collection)
    except connectors.ConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    count = _store(db, run, body.domain, body.side, rows, body.replace)
    log_action(db, user.username, "DATA_EXTRACTED", "migration_run", run_id,
               {"domain": body.domain, "side": body.side, "rows": count, "connector": body.connector})
    db.commit()
    return {"loaded": count, "domain": body.domain, "side": body.side}


@router.post("/runs/{run_id}/reconcile")
def reconcile(run_id: int, body: ReconcileRequest | None = None, db: Session = Depends(get_db),
              user: User = Depends(require("recon:execute"))):
    run = get_run_or_404(db, run_id)
    domains = (body.domains if body else None) or None
    if domains:
        for d in domains:
            if d not in DOMAIN_SPECS:
                raise HTTPException(400, f"Unknown domain {d}")
            check_domain(user, d)
    elif ROLE_DOMAINS.get(user.role) is not None:
        domains = sorted(ROLE_DOMAINS[user.role])
    result = run_reconciliation(db, run, user.username, domains)
    db.commit()
    return result


@router.post("/runs/{run_id}/signoff", response_model=SignOffOut)
def signoff(run_id: int, body: SignOffRequest, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    run = get_run_or_404(db, run_id)
    result = record_signoff(db, run, body.area, body.decision, body.comment, user)
    db.commit()
    return result
