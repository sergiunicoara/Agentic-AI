"""Safe Python eval sandbox — arithmetic and data transforms only."""
from __future__ import annotations

import ast
import math
import operator
import re


_SAFE_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Call, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
    ast.USub, ast.UAdd, ast.Name, ast.Load,
}

_SAFE_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "len": len, "int": int, "float": float, "str": str,
    "sqrt": math.sqrt, "log": math.log, "ceil": math.ceil, "floor": math.floor,
    "pi": math.pi, "e": math.e,
}


def python_eval(code: str) -> str:
    """Evaluate a safe arithmetic/data expression and return the result as string."""
    code = code.strip()
    # Block obvious injection
    if re.search(r"(import|exec|eval|open|os\.|sys\.|__)", code):
        return "Error: unsafe expression"
    try:
        tree = ast.parse(code, mode="eval")
        for node in ast.walk(tree):
            if type(node) not in _SAFE_NODES:
                return f"Error: disallowed construct '{type(node).__name__}'"
        result = eval(compile(tree, "<sandbox>", "eval"), {"__builtins__": {}}, _SAFE_NAMES)
        return str(result)
    except Exception as exc:
        return f"Error: {exc}"
