from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from app.services.auth import CurrentUser, get_current_user
from app.services.supabase import get_supabase_admin_client
from app.services import runs
from app.services.company_research import owned
from app.services.usage import reserve

router = APIRouter()


class ResearchRequest(BaseModel):
    request_key: UUID
    urls: list[HttpUrl] = Field(min_length=1, max_length=3)


def latest(db, uid, app_id):
    return db.table('company_research').select('*').eq('user_id', uid).eq('application_id', app_id).order('created_at', desc=True).limit(1).execute().data


@router.get('/{application_id}')
def get_research(application_id: UUID, user: CurrentUser = Depends(get_current_user)):
    db = get_supabase_admin_client()
    owned(db, user.id, str(application_id))
    try:
        rows = latest(db, user.id, str(application_id))
        return {'research': rows[0] if rows else None}
    except Exception:
        raise HTTPException(503, 'Company research storage is unavailable. Check the release migration.') from None


@router.post('/{application_id}')
def start_research(application_id: UUID, request: ResearchRequest, user: CurrentUser = Depends(get_current_user)):
    owned(get_supabase_admin_client(), user.id, str(application_id))
    if not runs.durable_enabled():
        raise HTTPException(503, 'Company research needs durable execution and a running worker. Your existing materials are available.')
    reserve(user.id, 'company_research', 5, str(request.request_key))
    row = runs.enqueue_for_user(user.id, 'company_research', {'application_id': str(application_id), 'urls': list(dict.fromkeys(str(u) for u in request.urls))}, str(request.request_key))
    return {'run_id': row['id'], 'status': row['status']}


@router.post('/{application_id}/cover-letter')
async def research_cover(application_id: UUID, user: CurrentUser = Depends(get_current_user)):
    import asyncio
    from app.agents.cover_letter import CoverLetterAgent
    from app.services.writing_evidence import with_resume,templates_for
    db = get_supabase_admin_client()
    application = await asyncio.to_thread(owned, db, user.id, str(application_id))
    rows = await asyncio.to_thread(latest, db, user.id, str(application_id))
    if not rows:
        raise HTTPException(409, 'Collect source research before requesting this draft.')
    await asyncio.to_thread(reserve, user.id, 'research_drafts', 10)
    resumes = await asyncio.to_thread(lambda: db.table('resumes').select('*').eq('user_id', user.id).eq('version', 'base').execute().data)
    if not resumes:
        raise HTTPException(409, 'Save your base résumé before drafting.')
    writer = CoverLetterAgent()
    profile={'name':resumes[0].get('name'),'headline':resumes[0].get('headline'),'_writing_templates':await asyncio.to_thread(templates_for,db,user.id)}
    body = await writer.generate(application.get('jd_analysis') or {'company': application['company'], 'role': application['role']}, with_resume(profile, resumes[0]), rows[0])
    return {'draft': body, 'fallback': writer.used_fallback, 'research_id': rows[0]['run_id'], 'research': rows[0], 'saved': False}
