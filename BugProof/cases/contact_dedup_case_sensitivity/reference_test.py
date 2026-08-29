from contacts import unique_emails


def test_dedup_treats_email_case_insensitively():
    entries = [
        {"email": "Jane@example.com", "name": "Jane"},
        {"email": "jane@example.com", "name": "Jane (dup)"},
    ]

    result = unique_emails(entries)

    assert len(result) == 1
