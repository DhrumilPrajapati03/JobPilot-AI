from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from app.services.auth import CurrentUser, get_current_user
from app.services.supabase import get_supabase_admin_client
from app.services.usage import reserve
from app.recommendation.service import create_snapshot, set_feedback
from app.config import settings
from app.services import runs

router = APIRouter()


@router.get('/status')
def recommendation_status(user: CurrentUser = Depends(get_current_user)):
    return {'baseline':'v2', 'experimental': bool(settings.RERANKER_PATH and runs.durable_enabled()), 'promoted':False}


class Snapshot(BaseModel):
    request_key: UUID
    posting_ids: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.posting_ids)) != len(self.posting_ids):
            raise ValueError('Each posting must appear once')
        return self


class Impression(BaseModel):
    run_id: UUID
    posting_id: UUID
    request_key: UUID
    position: int = Field(ge=1, le=100)
    visible_ms: int = Field(ge=500, le=60000)


class Feedback(BaseModel):
    signal: Literal['interested', 'not_relevant', 'clear']
    reason: Literal['wrong_role', 'location', 'seniority', 'skills', 'other'] | None = None

    @model_validator(mode='after')
    def validate_reason(self):
        if self.signal != 'not_relevant' and self.reason:
            raise ValueError('Reasons apply to not-relevant feedback only')
        return self


def unavailable(exc):
    if isinstance(exc, HTTPException):
        raise exc
    raise HTTPException(503, 'Recommendation feedback is unavailable. Check the release migration and try again.') from None


@router.get('/feedback')
def feedback(user: CurrentUser = Depends(get_current_user)):
    try:
        return {'feedback': get_supabase_admin_client().table('recommendation_feedback').select(
            'posting_id,signal,reason,updated_at').eq('user_id', user.id).limit(1000).execute().data}
    except Exception as exc:
        unavailable(exc)


@router.put('/feedback/{posting_id}')
def update_feedback(posting_id: UUID, request: Feedback, user: CurrentUser = Depends(get_current_user)):
    try:
        reserve(user.id, 'feedback', 500)
        return set_feedback(get_supabase_admin_client(), user.id, str(posting_id), request.signal, request.reason)
    except Exception as exc:
        unavailable(exc)


@router.post('/runs')
def snapshot(request: Snapshot, user: CurrentUser = Depends(get_current_user)):
    try:
        reserve(user.id, 'recommendation_lists', 1000, str(request.request_key))
        row = create_snapshot(get_supabase_admin_client(), user.id, [str(i) for i in request.posting_ids], str(request.request_key))
        return {'id': row['id'], 'items': row['items'], 'model_version': row['model_version']}
    except Exception as exc:
        unavailable(exc)


@router.post('/impressions')
def impression(request: Impression, user: CurrentUser = Depends(get_current_user)):
    try:
        reserve(user.id, 'impressions', 2000, str(request.request_key))
        return get_supabase_admin_client().rpc('record_recommendation_impression', {
            'p_user_id': user.id, 'p_run_id': str(request.run_id), 'p_posting_id': str(request.posting_id),
            'p_key': str(request.request_key), 'p_position': request.position, 'p_visible_ms': request.visible_ms,
        }).execute().data
    except Exception as exc:
        if 'recommendation_not_found' in str(exc):
            raise HTTPException(404, 'Displayed recommendation not found') from None
        unavailable(exc)


@router.post('/experiment')
def experiment(request: Snapshot, user: CurrentUser = Depends(get_current_user)):
    if len(request.posting_ids)>20:
        raise HTTPException(422, 'A shortlist experiment accepts at most 20 opportunities.')
    if not runs.durable_enabled() or not settings.RERANKER_PATH:
        raise HTTPException(503, 'The optional reranker is not configured. Baseline matching remains available.')
    ids = [str(i) for i in request.posting_ids]
    rows = get_supabase_admin_client().table('job_postings').select('id').eq('user_id', user.id).in_('id', ids).execute().data
    if len(rows)!=len(ids):
        raise HTTPException(404, 'Opportunity not found')
    reserve(user.id, 'ranking_experiments', 5, str(request.request_key))
    row = runs.enqueue_for_user(user.id, 'recommendation', {'posting_ids': ids}, str(request.request_key))
    return {'run_id': row['id'], 'status': row['status']}
