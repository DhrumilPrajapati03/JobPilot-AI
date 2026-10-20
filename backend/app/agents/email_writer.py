"""Cold Email Writer Agent.

Drafts personalised cold emails to HR/recruiters with
a 2-part follow-up sequence.
"""

from app.services.llm import get_default_llm


class EmailWriterAgent:
    """Agent responsible for crafting cold outreach emails."""

    used_fallback = False

    def _get_llm(self):
        return get_default_llm(temperature=0.4)

    async def generate(self, jd_analysis: dict, hr_contact: dict, user_profile: dict) -> dict:
        """Generate a cold email sequence (initial + 2 follow-ups)."""
        llm = self._get_llm()

        company = jd_analysis.get("company", "the company")
        role = jd_analysis.get("role", "the role")
        hr_name = hr_contact.get("name") if hr_contact else ""
        hr_salutation = f"Dear {hr_name}" if hr_name else "Hi there"

        prompt = (
            "You are an expert sales and recruitment copywriter. Write a highly personalized, short, "
            "and compelling cold outreach email to a recruiter for the following position. "
            "Also write two follow-up emails (+5 days and +12 days).\n\n"
            "=== Details ===\n"
            f"Candidate: {user_profile.get('name')}\n"
            f"Headline: {user_profile.get('headline')}\n"
            f"Company: {company}\n"
            f"Role: {role}\n"
            f"Skills: {', '.join(jd_analysis.get('required_skills', []))}\n"
            f"HR Salutation: {hr_salutation}\n\n"
            "=== Output Format ===\n"
            "Output your response strictly as 3 sections separated by '---':\n"
            "SECTION 1: Initial Email. Must start with 'Subject: [Subject line]' then a blank line, then the body.\n"
            "SECTION 2: Follow-up 1 (+5 days). Must start with 'Subject: [Subject line]' then a blank line, then the body.\n"
            "SECTION 3: Follow-up 2 (+12 days). Must start with 'Subject: [Subject line]' then a blank line, then the body.\n\n"
            "Keep the initial email under 150 words. Focus on how the candidate's core skills directly solve "
            "a need for the role."
        )

        try:
            res = await llm.ainvoke(prompt)
            sections = res.content.split("---")
            
            email_data = {}
            keys = ["initial", "follow_up_1", "follow_up_2"]
            
            for i, section in enumerate(sections[:3]):
                section_str = section.strip()
                lines = section_str.split("\n")
                subject = f"Outreach for {role} role at {company}"
                body = section_str
                
                # Try to parse Subject:
                for line in lines[:3]:
                    if line.lower().startswith("subject:"):
                        subject = line.split(":", 1)[1].strip()
                        body = "\n".join(lines[lines.index(line) + 1:]).strip()
                        break
                        
                email_data[keys[i]] = {
                    "subject": subject,
                    "body": body
                }
                
            # Fill missing keys if split failed
            for key in keys:
                if key not in email_data:
                    email_data[key] = {
                        "subject": f"Outreach for {role} at {company}",
                        "body": f"{hr_salutation},\n\nI recently applied to the {role} position and wanted to connect..."
                    }
                    
            return email_data
            
        except Exception as e:
            print(f"Error generating emails: {str(e)}")
            self.used_fallback = True
            return {
                "initial": {
                    "subject": f"Outreach: {role} role at {company}",
                    "body": f"{hr_salutation},\n\nI'm reaching out regarding the {role} role at {company}..."
                },
                "follow_up_1": {
                    "subject": f"Following up: {role} role at {company}",
                    "body": f"{hr_salutation},\n\nHope you're having a good week. I wanted to follow up on my note..."
                },
                "follow_up_2": {
                    "subject": f"Quick note: {role} role at {company}",
                    "body": f"{hr_salutation},\n\nI know you're busy, so I'll keep this short. Just wanted to see if..."
                }
            }
