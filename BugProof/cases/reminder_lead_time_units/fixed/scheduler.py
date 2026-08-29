from config import DEFAULT_REMINDER_LEAD_MINUTES


def reminder_trigger_time(event_time_epoch, lead_minutes=None):
    """Return the epoch timestamp at which a reminder should fire."""
    lead = lead_minutes if lead_minutes is not None else DEFAULT_REMINDER_LEAD_MINUTES
    return event_time_epoch - (lead * 60)
