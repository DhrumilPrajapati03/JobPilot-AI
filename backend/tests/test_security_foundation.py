import asyncio
import io
import socket
import time
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
import jwt
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.services import auth, safe_fetch, uploads
from app.services.request_limits import UploadBodyLimitMiddleware
from app.services.websocket import manager


OWNER_TOKEN = "owner-test-token-" + "x" * 32


@pytest.fixture
def security_client(monkeypatch):
    monkeypatch.setattr(auth.settings, "OWNER_API_TOKEN", OWNER_TOKEN)
    monkeypatch.setattr(auth.settings, "DISCOVERY_AUTO_SCAN", False)
    # The owner row normally comes from the database; this suite runs without one.
    monkeypatch.setattr(auth, "owner_identity", lambda: ("alice", "alice@example.invalid"))
    with TestClient(app) as client:
        yield client


def token(valid=True):
    return OWNER_TOKEN if valid else OWNER_TOKEN[:-1] + "y"


@pytest.mark.parametrize("credentials", [{}, {"token": "invalid"}, {"token": 123}, []])
def test_ws_rejects_bad_credentials(security_client, credentials):
    with security_client.websocket_connect("/ws/agent-stream/secret-run") as ws:
        ws.send_json(credentials)
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_ws_expiry_ownership_and_replay(security_client):
    run = "security-owned-run"
    foreign = "security-foreign-run"
    manager.register(run, "alice")
    manager.register(foreign, "someone-else")
    asyncio.run(manager.send_update(run, {"step": "complete", "status": "success", "message": "private result"}))
    for run_id, session, expected in [(foreign, token(), 4403), (run, token(valid=False), 4401)]:
        with security_client.websocket_connect(f"/ws/agent-stream/{run_id}") as ws:
            ws.send_json({"token": session})
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == expected
    with security_client.websocket_connect(f"/ws/agent-stream/{run}") as ws:
        ws.send_json({"token": token()})
        assert ws.receive_json()["message"] == "private result"
    manager.finished_at[run] = time.time() - 901
    with security_client.websocket_connect(f"/ws/agent-stream/{run}") as ws:
        ws.send_json({"token": token()})
        assert ws.receive_json()["type"] == "unknown_run"
    assert run not in manager.owners


def test_ws_silent_connection_times_out(security_client):
    with security_client.websocket_connect('/ws/agent-stream/no-credentials') as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_owner_token_is_required_and_compared_exactly(security_client, monkeypatch):
    assert security_client.get('/api/v1/profile/').status_code == 401
    for bad in (token(valid=False), OWNER_TOKEN + 'x', OWNER_TOKEN.upper()):
        assert security_client.get('/api/v1/profile/', headers={'Authorization': f'Bearer {bad}'}).status_code == 401
    assert security_client.get('/api/v1/profile/', headers={'Authorization': f'Basic {OWNER_TOKEN}'}).status_code == 401
    # A missing or too-short server token never authenticates anyone.
    monkeypatch.setattr(auth.settings, 'OWNER_API_TOKEN', 'short')
    assert security_client.get('/api/v1/profile/', headers={'Authorization': 'Bearer short'}).status_code == 503


@pytest.mark.parametrize("path", ["/api/v1/contacts/", "/api/v1/contacts/find?company_domain=example.com", "/api/v1/email/history"])
def test_placeholder_reads_require_auth(security_client, path):
    assert security_client.get(path).status_code in {401, 403}


def test_placeholder_send_requires_auth(security_client):
    assert security_client.post("/api/v1/email/send", json={"to_email": "a@example.com", "to_name": "A", "subject": "Hi", "body": "Draft"}).status_code in {401, 403}


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a", "http://a:b@example.com", "https://example.com:8080"])
def test_unsafe_schemes_credentials_ports(url):
    with pytest.raises(safe_fetch.UnsafeURL):
        asyncio.run(safe_fetch.public_target(url))


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "172.16.0.1", "192.168.1.1", "::1", "fe80::1", "::ffff:127.0.0.1", "224.0.0.1", "100.64.0.1", "64:ff9b::a00:1"])
def test_dns_rejects_non_public_addresses(monkeypatch, address):
    async def check():
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        with pytest.raises(safe_fetch.UnsafeURL):
            await safe_fetch.public_target("https://jobs.example.com/a")
    asyncio.run(check())


