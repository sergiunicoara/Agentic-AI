"""
CCA-F D2.1 Anti-Pattern: Vague Tool Descriptions → Misrouting
"Tool descriptions are more important than most people realize" — exam source

The exam will show you tool descriptions and ask which is correct.
Vague descriptions cause Claude to pick the wrong tool or use tools incorrectly.
"""

# ===========================================================================
# ❌ BAD: Vague descriptions — causes misrouting
# ===========================================================================

BAD_TOOLS = [
    {
        "name": "search",
        # PROBLEM: What does it search? Where? What does it return?
        # Claude may call this when it should call lookup_incident,
        # or may pass the wrong arguments because constraints aren't stated.
        "description": "Search for things",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }
    },
    {
        "name": "get_data",
        # PROBLEM: "Data" is meaningless. What data? From where? What format?
        # Claude cannot distinguish this from the above.
        "description": "Gets data from the database",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
        }
    },
    {
        "name": "analyze",
        # PROBLEM: Verb too broad. Analyze what? What is the output?
        # Will compete with every other tool for selection.
        "description": "Analyze the input and return results",
        "input_schema": {
            "type": "object",
            "properties": {"input": {"type": "string"}},
        }
    },
]

# WHY THIS FAILS:
# Claude selects tools based on descriptions. When two tools have similar
# vague descriptions, Claude either picks randomly or picks neither.
# The exam calls this "vague tool descriptions causing misrouting."


# ===========================================================================
# ✅ GOOD: Precise descriptions — VERB + NOUN + BOUNDARY + CONSTRAINTS
# ===========================================================================

GOOD_TOOLS = [
    {
        "name": "search_knowledge_base",
        # VERB: Search
        # NOUN: knowledge base articles
        # BOUNDARY: by keyword
        # CONSTRAINT: top 10, with title/URL/excerpt
        "description": "Search knowledge base articles by keyword. "
                       "Returns top 10 most relevant articles with title, URL, and excerpt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords (e.g. 'connection pool timeout postgres')"
                },
                "limit": {"type": "integer", "default": 10, "maximum": 50},
            },
            "required": ["query"],
        }
    },
    {
        "name": "get_incident_by_id",
        # VERB: Retrieve
        # NOUN: single incident record
        # BOUNDARY: by incident ID
        # CONSTRAINT: specific format, full details
        "description": "Retrieve a single incident record by its ID. "
                       "Returns full incident details including timeline, severity, and resolution notes. "
                       "Use search_incidents to find IDs first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "Incident ID in format INC-XXXX (e.g. INC-2047)"
                },
            },
            "required": ["incident_id"],
        }
    },
    {
        "name": "grep_log_file",
        # VERB: Search (grep)
        # NOUN: log file content
        # BOUNDARY: by regex pattern, returns matching lines
        # CONSTRAINT: file path required, returns 5 lines of context
        "description": "Search a log file for a regex pattern. "
                       "Returns up to 50 matching lines with 5 lines of surrounding context. "
                       "Use for finding error messages, stack traces, or event sequences in logs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "context_lines": {"type": "integer", "default": 5},
            },
            "required": ["file_path", "pattern"],
        }
    },
]

# EXAM RULE: When you see a tool description question, check:
# 1. Does it start with a specific verb? (search, retrieve, create, update — not "handles", "does", "manages")
# 2. Does it name the specific data being operated on?
# 3. Does it state a boundary (what it DOESN'T do)?
# 4. Does it include constraints (limits, formats, prerequisites)?
# If any of these are missing → it's the wrong answer.


# ===========================================================================
# D2.3: Tool overload prevention
# ===========================================================================

# ❌ BAD: One server with 15 tools — degrades selection accuracy
BAD_SINGLE_SERVER_TOOLS = ["search", "get", "create", "update", "delete",
                           "analyze", "summarize", "extract", "transform", "validate",
                           "notify", "schedule", "cancel", "archive", "restore"]
# PROBLEM: With 15 tools, Claude's tool selection accuracy degrades significantly.
# The exam says max ~8 tools per context before quality drops.

# ✅ GOOD: Split into role-scoped servers
GOOD_SPLIT = {
    "incident_server": ["query_incidents", "get_incident", "search_incidents"],  # 3 tools
    "log_server": ["grep_log_file", "read_log_range", "list_log_files"],         # 3 tools
    "kb_server": ["search_knowledge_base", "get_article", "list_categories"],   # 3 tools
}
