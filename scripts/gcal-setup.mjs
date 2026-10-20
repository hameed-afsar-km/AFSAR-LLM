#!/usr/bin/env node
// One-time OAuth setup for Google Calendar.
// Shows a URL, you approve in the browser, paste the code back, and the
// refresh token is saved to token.json for reuse by gcal-add.mjs.
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import readline from "node:readline";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { google } from "googleapis";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CREDENTIALS_PATH =
  process.env.GOOGLE_CREDENTIALS_PATH || path.join(__dirname, "credentials.json");
const TOKEN_PATH =
  process.env.GOOGLE_TOKEN_PATH || path.join(__dirname, "token.json");
const SCOPES = ["https://www.googleapis.com/auth/calendar.events"];

if (!fs.existsSync(CREDENTIALS_PATH)) {
  console.error(
    "ERROR: " + CREDENTIALS_PATH + " not found.\n" +
    "See the Google Calendar setup steps (create a project, enable the Calendar\n" +
    "API, download OAuth client credentials as JSON) and save the file as credentials.json."
  );
  process.exit(1);
}

const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, "utf8"));
const { client_id, client_secret, redirect_uris } = creds.installed || creds.web || {};
if (!client_id || !client_secret) {
  console.error("ERROR: credentials.json must contain client_id and client_secret.");
  process.exit(1);
}

const redirectUri = (redirect_uris || []).find((u) => u !== "urn:ietf:wg:oauth:2.0:oob") || "http://localhost";
const oauth2Client = new google.auth.OAuth2(client_id, client_secret, redirectUri);

const authUrl = oauth2Client.generateAuthUrl({
  access_type: "offline",
  prompt: "consent",
  scope: SCOPES,
});

console.log("Open this URL in your browser and grant access:\n\n  " + authUrl + "\n");

// Auto-open the browser on this machine so the user doesn't have to copy/paste.
try {
  if (process.platform === "win32") {
    spawn("cmd", ["/c", "start", "", authUrl], { stdio: "ignore" });
  } else if (process.platform === "darwin") {
    spawn("open", [authUrl], { stdio: "ignore" });
  } else {
    spawn("xdg-open", [authUrl], { stdio: "ignore" });
  }
} catch {
  // browser auto-open is best-effort; the printed URL still works
}

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
rl.question("Paste the authorization code here: ", async (code) => {
  rl.close();
  try {
    const { tokens } = await oauth2Client.getToken(code.trim());
    fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens));
    console.log("\nSaved credentials to " + TOKEN_PATH + "\nYou can now add events.");
  } catch (err) {
    console.error("\nFailed to exchange code: " + err.message);
    process.exit(1);
  }
});