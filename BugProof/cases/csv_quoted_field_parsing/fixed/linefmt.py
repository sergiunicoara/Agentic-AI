def parse_line(line, delimiter=","):
    """Split a single delimited line into fields, respecting double-quoted fields."""
    fields = []
    current = []
    in_quotes = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == '"':
            if in_quotes and i + 1 < n and line[i + 1] == '"':
                current.append('"')
                i += 2
                continue
            in_quotes = not in_quotes
        elif ch == delimiter and not in_quotes:
            fields.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    fields.append("".join(current))
    return fields
