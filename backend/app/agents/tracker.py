"""Tracker Agent.

Logs application details, updates status in the pipeline,
and sets follow-up reminders.

Tools: PostgreSQL write, calendar API
Input: Application data + status updates
Output: Updated application record
"""


class TrackerAgent:
    """Agent responsible for application lifecycle tracking.

    TODO (JP-022): Implement with LangGraph
    - Log new applications to Supabase
    - Update pipeline status
    - Set follow-up reminders after N days
    - Generate weekly application summaries
    """

    async def log_application(self, application_data: dict) -> dict:
        """Log a new application in the tracker."""
        raise NotImplementedError("Tracker Agent not yet implemented")

    async def update_status(self, application_id: str, status: str) -> dict:
        """Update an application's pipeline status."""
        raise NotImplementedError("Tracker Agent not yet implemented")
