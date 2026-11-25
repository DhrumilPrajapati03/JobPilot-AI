"""Real provider-adapter contracts and import -> facts -> matching regressions."""
import asyncio
import copy
import json
from types import SimpleNamespace

import httpx
import pytest

from app.api.v1 import discovery as discovery_api, resume as resume_api
from app.models.resume import Resume, ResumeContent
from app.services import discovery, llm, parser
from app.services.llm import OutputParserException
from app.services.job_boards import Posting
from test_application_flow import USER_ID, db, client  # noqa: F401


CONTENT = {
    'name': 'Ada Example', 'headline': 'Machine Learning Engineer',
    'summary': 'Builds Python and RAG applications.',
    'experience': [{'company': 'Example Labs', 'role': 'ML Engineer',
                    'duration': '2025 - Present', 'bullets': ['Built Python APIs.']}],
    'skills': {'primary': ['Python', 'FastAPI'], 'secondary': ['RAG', 'Docker']},
}


@pytest.fixture
def groq_factory(monkeypatch):
    """Use the real provider adapter and openai SDK against Groq's API shape, with only HTTP mocked."""
    monkeypatch.setattr(llm, '_cooldown', {})
    monkeypatch.setattr(llm.settings, 'GROQ_API_KEY', 'synthetic-test-key')
    clients = []

    def create(payload, name='openai/gpt-oss-20b', status=200):
        requests = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            # Reproduce the reported provider failure if code uses tools again.
            if body.get('tools'):
                return httpx.Response(400, json={'error': {
                    'message': "Tool call validation failed: attempted to call tool 'resume'",
                    'code': 'tool_use_failed', 'failed_generation': 'PRIVATE RESUME',
                }})
            if status != 200:
                return httpx.Response(status, json={'error': {
                    'message': 'Rate limit exceeded PRIVATE RESUME', 'type': 'rate_limit',
                }})
            return httpx.Response(200, json={
                'id': 'fixture', 'created': 1, 'model': name,
                'choices': [{'index': 0, 'finish_reason': 'stop',
                             'message': {'role': 'assistant', 'content': json.dumps(payload)}}],
            })

        transport = httpx.MockTransport(respond)
        sync = httpx.Client(transport=transport)
        asynchronous = httpx.AsyncClient(transport=transport)
        clients.append((sync, asynchronous))
        return llm.ChatModel('groq', name, max_retries=0,
                             http_client=sync, http_async_client=asynchronous), requests

    yield create
    for sync, asynchronous in clients:
        sync.close()
        asyncio.run(asynchronous.aclose())


@pytest.mark.parametrize('asynchronous', [False, True])
def test_groq_extraction_uses_json_not_tool_names(groq_factory, asynchronous):
    model, requests = groq_factory(CONTENT)
    structured = llm.with_structured(model, ResumeContent)
    prompt = [('human', 'Synthetic resume')]
    result = asyncio.run(structured.ainvoke(prompt)) if asynchronous else structured.invoke('Synthetic resume')
    assert isinstance(result, ResumeContent) and result.skills.primary == ['Python', 'FastAPI']
    request = requests[0]
    assert request['response_format'] == {'type': 'json_object'}
    assert 'tools' not in request and 'tool_choice' not in request
    assert request['messages'][0]['role'] == 'system'
    schema = json.loads(request['messages'][0]['content'].split('\n', 1)[1])
    assert 'experience' in schema['properties']
    assert not {'id', 'user_id', 'version', 'created_at', 'updated_at'} & schema['properties'].keys()


def test_json_mode_still_rejects_invalid_resume_schema(groq_factory):
    model, _ = groq_factory({'experience': 'PRIVATE RESUME'})
    with pytest.raises(OutputParserException):
        llm.with_structured(model, ResumeContent).invoke('Synthetic resume')


def test_groq_json_extraction_keeps_model_quota_fallback(groq_factory, capsys):
    limited, limited_requests = groq_factory({}, name='limited', status=429)
    working, working_requests = groq_factory(CONTENT, name='working')
    chain = llm.ModelChain([limited, working], ['limited', 'working'])
    result = llm.with_structured(chain, ResumeContent).invoke('Synthetic resume')
    assert result.name == 'Ada Example'
    assert len(limited_requests) == len(working_requests) == 1
    assert 'PRIVATE RESUME' not in capsys.readouterr().out


def test_resume_parser_discards_generated_database_metadata(groq_factory, monkeypatch):
    model, _ = groq_factory({**CONTENT, 'id': 'foreign-row', 'user_id': 'stranger',
                             'version': 'foreign-version', 'created_at': 'invalid timestamp'})
    monkeypatch.setattr(parser, 'get_default_llm', lambda **kw: model)
    result = parser.parse_resume_text('Synthetic professional content')
    assert isinstance(result, Resume) and result.name == CONTENT['name']
    assert result.id is None and result.user_id is None and result.created_at is None
    assert result.version == 'base'


