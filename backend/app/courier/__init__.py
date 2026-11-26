"""Courier: deterministic executors that run approved, frozen payloads (plan section 4).

Agents only propose. Courier is the only code that sends anything, and it only ever acts on
an action that has passed the policy gate (app.core.actions.start_execution)."""
