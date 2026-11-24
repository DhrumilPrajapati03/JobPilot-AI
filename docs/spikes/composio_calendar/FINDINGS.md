# Composio Google Calendar Direct Execution Spike

## Scope and safety

- Isolated spike only; no JobPilot or JobDots application source is modified.
- Composio user ID: `dhrumil-dev`.
- Google OAuth uses a custom client and requests only `https://www.googleapis.com/auth/calendar.events`.
- Test event uses dummy content, is scheduled for 25 November 2026 at 10:00–10:30 Asia/Kolkata, and should be deleted immediately after creation.
- Never put API keys, OAuth client secrets, access tokens, or refresh tokens in this file. Local runtime state and `.env` are ignored by Git.

## SDK and setup

- Python package: `composio==0.34.0` (selected from the official PyPI release history on 24 November 2026).
- Isolated environment: `spike/composio_calendar/.venv`.
- Local inputs: `COMPOSIO_API_KEY`, `GOOGLE_OAUTH_CLIENT_ID`, and `GOOGLE_OAUTH_CLIENT_SECRET` from process environment or ignored local `.env`.
- At initial setup, no credentials were available to the assistant process; the user later supplied them via the ignored local `.env`.
- SDK install completed in the isolated virtual environment. Python compilation and import checks passed.

## Official documentation used

