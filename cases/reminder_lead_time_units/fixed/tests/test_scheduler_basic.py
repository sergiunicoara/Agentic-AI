from scheduler import reminder_trigger_time


def test_custom_lead_time_overrides_the_default():
    trigger_time = reminder_trigger_time(1_000_000, lead_minutes=5)

    assert trigger_time == 1_000_000 - 300
