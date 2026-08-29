def parse_line(line, delimiter=","):
    """Split a single delimited line into fields, respecting double-quoted fields."""
    fields = []
    current = []
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == delimiter and not in_quotes:
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
    fields.append("".join(current))
    return fields
