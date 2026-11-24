"""Isolated Composio direct-execution spike for Google Calendar events.

Only dummy event data is used. OAuth scopes are fixed to calendar.events.
Secrets are read from process environment or this folder's ignored .env file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from composio import Composio
from composio.client.types import auth_config_create_params as auth_types

from composio_executor import ALLOWLIST, PINNED_VERSION, ComposioExecutor


ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / ".spike_state.json"
FINDINGS_PATH = ROOT / "FINDINGS.md"
USER_ID = "dhrumil-dev"
TOOLKIT = "googlecalendar"
EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
OAUTH_REDIRECT_URI = "https://backend.composio.dev/api/v1/auth-apps/add"
EXPECTED_CREATE_SLUG = "GOOGLECALENDAR_CREATE_EVENT"
EXPECTED_DELETE_SLUG = "GOOGLECALENDAR_DELETE_EVENT"
SECRET_ENV_NAMES = (
    "COMPOSIO_API_KEY",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
)


class ScopeVerificationError(RuntimeError):
    pass


class RecordedExecutionError(RuntimeError):
    """An unsuccessful response already written to FINDINGS.md."""


def load_local_env() -> None:
    """Load only the spike's ignored .env, without echoing any values."""
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in SECRET_ENV_NAMES or os.environ.get(name):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[name] = value


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing {name}. Set it in this process environment or in the ignored "
            "spike/composio_calendar/.env file; do not paste it into chat."
        )
    return value


def secrets_for_redaction() -> list[str]:
    return [os.environ[name] for name in SECRET_ENV_NAMES if os.environ.get(name)]


def redact_text(value: str) -> str:
    redacted = value
    for secret in secrets_for_redaction():
        redacted = redacted.replace(secret, "[REDACTED]")
    # Composio may include a partially masked project-key fragment in 401 errors;
    # redact the whole diagnostic value even when it does not match the local key.
    redacted = re.sub(r"(?i)(invalid\s+api\s+key\s*:\s*)\S+", r"\1[REDACTED]", redacted)
    redacted = re.sub(r"(?i)\b(?:ck|pk|sk)_[A-Za-z0-9_*.-]+", "[REDACTED_API_KEY]", redacted)
    redacted = re.sub(r"(?i)((?:api|project|composio)\s*key\s*[:=]\s*)\S+", r"\1[REDACTED]", redacted)
    redacted = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*", r"\1[REDACTED]", redacted)
    redacted = re.sub(
        r'(?i)("(?:access_token|refresh_token|client_secret|api_key|token)"\s*:\s*)"[^"]*"',
        r'\1"[REDACTED]"',
        redacted,
    )
    return redacted


