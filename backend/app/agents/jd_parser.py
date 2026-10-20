"""JD Parser Agent.

Extracts structured information from job descriptions:
role, company, required skills, keywords, tone, seniority
level, and tech stack.
"""

import re

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException, status
from app.models.application import JDAnalysis
from app.services.llm import get_default_llm, with_structured

# Long scraped pages are mostly boilerplate; this keeps prompts within model limits.
MAX_JD_CHARS = 12_000  # ~3k tokens: long enough for any real JD, kind to free-tier quotas
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_TAGS = re.compile(r"<[^>]+>")


def sanitize_jd_text(text: str) -> str:
    """Strip HTML tags and control characters before the JD reaches a prompt."""
    text = _CONTROL_CHARS.sub("", _HTML_TAGS.sub(" ", text or ""))
    return text.strip()[:MAX_JD_CHARS]


class JDParserAgent:
    """Agent responsible for parsing and analysing job descriptions.

    Uses LLM structured output to extract key information from
    JD text or scraped web pages.
    """

    async def _scrape_url(self, url: str) -> str:
        """Scrape the text content of a job listing URL."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to fetch job URL. Status code: {response.status_code}"
                    )
                
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Strip script and style elements
                for element in soup(["script", "style", "nav", "header", "footer", "form"]):
                    element.decompose()
                
                # Get text
                text = soup.get_text(separator=" ")
                # Collapse whitespace
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase for line in lines for phrase in line.split("  "))
                cleaned_text = " ".join(chunk for chunk in chunks if chunk)
                
                if not cleaned_text.strip():
                    raise ValueError("No readable text found on the page.")
                
                return cleaned_text

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error scraping job URL: {str(e)}"
            )

    async def parse(self, jd_url: str | None = None, jd_text: str | None = None) -> JDAnalysis:
        """Parse a job description and return structured analysis."""
        if not jd_url and not jd_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either a job URL or raw description text must be provided."
            )

        content_to_parse = jd_text
        if jd_url and not content_to_parse:
            content_to_parse = await self._scrape_url(jd_url)
        content_to_parse = sanitize_jd_text(content_to_parse)
        # Kept so callers can store / screen the text that was actually analysed (scraped for URLs).
        self.source_text = content_to_parse

        try:
            structured_llm = with_structured(get_default_llm(task="light"), JDAnalysis)

            prompt = (
                "You are an expert job description analysis assistant. Read the job description "
                "provided below and extract key details into the structured output schema.\n\n"
                "Instructions:\n"
                "- Extract exact required skills and tech stack.\n"
                "- Identify key industry terms as keywords.\n"
                "- Determine the tone (e.g. professional, startup, friendly, corporate).\n"
                "- Determine the seniority level (e.g. Junior, Mid, Senior, Lead).\n"
                "- Extract salary details if mentioned (e.g. '$120k - $150k' or 'Competitive').\n"
                "- Identify if the role is remote (remote=True) or hybrid/onsite (remote=False).\n"
                "- Classify company_type as 'mnc' (large multinational or enterprise), 'startup' "
                "(early or growth-stage venture), or 'sme' (small, local or family-run business).\n\n"
                f"Job Description Content:\n{content_to_parse}"
            )

            analysis = await structured_llm.ainvoke(prompt)
            return analysis

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to analyze job description: {str(e)}"
            )
