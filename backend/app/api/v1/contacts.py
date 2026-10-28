"""Owner-scoped recruiter research with source evidence and verification."""
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from app.services.auth import CurrentUser, get_current_user
from app.api.v1.email import admin, owned
from app.services import recruiters

router=APIRouter()

class ResearchRequest(BaseModel):
    application_id: uuid.UUID
    company_domain: str = Field(max_length=253)
    @field_validator('company_domain')
    @classmethod
    def domain(cls,value): return recruiters.domain_name(value)

@router.post('/research')
async def research_contacts(body: ResearchRequest,user: CurrentUser=Depends(get_current_user)):
    db=admin(); application=owned(db,'job_applications',body.application_id,user.id)
    return await recruiters.research(db,user.id,application,body.company_domain)

@router.get('/find')
async def find_contacts(company_domain: str,application_id: uuid.UUID,user: CurrentUser=Depends(get_current_user)):
    return await research_contacts(ResearchRequest(company_domain=company_domain,application_id=application_id),user)

@router.get('/')
async def list_contacts(application_id: uuid.UUID|None=None,user: CurrentUser=Depends(get_current_user)):
    query=admin().table('recruiter_leads').select('*').eq('user_id',user.id).order('verified_at',desc=True).limit(100)
    if application_id: query=query.eq('application_id',str(application_id))
    rows=query.execute().data
    return {'contacts':rows,'total':len(rows)}
