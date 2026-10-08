from enum import Enum


class Domain(str, Enum):
    CUSTOMER = "customer"
    ACCOUNT = "account"
    BALANCE = "balance"
    TRANSACTION = "transaction"
    AML = "aml"
    KYC = "kyc"
    SANCTIONS = "sanctions"
    AUDIT = "audit"


class Role(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    FINANCE = "finance"
    COMPLIANCE = "compliance"
    AUDITOR = "auditor"


class ExceptionCategory(str, Enum):
    MISSING_RECORD = "MISSING_RECORD"
    UNEXPECTED_RECORD = "UNEXPECTED_RECORD"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    BALANCE_VARIANCE = "BALANCE_VARIANCE"
    MAPPING_ISSUE = "MAPPING_ISSUE"
    AML_VALIDATION_FAILURE = "AML_VALIDATION_FAILURE"
    RULE_FAILURE = "RULE_FAILURE"


class ExceptionStatus(str, Enum):
    DETECTED = "DETECTED"
    ASSIGNED = "ASSIGNED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RootCause(str, Enum):
    TRANSFORMATION_ISSUE = "TRANSFORMATION_ISSUE"
    MISSING_RECORDS = "MISSING_RECORDS"
    SOURCE_ISSUE = "SOURCE_ISSUE"
    MAPPING_ISSUE = "MAPPING_ISSUE"
    LOAD_ISSUE = "LOAD_ISSUE"
    DATA_QUALITY_ISSUE = "DATA_QUALITY_ISSUE"


class RuleCategory(str, Enum):
    RECONCILIATION = "RECONCILIATION"
    THRESHOLD = "THRESHOLD"
    PERCENTAGE_THRESHOLD = "PERCENTAGE_THRESHOLD"
    COMPLIANCE = "COMPLIANCE"
    COMPLETENESS = "COMPLETENESS"


class SignOffArea(str, Enum):
    OPERATIONS = "OPERATIONS"
    FINANCE = "FINANCE"
    AML = "AML"
    COMPLIANCE = "COMPLIANCE"


class SignOffDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


SOURCE_SYSTEMS = [
    "Oracle", "SQL Server", "PostgreSQL", "DB2", "MongoDB", "Flat File", "CSV",
    "Parquet", "Snowflake", "Azure SQL", "Databricks",
]
TARGET_SYSTEMS = [
    "Actimize", "SAS AML", "Oracle FCCM", "Fircosoft", "Guidewire", "Snowflake",
    "Azure SQL", "Databricks", "Custom Application",
]
ENVIRONMENTS = ["DEV", "SIT", "UAT", "PROD"]

# Per-domain record key and compared fields.
DOMAIN_SPECS: dict[str, dict] = {
    Domain.CUSTOMER.value: {
        "key": "customer_id",
        "fields": ["full_name", "status", "segment", "country", "relationship_id", "date_of_birth"],
        "numeric": [],
        "mandatory": ["customer_id", "full_name", "status", "country"],
    },
    Domain.ACCOUNT.value: {
        "key": "account_id",
        "fields": ["customer_id", "account_type", "status", "currency", "open_date"],
        "numeric": [],
        "mandatory": ["account_id", "customer_id", "account_type", "status"],
    },
    Domain.BALANCE.value: {
        "key": "account_id",
        "fields": [
            "current_balance", "available_balance", "ledger_balance",
            "blocked_balance", "opening_balance", "closing_balance",
        ],
        "numeric": [
            "current_balance", "available_balance", "ledger_balance",
            "blocked_balance", "opening_balance", "closing_balance",
        ],
        "mandatory": ["account_id", "current_balance", "ledger_balance"],
    },
    Domain.TRANSACTION.value: {
        "key": "txn_id",
        "fields": ["account_id", "direction", "amount", "status", "txn_date"],
        "numeric": ["amount"],
        "mandatory": ["txn_id", "account_id", "direction", "amount"],
    },
    Domain.AML.value: {
        "key": "case_id",
        "fields": ["customer_id", "alert_type", "risk_rating", "risk_score", "case_status",
                   "sar_filed", "watchlist_match", "case_notes"],
        "numeric": ["risk_score"],
        "mandatory": ["case_id", "customer_id", "risk_rating", "case_status"],
    },
    Domain.KYC.value: {
        "key": "customer_id",
        "fields": ["kyc_status", "risk_classification", "pep_flag", "tax_id", "documents_count",
                   "last_review_date"],
        "numeric": ["documents_count"],
        "mandatory": ["customer_id", "kyc_status", "risk_classification"],
    },
    Domain.SANCTIONS.value: {
        "key": "match_id",
        "fields": ["customer_id", "list_name", "match_status", "screening_score", "finding"],
        "numeric": ["screening_score"],
        "mandatory": ["match_id", "customer_id", "match_status"],
    },
    Domain.AUDIT.value: {
        "key": "record_id",
        "fields": ["entity", "created_date", "updated_date", "user_id", "workflow_state",
                   "approved_by"],
        "numeric": [],
        "mandatory": ["record_id", "created_date", "user_id"],
    },
}

DOMAIN_SIGNOFF_AREA = {
    Domain.CUSTOMER.value: SignOffArea.OPERATIONS.value,
    Domain.ACCOUNT.value: SignOffArea.OPERATIONS.value,
    Domain.TRANSACTION.value: SignOffArea.OPERATIONS.value,
    Domain.AUDIT.value: SignOffArea.OPERATIONS.value,
    Domain.BALANCE.value: SignOffArea.FINANCE.value,
    Domain.AML.value: SignOffArea.AML.value,
    Domain.KYC.value: SignOffArea.COMPLIANCE.value,
    Domain.SANCTIONS.value: SignOffArea.COMPLIANCE.value,
}
