from contacts import unique_emails


def test_unique_emails_dedupes_case_insensitively():
    entries = [
        {"name": "Jane Doe", "email": "jane.doe@example.com"},
        {"name": "Jane Doe", "email": "Jane.Doe@example.com"},
    ]

    result = unique_emails(entries)

    assert len(result) == 1
    assert result[0]["email"] == "jane.doe@example.com"
