#!/usr/bin/env node
// Add an event to Google Calendar.
//
// Auth: prefers a service account (scripts/service-account.json). If that
// file is missing it falls back to OAuth (credentials.json + token.json from
// gcal-setup.mjs). A service account must be shared the target calendar in
// Google Calendar settings ("Share with specific people", Make changes to
// events). The calendar is auto-discovered on first use.
//
// Usage:
//   node gcal-add.mjs --summary "Ship v2" --start 2026-09-10T15:00:00   (timed, 1h)
//   node gcal-add.mjs --summary "Pay rent" --start 2026-09-01 --all-day
//   node gcal-add.mjs --summary "CTO review" --start 2026-09-10T15:00:00 --end 2026-09-10T16:30:00 --description "..."
//   node gcal-add.mjs --summary "..." --start ... --calendar you@gmail.com
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { google } from "googleapis";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CREDENTIALS_PATH =
  process.env.GOOGLE_CREDENTIALS_PATH || path.join(__dirname, "credentials.json");
const TOKEN_PATH =
  process.env.GOOGLE_TOKEN_PATH || path.join(__dirname, "token.json");
const SERVICE_ACCOUNT_PATH =
  process.env.GOOGLE_SERVICE_ACCOUNT_PATH || path.join(__dirname, "service-account.json");
const CALENDAR_ID_FILE =
  process.env.GOOGLE_CALENDAR_ID_FILE || path.join(__dirname, "calendar-id.txt");
const OAUTH_SCOPES = ["https://www.googleapis.com/auth/calendar.events"];
// Service accounts need metadata scope too so we can discover shared calendars.
const SA_SCOPES = ["https://www.googleapis.com/auth/calendar"];
const SYSTEM_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;

function argAfter(name, fallback = null) {
  const i = process.argv.indexOf(name);
  if (i === -1) return fallback;
  const v = process.argv[i + 1];
  if (v === undefined) return fallback;
  return v;
}

function helper({ summary, start, end, allDay, description, timezone }) {
  const event = { summary, description: description || undefined };

  if (allDay || /^\d{4}-\d{2}-\d{2}$/.test(start)) {
    const day = start.slice(0, 10);
    event.start = { date: day };
    event.end = { date: end ? end.slice(0, 10) : addDays(day, 1) };
  } else {
    if (Number.isNaN(Date.parse(start))) {
      console.error("ERROR: --start must be YYYY-MM-DD or an ISO datetime, got: " + start);
      process.exit(2);
    }
    const tz = timezone || SYSTEM_TZ;
    const startISO = new Date(start).toISOString();
    const endISO = new Date(end || new Date(start).getTime() + 60 * 60 * 1000).toISOString();
    event.start = { dateTime: startISO, timeZone: tz };
    event.end = { dateTime: endISO, timeZone: tz };
    event.reminders = { useDefault: false, overrides: [{ method: "popup", minutes: 60 }] };
  }
  return event;
}

function addDays(dateStr, n) {
  const d = new Date(dateStr.slice(0, 10) + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

async function main() {
  const summary = argAfter("--summary") || argAfter("-t");
  const start = argAfter("--start");
  const end = argAfter("--end");
  const allDay = process.argv.includes("--all-day");
  const description = argAfter("--description");
  const timezone = argAfter("--timezone");
  const calendarArg = argAfter("--calendar");

  if (!summary || !start) {
    console.error(
      "ERROR: --summary and --start are required.\n" +
      "Examples:\n" +
      '  node gcal-add.mjs --summary "Ship v2" --start 2026-09-10T15:00:00\n' +
      '  node gcal-add.mjs --summary "Pay rent" --start 2026-09-01 --all-day'
    );
    process.exit(2);
  }

  // Pick an auth method: service account first, then OAuth.
  let auth;
  let calendarId = calendarArg;
  if (fs.existsSync(SERVICE_ACCOUNT_PATH)) {
    const key = JSON.parse(fs.readFileSync(SERVICE_ACCOUNT_PATH, "utf8"));
    if (!key.client_email || !key.private_key) {
      console.error("ERROR: " + SERVICE_ACCOUNT_PATH + " is missing client_email/private_key.");
      process.exit(1);
    }
    auth = new google.auth.JWT({
      email: key.client_email,
      key: key.private_key,
      scopes: SA_SCOPES,
    });
    if (!calendarId && fs.existsSync(CALENDAR_ID_FILE)) {
      calendarId = fs.readFileSync(CALENDAR_ID_FILE, "utf8").trim();
    }
    if (!calendarId) {
      const cal = google.calendar({ version: "v3", auth });
      try {
        const list = await cal.calendarList.list();
        if (list.data.items && list.data.items.length) {
          calendarId = list.data.items[0].id;
        }
      } catch (e) {
        console.error("ERROR listing calendars: " + (e.message || e) + "\nIs your calendar shared with " + key.client_email + "?");
        process.exit(1);
      }
      if (!calendarId) {
        console.error("ERROR: no shared calendars found for " + key.client_email + ". Share your calendar in Google Calendar settings.");
        process.exit(1);
      }
    }
  } else if (fs.existsSync(CREDENTIALS_PATH) && fs.existsSync(TOKEN_PATH)) {
    if (!calendarId) calendarId = "primary";
    const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, "utf8"));
    const { client_id, client_secret, redirect_uris } = creds.installed || creds.web || {};
    const redirectUri = (redirect_uris || []).find((u) => u !== "urn:ietf:wg:oauth:2.0:oob") || "http://localhost";
    auth = new google.auth.OAuth2(client_id, client_secret, redirectUri);
    auth.setCredentials(JSON.parse(fs.readFileSync(TOKEN_PATH, "utf8")));
  } else {
    console.error(
      "ERROR: no calendar auth configured.\n" +
      "Either drop a service-account JSON key as scripts/service-account.json,\n" +
      "or use OAuth: node scripts/gcal-setup.mjs (creates credentials.json + token.json)."
    );
    process.exit(1);
  }

  const event = helper({ summary, start, end, allDay, description, timezone });
  const calendar = google.calendar({ version: "v3", auth });

  try {
    const res = await calendar.events.insert({ calendarId, resource: event });
    console.log(JSON.stringify({
      ok: true,
      calendarId,
      eventId: res.data.id,
      htmlLink: res.data.htmlLink,
      summary,
      start: event.start,
      end: event.end,
    }));
  } catch (err) {
    console.error("ERROR creating event: " + (err.message || err));
    process.exit(1);
  }
}

main();