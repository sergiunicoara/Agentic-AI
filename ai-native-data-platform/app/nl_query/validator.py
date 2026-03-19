from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.nl_query.intent import ALLOWED_SCHEMA, Filter, QueryIntent

# Any of these keywords appearing in a filter value is treated as an injection attempt.
_DANGEROUS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE|COPY|VACUUM)\b",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    ok: bool
    error: str = field(default="")


def validate_intent(intent: QueryIntent) -> ValidationResult:
    # Table whitelist
    if intent.table not in ALLOWED_SCHEMA:
        return ValidationResult(ok=False, error=f"Table '{intent.table}' is not allowed")

    allowed = set(ALLOWED_SCHEMA[intent.table])

    # select_columns
    for col in intent.select_columns:
        if col not in allowed:
            return ValidationResult(ok=False, error=f"Column '{col}' not in allowed schema for '{intent.table}'")

    # filter columns + value safety
    for f in intent.filters:
        if f.column not in allowed:
            return ValidationResult(ok=False, error=f"Filter column '{f.column}' not allowed")
        if isinstance(f.value, str) and _DANGEROUS.search(f.value):
            return ValidationResult(ok=False, error="Potentially unsafe value in filter")
        if isinstance(f.value, list):
            for v in f.value:
                if isinstance(v, str) and _DANGEROUS.search(v):
                    return ValidationResult(ok=False, error="Potentially unsafe value in filter list")

    # group_by columns
    for col in intent.group_by:
        if col not in allowed:
            return ValidationResult(ok=False, error=f"group_by column '{col}' not allowed")

    # order_by column
    if intent.order_by and intent.order_by.column not in allowed:
        return ValidationResult(ok=False, error=f"order_by column '{intent.order_by.column}' not allowed")

    # aggregation_column
    if intent.aggregation_column and intent.aggregation_column not in allowed:
        return ValidationResult(ok=False, error=f"aggregation_column '{intent.aggregation_column}' not allowed")

    return ValidationResult(ok=True)
