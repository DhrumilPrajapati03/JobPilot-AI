"""Resume Tailor Agent.

Rewrites resume sections to match JD keywords and requirements
using RAG over user skills + LLM rewriting.
"""

from app.models.resume import Resume
from app.services.llm import get_default_llm, with_structured
from app.services.vector_store import search_relevant
from app.resume_engine.validator import validate_no_hallucinations, calculate_ats_score


RESUME_METADATA_KEYS = ("id", "user_id", "version", "created_at", "updated_at")


class ResumeTailorAgent:
    """Agent responsible for tailoring resumes to specific JDs.

    Uses RAG retrieval of relevant user skills/projects, LLM rewrite
    with low temperature, and post-rewrite hallucination checks.
    """

    used_fallback = False

    def _get_best_llm(self):
        """Chat model from the single provider setting (see services.llm.default_provider)."""
        return get_default_llm()

    async def tailor(self, base_resume: dict, jd_analysis: dict) -> dict:
        """Generate a tailored resume for a specific JD.

        Args:
            base_resume: User's original base resume dictionary.
            jd_analysis: Structured JD analysis.

        Returns:
            Dictionary containing tailored resume JSON, ATS score,
            missing keywords, and actual renderer configurations.
        """
        user_id = base_resume.get("user_id") or ""
        
        # 1. RAG semantic search context
        rag_context = []
        if user_id:
            # Query vector store for the top 5 primary skills in the JD
            primary_skills = jd_analysis.get("required_skills", [])[:5]
            for skill in primary_skills:
                try:
                    matches = search_relevant(skill, user_id, top_k=2)
                    for match in matches:
                        rag_context.append(
                            f"- Skill: {skill} | Context: {match['text']} "
                            f"(Section: {match['metadata'].get('section_type')})"
                        )
                except Exception as e:
                    print(f"Warning: RAG search failed for skill '{skill}': {str(e)}")

        rag_context_str = "\n".join(rag_context) if rag_context else "No extra context found."

        # 2. Invoke LLM for structured rewrite
        llm = self._get_best_llm()
        structured_llm = with_structured(llm, Resume)

        prompt = (
            "You are a professional resume writer and ATS optimization specialist. "
            "Your task is to rewrite the user's base resume to align perfectly with the "
            "job description (JD) analysis details and semantic past contexts.\n\n"
            "=== Job Description Analysis ===\n"
            f"Role: {jd_analysis.get('role')}\n"
            f"Company: {jd_analysis.get('company')}\n"
            f"Seniority: {jd_analysis.get('seniority')}\n"
            f"Tone: {jd_analysis.get('tone')}\n"
            f"Required Skills: {', '.join(jd_analysis.get('required_skills', []))}\n"
            f"Tech Stack: {', '.join(jd_analysis.get('tech_stack', []))}\n"
            f"Keywords: {', '.join(jd_analysis.get('keywords', []))}\n\n"
            "=== User Past Work Context (RAG Results) ===\n"
            f"{rag_context_str}\n\n"
            "=== Base Resume Content ===\n"
            f"{base_resume}\n\n"
            "=== Rewriting Rules ===\n"
            "1. **Summary**: Rewrite the professional summary (3 lines max) to match "
            "the job's seniority level, role focus, and tone. Incorporate primary keywords.\n"
            "2. **Skills**: Reorder the skills arrays so that JD-matching primary skills "
            "are placed at the top of the 'primary' list. Non-matching but relevant skills "
            "should go to the 'secondary' list.\n"
            "3. **Experience Bullets**: Per job entry, rewrite bullet points to describe "
            "original accomplishments using tech keywords and terminology from the JD. "
            "Maintain all original facts: do NOT invent metrics, dates, companies, or roles.\n"
            "4. **Projects**: Reorder the projects so the most relevant ones appear first, "
            "and tailor descriptions to emphasize matching technology stacks.\n"
            "5. **Strict Guardrails**: Do NOT invent new employment periods, company names, "
            "or educational credentials. Every output must correspond strictly to the "
            "provided base resume inputs.\n\n"
            "Generate and return the tailored resume as valid JSON matching the requested schema."
        )

        try:
            tailored_resume_obj = await structured_llm.ainvoke(prompt)
            # mode="json" turns datetimes into strings so the content can be stored as JSONB.
            tailored_dict = tailored_resume_obj.model_dump(mode="json", exclude_none=True)
        except Exception as e:
            print(f"Error during LLM resume tailoring: {str(e)}")
            # Fall back to base resume if rewrite fails
            self.used_fallback = True
            tailored_dict = base_resume.copy()
        # Row metadata from the base resume (ids, timestamps) doesn't belong in tailored content.
        for key in RESUME_METADATA_KEYS:
            tailored_dict.pop(key, None)

        # 3. Post-Generation Hallucination checks & ATS Scoring
        violations = validate_no_hallucinations(
            tailored=tailored_dict,
            base=base_resume,
            jd_keywords=jd_analysis.get("keywords", []) + jd_analysis.get("required_skills", [])
        )

        # If hallucinations are detected, we could log them or clean them (fallback to base for safety)
        if violations:
            print(f"⚠️ Hallucinations detected: {violations}. Reverting invalid fields.")
            # For simplicity, if a company/date was altered, overwrite it back with the base resume values
            for idx, exp in enumerate(tailored_dict.get("experience", [])):
                if idx < len(base_resume.get("experience", [])):
                    base_exp = base_resume["experience"][idx]
                    exp["company"] = base_exp.get("company", "")
                    exp["duration"] = base_exp.get("duration", "")
            
            # Clean primary/secondary skills
            base_all_skills = set(
                s.strip().lower() for s in 
                base_resume.get("skills", {}).get("primary", []) + 
                base_resume.get("skills", {}).get("secondary", [])
            )
            jd_kw_lower = {k.strip().lower() for k in jd_analysis.get("keywords", []) + jd_analysis.get("required_skills", [])}
            
            cleaned_primary = [
                s for s in tailored_dict.get("skills", {}).get("primary", [])
                if s.strip().lower() in base_all_skills or s.strip().lower() in jd_kw_lower
            ]
            cleaned_secondary = [
                s for s in tailored_dict.get("skills", {}).get("secondary", [])
                if s.strip().lower() in base_all_skills or s.strip().lower() in jd_kw_lower
            ]
            tailored_dict["skills"] = {"primary": cleaned_primary, "secondary": cleaned_secondary}

        # Calculate final simulated ATS score
        score, missing = calculate_ats_score(tailored_dict, jd_analysis)

        return {
            "content": tailored_dict,
            "keyword_match_score": score,
            "missing_keywords": missing,
            "violations": violations
        }
