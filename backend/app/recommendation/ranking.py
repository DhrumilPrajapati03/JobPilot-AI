"""Optional offline shortlist reranking. Baseline scores and eligibility stay binding."""
import math
import threading
import time
from functools import lru_cache
from pathlib import Path
import json
import hashlib
from app.config import settings
from app.services.identity import digest

_lock = threading.Lock()


def verify_manifest(path):
    root = Path(path)
    if not root.is_dir() or not (root / 'config.json').is_file():
        raise ValueError('No prepared model directory')
    manifest=json.loads((root/'jobpilot-model.json').read_text())
    if not manifest.get('files') or not any(name.endswith('.safetensors') for name in manifest['files']):
        raise ValueError('Prepared safetensors weights are required')
    for name,expected in manifest['files'].items():
        file=(root/name).resolve()
        if not file.is_relative_to(root.resolve()) or hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
            raise ValueError('Model manifest mismatch')
    return root


@lru_cache(maxsize=1)
def model(path):
    root=verify_manifest(path)
    from sentence_transformers import CrossEncoder
    return CrossEncoder(str(root.resolve()), device='cpu', local_files_only=True, trust_remote_code=False, max_length=512)


def rerank(profile_text, postings, scorer=None):
    started = time.perf_counter()
    baseline = sorted(postings, key=lambda p: (-float(p.get('fit_score') or 0), p['id']))
    result = {'version': 'v3-shadow', 'baseline_ids': [p['id'] for p in baseline],
              'ordered_ids': [p['id'] for p in baseline], 'status': 'baseline_fallback',
              'promotion': 'not_evaluated', 'model_digest': None}
    try:
        if not scorer and not settings.RERANKER_PATH:
            raise ValueError('Not configured')
        # Only already-eligible roles enter the experiment; unknown/ineligible order is retained.
        candidates = [p for p in baseline if (p.get('matching_details') or {}).get('eligibility', {}).get('status') == 'eligible'][:20]
        if not candidates:
            raise ValueError('No eligible shortlist')
        pairs = [(profile_text[:5000], f"{p.get('title', '')}\n{p.get('company', '')}\n{p.get('description', '')[:5000]}") for p in candidates]
        with _lock:
            values = (scorer or model(settings.RERANKER_PATH).predict)(pairs)
        values = [float(x) for x in values]
        if len(values) != len(candidates) or not all(math.isfinite(x) for x in values):
            raise ValueError('Invalid model output')
        ordered = sorted(zip(candidates, values), key=lambda x: (-x[1], -float(x[0].get('fit_score') or 0), x[0]['id']))
        ids = [p['id'] for p, _ in ordered]
        result.update(ordered_ids=ids+[p['id'] for p in baseline if p['id'] not in ids], status='experimental',
                      model_digest=digest((Path(settings.RERANKER_PATH)/'jobpilot-model.json').read_text()) if not scorer else 'test-scorer')
    except Exception:
        # No model download, partial order, changed fit score or silent eligibility bypass.
        pass
    result['duration_ms'] = round((time.perf_counter()-started)*1000, 3)
    return result


async def execute(ctx):
    import asyncio
    from app.services.identity import load_vault
    from app.services.runs import PermanentRunError
    db, uid = ctx.store.client, ctx.run['user_id']
    ids = ctx.run['inputs']['posting_ids']
    async def evaluate():
        rows = await asyncio.to_thread(lambda: db.table('job_postings').select('*').eq('user_id', uid).in_('id', ids).execute().data)
        if len(rows) != len(ids):
            raise PermanentRunError('A posting was removed. Request a new experiment.')
        vault = await asyncio.to_thread(load_vault, db, uid)
        text = ' '.join(str(f['value']) for f in vault['facts'] if f['confirmed'])
        if not text:
            raise PermanentRunError('Confirm your résumé facts before a ranking experiment.')
        result = await asyncio.to_thread(rerank, text, rows)
        result['profile_digest'] = vault['source_digest']
        result['job_digests'] = {p['id']: digest([p.get('title'),p.get('description')]) for p in rows}
        return result
    return await ctx.stage('recommendation_experiment', 'Comparing the eligible shortlist with the optional local reranker', evaluate)