@pytest.mark.parametrize('payload', [{}, {'name': 'Ada Example'}, {'experience': 'PRIVATE RESUME'}])
def test_failed_import_is_private_and_preserves_saved_resume(db, client, groq_factory, monkeypatch, payload):
    model, _ = groq_factory(payload)
    monkeypatch.setattr(parser, 'get_default_llm', lambda **kw: model)
    monkeypatch.setattr(resume_api, 'extract_text_from_pdf', lambda _: 'PRIVATE RESUME')
    original = copy.deepcopy(db.tables['resumes'])
    response = client.post('/api/v1/resume/upload', files={'file': ('resume.pdf', b'%PDF-1.4', 'application/pdf')})
    assert response.status_code == 503
    assert 'Try importing it again' in response.json()['detail']
    assert 'PRIVATE RESUME' not in response.text and 'failed_generation' not in response.text
    assert db.tables['resumes'] == original


def test_provider_exception_is_not_returned_in_upload_response(db, client, monkeypatch):
    monkeypatch.setattr(resume_api, 'extract_text_from_pdf', lambda _: 'Synthetic source')

    def fail(_):
        raise RuntimeError('400 tool_use_failed failed_generation PRIVATE RESUME secret-token')

    monkeypatch.setattr(resume_api, 'parse_resume_text', fail)
    original = copy.deepcopy(db.tables['resumes'])
    response = client.post('/api/v1/resume/upload', files={'file': ('resume.pdf', b'%PDF-1.4', 'application/pdf')})
    assert response.status_code == 503 and 'secret-token' not in response.text
    assert 'PRIVATE RESUME' not in response.text and db.tables['resumes'] == original


def test_imported_resume_can_be_confirmed_and_used_in_job_feed(db, client, groq_factory, monkeypatch):
    model, _ = groq_factory(CONTENT)
    monkeypatch.setattr(parser, 'get_default_llm', lambda **kw: model)
    monkeypatch.setattr(resume_api, 'extract_text_from_pdf', lambda _: 'Ada builds Python and RAG applications.')
    monkeypatch.setattr(resume_api, 'embed_resume', lambda *a: None)
    db.storage = SimpleNamespace(from_=lambda _: SimpleNamespace(upload=lambda **kw: None))
    imported = client.post('/api/v1/resume/upload', files={'file': ('resume.pdf', b'%PDF-1.4', 'application/pdf')})
    assert imported.status_code == 200 and imported.json()['skills']['primary'] == ['Python', 'FastAPI']
    assert imported.json()['user_id'] == USER_ID and imported.json()['id'] == db.tables['resumes'][0]['id']
    vault = client.get('/api/v1/profile/facts').json()
    assert vault['facts'] and not vault['complete']
    assert any(f['value'] == 'Python' for f in vault['facts'])
    confirmed = client.post('/api/v1/profile/facts/confirm', json={
        'source_digest': vault['source_digest'], 'fact_ids': [f['id'] for f in vault['facts']],
    })
    assert confirmed.status_code == 200 and confirmed.json()['complete']
    client.post('/api/v1/profile/update', json={'work_preferences': {'preferred_roles': ['Machine Learning Engineer']}})
    assert client.get('/api/v1/profile/onboarding').json()['ready_for_matching']

    async def fetch(*args, **kwargs):
        return 'Example Labs', [Posting(ats='greenhouse', external_id='fixture', company='Example Labs',
            title='Machine Learning Engineer', location='Remote - India', remote=True,
            url='https://boards.greenhouse.io/example/jobs/fixture',
            description='Build Python, FastAPI, RAG and Docker applications.', posted_at=None)]

    monkeypatch.setattr(discovery, 'fetch_board', fetch)
    monkeypatch.setattr(discovery_api, 'get_db', lambda *a, **k: db)
    monkeypatch.setattr(llm.settings, 'MATCHING_SEMANTIC', False)
    db.tables['job_sources'] = [{'id': 'fixture-source', 'user_id': USER_ID, 'enabled': True,
                                 'ats': 'greenhouse', 'slug': 'example', 'company': 'Example Labs'}]
    summary = asyncio.run(discovery.scan_user(db, USER_ID, auto_draft=False))
    assert summary['new'] == 1
    response = client.get('/api/v1/discovery/postings?min_score=0')
    assert response.status_code == 200
    posting = db.tables['job_postings'][0]
    assert posting['fit_score'] > 0
    assert posting['matching_details']['identity']['complete']
    assert 'python' in [s.lower() for s in posting['matching_details']['confirmed_matched_skills']]