- [Composio Python SDK](https://docs.composio.dev/reference/sdk-reference/python)
- [Programmatic custom auth configs](https://docs.composio.dev/docs/authentication/programmatic-auth-configs)
- [Controlling OAuth scopes](https://docs.composio.dev/docs/authentication/controlling-scopes)
- [Google Calendar toolkit: custom OAuth, scopes, and tool catalog](https://docs.composio.dev/toolkits/googlecalendar)
- [Direct tool execution](https://docs.composio.dev/docs/tools-direct/executing-tools)
- [Toolkit versioning](https://docs.composio.dev/docs/tools-direct/toolkit-versioning)
- [Connected account links and status](https://docs.composio.dev/docs/auth-configuration/connected-accounts)

## Status

**Stopped after the create attempt:** the fresh connection reached `ACTIVE` with requested and granted scope exactly `https://www.googleapis.com/auth/calendar.events`. Direct execution of `GOOGLECALENDAR_CREATE_EVENT` returned HTTP 403 `ACCESS_TOKEN_SCOPE_INSUFFICIENT` during Google's `Calendars.Get` preflight, before an event was created. Per instructions, the delete tool was not called and no scope was broadened.

## Run sequence

From this folder, copy `.env.example` to `.env` and fill the three values locally. Then run these commands in order:

```powershell
.\.venv\Scripts\python.exe .\composio_calendar_spike.py discover
.\.venv\Scripts\python.exe .\composio_calendar_spike.py create-link
# Approve the printed Connect Link in your browser after checking the printed scope.
.\.venv\Scripts\python.exe .\composio_calendar_spike.py wait
.\.venv\Scripts\python.exe .\composio_calendar_spike.py execute
```

The OAuth client's authorized redirect URI must exactly match:
`https://backend.composio.dev/api/v1/auth-apps/add`.

The official Google Calendar toolkit instructions use the Composio callback `https://backend.composio.dev/api/v1/auth-apps/add`; the newer generic programmatic-auth page also documents the v3 callback. The spike will use the Google Calendar-specific callback and put the same exact URI in the custom config. This is a supported legacy endpoint according to Composio's programmatic auth documentation.

The script reads the created config back and refuses to create a Connect Link unless its effective configured scope is exactly the single `calendar.events` URL above. It will stop and record the exact sanitized API error if event creation or deletion fails for lack of scope; it will not widen OAuth permissions.

## Verified calls

Completed successfully:

```python
composio.auth_configs.create(
    toolkit="googlecalendar",
    options={
        "type": "use_custom_auth",
        "auth_scheme": "OAUTH2",
        "name": "JobDots Calendar Spike (events only)",
        "credentials": {
            "client_id": "[REDACTED]",
            "client_secret": "[REDACTED]",
            "scopes": "https://www.googleapis.com/auth/calendar.events",
            "oauth_redirect_uri": "https://backend.composio.dev/api/v1/auth-apps/add",
        },
    },
)
composio.auth_configs.get(auth_config_id)  # read-back returned exactly the one requested scope
composio.connected_accounts.link(user_id="dhrumil-dev", auth_config_id=auth_config_id)
composio.toolkits.get(slug="googlecalendar")
composio.tools.get_raw_composio_tools(toolkits=["googlecalendar"], search="event", limit=100)
composio.tools.get_raw_composio_tool_by_slug("GOOGLECALENDAR_CREATE_EVENT")
composio.tools.get_raw_composio_tool_by_slug("GOOGLECALENDAR_DELETE_EVENT")
composio.connected_accounts.list(user_ids=["dhrumil-dev"])
```

The auth config, read-back verification, Connect Link generation, toolkit/version discovery, tool search, and schema retrieval succeeded. The connection reached `ACTIVE`. One `tools.execute()` call was made for `GOOGLECALENDAR_CREATE_EVENT` with version `20261116_00`; it failed with the narrow-scope error recorded below before event creation. No delete call was made.

## Tool slugs, schemas, and pinned toolkit version

SDK discovery confirmed the following slugs from the toolkit search and retrieved their schemas:

- Create: `GOOGLECALENDAR_CREATE_EVENT`
- Delete: `GOOGLECALENDAR_DELETE_EVENT`
- Pinned version: `20261116_00` (present in the SDK's `available_versions` list)

The create schema requires a title (`summary`) and `start_datetime` for a timed event; `end_datetime` is supported. It also supports `calendar_id` (default `primary`), `send_updates`, `create_meeting_room`, `visibility`, and `transparency`. The spike will use a private, transparent event, disable Meet creation, and set `send_updates` to `none`. It omits attendees and description.

Scope metadata detail: the create tool declares two `all_of` scope groups. `calendar.events` satisfies the first group's alternatives. The second group lists `calendar`, `calendar.app.created`, `calendar.calendars`, `calendar.calendars.readonly`, or `calendar.readonly`, and does not list `calendar.events`. The delete tool's scope group does include `calendar.events`. The spike will not request additional scopes; if create fails for scope reasons, it records the exact sanitized error and stops as instructed.

## Latency and execution results

Create call latency: `1424.91 ms`. No event was created; delete was not attempted.

## Errors and fixes

The first `pip install` attempt was blocked by the local sandbox (`WinError 10013`, outbound socket denied). The same pinned install was retried with approved network access; `composio==0.34.0` and dependencies installed inside this spike's `.venv`, and the pip cache was kept under this spike directory. No package was installed into the main project's Python environment.

An initial local payload dry-run failed with `ZoneInfoNotFoundError: 'No time zone found with key Asia/Kolkata'` because this Windows Python installation has no system IANA timezone database and `tzdata` was not installed. The spike now uses the fixed UTC+05:30 offset for `Asia/Kolkata` and sends the IANA timezone name to Google, avoiding an additional dependency.

Auth-config creation initially returned HTTP 401 `Invalid API key` twice. The user corrected the local project key; creation then succeeded. The first SDK diagnostic included a masked key fragment; it was not repeated and has been scrubbed from this file. The script now suppresses detailed exceptions in terminal output and redacts Composio key patterns in findings.

After the user reported completing OAuth, `connected_accounts.list(user_ids=["dhrumil-dev"])` returned Google Calendar status `INITIATED`; no status reason was provided. `wait_for_connection()` ended with `ComposioSDKTimeoutError`. No create or delete call was attempted while the account was pending. Runtime errors are appended here with credentials redacted.

On retry, the filtered account list returned `EXPIRED`. The existing auth config read-back still contained exactly `https://www.googleapis.com/auth/calendar.events`; a fresh Connect Link was issued without creating another auth config.

The authorized direct create attempt returned HTTP 403 from Google during `calendar.v3.Calendars.Get`: `Request had insufficient authentication scopes.` Google reported reason `ACCESS_TOKEN_SCOPE_INSUFFICIENT`. The returned Composio response included `403 Client Error: Forbidden for url: https://www.googleapis.com/calendar/v3/calendars/primary`. No event was created. Execution stopped immediately; delete was not called and no broader scope was requested.

An initial local validation command used virtual-environment-relative paths while its working directory was the repository root, so PowerShell could not find `.venv\Scripts\python.exe`. Re-running the compile command from `spike/composio_calendar/` succeeded; this was a command working-directory mistake, not an SDK or code error.

## Dashboard log

User to paste the Composio dashboard log details for the create and delete calls here after execution. Only dummy event data should be present.

### Runtime error: custom auth config / Connect Link

```text
APIConnectionError: Connection error.
```

### Runtime error: custom auth config / Connect Link

```text
AuthenticationError: 401 Invalid API key: [REDACTED]
```

### Runtime error: custom auth config / Connect Link

```text
AuthenticationError: 401 Invalid API key: [REDACTED]
```

### Custom auth config and Connect Link

Created auth config `ac_62fM5kvaTdMP` using the custom Google OAuth client. Server read-back verified the exact configured scope `https://www.googleapis.com/auth/calendar.events` before link creation. Connect Link created for user `dhrumil-dev`. The link itself is intentionally not recorded in this file.

### Runtime error: waiting for ACTIVE connected account

```text
ComposioSDKTimeoutError: Timeout while waiting for connection ca_hxMIqSLFtVWl to be active
```

### SDK discovery

Toolkit search and schema lookup completed.

Available versions: `["20261116_00", "20261111_00", "20261110_00", "20261103_00", "20261101_00", "20261010_00", "20261009_00", "20261007_00", "20261006_00", "20261001_00", "20260915_00", "20260902_00", "20260826_00", "20260821_00", "20260812_00", "20260811_00", "20260721_00", "20260623_00", "20260615_00", "20260429_00", "20260427_00", "20260424_00", "20260422_01", "20260422_00", "20260420_00", "20260417_00", "20260415_00", "20260414_00", "20260413_01", "20260413_00", "20260410_00", "20260408_00", "20260407_00", "20260406_00", "20260403_00", "20260331_00", "20260330_00", "20260324_00", "20260323_00", "20260316_00", "20260312_00", "20260309_00", "20260307_00", "20260228_00", "20260227_00", "20260225_03", "20260225_02", "20260225_01", "20260225_00", "20260223_00"]`

Pinned version: `20261116_00`

Create slug: `GOOGLECALENDAR_CREATE_EVENT`

Delete slug: `GOOGLECALENDAR_DELETE_EVENT`

Full schemas are printed by the discovery command and retained locally in ignored `.spike_state.json`.

### Fresh Connect Link

Reused auth config `ac_62fM5kvaTdMP` after read-back confirmed exactly `https://www.googleapis.com/auth/calendar.events`. Generated a fresh link for `dhrumil-dev`; URL omitted from this file.

### Connected account

Account status reached `ACTIVE` for user `dhrumil-dev`.

### Create-event execution

Latency: `1424.91 ms`.

Create arguments (dummy only):
```json
{
  "summary": "JobDots spike test",
  "timezone": "Asia/Kolkata",
  "visibility": "private",
  "calendar_id": "primary",
  "end_datetime": "2026-11-25T10:30:00+05:30",
  "send_updates": "none",
  "transparency": "transparent",
  "start_datetime": "2026-11-25T10:00:00+05:30",
  "create_meeting_room": false
}
```

Sanitized response:
```json
{
  "data": {
    "http_error": "403 Client Error: Forbidden for url: https://www.googleapis.com/calendar/v3/calendars/primary",
    "message": "{\n  \"error\": {\n    \"code\": 403,\n    \"message\": \"Request had insufficient authentication scopes.\",\n    \"errors\": [\n      {\n        \"message\": \"Insufficient Permission\",\n        \"domain\": \"global\",\n        \"reason\": \"insufficientPermissions\"\n      }\n    ],\n    \"status\": \"PERMISSION_DENIED\",\n    \"details\": [\n      {\n        \"@type\": \"type.googleapis.com/google.rpc.ErrorInfo\",\n        \"reason\": \"ACCESS_TOKEN_SCOPE_INSUFFICIENT\",\n        \"domain\": \"googleapis.com\",\n        \"metadata\": {\n          \"method\": \"calendar.v3.Calendars.Get\",\n          \"service\": \"calendar-json.googleapis.com\"\n        }\n      }\n    ]\n  }\n}\n",
    "status_code": 403
  },
  "error": "{\n  \"error\": {\n    \"code\": 403,\n    \"message\": \"Request had insufficient authentication scopes.\",\n    \"errors\": [\n      {\n        \"message\": \"Insufficient Permission\",\n        \"domain\": \"global\",\n        \"reason\": \"insufficientPermissions\"\n      }\n    ],\n    \"status\": \"PERMISSION_DENIED\",\n    \"details\": [\n      {\n        \"@type\": \"type.googleapis.com/google.rpc.ErrorInfo\",\n        \"reason\": \"ACCESS_TOKEN_SCOPE_INSUFFICIENT\",\n        \"domain\": \"googleapis.com\",\n        \"metadata\": {\n          \"method\": \"calendar.v3.Calendars.Get\",\n          \"service\": \"calendar-json.googleapis.com\"\n        }\n      }\n    ]\n  }\n}\n",
  "successful": false
}
```

## Final scope finding

The custom auth config and ACTIVE connected account both requested/granted only `https://www.googleapis.com/auth/calendar.events`. The direct `GOOGLECALENDAR_CREATE_EVENT` call (version `20261116_00`) failed after `1424.91 ms` with HTTP 403 `ACCESS_TOKEN_SCOPE_INSUFFICIENT` during Google's `calendar.v3.Calendars.Get` preflight on `primary`; the exact sanitized response is recorded above. No event was created. The delete tool was not called. Per the user's instruction, the spike stopped without requesting or granting broader scopes.

Observed behavior: Composio's tool schema includes a second create-event scope requirement that does not list `calendar.events`, and Google's error confirmed this call path needs a broader calendar read permission before insertion. The auth config read-back itself matched the narrow scope exactly. No scope was broadened.

Dashboard log note: only a failed create attempt exists. There was no event and no delete call/log.

### Runtime error: create event

```text
RuntimeError: {
  "error": {
    "code": 403,
    "message": "Request had insufficient authentication scopes.",
    "errors": [
      {
        "message": "Insufficient Permission",
        "domain": "global",
        "reason": "insufficientPermissions"
      }
    ],
    "status": "PERMISSION_DENIED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT",
        "domain": "googleapis.com",
        "metadata": {
          "method": "calendar.v3.Calendars.Get",
          "service": "calendar-json.googleapis.com"
        }
      }
    ]
  }
}

```

Sanitized response:
```json
{
  "data": {
    "http_error": "403 Client Error: Forbidden for url: https://www.googleapis.com/calendar/v3/calendars/primary",
    "message": "{\n  \"error\": {\n    \"code\": 403,\n    \"message\": \"Request had insufficient authentication scopes.\",\n    \"errors\": [\n      {\n        \"message\": \"Insufficient Permission\",\n        \"domain\": \"global\",\n        \"reason\": \"insufficientPermissions\"\n      }\n    ],\n    \"status\": \"PERMISSION_DENIED\",\n    \"details\": [\n      {\n        \"@type\": \"type.googleapis.com/google.rpc.ErrorInfo\",\n        \"reason\": \"ACCESS_TOKEN_SCOPE_INSUFFICIENT\",\n        \"domain\": \"googleapis.com\",\n        \"metadata\": {\n          \"method\": \"calendar.v3.Calendars.Get\",\n          \"service\": \"calendar-json.googleapis.com\"\n        }\n      }\n    ]\n  }\n}\n",
    "status_code": 403
  },
  "error": "{\n  \"error\": {\n    \"code\": 403,\n    \"message\": \"Request had insufficient authentication scopes.\",\n    \"errors\": [\n      {\n        \"message\": \"Insufficient Permission\",\n        \"domain\": \"global\",\n        \"reason\": \"insufficientPermissions\"\n      }\n    ],\n    \"status\": \"PERMISSION_DENIED\",\n    \"details\": [\n      {\n        \"@type\": \"type.googleapis.com/google.rpc.ErrorInfo\",\n        \"reason\": \"ACCESS_TOKEN_SCOPE_INSUFFICIENT\",\n        \"domain\": \"googleapis.com\",\n        \"metadata\": {\n          \"method\": \"calendar.v3.Calendars.Get\",\n          \"service\": \"calendar-json.googleapis.com\"\n        }\n      }\n    ]\n  }\n}\n",
  "successful": false
}
```
