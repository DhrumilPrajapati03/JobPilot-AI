import asyncio
import copy
import json
from pathlib import Path

import pytest

from app.api.v1 import profile as profile_api
from app.config import settings
from app.models.resume import Resume
from app.models.user import WorkPreferences
from app.agents.resume_tailor import ResumeTailorAgent
from app.resume_engine.validator import validate_no_hallucinations
from app.services import discovery, identity, matching_semantics
from app.services.eligibility import evaluate_eligibility, experience_requirement
from app.services.job_identity import canonical_url, identity_keys
from app.services.job_matching import build_profile, score_posting
from app.services.matching_evaluation import evaluate_dataset
from test_application_flow import BASE_RESUME, USER_ID, db, client  # noqa: F401
from test_durable_execution import MemoryStore
from app.workflows.application import run_application
from app.workflows.context import ExecutionContext
from app.services.runs import PermanentRunError
from app.services.job_boards import Posting

REAL_TAILOR = ResumeTailorAgent.tailor


def test_confirmation_is_explicit_scoped_and_invalidated_by_content_change(db, client):
    vault = client.get('/api/v1/profile/facts').json()
    assert vault['facts'] and not vault['complete'] and vault['confirmed_count'] == 0
    ids = [f['id'] for f in vault['facts']]
    result = client.post('/api/v1/profile/facts/confirm', json={'source_digest': vault['source_digest'], 'fact_ids': ids})
    assert result.status_code == 200 and result.json()['complete']
    assert {r['user_id'] for r in db.tables['identity_confirmations']} == {USER_ID}
    assert client.delete('/api/v1/profile/facts/' + ids[0]).status_code == 200
    assert not client.get('/api/v1/profile/facts').json()['complete']
    db.tables['resumes'][0]['skills']['primary'].append('A new user-entered skill')
    result = client.post('/api/v1/profile/facts/confirm', json={'source_digest': vault['source_digest'], 'fact_ids': ids})
    assert result.status_code == 409
    assert client.get('/api/v1/profile/facts').json()['confirmed_count'] == 0


def test_other_account_confirmation_does_not_confirm_my_facts(db, client):
    vault = client.get('/api/v1/profile/facts').json()
    db.tables['identity_confirmations'] = [{'user_id':'stranger', 'source_digest':vault['source_digest'], 'fact_id':f['id']} for f in vault['facts']]
    assert client.get('/api/v1/profile/facts').json()['confirmed_count'] == 0
    assert client.post('/api/v1/profile/facts/confirm', json={'source_digest':vault['source_digest'], 'fact_ids':['f'*64]}).status_code == 422
    client.delete('/api/v1/profile/facts/' + vault['facts'][0]['id'])
    assert len(db.tables['identity_confirmations']) == len(vault['facts'])


def test_resume_metadata_change_does_not_invalidate_confirmation():
    original = copy.deepcopy(BASE_RESUME)
    updated = {**original, 'id':'different-row', 'updated_at':'2026-10-27T00:00:00Z'}
    assert identity.extract_facts(original) == identity.extract_facts(updated)


@pytest.mark.parametrize('description,minimum', [
    ('Minimum three years of Python experience.',3),('3 to 5 years of professional experience',3),
    ('0–2 years of relevant experience',0),('Five years of experience preferred',None),
    ('Our company has twenty years of industry experience',None),('Equipment warranty lasts three years.',None),
    ('Twenty years of relevant experience required',20),('Three-year professional experience required',3),
])
def test_requirement_extraction_retains_minimum_and_ignores_benefits(description, minimum):
    assert experience_requirement(description)[0] == minimum


def test_unknown_authorization_requires_review_and_skill_similarity_cannot_override_it():
    prefs = WorkPreferences(career_level='entry',experience_years=1,preferred_roles=['AI Engineer'])
    result = evaluate_eligibility({'title':'Junior AI Engineer','description':'Must be authorized to work in India. Python.', 'location':'India','remote':True},prefs)
    assert result['status'] == 'review'
    assert any(c['dimension'] == 'authorization' and c['evidence'] for c in result['checks'])
    profile = build_profile(BASE_RESUME,prefs)
    fit, flags = discovery._evaluate(prefs,profile,'India',ats='greenhouse',company='Co',title='Senior AI Engineer',description='Python, SQL, Docker, FastAPI',location='India',remote=True)
    assert fit.score == 0 and flags and fit.details['eligibility']['status'] == 'ineligible'


