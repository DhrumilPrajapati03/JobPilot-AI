# JobDots (Chrome extension)

## Side panel (JobDots)

Click the extension icon → **Open the JobDots panel**. The first time, allow it to read job
pages (Chrome asks once; you can revoke it in `chrome://extensions`).

- **Capture this job**: on a job posting, opens a case and Supervisor starts on it (company
  brief, people, tailored resume, then an email for your approval). Select the job
  description first if the page has a lot else on it.
- **Read this form's questions**: on the application form, the Answerer answers each
  question and says where the answer came from: *From your vault*, *Reused*, *Adapted*,
  *Drafted* or *Needs you* (legal agreements, consents, files, and anything it couldn't
  answer from what you've confirmed). Pay and visa answers are always marked to check.
- Edit anything, then **Fill the form**: every answer with a value goes into the form (in
  every frame), and each answer then says whether it was filled, needs checking (pay, visa,
  anything the form changed), or was already filled and left as is. New and edited answers
  also go to your answer bank (as new versions), so next time they are reused. Tick "Don't
  save this one" to keep an answer out of the bank.

The panel never ticks consents, never attaches files yet, and never submits: you check the
form and click Submit yourself. It never sees your token; the service worker
makes every call, and only the panel may call the side panel routes.

---

## Autofill (from JobPilot)

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
- After you submit yourself, click **Report that I submitted** to record a
  user-reported submission and move the application to *Applied*. Browser
  confirmation observations are stored separately and never mark it applied.

Sprint 5 freezes the application's tailored PDF per preparation session, checks
actual field values and file hashes, preserves existing answers, and flags
unresolved controls. Selected files and completed forms do not prove employer
acceptance. See the [compatibility matrix](tests/browser/COMPATIBILITY.md). Apply the development
migrations and reload the extension before using the new session workflow.

## Development checks

From this folder: `npm ci`, `npm test`, and `npm run test:browser`. Install the
pinned Playwright Chromium browser into the ignored project cache first:
`npx playwright install chromium` (the config sets `PLAYWRIGHT_BROWSERS_PATH`
to `../.tool-cache/playwright`).

## Hosting

The extension uses exact origins: localhost development URLs and the documented
example hosts `https://jobpilot-api.onrender.com` / `https://jobpilot-web.onrender.com`.
For your actual deployment, update both `policy.js` and `manifest.json` with the exact
API and web origins, then reload the extension. Broad Render wildcards are not accepted.

Answers captured by the extension default to sensitive. Custom answers can be reviewed
in Profile → Answers, where you can deliberately change “Keep private from AI prompts”.
