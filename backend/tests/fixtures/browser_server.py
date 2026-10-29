"""Local browser fixture server, never imported by the production application.

Real FastAPI routes/business logic; synthetic auth, in-memory DB and provider
boundaries. Hosted SQL tests independently exercise the actual DB contracts.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

if os.environ.get('JOBPILOT_E2E') != '1':
    raise RuntimeError('This synthetic server requires JOBPILOT_E2E=1')
sys.path[:0] = [str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
os.environ.update(DEBUG='false',DISCOVERY_AUTO_SCAN='false',EXECUTION_MODE='inline',LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false',ANONYMIZED_TELEMETRY='false')
from pydantic_settings.sources import DotEnvSettingsSource
no_dotenv = patch.object(DotEnvSettingsSource,'__call__',return_value={});no_dotenv.start()

import copy
from contextvars import ContextVar
import io
import uuid
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from fastapi import Header,HTTPException,Response
from jose import jwt
from pypdf import PdfWriter
from app.main import app
from app.config import settings
from app.services.auth import get_current_user,CurrentUser
from app.services import auth,autopilot
from app.agents import orchestrator
from app.api.v1 import resume as resume_api
from app.models.resume import Resume
from app.models.application import JDAnalysis
from test_application_flow import FakeSupabase,FakeResult

ALICE='11111111-1111-4111-8111-111111111111'
BOB='22222222-2222-4222-8222-222222222222'
fixture_uid=ContextVar('fixture_uid',default=None)
db=FakeSupabase()
db.tables['user_profiles']=[{'id':ALICE,'name':'','work_preferences':{}},{'id':BOB,'name':'Bob Fixture','work_preferences':{}}]
for key in type(settings).model_fields:
    if 'KEY' in key or key in {'SENTRY_DSN','SUPABASE_URL','SUPABASE_JWT_SECRET'}:setattr(settings,key,'')
settings.DISCOVERY_AUTO_SCAN=False;settings.MAILBOX_ENABLED=False;settings.MAIL_SEND_ENABLED=False
settings.FRONTEND_URL='http://127.0.0.1:5174'
# CORS middleware reads settings at module construction time.
for middleware in app.user_middleware:
    if middleware.cls.__name__=='CORSMiddleware':middleware.kwargs['allow_origins']=['http://127.0.0.1:5174']

async def verify(token):
    try:claims=jwt.get_unverified_claims(token)
    except Exception:raise HTTPException(401,'Invalid fixture session') from None
    if claims.get('sub') not in {ALICE,BOB}:raise HTTPException(401,'Invalid fixture session')
    return claims
async def user(authorization: str=Header(default='')):
    token=authorization.removeprefix('Bearer ');claims=await verify(token)
    fixture_uid.set(claims['sub'])
    return CurrentUser(id=claims['sub'],email=claims['email'],token=token)
app.dependency_overrides[get_current_user]=user;auth._verify_token=verify
for module in list(sys.modules.values()):
    if getattr(module,'__name__','').startswith('app.'):
        if hasattr(module,'get_supabase_client'):module.get_supabase_client=lambda **kwargs:db
        if hasattr(module,'get_supabase_admin_client'):module.get_supabase_admin_client=lambda:db
autopilot.server_ready=lambda:True
autopilot.account_email=lambda _db,uid:'alice@example.invalid' if uid==ALICE else 'bob@example.invalid'
db.storage=SimpleNamespace(from_=lambda bucket:SimpleNamespace(upload=lambda **kwargs:None))
writer=PdfWriter();writer.add_blank_page(width=612,height=792);buffer=io.BytesIO();writer.write(buffer);PDF=buffer.getvalue()
resume_api.extract_text_from_pdf=lambda raw:'Synthetic résumé: Ada Fixture, Python engineer.'
resume_api.parse_resume_text=lambda text:Resume(name='Ada Fixture' if fixture_uid.get()==ALICE else 'Bob Fixture',headline='ML Engineer',summary='Builds Python tools.',skills={'primary':['Python'],'secondary':[]})
resume_api.embed_resume=lambda *a,**kw:None
async def render(_content):return PDF,1
orchestrator.render_resume_pdf=render;resume_api.render_resume_pdf=render
async def parse(self,**kw):return JDAnalysis(role='ML Engineer',company='FixtureCo',seniority='Entry',required_skills=['Python'],keywords=['Python'],tech_stack=['Python'],tone='professional')
async def tailor(self,base,jd):return {'content':base,'keyword_match_score':100,'missing_keywords':[]}
async def cover(*args,**kw):return 'Synthetic cover letter for FixtureCo.'
async def emails(*args,**kw):return {k:{'subject':'Synthetic draft','body':'Review before sending.'} for k in ('initial','follow_up_1','follow_up_2')}
async def dms(*args,**kw):return {'connection_request':'Synthetic draft','follow_up':'Review this draft.'}
orchestrator.JDParserAgent.parse=parse;orchestrator.ResumeTailorAgent.tailor=tailor
orchestrator.CoverLetterAgent.generate=cover;orchestrator.EmailWriterAgent.generate=emails;orchestrator.DMWriterAgent.generate=dms

def rpc(name,p):
    if name=='create_application_session':
        rows=db.tables.setdefault('application_execution_sessions',[])
        old=next((s for s in rows if s['id']==p['p_id']),None)
        if not old:
            old={'id':p['p_id'],'user_id':p['p_user_id'],'application_id':p['p_application_id'],'page_url':p['p_page_url'],'document_id':None,'created_at':datetime.now(timezone.utc).isoformat()};rows.append(old)
        return FakeResult(old)
    if name=='append_application_event':
        rows=db.tables.setdefault('application_events',[])
        old=next((e for e in rows if e['session_id']==p['p_session_id'] and e['request_key']==p['p_key']),None)
        if old:return FakeResult(old)
        event={'id':len(rows)+1,'user_id':p['p_user_id'],'session_id':p['p_session_id'],'kind':p['p_kind'],'request_key':p['p_key'],'details':p['p_details'],'created_at':datetime.now(timezone.utc).isoformat()};rows.append(event)
        if p['p_kind']=='user_reported_submitted':
            sid=next(s for s in db.tables['application_execution_sessions'] if s['id']==p['p_session_id'])
            db.table('job_applications').update({'status':'applied','applied_at':event['created_at'],'follow_up_at':(datetime.now(timezone.utc)+timedelta(days=5)).isoformat()}).eq('id',sid['application_id']).eq('user_id',p['p_user_id']).execute()
        return FakeResult(event)
    if name=='get_product_metrics':
        # Hosted SQL tests independently verify the real aggregate contracts.
        uid=fixture_uid.get()
        return FakeResult({'generated_applications':sum(a['user_id']==uid for a in db.tables.get('job_applications',[])), 'prepared_applications':0,'attempted_applications':0,'browser_observed_applications':0,
            'user_reported_applications':sum(e['user_id']==uid for e in db.tables.get('application_events',[])),'independently_verified_submissions':None,
            'preparation':{'inspected_fields':0,'filled_fields':0,'preserved_fields':0,'review_fields':0,'invalid_fields':0,'truncated_applications':0,'time_samples':0,'median_seconds':None,'p95_seconds':None},
            'gmail':{'accepted_messages':0,'correlated_replied_messages':0,'reviewed_human_replied_messages':0,'bounce_observed_messages':0,'unknown_outcomes':0},
            'runs':{'failed':0,'recovered':0,'pending':0},'stage_timings':[],'cost_per_application':None,'measurement_note':'Synthetic local workflow; no external mail or employer submission.'})
    raise RuntimeError('Unsupported fixture RPC')
db.rpc=lambda name,p:SimpleNamespace(execute=lambda:rpc(name,p))

@app.get('/__fixture__/resume.pdf')
def fixture_pdf():return Response(PDF,media_type='application/pdf')

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8001,access_log=False,log_level='warning')