def test_labeled_dataset_lexical_fallback_has_no_false_positive(monkeypatch):
    monkeypatch.setattr(settings,'MATCHING_SEMANTIC',False)
    dataset = json.loads((Path(__file__).parents[1]/'evaluations/matching_cases.json').read_text())
    report = evaluate_dataset(dataset)
    assert report['eligibility_accuracy'] == 1
    assert report['false_positives'] == 0
    assert report['recall'] >= .85
    assert report['semantic_cases'] == 0


def test_cached_semantic_model_adds_role_paraphrase_recall(monkeypatch):
    if matching_semantics.local_model() is None:
        pytest.skip('Install the local MiniLM model to run this optional model integration test')
    monkeypatch.setattr(settings,'MATCHING_SEMANTIC',True)
    dataset = json.loads((Path(__file__).parents[1]/'evaluations/matching_cases.json').read_text())
    report = evaluate_dataset(dataset)
    assert report['eligibility_accuracy'] == 1 and report['false_positives'] == 0
    assert report['recall'] >= .9 and report['semantic_cases'] == len(dataset['cases'])
    assert next(r for r in report['outcomes'] if r['id']=='semantic-developer-title')['actual_relevant']


def test_missing_semantic_model_is_explicit_and_does_not_call_a_provider(monkeypatch):
    monkeypatch.setattr(settings,'MATCHING_SEMANTIC',True)
    monkeypatch.setattr(matching_semantics,'vector',lambda *a: (_ for _ in ()).throw(FileNotFoundError()))
    fit = score_posting('ML Engineer','Python and SQL',build_profile(BASE_RESUME,WorkPreferences()))
    assert fit.details['semantic_model'] == 'unavailable'
    assert fit.details['components']['semantic'] is None
    assert fit.details['weights']['semantic'] == 0


def test_dedup_tracks_same_url_without_merging_distinct_requisitions():
    original = {'company':'Co','title':'Junior ML Engineer','location':'India','url':'https://boards.greenhouse.io/co/jobs/123?utm_source=x','description':'Build Python products'}
    copy_post = {**original,'url':'https://job-boards.greenhouse.io/co/jobs/123?gh_src=tracking#apply'}
    another = {**original,'url':'https://boards.greenhouse.io/co/jobs/124'}
    assert identity_keys(original)[0] == identity_keys(copy_post)[0]
    assert not set(identity_keys(original)) & set(identity_keys(another))
    assert canonical_url('https://example.com/apply?jobId=1') != canonical_url('https://example.com/apply?jobId=2')


def test_same_title_different_locations_and_requisition_ids_are_distinct():
    original = {'company':'Co','title':'ML Engineer','location':'India','url':'https://jobs.example.com/co/jobs/123','description':'Build Python and SQL applications. ' * 5}
    another = {**original,'location':'United States','url':'https://jobs.example.com/co/jobs/124'}
    assert not set(identity_keys(original)) & set(identity_keys(another))
    same_city = {**another,'location':'India'}
    assert not set(identity_keys(original)) & set(identity_keys(same_city))


def test_jd_skill_is_not_resume_evidence_and_credentials_are_fixed():
    tailored = copy.deepcopy(BASE_RESUME)
    tailored['skills']['primary'].append('Kubernetes')
    tailored['education'][0]['degree']='PhD'
    tailored['experience'][0]['bullets'].append('Improved throughput by 900%')
    errors = validate_no_hallucinations(tailored,BASE_RESUME,['Kubernetes'])
    assert any('Kubernetes' in e for e in errors)
    assert any('credential' in e for e in errors)
    assert any('numeric' in e for e in errors)


