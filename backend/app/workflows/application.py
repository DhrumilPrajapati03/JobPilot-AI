"""A LangGraph pipeline with per-node, lease-fenced Supabase checkpoints.

The graph is reconstructed on recovery; completed nodes return their persisted
outputs. Database material persistence is one transactional, idempotent RPC.
"""
import asyncio
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents import orchestrator as agents
from app.services import autopilot, referrals
from app.services.job_filters import evaluate_skip_rules, india_eligibility_flag
from app.services.runs import PermanentRunError


class GraphState(TypedDict):
    run_id: str


async def run_application(ctx, email: str):
    db, uid, inputs = ctx.store.client, ctx.run["user_id"], ctx.run["inputs"]
    saved = ctx.checkpoints.get("database_saving")
    if saved and not db.table("job_applications").select("id").eq("id", saved["application_id"]).eq("user_id", uid).execute().data:
        raise PermanentRunError("The generated application was deleted. Start a new application deliberately.")

    async def parse():
        if inputs.get("posting_id"):
            rows = db.table("job_postings").select("*").eq("id", inputs["posting_id"]).eq("user_id", uid).execute().data
            if not rows:
                raise PermanentRunError("The source posting was removed.")
            if reason := india_eligibility_flag(rows[0]):
                raise PermanentRunError(reason)
        parser = agents.JDParserAgent()
        analysis = await parser.parse(jd_url=inputs.get("jd_url"), jd_text=inputs.get("jd_text"))
        return {"analysis": analysis.model_dump(mode="json"), "source_text": parser.source_text if hasattr(parser, "source_text") else inputs.get("jd_text", "")}

    async def profile():
        p = db.table("user_profiles").select("*").eq("id", uid).execute().data
        r = db.table("resumes").select("*").eq("user_id", uid).eq("version", "base").execute().data
        if not r:
            raise PermanentRunError("Save a base resume on the Profile page before generating an application.")
        return {"profile": p[0] if p else {}, "resume": r[0]}

    def analysis():
        parsed = ctx.checkpoints["jd_parsing"]
        result = dict(parsed["analysis"])
        result["skip_flags"] = evaluate_skip_rules(ctx.checkpoints["profile_loading"]["profile"].get("work_preferences"),
                                                  result.get("company", ""), parsed["source_text"], result)
        return result

    async def tailor():
        writer = agents.ResumeTailorAgent()
        result = await writer.tailor(ctx.checkpoints["profile_loading"]["resume"], analysis())
        return {**result, "score": result["keyword_match_score"],
                "warning": "AI rewriting failed; base resume used. Review before applying." if writer.used_fallback else ""}

    async def pdf():
        try:
            content = agents.build_render_content(ctx.checkpoints["resume_tailoring"]["content"], ctx.checkpoints["profile_loading"]["profile"], email=email)
            raw, _ = await agents.render_resume_pdf(content)
            pages = agents.validate_page_count(raw)
            return {"pages": pages, "warning": f"Resume runs {pages} pages; consider trimming." if pages > 1 else ""}
        except Exception:
            return {"warning": "Server PDF export is unavailable. Use the resume preview's browser export."}

    async def write(kind):
        writer = {"cover": agents.CoverLetterAgent, "emails": agents.EmailWriterAgent, "dms": agents.DMWriterAgent}[kind]()
        p = ctx.checkpoints["profile_loading"]["profile"]
        result = await (writer.generate(analysis(), p) if kind == "cover" else writer.generate(analysis(), agents.DEFAULT_CONTACT, p))
        return {"content": result, "warning": "A basic outreach template was used; rewrite before sending." if writer.used_fallback else ""}

    async def outreach_done():
        return {"warning": "Some outreach used fallback templates. Review before sending." if any(
            ctx.checkpoints[k].get("warning") for k in ("cover_draft", "email_drafts", "dm_drafts")) else ""}

    async def persist():
        jd = analysis()
        application = {"company": jd.get("company") or "Unknown Company", "role": jd.get("role") or "Unknown Role",
                       "jd_url": inputs.get("jd_url") or "", "jd_text": inputs.get("jd_text") or ctx.checkpoints["jd_parsing"]["source_text"],
                       "jd_analysis": jd, "source": inputs.get("source", "manual"),
                       "cover_letter": ctx.checkpoints["cover_draft"]["content"], "linkedin_dm": ctx.checkpoints["dm_drafts"]["content"]}
        emails = ctx.checkpoints["email_drafts"]["content"]
        sequence = [{"subject": emails[key].get("subject", ""), "body": emails[key].get("body", ""), "sequence_number": i + 1}
                    for i, key in enumerate(agents.EMAIL_SEQUENCE_KEYS) if key in emails]
        return await asyncio.to_thread(ctx.store.rpc, "save_run_application", p_run_id=ctx.run["id"], p_token=ctx.token,
                                       p_application=application, p_tailored=ctx.checkpoints["resume_tailoring"], p_emails=sequence)

    async def referral():
        app = ctx.checkpoints["database_saving"]
        try:
            ranked = referrals.rank_contacts(referrals.load_index(db, uid).find(app["company"]), app["role"])
            if not ranked:
                return {"count": 0}
            best = ranked[0].contact
            existing = db.table("referral_requests").select("id").eq("application_id", app["application_id"]).eq("contact_id", best["id"]).eq("user_id", uid).execute().data
            if not existing:
                text, _ = await referrals.draft_referral_message(best, app, ctx.checkpoints["profile_loading"]["profile"], ctx.checkpoints["profile_loading"]["resume"])
                # Preserve later user edits/outcomes on recovery. The upsert is
                # fenced in the DB transaction rather than an unchecked admin write.
                await asyncio.to_thread(ctx.store.rpc, "save_run_referral", p_run_id=ctx.run["id"], p_token=ctx.token,
                                        p_contact_id=best["id"], p_message=text)
            return {"count": len(ranked)}
        except Exception as exc:
            if "lease_lost" in str(exc):
                raise
            return {"warning": "Referral lookup was unavailable. Review your Network page."}

    async def prepare():
        try:
            await autopilot.prepare_application_form(db, uid, ctx.checkpoints["database_saving"]["application_id"], email)
            return {"prepared": True}
        except Exception:
            return {"warning": "Form preparation is unavailable; retry preparation from the apply queue."}

    stages = [
        ("jd_parsing", "Parsing the job description", parse),
        ("profile_loading", "Loading your profile and resume", profile),
        ("resume_tailoring", "Tailoring your resume", tailor),
        ("pdf_rendering", "Checking PDF export", pdf),
        ("cover_draft", "Drafting the cover letter", lambda: write("cover")),
        ("email_drafts", "Drafting the email sequence", lambda: write("emails")),
        ("dm_drafts", "Drafting LinkedIn messages", lambda: write("dms")),
        ("outreach_generation", "Checking the outreach package", outreach_done),
        ("database_saving", "Saving application materials", persist),
        ("referral_check", "Checking your referral network", referral),
        ("form_preparation", "Preparing form answers", prepare),
    ]
    graph = StateGraph(GraphState)
    previous = START
    for name, message, operation in stages:
        async def node(state, stage=name, label=message, fn=operation):
            await ctx.stage(stage, label, fn)
            return state
        graph.add_node(name, node)
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    await graph.compile().ainvoke({"run_id": ctx.run["id"]})
    return ctx.checkpoints["database_saving"]
