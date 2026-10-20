"""LinkedIn DM Writer Agent.

Creates short, personalised LinkedIn connection requests
and follow-up DM pairs for HR outreach.
"""

from app.services.llm import get_default_llm


class DMWriterAgent:
    """Agent responsible for drafting LinkedIn DM outreach."""

    used_fallback = False

    def _get_llm(self):
        return get_default_llm(temperature=0.4)

    async def generate(self, jd_analysis: dict, hr_contact: dict, user_profile: dict) -> dict:
        """Generate a LinkedIn DM pair (connection request + follow-up)."""
        llm = self._get_llm()

        company = jd_analysis.get("company", "the company")
        role = jd_analysis.get("role", "the role")
        hr_name = hr_contact.get("name") if hr_contact else ""
        first_name = hr_name.split(" ")[0] if hr_name else ""

        prompt = (
            "You are a professional networker. Write a LinkedIn connection request and a follow-up DM "
            "for the following target role. Keep connection requests under 300 characters (LinkedIn limit).\n\n"
            "=== Details ===\n"
            f"Candidate: {user_profile.get('name')}\n"
            f"Role: {role}\n"
            f"Company: {company}\n"
            f"Target Recruiter Name: {hr_name}\n\n"
            "=== Output Format ===\n"
            "Output your response strictly as 2 sections separated by '---':\n"
            "SECTION 1: Connection Request (strictly < 300 characters, including spaces).\n"
            "SECTION 2: Follow-up DM (longer, professional message, max 150 words).\n\n"
            "Do not include any headers like 'SECTION 1:' in the output. Just output the content separated by '---'."
        )

        try:
            res = await llm.ainvoke(prompt)
            sections = res.content.split("---")
            
            conn_req = "Hi " + (first_name or "there") + ", I'd love to connect. I see you recruit for " + role + " roles at " + company + ". Let's connect!"
            follow_up = "Hi " + (first_name or "there") + ",\n\nThanks for connecting. I'm reaching out because I recently applied for the " + role + " role at " + company + " and wanted to..."
            
            if len(sections) >= 2:
                conn_req = sections[0].strip()
                follow_up = sections[1].strip()
                
            # Truncate connection request if LLM ignored limit
            if len(conn_req) > 299:
                conn_req = conn_req[:295] + "..."

            return {
                "connection_request": conn_req,
                "follow_up": follow_up
            }
            
        except Exception as e:
            print(f"Error generating DMs: {str(e)}")
            self.used_fallback = True
            return {
                "connection_request": f"Hi {first_name or 'there'}, I'd love to connect. I see you recruit for {role} roles at {company}.",
                "follow_up": f"Hi {first_name or 'there'},\n\nThanks for connecting. I applied to the {role} position and would love to introduce myself..."
            }
