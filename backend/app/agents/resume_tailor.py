"""Resume Tailor Agent.

Rewrites resume sections to match JD keywords and requirements
using RAG over user skills + LLM rewriting.

Follows the 12-step pipeline:
1. Load base resume JSON
2. Load JD analysis
3. Keyword gap analysis
4. Skills reorder
5. Summary rewrite
6. Experience bullet rewrite
7. Project reorder + rewrite
8. Hallucination guard check
9. ATS score calculation
10. PDF render
11. Diff generation
12. Human review gate

Tools: ChromaDB (skills lookup), LLM, PDF generation
Input: Base Resume + JD Analysis
Output: TailoredResume with PDF
"""


class ResumeTailorAgent:
    """Agent responsible for tailoring resumes to specific JDs.

    TODO (JP-011, JP-053): Implement with LangGraph
    - RAG retrieval of relevant user skills/projects
    - LLM rewrite with temperature 0.3
    - Hallucination guards (company, date, skills validation)
    - ATS keyword match scoring
    """

    async def tailor(self, base_resume: dict, jd_analysis: dict) -> dict:
        """Generate a tailored resume for a specific JD."""
        raise NotImplementedError("Resume Tailor Agent not yet implemented")
