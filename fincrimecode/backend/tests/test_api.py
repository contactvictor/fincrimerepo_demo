import io
import zipfile


def test_auth_and_rbac(client, tokens):
    assert client.get("/api/runs").status_code == 401
    me = client.get("/api/auth/me", headers=tokens["auditor"]).json()
    assert me["role"] == "auditor"
    assert client.post("/api/runs", headers=tokens["analyst"], json={
        "name": "x run", "source_system": "Oracle", "target_system": "Actimize"}).status_code == 403
    assert client.post("/api/login", data={}).status_code in (404, 405)
    bad = client.post("/api/auth/login", data={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401


def test_seeded_runs_and_dashboards(client, tokens):
    runs = client.get("/api/runs", headers=tokens["analyst"]).json()
    assert len(runs) == 3
    ex = client.get("/api/dashboard/executive", headers=tokens["analyst"]).json()
    assert ex["kpis"]["records_processed"] > 0 and 0 < ex["kpis"]["reconciliation_pct"] < 100
    assert len(ex["heatmap"]) == 8 and len(ex["exception_trend"]) == 21
    for name in ["finance", "aml", "compliance"]:
        assert client.get(f"/api/dashboard/{name}", headers=tokens["auditor"]).status_code == 200


def test_create_reconcile_and_drilldown(client, tokens):
    run = client.post("/api/runs", headers=tokens["admin"], json={
        "name": "API test run", "source_system": "PostgreSQL", "target_system": "Fircosoft",
        "environment": "DEV", "generate_demo_data": True, "demo_customers": 50, "defect_level": 1}).json()
    rid = run["id"]
    assert run["status"] == "LOADED"
    # finance may only reconcile its own domains
    assert client.post(f"/api/runs/{rid}/reconcile", headers=tokens["finance"],
                       json={"domains": ["aml"]}).status_code == 403
    res = client.post(f"/api/runs/{rid}/reconcile", headers=tokens["admin"], json={}).json()
    assert set(res["domains"]) == {"customer", "account", "balance", "transaction", "aml", "kyc", "sanctions", "audit"}
    recs = client.get(f"/api/recon/{rid}/records", headers=tokens["analyst"],
                      params={"domain": "balance", "status": "MISMATCHED"}).json()
    assert recs["total"] > 0 and recs["items"][0]["field_differences"]
    key = recs["items"][0]["record_key"]
    assert client.get(f"/api/recon/{rid}/records/balance/{key}", headers=tokens["analyst"]).status_code == 200
    csv_resp = client.get(f"/api/recon/{rid}/records/export", headers=tokens["analyst"], params={"domain": "balance"})
    assert csv_resp.status_code == 200 and csv_resp.text.startswith("record_key")
    fields = client.get(f"/api/recon/{rid}/fields/balance", headers=tokens["analyst"]).json()
    assert any(f["mismatches"] for f in fields)


def test_exception_workflow(client, tokens):
    page = client.get("/api/exceptions", headers=tokens["analyst"],
                      params={"status": "DETECTED", "domain": "customer"}).json()
    code = page["items"][0]["code"]
    h = tokens["analyst"]
    assert client.post(f"/api/exceptions/{code}/transition", headers=h,
                       json={"to_status": "RESOLVED"}).status_code == 400
    assert client.post(f"/api/exceptions/{code}/transition", headers=h,
                       json={"to_status": "ASSIGNED"}).status_code == 400  # owner required
    r = client.post(f"/api/exceptions/{code}/transition", headers=h,
                    json={"to_status": "ASSIGNED", "owner": "analyst", "comment": "taking it"})
    assert r.status_code == 200 and r.json()["owner"] == "analyst"
    client.post(f"/api/exceptions/{code}/transition", headers=h, json={"to_status": "INVESTIGATING"})
    assert client.post(f"/api/exceptions/{code}/transition", headers=h,
                       json={"to_status": "RESOLVED"}).status_code == 400  # comment required
    client.post(f"/api/exceptions/{code}/transition", headers=h,
                json={"to_status": "RESOLVED", "comment": "fixed mapping"})
    # four-eyes: owner cannot close
    assert client.post(f"/api/exceptions/{code}/transition", headers=h,
                       json={"to_status": "CLOSED"}).status_code == 400
    done = client.post(f"/api/exceptions/{code}/transition", headers=tokens["admin"], json={"to_status": "CLOSED"})
    assert done.json()["status"] == "CLOSED" and len(done.json()["history"]) == 4
    # auditors are read-only
    assert client.post(f"/api/exceptions/{code}/transition", headers=tokens["auditor"],
                       json={"to_status": "ASSIGNED", "owner": "admin"}).status_code == 403
    # compliance cannot touch balance exceptions
    bal = client.get("/api/exceptions", headers=h, params={"domain": "balance", "status": "DETECTED"}).json()
    assert client.post(f"/api/exceptions/{bal['items'][0]['code']}/transition", headers=tokens["compliance"],
                       json={"to_status": "ASSIGNED", "owner": "compliance"}).status_code == 403
    explain = client.get(f"/api/exceptions/{code}/explain", headers=h).json()
    assert explain["provider"] == "built-in" and explain["recommended_action"]


def test_signoff_blocked_by_critical(client, tokens):
    detail = client.get("/api/runs/1", headers=tokens["finance"]).json()
    assert detail["signoff_blockers"]["FINANCE"] > 0
    r = client.post("/api/runs/1/signoff", headers=tokens["finance"],
                    json={"area": "FINANCE", "decision": "APPROVED"})
    assert r.status_code == 400 and "CRITICAL" in r.json()["detail"]
    assert client.post("/api/runs/1/signoff", headers=tokens["finance"],
                       json={"area": "AML", "decision": "APPROVED"}).status_code == 403
    rej = client.post("/api/runs/1/signoff", headers=tokens["finance"],
                      json={"area": "FINANCE", "decision": "REJECTED", "comment": "variances open"})
    assert rej.status_code == 200
    assert client.get("/api/runs/1", headers=tokens["finance"]).json()["run"]["signoff_status"] == "REJECTED"


def test_reports(client, tokens):
    types = {t["type"]: t["allowed"] for t in client.get("/api/reports/types", headers=tokens["auditor"]).json()}
    assert types["AUDIT_PACK"] and not types["BUSINESS_RECONCILIATION"]
    assert client.post("/api/reports", headers=tokens["auditor"],
                       json={"run_id": 1, "report_type": "BUSINESS_RECONCILIATION"}).status_code == 403
    for rtype in ["BUSINESS_RECONCILIATION", "COMPLIANCE", "MANAGEMENT_SUMMARY", "MIGRATION_SUMMARY",
                  "DETAILED_MISMATCH"]:
        rep = client.post("/api/reports", headers=tokens["admin"], json={"run_id": 1, "report_type": rtype})
        assert rep.status_code == 201, rep.text
        dl = client.get(f"/api/reports/{rep.json()['id']}/download", headers=tokens["admin"])
        assert dl.status_code == 200 and len(dl.content) > 1000
        if rtype != "DETAILED_MISMATCH":
            assert dl.content.startswith(b"%PDF")
    pack = client.post("/api/reports", headers=tokens["auditor"], json={"run_id": 1, "report_type": "AUDIT_PACK"})
    assert pack.status_code == 201
    dl = client.get(f"/api/reports/{pack.json()['id']}/download", headers=tokens["auditor"])
    names = zipfile.ZipFile(io.BytesIO(dl.content)).namelist()
    assert "manifest.json" in names and "05_approval_log.csv" in names and "03_exception_log.csv" in names
    assert client.post("/api/reports", headers=tokens["admin"],
                       json={"run_id": 3, "report_type": "MIGRATION_SUMMARY"}).status_code == 400


def test_ai_assistant(client, tokens):
    h = tokens["analyst"]
    cases = {
        "Why did reconciliation fail?": "why_failed",
        "Show accounts with highest mismatch.": "highest_mismatch",
        "Which AML cases failed migration?": "aml_failures",
        "Show root cause of balance variance.": "balance_root_cause",
        "Show all AML cases with reconciliation failures": "aml_failures",
        "How are we doing?": "overview",
    }
    for q, intent in cases.items():
        r = client.post("/api/ai/ask", headers=h, json={"question": q, "run_id": 1}).json()
        assert r["intent"] == intent, (q, r["intent"])
        assert r["answer"]
    aml = client.post("/api/ai/ask", headers=h, json={"question": "Which AML cases failed migration?", "run_id": 1}).json()
    assert "case_notes" in aml["answer"]
    assert client.post("/api/ai/ask", headers=tokens["auditor"], json={"question": "hi"}).status_code == 403


def test_upload_and_rules_admin(client, tokens):
    run = client.post("/api/runs", headers=tokens["admin"], json={
        "name": "Upload run", "source_system": "CSV", "target_system": "Custom Application", "environment": "DEV"}).json()
    rid = run["id"]
    src = b"customer_id,full_name,status,country\nC1,Ann,ACTIVE,GB\nC2,Bob,ACTIVE,US\n"
    tgt = b"customer_id,full_name,status,country\nC1,Ann,A,GB\n"
    for side, content in (("source", src), ("target", tgt)):
        r = client.post(f"/api/runs/{rid}/upload", headers=tokens["admin"],
                        data={"domain": "customer", "side": side}, files={"file": ("c.csv", content, "text/csv")})
        assert r.status_code == 200 and r.json()["loaded"] == (2 if side == "source" else 1)
    bad = client.post(f"/api/runs/{rid}/upload", headers=tokens["admin"], data={"domain": "customer", "side": "source"},
                      files={"file": ("c.csv", b"name\nx\n", "text/csv")})
    assert bad.status_code == 400
    res = client.post(f"/api/runs/{rid}/reconcile", headers=tokens["admin"], json={"domains": ["customer"]}).json()
    assert res["domains"]["customer"]["matched"] == 0 and res["domains"]["customer"]["records"] == 2

    rule = client.post("/api/rules", headers=tokens["admin"], json={
        "name": "Max current balance variance", "category": "THRESHOLD", "domain": "balance",
        "params": {"field": "current_balance", "measure": "max_abs_variance", "operator": "<=", "value": 100}})
    assert rule.status_code == 201
    assert client.post("/api/rules", headers=tokens["admin"], json={
        "name": "bad rule", "category": "THRESHOLD", "domain": "balance", "params": {"field": "x"}}).status_code == 400
    assert client.post("/api/rules", headers=tokens["finance"], json={
        "name": "bad rule", "category": "COMPLETENESS", "domain": "balance"}).status_code == 403
    logs = client.get("/api/admin/audit-logs", headers=tokens["auditor"]).json()
    assert any(entry["action"] == "RULE_CREATED" for entry in logs)
    assert client.get("/api/admin/audit-logs", headers=tokens["analyst"]).status_code == 403
    assert client.get("/api/search", headers=tokens["analyst"], params={"q": "EXC-0001"}).json()["exceptions"]
