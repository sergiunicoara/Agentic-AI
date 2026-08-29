# Trajectory

## What I read

- `report.md`: Users report that calendar reminders fire "way too late" —
  effectively right at event start instead of ahead of time. Default lead
  time in settings is 15 minutes, but the notification appears only "a few
  seconds" before the event. Custom lead times on individual events have
  the same problem.

- `buggy/config.py`:
  ```
  DEFAULT_REMINDER_LEAD_MINUTES = 15
  ```
  A single constant, named in minutes, set to 15.

- `buggy/scheduler.py`:
  ```python
  from config import DEFAULT_REMINDER_LEAD_MINUTES


  def reminder_trigger_time(event_time_epoch, lead_minutes=None):
      """Return the epoch timestamp at which a reminder should fire."""
      lead = lead_minutes if lead_minutes is not None else DEFAULT_REMINDER_LEAD_MINUTES
      return event_time_epoch - lead
  ```

## What I concluded

`event_time_epoch` is an epoch timestamp, whose units are seconds. `lead`
(whether the default `DEFAULT_REMINDER_LEAD_MINUTES` or a caller-supplied
`lead_minutes`) is explicitly named/documented in minutes. The function
subtracts `lead` directly from `event_time_epoch` without converting minutes
to seconds (`lead * 60`). So a "15 minute" lead time only pushes the trigger
time back by 15 seconds, not 900 seconds — exactly matching the report's
description of reminders firing "only a few seconds before the event"
instead of 15 minutes before, for both the default and any custom
`lead_minutes` value.

## Test written

`candidate_test.py` (in the working directory, sibling of `report.md` and
`buggy/`) contains two tests:

1. `test_default_lead_time_is_minutes_before_event` — calls
   `reminder_trigger_time(event_time_epoch)` with no explicit lead, and
   asserts the result equals `event_time_epoch - DEFAULT_REMINDER_LEAD_MINUTES * 60`
   (i.e. 900 seconds before the event, using the module's own default
   constant).
2. `test_custom_lead_time_is_minutes_before_event` — calls
   `reminder_trigger_time(event_time_epoch, lead_minutes=10)` and asserts
   the result equals `event_time_epoch - 10 * 60` (600 seconds before the
   event).

Both encode "lead_minutes means minutes, so convert to seconds before
subtracting from an epoch-seconds timestamp" — the behavior the report says
is missing.

## What happened when I ran the test

Per the task instructions, I copied `candidate_test.py` into `buggy/`,
ran `python -m pytest candidate_test.py -v` from inside `buggy/`, and then
deleted the copy (and the `__pycache__` directory pytest created) so that
`buggy/` was restored to its original two files.

Observed output: both tests **FAILED**.

- `test_default_lead_time_is_minutes_before_event`: `assert 999985 == 999100`
  (event_time_epoch=1,000,000; buggy code returned `1_000_000 - 15 = 999985`
  instead of the expected `1_000_000 - 15*60 = 999100`).
- `test_custom_lead_time_is_minutes_before_event`: `assert 1999990 == 1999400`
  (event_time_epoch=2,000,000, lead_minutes=10; buggy code returned
  `2_000_000 - 10 = 1999990` instead of the expected `2_000_000 - 10*60 = 1999400`).

This confirms the reported bug: reminders trigger only `lead_minutes`
*seconds* before the event instead of `lead_minutes` *minutes* before, for
both the default and a custom lead time.

## Files read / commands run:

- Read `report.md`
- Read `buggy/config.py`
- Read `buggy/scheduler.py`
- Wrote `candidate_test.py` in the working directory
- `cp candidate_test.py buggy/candidate_test.py`
- `cd buggy && python -m pytest candidate_test.py -v` (both tests FAILED, output captured above)
- `rm buggy/candidate_test.py`
- `rm -rf buggy/__pycache__` (cleanup of pytest-generated cache so `buggy/` matches its original state)
- `ls -la buggy` (confirmed only `config.py` and `scheduler.py` remain, unmodified)
