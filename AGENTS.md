<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Task capture (automatic)

When the user mentions a task, deadline, "remind me", or an upcoming commitment
in conversation, capture it automatically:

1. Extract the task title and any due date/time (resolve relative dates like
   "tomorrow" against today's real date).
2. Append it to the Sticky Notes TODO note:
   `python "scripts/capture_task.py" "<task title>"`
3. If a date/time was given, add it to Google Calendar too:
   - timed: `node "scripts/gcal-add.mjs" --summary "<title>" --start <ISO>`
   - date-only: `node "scripts/gcal-add.mjs" --summary "<title>" --start YYYY-MM-DD --all-day`
   - Pass `--calendar <email>` if the calendar isn't auto-detected.
   - If neither `scripts/token.json` nor `scripts/service-account.json` exists,
     tell the user the calendar isn't set up yet; still do the sticky note.
   - `scripts/service-account.json` is auto-detected and needs no consent screen.
4. Confirm briefly: what was appended to the TODO note and the calendar link (if any).

Never block the sticky-note capture on calendar authorization.
