"""Verify Storage isolation with two temporary users; remove fixtures in finally.

Run explicitly from backend with --project matching the .env Supabase ref.
No email is sent: users are admin-created and already confirmed.
"""
import argparse
import io
import json
import secrets
import uuid

import httpx
from dotenv import dotenv_values
from pypdf import PdfWriter


def check(project):
    config=dotenv_values('.env')
    url=(config.get('SUPABASE_URL') or '').rstrip('/')
    if url != f'https://{project}.supabase.co':
        raise SystemExit('The explicit project ref must match SUPABASE_URL in .env')
    service=config.get('SUPABASE_SERVICE_KEY') or ''; anon=config.get('SUPABASE_KEY') or ''
    if not service or not anon: raise SystemExit('Configure the server and public Supabase keys locally')
    privileged={'apikey':service,'Authorization':'Bearer '+service}
    created=[]; paths=[]; passed=False; cleanup=True
    writer=PdfWriter(); writer.add_blank_page(width=72,height=72); stream=io.BytesIO(); writer.write(stream); pdf=stream.getvalue()
    with httpx.Client(base_url=url,timeout=30,trust_env=False,follow_redirects=False) as client:
        try:
            sessions=[]
            for _ in range(2):
                address='jobpilot-storage-'+uuid.uuid4().hex+'@example.invalid'; password=secrets.token_urlsafe(40)
                response=client.post('/auth/v1/admin/users',headers=privileged,json={'email':address,'password':password,'email_confirm':True})
                assert response.status_code in (200,201), f'Fixture creation failed ({response.status_code})'
                user=response.json(); uuid.UUID(user['id'])
                assert user['email']==address
                created.append(user['id'])
                login=client.post('/auth/v1/token?grant_type=password',headers={'apikey':anon},json={'email':address,'password':password})
                assert login.status_code==200, f'Fixture login failed ({login.status_code})'
                sessions.append({'apikey':anon,'Authorization':'Bearer '+login.json()['access_token']})
            path=created[0]+'/'+uuid.uuid4().hex+'.pdf'; paths.append(path)
            upload=client.post('/storage/v1/object/resumes/'+path,headers={**sessions[0],'Content-Type':'application/pdf'},content=pdf)
            assert upload.status_code==200, f'Owner upload failed ({upload.status_code})'
            updated=pdf+b'\n% ownership fixture\n'
            replace=client.post('/storage/v1/object/resumes/'+path,headers={**sessions[0],'Content-Type':'application/pdf','x-upsert':'true'},content=updated)
            assert replace.status_code==200, f'Owner upsert failed ({replace.status_code})'
            assert client.get('/storage/v1/object/authenticated/resumes/'+path,headers=sessions[0]).content==updated
            assert client.get('/storage/v1/object/authenticated/resumes/'+path,headers=sessions[1]).status_code!=200
            assert client.get('/storage/v1/object/public/resumes/'+path).status_code!=200
            signed=client.post('/storage/v1/object/sign/resumes/'+path,headers=sessions[1],json={'expiresIn':60})
            assert signed.status_code!=200, 'Stranger signed a private object'
            attack=client.post('/storage/v1/object/resumes/'+path,headers={**sessions[1],'Content-Type':'application/pdf','x-upsert':'true'},content=pdf)
            assert attack.status_code!=200, 'Stranger replaced an owner object'
            client.request('DELETE','/storage/v1/object/resumes',headers=sessions[1],json={'prefixes':[path]})
            assert client.get('/storage/v1/object/authenticated/resumes/'+path,headers=sessions[0]).content==updated
            passed=True
        finally:
            if paths:
                response=client.request('DELETE','/storage/v1/object/resumes',headers=privileged,json={'prefixes':paths})
                cleanup=cleanup and response.status_code==200
            for uid in created:
                response=client.delete('/auth/v1/admin/users/'+uid,headers=privileged)
                cleanup=cleanup and response.status_code==200
            print(json.dumps({'storage_isolation_passed':passed,'fixture_users':len(created),'cleanup_succeeded':cleanup}))
    if not cleanup: raise SystemExit('Fixture cleanup needs attention')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--project',required=True)
    check(parser.parse_args().project)
