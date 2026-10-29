"""Bounded process metrics and allowlisted diagnostics. Never log request data."""
import json
import logging
import re
import threading
import time
import uuid

from app.config import settings

log = logging.getLogger('jobpilot.requests')
BUCKETS = (50, 100, 250, 500, 1000, 2500, 5000, 10000)


class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.rows = {}
        self.started = time.monotonic()

    def observe(self, method, route, status, elapsed):
        with self.lock:
            key = (method, route)
            if key not in self.rows and len(self.rows) >= 128:
                key = ('OTHER', '<overflow>')
            row = self.rows.setdefault(key, {'count':0,'errors':0,'client_errors':0,'total_ms':0.0,'buckets':[0]*9})
            row['count'] += 1
            row['errors'] += status >= 500
            row['client_errors'] += 400 <= status < 500
            row['total_ms'] += elapsed
            index = next((i for i,b in enumerate(BUCKETS) if elapsed <= b),8)
            row['buckets'][index] += 1

    def snapshot(self):
        with self.lock:
            result = []
            for (method,route), r in sorted(self.rows.items()):
                cumulative = 0; p95 = None
                for index,n in enumerate(r['buckets']):
                    cumulative += n
                    if cumulative >= r['count'] * .95:
                        p95 = BUCKETS[index] if index < len(BUCKETS) else None
                        break
                result.append({'method':method,'route':route,'requests':r['count'],'server_errors':r['errors'],
                    'client_errors':r['client_errors'],'mean_ms':round(r['total_ms']/r['count'],2),'p95_bucket_upper_ms':p95})
            return {'scope':'this API process since startup','uptime_seconds':round(time.monotonic()-self.started), 'routes':result}


metrics = Metrics()


def safe_sentry_event(event, hint):
    """Reconstruct rather than recursively trying to redact untrusted payloads."""
    kind = type(hint['exc_info'][1]).__name__ if hint.get('exc_info') else 'ApplicationError'
    kind = re.sub(r'[^A-Za-z0-9_]', '', kind)[:80] or 'ApplicationError'
    return {'level':'error','message':'Unhandled JobPilot error','exception':{'values':[{'type':kind,'value':'Details omitted for privacy'}]},
            'fingerprint':['jobpilot',kind]}


def setup_monitoring():
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        log.addHandler(handler)
    log.setLevel(logging.INFO if settings.REQUEST_LOGS_ENABLED else logging.WARNING)
    log.propagate = False
    if settings.SENTRY_DSN:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.SENTRY_DSN,default_integrations=False,auto_enabling_integrations=False,
            send_default_pii=False,max_request_body_size='never',traces_sample_rate=None,
            before_send=safe_sentry_event,before_breadcrumb=lambda b,h:None,auto_session_tracking=False,
            send_client_reports=False)


def capture_error(exc):
    if settings.SENTRY_DSN:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)


class RequestMetricsMiddleware:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope,receive,send)
        started = time.perf_counter(); request_id = str(uuid.uuid4()); status = 500
        method = scope.get('method','OTHER')
        if method not in {'GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'}: method = 'OTHER'
        async def measured_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                headers = [(k,v) for k,v in message.get('headers',[]) if k.lower() not in (b'x-request-id',b'server-timing')]
                headers += [(b'x-request-id',request_id.encode()),(b'server-timing',f'app;dur={(time.perf_counter()-started)*1000:.2f}'.encode())]
                message = {**message,'headers':headers}
            await send(message)
        try:
            await self.app(scope,receive,measured_send)
        except Exception as exc:
            capture_error(exc)
            raise
        finally:
            elapsed = (time.perf_counter()-started)*1000
            route = getattr(scope.get('route'),'path',None) or '<unmatched>'
            metrics.observe(method,route,status,elapsed)
            if settings.REQUEST_LOGS_ENABLED:
                log.info(json.dumps({'request_id':request_id,'method':method,'route':route,'status':status,'elapsed_ms':round(elapsed,2)}))
