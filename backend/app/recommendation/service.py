from app.services.identity import digest, load_vault
from fastapi import HTTPException


def create_snapshot(db, uid: str, ids: list[str], key: str):
    existing = db.table('recommendation_runs').select('*').eq('user_id', uid).eq('request_key', key).execute().data
    if existing:
        if [i['posting_id'] for i in existing[0]['items']] != ids:
            raise HTTPException(409, 'This request key was used for a different displayed list.')
        return existing[0]
    rows = db.table('job_postings').select('*').eq('user_id', uid).in_('id', ids).execute().data
    owned = {r['id']: r for r in rows}
    if len(owned) != len(ids):
        raise HTTPException(404, 'One or more opportunities are no longer available.')
    vault = load_vault(db, uid)
    items = []
    for position, pid in enumerate(ids, 1):
        row = owned[pid]
        details = row.get('matching_details') or {}
        items.append({'posting_id': pid, 'position': position, 'score': row.get('fit_score'),
                      'job_digest': digest([row.get('title'), row.get('description'), row.get('url')]),
                      'matching_version': details.get('version', 'v2'),
                      'semantic_model': details.get('semantic_model'),
                      'eligibility': (details.get('eligibility') or {}).get('status')})
    payload = {'user_id': uid, 'request_key': key, 'model_version': 'v2-display-observation',
               'profile_digest': digest([vault['source_digest'], sorted(f['id'] for f in vault['facts'] if f['confirmed'])]),
               'items': items}
    # Display order is a client observation, not a trusted model-quality label.
    try:
        return db.table('recommendation_runs').insert(payload).execute().data[0]
    except Exception as exc:
        if getattr(exc, 'code', '') == '23505':
            rows = db.table('recommendation_runs').select('*').eq('user_id', uid).eq('request_key', key).execute().data
            if rows:
                if [i['posting_id'] for i in rows[0]['items']] != ids:
                    raise HTTPException(409, 'This request key was used for a different displayed list.') from None
                return rows[0]
        raise


def set_feedback(db, uid, pid, signal, reason):
    if not db.table('job_postings').select('id').eq('user_id', uid).eq('id', pid).execute().data:
        raise HTTPException(404, 'Opportunity not found')
    if signal == 'clear':
        db.table('recommendation_feedback').delete().eq('user_id', uid).eq('posting_id', pid).execute()
        return {'posting_id': pid, 'signal': None, 'reason': None}
    from datetime import datetime, timezone
    row = {'user_id': uid, 'posting_id': pid, 'signal': signal, 'reason': reason,
           'updated_at': datetime.now(timezone.utc).isoformat()}
    return db.table('recommendation_feedback').upsert(row, on_conflict='user_id,posting_id').execute().data[0]
