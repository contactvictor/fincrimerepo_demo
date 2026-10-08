from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    email: str
    role: str
    active: bool


class MeOut(UserOut):
    permissions: list[str]
    domains: list[str] | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeOut


class RunCreate(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    description: str = ""
    source_system: str
    target_system: str
    environment: str = "UAT"
    generate_demo_data: bool = False
    demo_customers: int = Field(200, ge=10, le=20000)
    defect_level: float = Field(0.5, ge=0, le=5)


class RunOut(ORM):
    id: int
    name: str
    description: str
    source_system: str
    target_system: str
    environment: str
    status: str
    progress: float
    records_processed: int
    reconciliation_pct: float
    signoff_status: str
    created_by: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ReconcileRequest(BaseModel):
    domains: list[str] | None = None


class SqlExtractRequest(BaseModel):
    domain: str
    side: str = Field(pattern="^(source|target)$")
    connector: str = Field(pattern="^(sql|mongodb)$")
    url: str
    query: str = ""
    database: str = ""
    collection: str = ""
    replace: bool = True


class SignOffRequest(BaseModel):
    area: str
    decision: str
    comment: str = ""


class SignOffOut(ORM):
    id: int
    area: str
    decision: str
    actor: str
    role: str
    comment: str
    at: datetime


class SummaryOut(ORM):
    domain: str
    metric: str
    source_value: float
    target_value: float
    difference: float
    matched: bool


class RecordOut(ORM):
    id: int
    domain: str
    record_key: str
    status: str
    source_data: dict | None
    target_data: dict | None
    field_differences: list
    variance: float


class RuleIn(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    description: str = ""
    category: str
    domain: str
    params: dict = {}
    severity: str = "HIGH"
    active: bool = True


class RuleOut(ORM):
    id: int
    name: str
    description: str
    category: str
    domain: str
    params: dict
    severity: str
    active: bool


class RuleResultOut(ORM):
    rule_id: int
    rule_name: str
    category: str
    domain: str
    passed: bool
    actual: str
    expected: str
    detail: str


class HistoryOut(ORM):
    from_status: str | None
    to_status: str
    actor: str
    comment: str
    at: datetime


class ExceptionOut(ORM):
    id: int
    code: str
    run_id: int
    domain: str
    category: str
    severity: str
    root_cause: str
    root_cause_detail: str
    record_key: str | None
    field: str | None
    source_value: str | None
    target_value: str | None
    variance: float
    description: str
    owner: str | None
    status: str
    resolution: str
    created_at: datetime
    updated_at: datetime


class ExceptionDetailOut(ExceptionOut):
    history: list[HistoryOut]
    allowed_transitions: list[str] = []


class TransitionRequest(BaseModel):
    to_status: str
    owner: str | None = None
    comment: str = ""


class ReportRequest(BaseModel):
    run_id: int
    report_type: str


class ReportOut(ORM):
    id: int
    run_id: int
    report_type: str
    file_format: str
    filename: str
    sha256: str
    size_bytes: int
    created_by: str
    created_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    run_id: int | None = None
    environment: str | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str
    email: str = ""
    role: str
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(None, min_length=8)


class AuditLogOut(ORM):
    id: int
    actor: str
    action: str
    entity: str
    entity_id: str
    detail: dict
    at: datetime
