"""Cold Email Writer Agent.

Drafts personalised cold emails to HR/recruiters with
a 2-part follow-up sequence.

Tools: LLM, HR contact data, email templates
Input: JD Analysis + HR Contact + User Profile
Output: Initial email + 2 follow-up drafts
"""


class EmailWriterAgent:
    """Agent responsible for crafting cold outreach emails.

    TODO (JP-018): Implement with LangGraph
    - Generate personalised initial email
    - Create +5 day and +10 day follow-up drafts
    - Support variable chip interpolation
    - Maintain professional yet warm tone
    """

    async def generate(self, jd_analysis: dict, hr_contact: dict, user_profile: dict) -> dict:
        """Generate a cold email sequence (initial + 2 follow-ups)."""
        raise NotImplementedError("Email Writer Agent not yet implemented")
