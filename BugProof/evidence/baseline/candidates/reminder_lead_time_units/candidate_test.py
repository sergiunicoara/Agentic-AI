from scheduler import reminder_trigger_time


def test_default_lead_time_is_minutes_before_event():
    """DEFAULT_REMINDER_LEAD_MINUTES is documented/used as minutes, so the
    reminder should fire that many minutes (i.e. minutes * 60 seconds)
    before the event, not that many seconds before it."""
    event_time_epoch = 1_000_000
    lead_minutes = 15

    trigger_time = reminder_trigger_time(event_time_epoch, lead_minutes)

    expected_trigger_time = event_time_epoch - (lead_minutes * 60)
    assert trigger_time == expected_trigger_time

    # Sanity: the reminder must fire well ahead of the event, not mere
    # seconds beforehand.
    seconds_before_event = event_time_epoch - trigger_time
    assert seconds_before_event >= 60 * lead_minutes


def test_custom_lead_time_is_minutes_before_event():
    """Custom per-event lead times are also expressed in minutes and must
    be converted to seconds the same way as the default."""
    event_time_epoch = 5_000_000
    lead_minutes = 10

    trigger_time = reminder_trigger_time(event_time_epoch, lead_minutes)

    expected_trigger_time = event_time_epoch - (lead_minutes * 60)
    assert trigger_time == expected_trigger_time
