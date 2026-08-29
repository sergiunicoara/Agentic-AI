from contacts import unique_emails


def test_unique_emails_dedupes_case_insensitively():
    """Same person, same email, different capitalization should be
    treated as a duplicate and only the first occurrence kept.

    report.md: the two records are for the "[s]ame person, same email
    address", "just typed with different capitalization", and the
    cleanup step is expected to "catch that and only keep one of them".
    """
    entries = [
        {"name": "Jane Doe", "email": "jane.doe@example.com"},
        {"name": "Jane Doe", "email": "Jane.Doe@example.com"},
    ]

    # Re-computable straight from the setup literals above, without
    # calling the function under test: the two emails are the same
    # address once case is normalized, so exactly one distinct email is
    # represented among the entries.
    expected_unique_count = len({entry["email"].lower() for entry in entries})

    result = unique_emails(entries)

    assert len(result) == expected_unique_count
    assert result[0]["email"] == "jane.doe@example.com"
