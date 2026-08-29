def unique_emails(entries):
    """Return entries with duplicate emails removed, keeping the first occurrence."""
    seen = set()
    result = []
    for entry in entries:
        email = entry["email"].lower()
        if email not in seen:
            seen.add(email)
            result.append(entry)
    return result
