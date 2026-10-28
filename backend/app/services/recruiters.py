"""Evidence-backed domain research. Never infer an address from a name pattern."""
import re
from datetime import datetime, timezone, date
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from app.config import settings
from app.services.mailbox import valid_email
from app.services.referrals import company_key, companies_match


async def hunter(path, params):
    if not settings.HUNTER_API_KEY:
        raise HTTPException(503,'Recruiter research is not configured. No addresses have been guessed.')
    try:
        async with httpx.AsyncClient(timeout=20,trust_env=False,follow_redirects=False) as client:
            response=await client.get('https://api.hunter.io/v2/'+path,params=params,headers={'X-API-KEY':settings.HUNTER_API_KEY})
        if response.status_code != 200: raise ValueError('Provider request not complete')
        return response.json()['data']
    except (httpx.HTTPError,ValueError,KeyError) as exc:
        raise HTTPException(503,'Recruiter research could not be verified. Try again later.') from exc


def domain_name(value):
    value=value.strip().lower()
    if len(value)>253 or not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',value):
        raise ValueError('Enter a company domain without a URL or path')
    return value


async def research(db,uid,application,domain):
    domain=domain_name(domain)
    data=await hunter('domain-search',{'domain':domain,'department':'hr','limit':10})
    if not companies_match(company_key(data.get('organization') or ''),company_key(application['company'])):
        raise HTTPException(409,'The research provider did not confirm this domain belongs to the application company.')
    leads=[]; checked=0
    for candidate in data.get('emails',[])[:10]:
        position=candidate.get('position') or ''
        if not re.search(r'\b(recruit(?:er|ing|ment)?|talent|human resources|hr|people)\b',position,re.I): continue
        if candidate.get('provenance') != 'found': continue
        try: email=valid_email(candidate.get('value',''))
        except ValueError: continue
        if email.rsplit('@',1)[1].lower()!=domain: continue
        sources=[]
        for source in candidate.get('sources',[])[:20]:
            url=source.get('uri') or ''
            try: parsed=urlsplit(url)
            except ValueError: continue
            if parsed.scheme=='https' and parsed.hostname and parsed.username is None and parsed.password is None:
                sources.append({'url':url,'last_seen_on':source.get('last_seen_on'),'extracted_on':source.get('extracted_on')})
        if not sources or checked>=5: continue
        verification=await hunter('email-verifier',{'email':email}); checked+=1
        if verification.get('status')!='valid' or verification.get('accept_all') or verification.get('disposable'): continue
        if (verification.get('email') or '').lower()!=email.lower(): continue
        try:
            verified_on=date.fromisoformat(verification.get('verification',{}).get('date') or '')
        except ValueError: continue
        if not 0 <= (datetime.now(timezone.utc).date()-verified_on).days <= 31: continue
        full_name=' '.join(filter(None,[candidate.get('first_name'),candidate.get('last_name')]))
        if not full_name: continue
        leads.append({'user_id':uid,'application_id':application['id'],'email':email,'full_name':full_name,'position':position,'domain':domain,
            'sources':sources+[{'provider':'hunter','verification_date':verification.get('verification',{}).get('date')}],
            'verification':'provider_valid','verified_at':datetime.now(timezone.utc).isoformat()})
    if leads: db.table('recruiter_leads').upsert(leads,on_conflict='user_id,application_id,email').execute()
    return {'contacts':leads,'total':len(leads),'checked':checked,
        'note':'Email deliverability is provider-verified. Review source dates, role, and employer before contacting anyone.'}
