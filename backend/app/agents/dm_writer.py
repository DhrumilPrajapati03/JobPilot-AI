"""LinkedIn DM Writer Agent.

Creates short, personalised LinkedIn connection requests
and follow-up DM pairs for HR outreach.

Tools: LLM, company research
Input: JD Analysis + HR Contact + User Profile
Output: Connection request message + follow-up DM
"""


class DMWriterAgent:
    """Agent responsible for drafting LinkedIn DM outreach.

    TODO (JP-019): Implement with LangGraph
    - Short connection request (300 char limit)
    - Follow-up DM after connection accepted
    - Professional, non-spammy tone
    """

    async def generate(self, jd_analysis: dict, hr_contact: dict, user_profile: dict) -> dict:
        """Generate a LinkedIn DM pair (connection request + follow-up)."""
        raise NotImplementedError("DM Writer Agent not yet implemented")
