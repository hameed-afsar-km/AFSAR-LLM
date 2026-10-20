#!/usr/bin/env python3
"""Manage a "TODO" Sticky Note in the Windows Sticky Notes app.

The app stores notes in a SQLite DB (plum.sqlite) with an undocumented
format. We talk to it directly with the stdlib, then restart the app so the
change shows up.

Usage:
  python capture_task.py "<task text>"                 # append to the TODO note (create it if missing)
  python capture_task.py "<task text>" --note "TODO"   # use a different note title
  python capture_task.py --list                        # list all notes (plain text)
  python capture_task.py ... --dry-run --db <copy>     # inspect against a copy, no app restart
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid

DB_PATH = os.path.expandvars(
    r"%LOCALAPPDATA%\Packages\Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe"
    r"\LocalState\plum.sqlite"
)
PROC_NAME = "Microsoft.Notes.exe"
APP_URI = r"shell:AppsFolder\Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe!App"
THEMES = {"Yellow", "Blue", "Green", "Pink", "Purple", "Gray", "Charcoal"}

_BLOCK_RE = re.compile(r"^\\id=[0-9a-fA-F-]{36} ?(.*)$", re.DOTALL)


def parse_note_raw(raw):
    """Strip the internal \\id=<uuid> block markers, returning visible text."""
    if not raw:
        return ""
    out = []
    for line in raw.split("\n"):
        m = _BLOCK_RE.match(line)
        out.append(m.group(1) if m else line)
    return "\n".join(out)


def build_text(plain):
    """Wrap plain text back into the Sticky Notes internal block format."""
    return "\n".join(f"\\id={uuid.uuid4()} {line}" for line in plain.split("\n"))


def now_filetime():
    ticks = time.time_ns() // 100
    return ticks + 116_444_736_000_000_000


def first_line(text):
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def find_title_note(rows, title):
    """Return the row whose first visible line equals `title` (case-insensitive)."""
    matches = []
    for d in rows:
        if first_line(d["_text"]).upper() == title.upper():
            matches.append(d)
    if not matches:
        return None
    matches.sort(key=lambda d: (d.get("UpdatedAt") or 0), reverse=True)
    return matches[0]


def kill_app():
    try:
        subprocess.run(["taskkill", "/f", "/im", PROC_NAME],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.7)
    except OSError:
        pass


def launch_app():
    try:
        subprocess.Popen(["explorer.exe", APP_URI],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(description="Capture a task into the Windows Sticky Notes TODO note.")
    ap.add_argument("task", nargs="?", default=None, help="task text to append")
    ap.add_argument("--text", dest="text", default=None, help="alternative to positional task")
    ap.add_argument("--note", default="TODO", help="first-line title of the note to use (default: TODO)")
    ap.add_argument("--theme", default="Yellow", choices=sorted(THEMES))
    ap.add_argument("--db", default=DB_PATH, help="path to plum.sqlite (default: live app DB)")
    ap.add_argument("--list", action="store_true", help="just list existing notes")
    ap.add_argument("--dry-run", action="store_true", help="compute the plan without writing or touching the app")
    ap.add_argument("--no-restart", action="store_true", help="write but do not kill/relaunch the app")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    task = args.text if args.text is not None else args.task
    if not task and not args.list:
        ap.error("a task is required (positional or --text)")
    if args.dry_run and args.list:
        ap.error("--list and --dry-run are mutually exclusive")

    if not os.path.exists(args.db):
        print(json.dumps({"ok": False, "error": f"plum.sqlite not found at {args.db}",
                          "hint": "Is Windows Sticky Notes installed?"}))
        sys.exit(1)

    # Kill the app first so it cannot clobber our writes from memory / WAL.
    restart = not (args.dry_run or args.no_restart)
    if restart:
        kill_app()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = [dict(r) for r in cur.execute(
        'SELECT * FROM "Note" WHERE "DeletedAt" IS NULL').fetchall()]
    for d in rows:
        d["_text"] = parse_note_raw(d.get("Text"))

    if args.list:
        if not rows:
            print("(no active notes)")
        for d in rows:
            print(f"[{d['Theme']}] {d['Id']}")
            print(parse_note_raw(d.get("Text")))
            print("---")
        con.close()
        return

    title = args.note.strip() or "TODO"
    found = find_title_note(rows, title)

    if found:
        plain = parse_note_raw(found["Text"]).rstrip("\n")
        existing_lines = [l.strip().upper() for l in plain.split("\n")]
        if task.strip().upper() in existing_lines:
            con.close()
            print(json.dumps({"ok": True, "action": "duplicate",
                              "note_id": found["Id"], "message": "task already on the TODO note"}))
            return
        new_plain = (plain + "\n" + task) if plain else task
        note_id = found["Id"]
        action = "appended"
    else:
        parent_id = None
        if rows:
            parent_id = rows[0].get("ParentId")
        if not parent_id:
            parent_id = str(uuid.uuid4())
        note_id = str(uuid.uuid4())
        new_plain = title + "\n" + task
        action = "created"

    now = now_filetime()

    if args.dry_run:
        con.close()
        print(json.dumps({"ok": True, "dry_run": True,
                          "plan": action, "target_note_id": note_id,
                          "would_add": task,
                          "note_body": new_plain}))
        return

    if found:
        cur.execute('UPDATE "Note" SET "Text" = ?, "UpdatedAt" = ? WHERE "Id" = ?',
                    (build_text(new_plain), now, note_id))
    else:
        cur.execute(
            """
            INSERT INTO "Note" (
                "Id", "ParentId", "Text", "Theme",
                "IsOpen", "IsAlwaysOnTop",
                "IsFutureNote", "PendingInsightsScan",
                "IsRemoteDataInvalid", "RemoteSchemaVersion",
                "CreatedAt", "UpdatedAt", "DeletedAt", "Type"
            ) VALUES (?,?,?,?,?,?,0,0,0,0,?,?,NULL,NULL)
            """,
            (note_id, parent_id, build_text(new_plain), args.theme,
             1, 0, now, now),
        )
    con.commit()
    con.close()

    launch_app()

    print(json.dumps({"ok": True, "action": action, "note_id": note_id,
                      "added": task, "dry_run": False}))


if __name__ == "__main__":
    main()
