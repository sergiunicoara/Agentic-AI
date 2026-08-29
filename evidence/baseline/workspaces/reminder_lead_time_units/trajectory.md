# Trajectory

Read `report.md`: reminders fire only seconds before an event instead of the
configured lead time (default 15 minutes, or a custom per-event value).

Inspected `buggy/config.py` (just `DEFAULT_REMINDER_LEAD_MINUTES = 15`) and
`buggy/scheduler.py`, which contains:

```python
def reminder_trigger_time(event_time_epoch, lead_minutes=None):
    lead = lead_minutes if lead_minutes is not None else DEFAULT_REMINDER_LEAD_MINUTES
    return event_time_epoch - lead
```

`lead_minutes` is a value expressed in minutes but is subtracted directly
from `event_time_epoch`, which is in seconds, with no `* 60` conversion.
So a 15-minute lead time only pushes the trigger back 15 seconds, matching
the reported symptom ("fires a few seconds before the event" instead of
minutes before). This affects both the default lead time and any custom
per-event lead time, exactly as described in the report.

Wrote `candidate_test.py` (in the working directory, importing `from
scheduler import reminder_trigger_time` as it will be run as a sibling of
the buggy modules) with two tests: one for the default 15-minute lead and
one for a custom 10-minute lead, each asserting the trigger time is
`event_time_epoch - lead_minutes * 60`.

Per instructions, copied `candidate_test.py` into `buggy/` once, ran
`pytest` from there, and both tests failed against the current code
(e.g. `assert 999985 == 999100` for the 15-minute case — the code only
subtracted 15 seconds instead of 900). Removed the temporary copy from
`buggy/` afterward; `buggy/` is unchanged from its original state
(`config.py`, `scheduler.py`, plus its pre-existing `__pycache__`).
