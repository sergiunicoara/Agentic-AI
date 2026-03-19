from __future__ import annotations

from app.nl_query.intent import ALLOWED_SCHEMA, QueryIntent


def build_sql(intent: QueryIntent, workspace_id: str) -> tuple[str, dict]:
    """Build a parameterized SELECT statement from a validated QueryIntent.

    Returns (sql, params) where sql uses SQLAlchemy :name placeholders.
    Column and table names are whitelisted before reaching here — they are
    safe to interpolate directly into the SQL string as identifiers.
    All user-supplied *values* are always parameterized.
    """
    params: dict = {"_workspace_id": workspace_id}
    allowed_cols = ALLOWED_SCHEMA[intent.table]
    workspace_scoped = "workspace_id" in allowed_cols

    # --- SELECT clause ---
    if intent.aggregation:
        agg = intent.aggregation.upper()
        if agg == "COUNT" and not intent.aggregation_column:
            agg_expr = "COUNT(*)"
        else:
            col = intent.aggregation_column or "*"
            agg_expr = f"{agg}({col})"
        if intent.group_by:
            select_expr = ", ".join(intent.group_by) + f", {agg_expr}"
        else:
            select_expr = agg_expr
    else:
        cols = intent.select_columns if intent.select_columns else allowed_cols
        select_expr = ", ".join(cols)

    sql = f"SELECT {select_expr} FROM {intent.table}"

    # --- WHERE clause ---
    conditions: list[str] = []

    # Multi-tenancy: always scope by workspace_id when the table has that column.
    if workspace_scoped:
        conditions.append("workspace_id = :_workspace_id")

    for i, f in enumerate(intent.filters):
        pname = f"_v{i}"
        op = f.operator

        if op in ("IS NULL", "IS NOT NULL"):
            conditions.append(f"{f.column} {op}")

        elif op == "IN":
            vals = f.value if isinstance(f.value, list) else [f.value]
            placeholders = ", ".join(f":_v{i}_{j}" for j in range(len(vals)))
            for j, v in enumerate(vals):
                params[f"_v{i}_{j}"] = v
            conditions.append(f"{f.column} IN ({placeholders})")

        else:
            params[pname] = f.value
            conditions.append(f"{f.column} {op} :{pname}")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    # --- GROUP BY ---
    if intent.aggregation and intent.group_by:
        sql += " GROUP BY " + ", ".join(intent.group_by)

    # --- ORDER BY ---
    if intent.order_by:
        direction = "DESC" if intent.order_by.direction.upper() == "DESC" else "ASC"
        sql += f" ORDER BY {intent.order_by.column} {direction}"

    # --- LIMIT --- (capped at 1000, already validated by QueryIntent)
    sql += f" LIMIT {min(intent.limit, 1000)}"

    return sql, params
