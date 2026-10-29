"""Private operations endpoint. Liveness is public; detailed metrics are not."""
import hmac
import time
import threading

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.services import observability
from app.services.supabase import get_supabase_admin_client

router = APIRouter()
_cache_lock = threading.Lock()
_cache = {'until':0.0,'key':None,'health':None}


def check_readiness():
    try:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise ValueError()
        key = (settings.SUPABASE_URL,settings.SUPABASE_SERVICE_KEY)
        with _cache_lock:
            if time.monotonic() >= _cache['until'] or _cache['key'] != key:
                try:
                    _cache['health'] = get_supabase_admin_client().rpc('get_execution_health',{}).execute().data
                except Exception:
                    _cache['health'] = None
                _cache.update(key=key,until=time.monotonic()+5)
            health = _cache['health']
        if health is None: return False,None
        ready = settings.EXECUTION_MODE != 'durable' or health['healthy_workers'] > 0
        return ready, health
    except Exception:
        return False, None


@router.get('/ready')
def ready():
    ok, health = check_readiness()
    return JSONResponse({'status':'ready' if ok else 'not_ready','database':health is not None,
                         'worker':bool(health and health['healthy_workers']) if settings.EXECUTION_MODE == 'durable' else 'not_required'},status_code=200 if ok else 503)


@router.get('/ops/metrics')
def operational_metrics(x_ops_token: str = Header(default='')):
    if not settings.OBSERVABILITY_TOKEN:
        raise HTTPException(503,'Operations monitoring is not configured')
    if not hmac.compare_digest(x_ops_token.encode(),settings.OBSERVABILITY_TOKEN.encode()):
        raise HTTPException(401,'Invalid operations credentials')
    ok, health = check_readiness()
    return {'ready':ok,'execution':health,'http':observability.metrics.snapshot(),
            'alerts':{'database_unavailable':health is None,'no_healthy_worker':settings.EXECUTION_MODE=='durable' and not (health or {}).get('healthy_workers'),
                      'expired_leases':(health or {}).get('expired_leases',0)>0,'failed_runs':(health or {}).get('failed_24h',0)>0,
                      'queue_delay':(health or {}).get('oldest_ready_seconds',0)>300}}
