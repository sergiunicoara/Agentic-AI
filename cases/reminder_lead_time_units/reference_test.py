from scheduler import reminder_trigger_time


def test_default_lead_time_fires_fifteen_minutes_before_the_event():
    event_time = 1_000_000

    trigger_time = reminder_trigger_time(event_time)

    assert event_time - trigger_time == 15 * 60
