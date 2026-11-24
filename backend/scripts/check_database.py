"""Disposable PostgreSQL migration/RLS checks. Never connects to hosted databases.

Requires Docker. The auth/storage helpers model the Supabase database contract;
this does not replace hosted Auth, Storage API or advisor acceptance checks.
"""
import secrets
import argparse
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = """
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema auth; create schema storage; create schema extensions;
create extension if not exists pgcrypto with schema extensions;
create table auth.users(id uuid primary key,email text,raw_app_meta_data jsonb default '{}',raw_user_meta_data jsonb default '{}');
create table auth.sessions(id uuid primary key,user_id uuid references auth.users(id) on delete cascade,not_after timestamptz);
create function auth.uid() returns uuid language sql stable as $$
 select coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid;
$$;
create function auth.jwt() returns jsonb language sql stable as $$ select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb $$;
create function auth.role() returns text language sql stable as $$ select auth.jwt()->>'role' $$;
grant usage on schema auth,storage,extensions,public to anon,authenticated,service_role;
grant select on auth.users to service_role;
create table storage.buckets(id text primary key,name text,public boolean default false,file_size_limit bigint,allowed_mime_types text[]);
create table storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text references storage.buckets(id),name text,owner uuid,metadata jsonb);
alter table storage.objects enable row level security;
create function storage.foldername(name text) returns text[] language sql immutable as $$ select (string_to_array(name,'/'))[1:array_length(string_to_array(name,'/'),1)-1] $$;
grant all on storage.objects,storage.buckets to authenticated,service_role;
alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
alter default privileges in schema public grant all on sequences to anon,authenticated,service_role;
"""


def sql(container, query):
    result = subprocess.run(['docker','exec','-i',container,'psql','-X','-v','ON_ERROR_STOP=1','-U','postgres','-d','postgres'],
                            input=query,text=True,encoding='utf-8',capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    return result.stdout


def backup_restore(container):
    # This container contains exclusively synthetic fixtures. Never export a hosted DB.
    sql(container,"insert into auth.users(id,email) values('99999999-9999-4999-8999-999999999999','restore@example.invalid');")
    archive=subprocess.run(['docker','exec',container,'pg_dump','-U','postgres','-d','postgres','-Fc'],capture_output=True,check=True).stdout
    if not 1000<len(archive)<10_000_000:raise RuntimeError('Unexpected synthetic archive size')
    sql(container,'create database release_restore;')
    result=subprocess.run(['docker','exec','-i',container,'pg_restore','-U','postgres','-d','release_restore','--exit-on-error'],input=archive,capture_output=True)
    if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[-3000:])
    restored=subprocess.run(['docker','exec',container,'psql','-XqAt','-v','ON_ERROR_STOP=1','-U','postgres','-d','release_restore','-c',"select count(*) from auth.users where email='restore@example.invalid'; select public.release_schema_ready();"],capture_output=True,text=True,check=True).stdout.strip()
    if restored!='1\nt':raise RuntimeError('Synthetic restore verification failed: '+restored)
    print('PASS: synthetic pg_dump archive restored into a separate database; fixture and schema readiness verified.',flush=True)


def main(worker_recovery=False):
    name='jobpilot-release-check-'+uuid.uuid4().hex[:12]
    created=False
    try:
        result=subprocess.run(['docker','run','--rm','-d','--name',name,'--label','jobpilot.test=release',
                        '--network','none','--memory','768m','--cpus','2','--pids-limit','256',
                        '-e','POSTGRES_PASSWORD='+secrets.token_urlsafe(32),'postgres:17'],capture_output=True,timeout=180)
        if result.returncode:raise RuntimeError('Disposable database startup failed: '+result.stderr.decode(errors='replace')[-1800:])
        created=True
        for _ in range(60):
            ready=subprocess.run(['docker','exec',name,'pg_isready','-U','postgres'],capture_output=True)
            if ready.returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('Disposable Postgres did not start')
        sql(name,FOUNDATION)
        migrations=sorted((ROOT/'supabase/migrations').glob('*.sql'))
        for file in migrations:
            sql(name,'begin;\n'+file.read_text(encoding='utf-8')+'\ncommit;')
            print('Migration passed:',file.name,flush=True)
        for file in sorted((ROOT/'supabase/tests').glob('*.sql')):
            sql(name,file.read_text(encoding='utf-8'))
            print('SQL check passed:',file.name,flush=True)
        if worker_recovery:
            from check_worker_recovery import check
            check(name)
        backup_restore(name)
        print(f'PASS: {len(migrations)} migrations and all SQL checks on isolated PostgreSQL 17.',flush=True)
    finally:
        # The random container is exclusively ours; never prune or stop other resources.
        if created:subprocess.run(['docker','rm','-f',name],check=True,capture_output=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-recovery',action='store_true',help='Requires backend dependencies; exercises real Worker process recovery')
    main(parser.parse_args().worker_recovery)