def to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=False)
    if hasattr(value, "model_dump_json"):
        return json.loads(value.model_dump_json())
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    if hasattr(value, "__dict__"):
        return {str(k): to_plain(v) for k, v in vars(value).items() if not k.startswith("_")}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def redact_object(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).casefold() in {
                "access_token", "refresh_token", "client_secret", "api_key", "token",
                "authorization", "credentials",
            }:
                # Scope is non-secret and useful to inspect, even inside credentials.
                if str(key).casefold() == "credentials" and isinstance(item, dict):
                    output[str(key)] = {
                        k: redact_object(v) if str(k).casefold() in {"scopes", "scope"} else "[REDACTED]"
                        for k, v in item.items()
                    }
                else:
                    output[str(key)] = "[REDACTED]"
            else:
                output[str(key)] = redact_object(item)
        return output
    if isinstance(value, list):
        return [redact_object(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def safe_json(value: Any) -> str:
    return json.dumps(redact_object(to_plain(value)), indent=2, ensure_ascii=False, default=str)


def record_finding(section: str, text: str) -> None:
    content = redact_text(text).strip()
    with FINDINGS_PATH.open("a", encoding="utf-8") as findings:
        findings.write(f"\n### {section}\n\n{content}\n")


def record_error(label: str, error: BaseException, response: Any | None = None) -> None:
    message = redact_text(f"{type(error).__name__}: {error}")
    extra = f"\n\nSanitized response:\n```json\n{safe_json(response)}\n```" if response is not None else ""
    record_finding(f"Runtime error: {label}", f"```text\n{message}\n```{extra}")


def make_client() -> Composio:
    return Composio(api_key=require_env("COMPOSIO_API_KEY"))


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def flatten_scope_values(config: Any) -> list[str]:
    data = to_plain(config)
    if not isinstance(data, dict):
        return []
    values: list[str] = []
    # Auth-config retrieval currently places the effective OAuth scope list in credentials.
    credentials = data.get("credentials")
    if isinstance(credentials, dict):
        scopes = credentials.get("scopes", credentials.get("scope"))
        if isinstance(scopes, str):
            values.extend(part.strip() for part in scopes.split(",") if part.strip())
        elif isinstance(scopes, (list, tuple)):
            values.extend(str(part).strip() for part in scopes if str(part).strip())
    scopes = data.get("scopes", data.get("scope"))
    if isinstance(scopes, str):
        values.extend(part.strip() for part in scopes.split(",") if part.strip())
    elif isinstance(scopes, (list, tuple)):
        values.extend(str(part).strip() for part in scopes if str(part).strip())
    return sorted(set(values))


def extract_tool_slug(tool: Any) -> str:
    data = to_plain(tool)
    if isinstance(data, dict):
        for key in ("slug", "tool_slug", "name"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value.upper()
    for key in ("slug", "tool_slug", "name"):
        value = getattr(tool, key, None)
        if isinstance(value, str) and value:
            return value.upper()
    return ""


def tool_schema(client: Composio, slug: str) -> Any:
    return client.tools.get_raw_composio_tool_by_slug(slug)


def discover() -> None:
    client = make_client()
    try:
        toolkit = client.toolkits.get(slug=TOOLKIT)
        toolkit_data = to_plain(toolkit)
        print("Google Calendar toolkit metadata:")
        print(safe_json(toolkit_data))

        meta = toolkit_data.get("meta", {}) if isinstance(toolkit_data, dict) else {}
        available = meta.get("available_versions", meta.get("availableVersions", [])) if isinstance(meta, dict) else []
        current = meta.get("version") if isinstance(meta, dict) else None
        if not available and current:
            available = [current]
        print("\nAvailable toolkit versions:")
        print(json.dumps(available, indent=2))
        if PINNED_VERSION not in available:
            raise RuntimeError(
                f"Pinned version {PINNED_VERSION} was not returned in toolkit available_versions. "
                "Stop and update the spike pin only after inspecting the SDK response."
            )

        candidates = client.tools.get_raw_composio_tools(
            toolkits=[TOOLKIT], search="event", limit=100
        )
        found_slugs = sorted({slug for item in candidates if (slug := extract_tool_slug(item))})
        print("\nEvent tool slugs returned by toolkit search:")
        print(json.dumps(found_slugs, indent=2))
        if EXPECTED_CREATE_SLUG not in found_slugs or EXPECTED_DELETE_SLUG not in found_slugs:
            raise RuntimeError(
                "The toolkit search did not return both event tools expected by the current "
                f"Google Calendar catalog page. Returned: {found_slugs}"
            )

        schemas = {}
        for label, slug in (("create", EXPECTED_CREATE_SLUG), ("delete", EXPECTED_DELETE_SLUG)):
            schema = tool_schema(client, slug)
            schemas[label] = to_plain(schema)
            print(f"\n{label.title()} tool schema ({slug}):")
            print(safe_json(schema))

        state = read_state()
        state.update({
            "toolkit": TOOLKIT,
            "pinned_version": PINNED_VERSION,
            "create_slug": EXPECTED_CREATE_SLUG,
            "delete_slug": EXPECTED_DELETE_SLUG,
            "tool_schemas": schemas,
        })
        write_state(state)
        record_finding(
            "SDK discovery",
            "Toolkit search and schema lookup completed.\n\n"
            f"Available versions: `{json.dumps(available)}`\n\n"
            f"Pinned version: `{PINNED_VERSION}`\n\n"
            f"Create slug: `{EXPECTED_CREATE_SLUG}`\n\n"
            f"Delete slug: `{EXPECTED_DELETE_SLUG}`\n\n"
            "Full schemas are printed by the discovery command and retained locally in ignored `.spike_state.json`.",
        )
    except Exception as error:
        record_error("SDK discovery", error)
        raise


def create_connect_link() -> None:
    client = make_client()
    state = read_state()
    required = ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"]
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        raise RuntimeError("Missing local OAuth variable(s): " + ", ".join(missing))

    try:
        options = {
            "type": "use_custom_auth",
            "auth_scheme": "OAUTH2",
            "name": "JobDots Calendar Spike (events only)",
            "credentials": cast(auth_types.AuthConfigUnionMember1Credentials, {
                "client_id": require_env("GOOGLE_OAUTH_CLIENT_ID"),
                "client_secret": require_env("GOOGLE_OAUTH_CLIENT_SECRET"),
                "scopes": EVENTS_SCOPE,
                "oauth_redirect_uri": OAUTH_REDIRECT_URI,
            }),
        }
        auth_config = client.auth_configs.create(toolkit=TOOLKIT, options=options)
        auth_config_id = str(getattr(auth_config, "id", ""))
        if not auth_config_id:
            raise RuntimeError("Composio created no auth-config ID in its response.")

        # Read the server-side config back and refuse to generate a link unless the
        # effective requested scope is exactly the one permitted by the user.
        try:
            verified_config = client.auth_configs.get(auth_config_id)
        except Exception as error:
            record_error("auth config scope read-back", error)
            try:
                deletion = client.auth_configs.delete(auth_config_id)
                record_finding(
                    "Cleanup after auth config read-back error",
                    "Deleted the newly created auth config because its effective scope could not be verified.\n\n"
                    f"Sanitized deletion response:\n```json\n{safe_json(deletion)}\n```",
                )
            except Exception as cleanup_error:
                record_error("cleanup after auth config read-back error", cleanup_error)
            raise RecordedExecutionError(
                "Could not verify the auth config scope; the unverified config was deleted if possible. No link was created."
            ) from None
        scope_values = flatten_scope_values(verified_config)
        if scope_values != [EVENTS_SCOPE]:
            error = ScopeVerificationError(
                "Refusing to create a Connect Link: the retrieved auth config scopes were "
                f"{scope_values!r}, expected exactly [{EVENTS_SCOPE!r}]."
            )
            record_error("scope verification before link", error, verified_config)
            # The just-created config is unusable for this spike if Composio did not
            # preserve the exact scope. Remove it before stopping; never link it.
            try:
                deletion = client.auth_configs.delete(auth_config_id)
                record_finding(
                    "Cleanup of unverified auth config",
                    "Deleted the newly created auth config because its read-back scope did not match the requested single scope.\n\n"
                    f"Sanitized deletion response:\n```json\n{safe_json(deletion)}\n```",
                )
            except Exception as cleanup_error:
                record_error("cleanup of unverified auth config", cleanup_error)
            raise error

        # Save only non-secret IDs and the expected scope, never OAuth credentials.
        state.update({
            "auth_config_id": auth_config_id,
            "requested_scopes": scope_values,
            "user_id": USER_ID,
        })
        write_state(state)
        print(f"Auth config created: {auth_config_id}")
        print(f"Verified requested scopes: {json.dumps(scope_values)}")
        print(f"Registered OAuth redirect URI: {OAUTH_REDIRECT_URI}")
        print("No Connect Link will be generated unless the verified scope is exactly calendar.events.")

        connection_request = client.connected_accounts.link(
            user_id=USER_ID,
            auth_config_id=auth_config_id,
        )
        redirect_url = str(getattr(connection_request, "redirect_url", ""))
        request_id = str(getattr(connection_request, "id", ""))
        if not redirect_url or not request_id:
            raise RuntimeError("Connect Link response did not include the URL and request ID.")
        state.update({"connection_request_id": request_id})
        write_state(state)
        print("\nRequested scopes for this Connect Link: https://www.googleapis.com/auth/calendar.events")
        print("Connect Link (approve only after checking the scope above):")
        print(redirect_url)
        print("\nAfter you approve it in Google, run: python composio_calendar_spike.py wait")
        record_finding(
            "Custom auth config and Connect Link",
            f"Created auth config `{auth_config_id}` using the custom Google OAuth client. "
            f"Server read-back verified the exact configured scope `{EVENTS_SCOPE}` before link creation. "
            f"Connect Link created for user `{USER_ID}`. The link itself is intentionally not recorded in this file.",
        )
    except Exception as error:
        if not isinstance(error, (ScopeVerificationError, RecordedExecutionError)):
            record_error("custom auth config / Connect Link", error)
        raise


def wait_for_active() -> None:
    client = make_client()
    state = read_state()
    request_id = state.get("connection_request_id")
    if not request_id:
        raise RuntimeError("No saved Connect Link request ID. Run the create-link command first.")
    try:
        account = client.connected_accounts.wait_for_connection(request_id)
        data = to_plain(account)
        status = str(data.get("status", "")) if isinstance(data, dict) else str(getattr(account, "status", ""))
        print("Connected account response:")
        print(safe_json(account))
        if status.upper() != "ACTIVE":
            raise RuntimeError(f"Connected account did not become ACTIVE; status={status!r}.")
        account_id = str(data.get("id", "")) if isinstance(data, dict) else str(getattr(account, "id", ""))
        state.update({"connected_account_id": account_id, "connected_account_status": "ACTIVE"})
        write_state(state)
        record_finding("Connected account", f"Account status reached `ACTIVE` for user `{USER_ID}`.")
    except Exception as error:
        record_error("waiting for ACTIVE connected account", error)
        raise


def create_fresh_link() -> None:
    """Reuse the verified custom auth config and issue a fresh Connect Link."""
    client = make_client()
    state = read_state()
    auth_config_id = state.get("auth_config_id")
    if not auth_config_id:
        raise RuntimeError("No saved custom auth config. Run create-link first.")
    try:
        config = client.auth_configs.get(auth_config_id)
        scope_values = flatten_scope_values(config)
        if scope_values != [EVENTS_SCOPE]:
            raise ScopeVerificationError(
                "Refusing to create a fresh Connect Link: auth config read-back is not exactly calendar.events."
            )

        accounts = client.connected_accounts.list(
            user_ids=[USER_ID],
            auth_config_ids=[auth_config_id],
        )
        items = getattr(accounts, "items", None)
        if items is None and isinstance(accounts, dict):
            items = accounts.get("items", [])
        statuses = [str(getattr(item, "status", item.get("status", "")) if isinstance(item, dict) else getattr(item, "status", "")) for item in (items or [])]
        print(f"Verified existing auth config scopes: {json.dumps(scope_values)}")
        print(f"Existing account statuses for dhrumil-dev: {json.dumps(statuses)}")
        if any(status.upper() == "ACTIVE" for status in statuses):
            state.update({"connected_account_status": "ACTIVE"})
            write_state(state)
            print("An ACTIVE connection already exists; no new Connect Link was created.")
            record_finding(
                "Connection retry check",
                "Existing account for the saved auth config was already ACTIVE; no duplicate Connect Link was created.",
            )
            return

        request = client.connected_accounts.link(
            user_id=USER_ID,
            auth_config_id=auth_config_id,
        )
        redirect_url = str(getattr(request, "redirect_url", ""))
        request_id = str(getattr(request, "id", ""))
        if not redirect_url or not request_id:
            raise RuntimeError("Fresh Connect Link response omitted its URL or request ID.")
        state.update({"connection_request_id": request_id, "requested_scopes": scope_values})
        write_state(state)
        print(f"Requested scope (verified before link creation): {EVENTS_SCOPE}")
        print("Fresh Connect Link:")
        print(redirect_url)
        print("Open it promptly, complete Google consent, and return to Composio.")
        record_finding(
            "Fresh Connect Link",
            f"Reused auth config `{auth_config_id}` after read-back confirmed exactly `{EVENTS_SCOPE}`. "
            "Generated a fresh link for `dhrumil-dev`; URL omitted from this file.",
        )
    except Exception as error:
        if not isinstance(error, ScopeVerificationError):
            record_error("fresh Connect Link", error)
        raise


def scope_error(response: Any, error: BaseException | None = None) -> bool:
    message = safe_json(response) if response is not None else ""
    if error is not None:
        message += " " + redact_text(str(error))
    lowered = message.casefold()
    return any(term in lowered for term in (
        "insufficient scope", "insufficient authentication scopes", "access_denied",
        "insufficientpermissions", "insufficient permissions", "insufficient_scope",
        "missing scope", "scope not granted", "required scope",
    ))


def response_succeeded(response: dict) -> bool:
    if "successful" in response:
        return bool(response["successful"])
    if "success" in response:
        return bool(response["success"])
    return True


def response_error_text(response: dict) -> str:
    for key in ("error", "message", "data"):
        value = response.get(key)
        if value and key != "data":
            return str(value)
    return safe_json(response)


def extract_event_id(response: dict) -> str:
    def visit(value: Any) -> str:
        if isinstance(value, dict):
            for key in ("event_id", "id"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate:
                    return candidate
            for child in value.values():
                found = visit(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = visit(child)
                if found:
                    return found
        return ""
    return visit(response)


def required_schema_keys(schema: Any) -> list[str]:
    data = to_plain(schema)
    if not isinstance(data, dict):
        return []
    for key in ("input_parameters", "parameters", "input_schema", "inputSchema"):
        block = data.get(key)
        if isinstance(block, dict):
            required = block.get("required", [])
            if isinstance(required, list):
                return [str(item) for item in required]
    return []


def build_event_payload(schema: Any) -> dict[str, Any]:
    """Build dummy values only after inspecting the SDK-provided input schema."""
    data = to_plain(schema)
    if not isinstance(data, dict):
        raise RuntimeError("Create-event schema is not a JSON object; refusing to guess arguments.")
    input_schema = None
    for key in ("input_parameters", "parameters", "input_schema", "inputSchema"):
        if isinstance(data.get(key), dict):
            input_schema = data[key]
            break
    if not input_schema:
        raise RuntimeError("Create-event schema has no recognized input schema; refusing to guess arguments.")
    properties = input_schema.get("properties", {})
    if not isinstance(properties, dict):
        raise RuntimeError("Create-event schema properties are missing; refusing to guess arguments.")

    # Asia/Kolkata is a fixed UTC+05:30 zone (no DST), so use the precise offset
    # directly and send the IANA zone name separately. This avoids a tzdata package
    # dependency on Windows, where the system zone database may be absent.
    kolkata_tz = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
    tomorrow = datetime.now(kolkata_tz).date() + timedelta(days=1)
    start = datetime.combine(tomorrow, datetime.min.time().replace(hour=10), tzinfo=kolkata_tz)
    end = start + timedelta(minutes=30)
    values: dict[str, Any] = {}
    key_map = {
        "calendar_id": "primary",
        "calendarid": "primary",
        "summary": "JobDots spike test",
        "title": "JobDots spike test",
        "event_title": "JobDots spike test",
        "start_datetime": start.isoformat(),
        "end_datetime": end.isoformat(),
        "timezone": "Asia/Kolkata",
        "time_zone": "Asia/Kolkata",
        "send_updates": "none",
        "create_meeting_room": False,
        "visibility": "private",
        "transparency": "transparent",
    }
    for property_name in properties:
        normalized = re.sub(r"[^a-z0-9]", "", str(property_name).casefold())
        for known_name, value in key_map.items():
            if normalized == re.sub(r"[^a-z0-9]", "", known_name.casefold()):
                values[str(property_name)] = value
                break

    required = required_schema_keys(schema)
    missing = [key for key in required if key not in values]
    if missing:
        raise RuntimeError(
            "Create-event schema requires fields not yet mapped to dummy-only values: "
            f"{missing}. Inspect the printed schema and update the spike payload mapping."
        )
    return values


def create_and_delete() -> None:
    state = read_state()
    if state.get("connected_account_status") != "ACTIVE":
        raise RuntimeError("The saved connected account is not ACTIVE; run the wait command first.")
    if state.get("requested_scopes") != [EVENTS_SCOPE]:
        raise ScopeVerificationError("Saved auth config scope is not exactly calendar.events; refusing execution.")
    if state.get("pinned_version") != PINNED_VERSION:
        raise RuntimeError("The saved toolkit version does not match the code's pinned version.")
    schemas = state.get("tool_schemas", {})
    create_schema = schemas.get("create")
    if not create_schema:
        raise RuntimeError("No discovered create schema. Run the discover command first.")

    client = make_client()
    connected_account_id = state.get("connected_account_id")
    if not connected_account_id:
        raise RuntimeError("No active connected_account_id was saved; refusing to guess the account.")
    executor = ComposioExecutor(
        client,
        user_id=USER_ID,
        connected_account_id=connected_account_id,
    )
    create_payload = build_event_payload(create_schema)
    print("Create payload sent to Composio:")
    print(json.dumps(create_payload, indent=2))
    start = time.perf_counter()
    try:
        create_response = executor.execute("calendar.create_event", create_payload)
        create_latency_ms = round((time.perf_counter() - start) * 1000, 2)
        print(f"\nCreate execute latency: {create_latency_ms} ms")
        print("Create response (tokens redacted):")
        print(safe_json(create_response))
        record_finding(
            "Create-event execution",
            f"Latency: `{create_latency_ms} ms`.\n\nCreate arguments (dummy only):\n```json\n"
            f"{json.dumps(create_payload, indent=2)}\n```\n\nSanitized response:\n```json\n"
            f"{safe_json(create_response)}\n```",
        )
        if not response_succeeded(create_response):
            error_text = response_error_text(create_response)
            record_error("create event", RuntimeError(error_text), create_response)
            if scope_error(create_response):
                raise ScopeVerificationError("Create-event call failed due to the narrow OAuth scope; stopping as requested.")
            raise RecordedExecutionError("Create-event execution returned unsuccessful response.")
        event_id = extract_event_id(create_response)
        if not event_id:
            raise RuntimeError("Create call succeeded but no event ID was present in its response; cannot safely delete.")
    except Exception as error:
        if isinstance(error, (ScopeVerificationError, RecordedExecutionError)):
            raise
        record_error("create event", error)
        if scope_error(None, error):
            raise ScopeVerificationError("Create-event call failed due to the narrow OAuth scope; stopping as requested.")
        raise

    delete_schema = schemas.get("delete")
    if not delete_schema:
        raise RuntimeError("No discovered delete schema. The created event remains; inspect and delete it manually.")
    delete_properties = {}
    schema_data = delete_schema if isinstance(delete_schema, dict) else {}
    for key in ("input_parameters", "parameters", "input_schema", "inputSchema"):
        if isinstance(schema_data.get(key), dict):
            delete_properties = schema_data[key].get("properties", {})
            break
    if not isinstance(delete_properties, dict):
        raise RuntimeError("Delete-event schema properties are missing; the created event remains.")
    delete_payload: dict[str, Any] = {}
    for property_name in delete_properties:
        normalized = re.sub(r"[^a-z0-9]", "", str(property_name).casefold())
        if normalized in {"eventid", "id"}:
            delete_payload[str(property_name)] = event_id
        elif normalized in {"calendarid"}:
            delete_payload[str(property_name)] = "primary"
        elif normalized in {"sendupdates"}:
            delete_payload[str(property_name)] = "none"
    missing_delete = [key for key in required_schema_keys(delete_schema) if key not in delete_payload]
    if missing_delete:
        raise RuntimeError(
            "Delete-event schema requires unmapped fields "
            f"{missing_delete}; the created event remains for manual cleanup."
        )

    print("\nDelete payload sent to Composio:")
    print(json.dumps(delete_payload, indent=2))
    start = time.perf_counter()
    try:
        delete_response = executor.execute("calendar.delete_event", delete_payload)
        delete_latency_ms = round((time.perf_counter() - start) * 1000, 2)
        print(f"Delete execute latency: {delete_latency_ms} ms")
        print("Delete response (tokens redacted):")
        print(safe_json(delete_response))
        record_finding(
            "Delete-event execution",
            f"Latency: `{delete_latency_ms} ms`.\n\nDelete arguments (event ID redacted):\n```json\n"
            f"{json.dumps({k: ('[REDACTED_EVENT_ID]' if k.casefold() in {'event_id','eventid','id'} else v) for k,v in delete_payload.items()}, indent=2)}\n```\n\n"
            f"Sanitized response:\n```json\n{safe_json(delete_response)}\n```",
        )
        if not response_succeeded(delete_response):
            error_text = response_error_text(delete_response)
            record_error("delete event", RuntimeError(error_text), delete_response)
            if scope_error(delete_response):
                raise ScopeVerificationError("Delete-event call failed due to the narrow OAuth scope; stopping as requested.")
            raise RecordedExecutionError("Delete-event execution returned unsuccessful response.")
    except Exception as error:
        if isinstance(error, (ScopeVerificationError, RecordedExecutionError)):
            raise
        record_error("delete event", error)
        if scope_error(None, error):
            raise ScopeVerificationError("Delete-event call failed due to the narrow OAuth scope; stopping as requested.")
        raise


def main() -> int:
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("discover", "create-link", "relink", "wait", "execute"),
        help="Run SDK discovery, create/approve OAuth link, wait for ACTIVE, or execute and delete the dummy event.",
    )
    args = parser.parse_args()
    try:
        if args.command == "discover":
            discover()
        elif args.command == "create-link":
            create_connect_link()
        elif args.command == "relink":
            create_fresh_link()
        elif args.command == "wait":
            wait_for_active()
        elif args.command == "execute":
            create_and_delete()
        return 0
    except Exception as error:
        # Detailed sanitized exception text is already in FINDINGS.md. Keep terminal
        # output credential-safe even if a provider returns an unexpectedly masked key.
        print(
            f"ERROR: {type(error).__name__}; sanitized details recorded in FINDINGS.md.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
