from config import DEFAULT_REMINDER_LEAD_MINUTES
from scheduler import reminder_trigger_time


def test_default_lead_time_is_minutes_before_event():
    """DEFAULT_REMINDER_LEAD_MINUTES is 15 minutes; the reminder should fire
    15 minutes (900 seconds) before the event, not 15 seconds before."""
    event_time_epoch = 1_000_000
    expected = event_time_epoch - DEFAULT_REMINDER_LEAD_MINUTES * 60

    result = reminder_trigger_time(event_time_epoch)

    assert result == expected


def test_custom_lead_time_is_minutes_before_event():
    """A custom lead_minutes value should also be converted to seconds
    before being subtracted from the event time."""
    event_time_epoch = 2_000_000
    custom_lead_minutes = 10
    expected = event_time_epoch - custom_lead_minutes * 60

    result = reminder_trigger_time(event_time_epoch, lead_minutes=custom_lead_minutes)

    assert result == expected
