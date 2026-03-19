from __future__ import annotations

import time

from app.core.observability import emit_event
from app.nl_query.audit import write_audit_log
from app.nl_query.executor import execute_query
from app.nl_query.intent import extract_intent
from app.nl_query.sql_builder import build_sql
from app.nl_query.validator import validate_intent


class NLQueryError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def run_nl_query(nl_query: str, workspace_id: str) -> dict:
    """Full NLP → JSON → SQL → result pipeline.

    Steps:
      1. PydanticAI extracts a structured QueryIntent from the natural language query.
      2. Validator enforces table/column whitelist and injection guards.
      3. SQL builder produces a parameterized SELECT with workspace_id scoping.
      4. Executor runs the query with a hard statement_timeout.
      5. Audit log captures every query regardless of outcome.
    """
    t0 = time.time()
    sql = ""
    params: dict = {}
    results: list[dict] = []
    error: str | None = None

    try:
        # 1. NLP → QueryIntent
        intent = extract_intent(nl_query)
        emit_event(
            "nl_query_intent_extracted",
            {
                "workspace_id": workspace_id,
                "table": intent.table,
                "aggregation": intent.aggregation,
                "filter_count": len(intent.filters),
            },
        )

        # 2. Validate (whitelist + injection guard)
        validation = validate_intent(intent)
        if not validation.ok:
            raise NLQueryError(f"Query validation failed: {validation.error}")

        # 3. Build parameterized SQL
        sql, params = build_sql(intent, workspace_id)
        emit_event("nl_query_sql_built", {"workspace_id": workspace_id, "sql": sql})

        # 4. Execute
        results = execute_query(sql, params)

    except NLQueryError:
        raise
    except Exception as exc:
        error = str(exc)
        raise NLQueryError(f"Query execution failed: {error}", status_code=500)
    finally:
        latency_ms = int((time.time() - t0) * 1000)
        write_audit_log(
            workspace_id=workspace_id,
            nl_query=nl_query,
            generated_sql=sql,
            params=params,
            row_count=len(results),
            latency_ms=latency_ms,
            error=error,
        )

    return {
        "sql": sql,
        "results": results,
        "row_count": len(results),
    }