def test_tailor_rejects_whole_unsupported_output_instead_of_fixing_only_tags(monkeypatch):
    output=copy.deepcopy(BASE_RESUME)
    output['skills']['primary'].append('Kubernetes')
    class LLM:
        def with_structured_output(self,*a,**kw): return self
        async def ainvoke(self,*a,**kw): return Resume(**output)
    monkeypatch.setattr(ResumeTailorAgent,'_get_best_llm',lambda self: LLM())
    monkeypatch.setattr('app.agents.resume_tailor.search_relevant',lambda *a,**kw: [])
    agent=ResumeTailorAgent()
    result=asyncio.run(REAL_TAILOR(agent,BASE_RESUME,{'required_skills':['Kubernetes']}))
    assert agent.used_fallback and result['violations']
    assert 'Kubernetes' not in result['content']['skills']['primary']


def test_auto_drafting_waits_for_explicit_current_resume_confirmation(db):
    prefs=WorkPreferences(auto_draft_enabled=True,auto_draft_min_score=50)
    db.tables['job_postings']=[{'id':'posting','user_id':USER_ID,'title':'Junior AI Engineer','company':'Co','description':'Python',
        'location':'India','remote':True,'fit_score':99,'status':'new'}]
    assert discovery.start_auto_drafts(db,USER_ID,prefs) == []
    assert db.tables['job_postings'][0]['status'] == 'new'


@pytest.mark.parametrize('change', ['revoked','changed','disabled'])
def test_auto_recovery_rechecks_confirmation_and_preferences_before_cached_nodes(db,change):
    store=MemoryStore(db)
    store.row['inputs']['auto']=True
    store.row['checkpoints']['jd_parsing']={'analysis':{'role':'AI Engineer'}}
    store.row['checkpoints']['profile_loading']={'resume':copy.deepcopy(db.tables['resumes'][0])}
    db.tables['user_profiles'][0]['work_preferences']={'auto_draft_enabled':True}
    if change == 'changed':
        db.tables['resumes'][0]['summary']='Changed after the worker checkpoint'
    source_digest,facts=identity.extract_facts(db.tables['resumes'][0])
    db.tables['identity_confirmations']=[{'user_id':USER_ID,'source_digest':source_digest,'fact_id':f['id']} for f in facts]
    if change == 'revoked': db.tables['identity_confirmations'].pop()
    if change == 'disabled': db.tables['user_profiles'][0]['work_preferences']['auto_draft_enabled']=False
    ctx=ExecutionContext(store,store.claim('replacement'))
    with pytest.raises(PermanentRunError): asyncio.run(run_application(ctx,''))
    assert store.material_commits == 0 and not store.events_log


@pytest.mark.parametrize('change', ['location','seniority'])
def test_rescan_updates_existing_hiring_scope_without_resetting_posting_identity(db,monkeypatch,change):
    db.tables['user_profiles'][0]['work_preferences']={'preferred_roles':['ML Engineer'],'career_level':'entry','experience_years':1}
    db.tables['job_sources']=[{'id':'source','user_id':USER_ID,'ats':'lever','slug':'co','company':'Co','enabled':True}]
    state={'title':'Junior ML Engineer','location':'India'}
    async def fetch(*a,**kw):
        return 'Co',[Posting('lever','stable-id','Co',state['title'],state['location'],True,'https://jobs.lever.co/co/stable-id','Python and SQL. One year of relevant experience.',None)]
    monkeypatch.setattr(discovery,'fetch_board',fetch)
    asyncio.run(discovery.scan_user(db,USER_ID,auto_draft=False))
    first=copy.deepcopy(db.tables['job_postings'][0])
    assert first['status']=='new'
    if change=='location': state['location']='United States'
    else: state['title']='Senior ML Engineer'
    asyncio.run(discovery.scan_user(db,USER_ID,auto_draft=False))
    updated=db.tables['job_postings'][0]
    assert len(db.tables['job_postings'])==1 and updated['id']==first['id']
    assert updated['status']=='skipped' and updated['matching_details']['eligibility']['status']!='eligible'
