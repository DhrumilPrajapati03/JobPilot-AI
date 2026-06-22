"""JD Parser Agent.

Extracts structured information from job descriptions:
role, company, required skills, keywords, tone, seniority
level, and tech stack.

Tools: web_scrape, LLM (structured output)
Input: JD URL or raw text
Output: JDAnalysis structured model
"""


class JDParserAgent:
    """Agent responsible for parsing and analysing job descriptions.

    Uses LLM structured output to extract key information from
    JD text or scraped web pages.

    TODO (JP-009): Implement with LangGraph
    - Accept JD URL (scrape with httpx + BeautifulSoup) or raw text
    - LLM structured output via Pydantic schema
    - Return JDAnalysis model
    """

    async def parse(self, jd_url: str | None = None, jd_text: str | None = None) -> dict:
        """Parse a job description and return structured analysis."""
        raise NotImplementedError("JD Parser Agent not yet implemented")
