# Google and GitHub sign-in

Updated 13 November 2026. App support is implemented alongside email magic links.
The owner completed Google/GitHub provider setup. Read-only verification confirms
both providers are enabled with client IDs and secrets present, and JobPilotAI Auth
is healthy. Public Auth settings advertise both providers; each authorize endpoint
returns an HTTPS redirect to its expected provider with the exact Supabase callback.
The local `/login` return URLs below are configured. The site URL remains
`http://localhost:5173`, and email login remains enabled. This verification changed
no hosted configuration, database schema, application data, environment files or
deployment. On 13 November the owner confirmed the local login flow works after
testing Google/GitHub. This is owner-reported browser acceptance; distinct-account
isolation, identity linking and production-domain acceptance remain separate checks.

## 1. Callback URLs

Provider callback for this hosted Supabase project, including local app testing:

```text
https://vgpkzekcfnogvvykfzoo.supabase.co/auth/v1/callback
```

In [JobPilotAI Auth URL Configuration](https://supabase.com/dashboard/project/vgpkzekcfnogvvykfzoo/auth/url-configuration),
the following local return URLs are now configured:

```text
http://localhost:5173/login
http://127.0.0.1:5173/login
```

The existing `http://localhost:5173` root entry is preserved for old email links.
Add the real `https://<your-production-domain>/login` only when deploying; do not
save a placeholder. Match the port actually running locally. The
provider callback above and the app return URLs serve different steps of sign-in.
Local app testing uses hosted JobPilotAI; localhost:54321 is only for a separate
locally running Supabase stack, not the current configuration.

## 2. Google

1. In [Google Cloud credentials](https://console.cloud.google.com/apis/credentials), configure an OAuth consent app and create a **Web application**
   OAuth client. Add intended test users while the consent app is in testing mode.
2. Add the current frontend origin, such as `http://localhost:5173`, to authorized
   JavaScript origins. Add the Supabase callback above to authorized redirect URIs.
3. In [JobPilotAI Sign In / Providers](https://supabase.com/dashboard/project/vgpkzekcfnogvvykfzoo/auth/providers),
   open Google, enter the client ID/secret, enable it and save. Keep nonce checking enabled.
4. For production, configure the real HTTPS origin and complete Google's consent
   publishing requirements before inviting users beyond the test audience.

The app requests only `openid email profile`. Google sign-in does not connect Gmail.
See [Supabase's Google setup guide](https://supabase.com/docs/guides/auth/social-sign-in/auth-google).

## 3. GitHub

1. Open [GitHub's New OAuth App form](https://github.com/settings/applications/new).
   Use `JobPilot AI` as the name and `http://localhost:5173` as the homepage.
2. Set the homepage to the app URL and the authorization callback to the Supabase
   callback above. Leave Device Flow off for this browser flow.
3. Generate a client secret. Enter the client ID/secret in JobPilotAI's GitHub
   provider configuration, enable it and save.

The app requests `user:email` for sign-in; it requests no repository/write access.
See [Supabase's GitHub setup guide](https://supabase.com/docs/guides/auth/social-sign-in/auth-github).

**Keep both client secrets in Supabase provider settings.** No new frontend/backend
environment keys are needed. Do not put provider secrets in `VITE_*`, Git or chat.
The separately authorized Composio connection can now manage Supabase Auth.
The available tools cannot register Google/GitHub OAuth apps; their creation and
entering the resulting credentials in Supabase still require the project owner.
Provider enablement and credential presence were verified on 13 November 2026.
Do not enable a provider with empty credentials.

## 4. Test locally

1. Run the existing backend/frontend and open `/login`.
2. Continue with Google, approve consent, and confirm arrival at `/workspace`.
   Sign out, then repeat with GitHub and with an email magic link.
3. Cancel consent or use browser Back: sign-in options should remain recoverable.
   Try an expired/reused link and an incognito callback without its original verifier.
4. Test two accounts. Matching verified email addresses can be linked by Supabase;
   different emails can create separate users. Confirm the returned account and
   existing applications before editing. No records are manually merged by this code.
5. Recheck exact HTTPS redirects after deployment. No database migration is needed.

Account linking follows [Supabase's identity linking behavior](https://supabase.com/docs/guides/auth/auth-identity-linking).
Use a verified email on GitHub and review the email returned by the provider.

New sign-ins use PKCE, with SDK-owned code exchange and a fixed same-origin
`/login` return. Start and finish in the same browser. Previously issued implicit
email links are accepted through SDK `setSession`; future requests still use PKCE.
Callback secrets/error descriptions are removed from the URL and errors use safe
copy. Disabled providers show an in-app email fallback instead of navigating to
an off-site configuration error.

## Verification

**Earlier code verification: 35 frontend checks, the frontend build and all 14 app browser workflows passed.**
The five social-auth browser workflows passed again after the final startup guard.
Frontend checks and browser fixtures exercise both providers, real SDK PKCE
challenge/verifier exchange, Back/cancellation, missing verifier, disabled-provider
fallback, and old email link → sign-out → new PKCE login. These use fictional
provider/Auth boundaries, not real Google/GitHub consent or actual account linking.
These code checks were completed on 8 November; they were not rerun for the
read-only provider configuration check on 13 November.

Live configuration verification on 13 November 2026:

| Check | Result |
| --- | --- |
| JobPilotAI Auth health | `ACTIVE_HEALTHY` |
| Google/GitHub configuration | Both enabled; client IDs and secrets present; Google ID has the expected web-client suffix |
| Email requirement | Users without an email are disallowed for both providers |
| Google nonce checks | Enabled (`skip_nonce_check=false`) |
| Public `/auth/v1/settings` | HTTP 200; Google, GitHub and email advertised as available |
| Google `/auth/v1/authorize` | HTTP 302 to `accounts.google.com`; callback matches JobPilotAI |
| GitHub `/auth/v1/authorize` | HTTP 302 to `github.com`; callback matches JobPilotAI |
| App return URLs | Exact localhost/127.0.0.1 port 5173 `/login` entries present |

The redirect probes used PKCE and the frontend's public key; they did not follow
provider consent, authenticate a person or inspect account records. After these
probes, the owner reported successful local Google/GitHub login on 13 November.
No browser session, account email or provider tokens were shared with the assistant.
Audience coverage beyond the tested accounts, actual identity linking, separate-user
isolation and production HTTPS redirects remain unverified by this acceptance.
No secrets or raw OAuth state/redirect URLs were printed or written into this record.

The independent UI checker found three lifecycle/status issues; all were fixed
and source-rechecked. Its theme calibration used an isolated temporary checkout,
which was removed. Review scope expanded to shared auth/SDK callbacks (roughly 59
file reads across author/checkers, above the small UI budget); only the login page
UI changed. Visual accessibility and real provider consent are not certified.
