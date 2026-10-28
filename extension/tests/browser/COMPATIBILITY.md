# Employer-form compatibility matrix

28 October 2026. Fixture checks are automated in Chromium. Public-page observations are read-only and never enter candidate data, upload files, authenticate or submit. A fixture pass is not a certification of every employer's current form.

| Provider / pattern | Automated local coverage | Current public observation | Live fill/submission acceptance |
| --- | --- | --- | --- |
| Greenhouse | Native contact/select/file/consent, validation, snapshots, next-vs-submit, confirmation, full navigation | [Anthropic form](https://job-boards.greenhouse.io/anthropic/jobs/5456619008): HTTP 200; 25 visible controls, 14 required; text/select/tel/file/textarea | Pending a deliberate user-supervised test |
| Lever | Grouped radio/checkbox; no changes to an existing choice | Wealthsimple public postings API returned no postings; alternative StackAdapt API returned 404 | Pending an available representative employer form |
| Ashby | Searchable input/button combobox, linked portal listbox, exact matching | [Linear form](https://jobs.ashbyhq.com/linear/d3bc1ced-3ce4-4086-a050-555055dbb1ff/application): HTTP 200; browser inspection unavailable; no bypass attempted | Pending |
| SmartRecruiters | Native multiselect and upload-format/rejection handling | [Bosch posting](https://jobs.smartrecruiters.com/BoschGroup/744000158275119): HTTP 200; no application controls on the unopened job-description step | Pending |
| Generic/other | Required/email/number/pattern/length/read-only, existing values, replaced controls, dynamic questions, corrupt/changed PDF, ARIA radio | No universal adapter or automatic confirmation claimed | User review/manual reporting |

The URLs were selected from public ATS posting APIs, not inferred requisition IDs. Observations and timestamps for successfully visited pages are in [live-form-observations.json](live-form-observations.json). URLs may expire or change.

The two unpacked-extension tests intercept employer/API network requests and use a synthetic candidate. They verify an actual isolated content script and service worker, native user submission on a fixture, confirmation sequencing, full-page navigation and explicit user-report status updates. They do not send an application to any employer.

An observed confirmation requires a supported ATS origin, a provider-specific marker with explicit received/submitted wording, no active collected form controls, and a linked attempt within 15 minutes. Generic thank-you text, completed autofill, opening Apply, Next/Continue and invalid native submissions are insufficient. Browser DOM observations are not independently verified employer receipts.

Unsupported custom widgets, localized/unrecognized final controls, closed shadow roots, cross-origin frame changes and AJAX-only submission flows may require manual action/reporting. Resume selection is checked in the browser; asynchronous provider upload acceptance remains unknown.