def test_public_page_pins_ip_and_validates_redirect(monkeypatch):
    calls = []
    async def check():
        async def resolve(host, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34" if host == 'jobs.example.com' else '127.0.0.1', 443))]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        original_client = httpx.AsyncClient
        def transport(request):
            calls.append(request)
            assert request.url.host == "93.184.216.34"
            assert request.headers["host"] == "jobs.example.com"
            assert request.extensions["sni_hostname"] == "jobs.example.com"
            return httpx.Response(302, headers={"location": "https://internal.example.com/secret"})
        monkeypatch.setattr(safe_fetch.httpx, "AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(transport), **kw))
        with pytest.raises(safe_fetch.UnsafeURL):
            await safe_fetch.fetch_public_html("https://jobs.example.com/job")
        assert len(calls) == 1
    asyncio.run(check())


def test_mixed_dns_answers_are_rejected(monkeypatch):
    async def check():
        async def resolve(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ['93.184.216.34','127.0.0.1']]
        monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', resolve)
        with pytest.raises(safe_fetch.UnsafeURL):
            await safe_fetch.public_target('https://jobs.example.com')
    asyncio.run(check())


def test_redirect_loop_is_bounded(monkeypatch):
    async def target(value):
        return httpx.URL(value), '93.184.216.34'
    monkeypatch.setattr(safe_fetch, 'public_target', target)
    original_client = httpx.AsyncClient
    calls = []
    def response(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': '/again'})
    monkeypatch.setattr(safe_fetch.httpx, 'AsyncClient', lambda **kw: original_client(transport=httpx.MockTransport(response), **kw))
    with pytest.raises(safe_fetch.UnsafeURL):
        asyncio.run(safe_fetch.fetch_public_html('https://jobs.example.com/job'))
    assert len(calls) == safe_fetch.MAX_REDIRECTS + 1


@pytest.mark.parametrize("headers,body,valid", [
    ({"content-type": "text/html"}, b"<h1>Engineer</h1>", True),
    ({"content-type": "application/pdf"}, b"PDF", False),
    ({"content-type": "text/html", "content-encoding": "gzip"}, b"", False),
    ({"content-type": "text/html"}, b"x" * (safe_fetch.MAX_PAGE_BYTES + 1), False),
], ids=['html', 'binary', 'compressed', 'oversized'])
def test_page_content_limits(monkeypatch, headers, body, valid):
    async def target(_value):
        return httpx.URL('https://jobs.example.com/job'), '93.184.216.34'
    monkeypatch.setattr(safe_fetch, "public_target", target)
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers=headers, stream=httpx.ByteStream(body)))
    monkeypatch.setattr(safe_fetch.httpx, "AsyncClient", lambda **kw: original_client(transport=transport, **kw))
    if valid:
        assert "Engineer" in asyncio.run(safe_fetch.fetch_public_html('https://jobs.example.com/job'))
    else:
        with pytest.raises(safe_fetch.UnsafeURL):
            asyncio.run(safe_fetch.fetch_public_html('https://jobs.example.com/job'))


def test_resume_upload_signatures_and_limits():
    for filename, data, code in [('cv.pdf', b'not pdf', 400), ('cv.exe', b'xx', 400),
                                 ('cv.docx', b'not zip', 400), ('cv.pdf', b'x' * (uploads.MAX_RESUME_BYTES + 1), 413)]:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(uploads.read_resume(UploadFile(io.BytesIO(data), filename=filename)))
        assert exc.value.status_code == code
    data, filename = asyncio.run(uploads.read_resume(UploadFile(io.BytesIO(b'%PDF-1.4'), filename='../CV.PDF')))
    assert filename == 'CV.PDF' and data.startswith(b'%PDF-')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('word/document.xml', 'x' * (31 * 1024 * 1024))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(uploads.read_resume(UploadFile(io.BytesIO(archive.getvalue()), filename='cv.docx')))
    assert exc.value.status_code == 413


def test_chunked_body_limit_runs_before_multipart_parser(monkeypatch, security_client):
    monkeypatch.setitem(UploadBodyLimitMiddleware.LIMITS, '/api/v1/resume/upload', 16)
    response = security_client.post('/api/v1/resume/upload', content=iter([b'x' * 10, b'y' * 10]))
    assert response.status_code == 413


def test_alembic_has_one_linear_head_starting_at_the_baseline():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    backend = Path(__file__).resolve().parents[1]
    scripts = ScriptDirectory.from_config(Config(str(backend / 'alembic.ini')))
    assert len(scripts.get_heads()) == 1
    assert scripts.get_base() == '0001'
    baseline = (backend / 'migrations/0001_baseline.sql').read_text(encoding='utf-8')
    # Single-owner local database: no Supabase roles, policies or RLS (checked live in tests/sql/baseline_smoke.sql).
    for forbidden in ('CREATE POLICY', 'ROW LEVEL SECURITY', 'service_role', 'GRANT ', 'storage.'):
        assert forbidden not in baseline.split('set local check_function_bodies')[1], forbidden
