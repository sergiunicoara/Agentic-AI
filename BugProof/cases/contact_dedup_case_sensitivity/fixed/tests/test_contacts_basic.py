from contacts import unique_emails


def test_dedup_keeps_distinct_emails():
    entries = [{"email": "a@x.com"}, {"email": "b@x.com"}]

    result = unique_emails(entries)

    assert len(result) == 2
