"""Research Agent.

Finds company information, culture, recent news, and
HR contacts to enrich the application context.

Tools: web_search, Hunter.io, LinkedIn scrape
Input: Company name / domain
Output: Company research summary + HR contacts
"""


class ResearchAgent:
    """Agent responsible for company and HR research.

    TODO (JP-032): Implement with LangGraph
    - Web search for company info and recent news
    - Hunter.io / Apollo.io for HR contact discovery
    - LinkedIn company page analysis
    - Culture and values extraction
    """

    async def research(self, company: str, domain: str | None = None) -> dict:
        """Research a company and find relevant HR contacts."""
        raise NotImplementedError("Research Agent not yet implemented")
