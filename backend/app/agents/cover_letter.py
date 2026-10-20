"""Cover Letter Agent.

Generates personalised cover letters using company research,
JD analysis, and the user's professional story.
"""

from app.services.llm import get_default_llm


class CoverLetterAgent:
    """Agent responsible for generating personalised cover letters."""

    used_fallback = False

    def _get_llm(self):
        return get_default_llm(temperature=0.4)

    async def generate(
        self,
        jd_analysis: dict,
        user_profile: dict,
        company_research: dict | None = None,
    ) -> str:
        """Generate a cover letter for a specific application."""
        llm = self._get_llm()

        prompt = (
            "You are a professional cover letter writer. Draft a compelling, personalized cover letter "
            "for the following role. Keep it professional, engaging, and concise (max 350 words).\n\n"
            "=== Job Details ===\n"
            f"Role: {jd_analysis.get('role')}\n"
            f"Company: {jd_analysis.get('company')}\n"
            f"Required Skills: {', '.join(jd_analysis.get('required_skills', []))}\n\n"
            "=== User Details ===\n"
            f"Name: {user_profile.get('name')}\n"
            f"Headline: {user_profile.get('headline')}\n"
            f"Location: {user_profile.get('location')}\n\n"
            "=== Output Rules ===\n"
            "1. Address the hiring team of the company.\n"
            "2. Align your tone with the JD seniority and style.\n"
            "3. Mention 2-3 matching primary skills and how the candidate can bring value.\n"
            "4. Return only the body of the cover letter, ready to send."
        )

        try:
            res = await llm.ainvoke(prompt)
            return res.content
        except Exception as e:
            print(f"Error generating cover letter: {str(e)}")
            self.used_fallback = True
            return f"Dear Hiring Team,\n\nI am writing to express my strong interest in the {jd_analysis.get('role')} role at {jd_analysis.get('company')}..."
