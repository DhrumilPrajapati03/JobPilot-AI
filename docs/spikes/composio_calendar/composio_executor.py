"""Small allowlisted wrapper for deterministic Composio direct execution."""

from __future__ import annotations

from typing import Any


PINNED_VERSION = "20261116_00"

# Callers select an application action. They cannot supply an arbitrary tool slug.
ALLOWLIST: dict[str, tuple[str, str]] = {
    "calendar.create_event": ("GOOGLECALENDAR_CREATE_EVENT", PINNED_VERSION),
    "calendar.delete_event": ("GOOGLECALENDAR_DELETE_EVENT", PINNED_VERSION),
}


class ComposioExecutor:
    def __init__(
        self,
        composio: Any,
        user_id: str = "dhrumil-dev",
        connected_account_id: str | None = None,
    ) -> None:
        self._composio = composio
        self._user_id = user_id
        self._connected_account_id = connected_account_id

    def execute(self, action_kind: str, payload: dict) -> dict:
        """Execute only an allowlisted action, with its fixed slug and version."""
        if action_kind not in ALLOWLIST:
            raise ValueError(f"Unsupported action_kind: {action_kind!r}")

        tool_slug, version = ALLOWLIST[action_kind]
        execution_options = {
            "arguments": payload,
            "user_id": self._user_id,
            "version": version,
        }
        if self._connected_account_id:
            execution_options["connected_account_id"] = self._connected_account_id
        response = self._composio.tools.execute(tool_slug, **execution_options)
        if hasattr(response, "model_dump"):
            return response.model_dump(mode="json")
        if isinstance(response, dict):
            return response
        if hasattr(response, "__dict__"):
            return dict(response.__dict__)
        return {"response": response}
