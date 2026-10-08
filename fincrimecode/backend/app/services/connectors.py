"""Source / target data connectors. Every connector returns a list of JSON-safe dicts."""
import io
import json
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

# Source systems reachable through SQLAlchemy given the right driver/dialect.
SQL_DIALECT_HINTS = {
    "Oracle": "oracle+oracledb://user:pass@host:1521/?service_name=SVC",
    "SQL Server": "mssql+pyodbc://user:pass@dsn",
    "Azure SQL": "mssql+pyodbc://user:pass@server.database.windows.net/db?driver=ODBC+Driver+18+for+SQL+Server",
    "PostgreSQL": "postgresql+psycopg2://user:pass@host:5432/db",
    "DB2": "db2+ibm_db://user:pass@host:50000/db",
    "Snowflake": "snowflake://user:pass@account/db/schema?warehouse=WH",
    "Databricks": "databricks://token:TOKEN@host?http_path=/sql/1.0/warehouses/ID",
}


class ConnectorError(ValueError):
    pass


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def read_file(filename: str, content: bytes, delimiter: str | None = None) -> list[dict]:
    name = filename.lower()
    try:
        if name.endswith(".parquet"):
            df = pd.read_parquet(io.BytesIO(content))
        elif name.endswith(".json"):
            df = pd.read_json(io.BytesIO(content))
        elif name.endswith((".csv", ".txt", ".dat", ".psv", ".tsv")):
            sep = delimiter or ("\t" if name.endswith(".tsv") else "|" if name.endswith(".psv") else ",")
            df = pd.read_csv(io.BytesIO(content), sep=sep, dtype=str, keep_default_na=False,
                             na_values=[""])
        else:
            raise ConnectorError("Supported files: .csv, .txt/.dat (flat file), .tsv, .psv, .parquet, .json")
    except ConnectorError:
        raise
    except Exception as exc:  # pandas raises many parser-specific errors
        raise ConnectorError(f"Could not parse {filename}: {exc}") from exc
    return dataframe_to_records(df)


def read_sql(url: str, query: str) -> list[dict]:
    if not query.strip().lower().startswith(("select", "with")):
        raise ConnectorError("Only read-only SELECT/WITH queries are allowed")
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            df = pd.read_sql(text(query), conn)
    except Exception as exc:
        raise ConnectorError(f"SQL extraction failed: {exc}") from exc
    finally:
        try:
            engine.dispose()
        except UnboundLocalError:
            pass
    return dataframe_to_records(df)


def read_mongodb(uri: str, database: str, collection: str, query: dict | None = None) -> list[dict]:
    try:
        from pymongo import MongoClient  # optional dependency
    except ImportError as exc:
        raise ConnectorError("Install 'pymongo' to enable the MongoDB connector") from exc
    with MongoClient(uri, serverSelectionTimeoutMS=5000) as client:
        docs = list(client[database][collection].find(query or {}, {"_id": 0}))
    return json.loads(json.dumps(docs, default=str))
