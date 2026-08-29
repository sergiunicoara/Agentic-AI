from contacts import unique_emails


def test_unique_emails_dedupes_case_insensitively():
    """Same person, same email, different capitalization should be
    treated as a duplicate and only the first occurrence kept."""
    entries = [
        {"name": "Jane Doe", "email": "jane.doe@example.com"},
        {"name": "Jane Doe", "email": "Jane.Doe@example.com"},
    ]

    result = unique_emails(entries)

    assert len(result) == 1
    assert result[0]["email"] == "jane.doe@example.com"
