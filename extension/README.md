# JobPilot Autofill (Chrome extension)

Fills job application forms with your JobPilot data: name and contact details, your
tailored resume PDF, cover letter, saved screening answers, and AI drafts for open
questions (always flagged for review). **It never clicks Submit.** You check the form
and submit it yourself.

## Install (developer mode)

1. Open `chrome://extensions` and turn on **Developer mode** (top right).
2. Click **Load unpacked** and choose this `extension` folder.
3. Pin "JobPilot Autofill" from the puzzle-piece menu.

## Connect it to your account

1. Open JobPilot → **Settings** → **Chrome extension** → **Connect extension**.
2. That's it: the page hands the extension a personal token. (If the page can't reach
   the extension, it shows the token; paste it, and your API URL, in the extension's
   popup under *Connection settings*.)

You can revoke tokens in Settings at any time.

## Use it

- Open an application from your **Apply queue** (or the morning digest email).
- On Greenhouse, Lever, Ashby and SmartRecruiters forms, click **JobPilot · Fill this
  application** (bottom right). On any other site, click the extension icon → **Fill this page**.
- Green outlines: filled. Amber: needs you (legal agreements, questions with no saved
  answer, AI drafts to personalise). Click an item in the panel to jump to it.
- After typing missing answers, **Save my answers** stores them so they fill next time.
- After you click the site's Submit button, click **I submitted it** to move the
  application to *Applied* in JobPilot (with a follow-up reminder).

## Hosting

The extension can talk to `http://localhost:8000` and any `*.onrender.com` API. If you
host the API elsewhere, add its origin to `host_permissions` in `manifest.json`, and the
web app's origin to the `connect.js` content script matches.
