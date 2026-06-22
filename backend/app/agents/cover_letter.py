"""Cover Letter Agent.

Generates personalised cover letters using company research,
JD analysis, and the user's professional story.

Tools: LLM, company info from Research Agent
Input: JD Analysis + Company Research + User Profile
Output: Cover letter text
"""


class CoverLetterAgent:
    """Agent responsible for generating personalised cover letters.

    TODO (JP-017): Implement with LangGraph
    - Use company research data for personalisation
    - Match tone and seniority from JD analysis
    - Reference specific user achievements relevant to the role
    """

    async def generate(
        self,
        jd_analysis: dict,
        user_profile: dict,
        company_research: dict | None = None,
    ) -> str:
        """Generate a cover letter for a specific application."""
        raise NotImplementedError("Cover Letter Agent not yet implemented")
