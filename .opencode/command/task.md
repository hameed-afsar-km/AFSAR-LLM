---
description: Capture a task/deadline to the Sticky Notes TODO note and Google Calendar.
---

Capture the following into the user's task system:

$ARGUMENTS

## What to do

1. Extract the task title (what must get done) and any due date/time mentioned
   (e.g. "tomorrow", "next Monday", "by 3pm", "this weekend"). Use today's date
   as the reference point when resolving relative dates.
2. Run the Sticky Notes capture (always):
   - `python "scripts/capture_task.py" "<task title>"`
   - Use the note `--note TODO` default; keep it unless told otherwise.
3. If the input included a date or time, also create a Google Calendar event
   (only if `scripts/token.json` *or* `scripts/service-account.json` exists; if
   neither does, tell the user the calendar isn't set up yet and stop — do not
   add to the calendar yet):
   - **Known time** (e.g. "3pm next Friday"): pass an ISO datetime and let the
     script default to a 1-hour duration:
     `node "scripts/gcal-add.mjs" --summary "<task title>" --start <ISO>`
   - **Date only** (no time): use an all-day event:
     `node "scripts/gcal-add.mjs" --summary "<task title>" --start YYYY-MM-DD --all-day`
4. Report back concisely: what was appended to the TODO note, and (if applicable)
   the calendar event link.

## Rules

- Quote every argument so spaces and special characters survive.
- Do not invent a time if the user only gave a date — use `--all-day`.
- If a task has no date at all, capture it to Sticky Notes only.
- Never fail the whole capture because the calendar isn't authorized yet; the
  sticky note always comes first.