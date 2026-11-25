"""Disposable PostgreSQL checks: Alembic migrations, SQL tests, worker recovery, backup/restore.

Requires Docker. Starts a throwaway pgvector/Postgres 17 container published on a random
127.0.0.1 port, runs `alembic upgrade head` against it, then the SQL checks in tests/sql/.
Never connects to any other database; the container is removed at the end.
"""
import argparse
import os
import secrets
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Same image as compose.yaml at the repo root; keep the two in step.
IMAGE = 'pgvector/pgvector:pg17@sha256:b513c48566e4777cd3370451400000c78eda6a08131d68f4c31d4a76f27bd8fd'


def sql(container, query):
    result = subprocess.run(['docker', 'exec', '-i', container, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'postgres'],
                            input=query, text=True, encoding='utf-8', capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    return result.stdout


def migrate(container, password):
    port = subprocess.run(['docker', 'port', container, '5432/tcp'], capture_output=True, text=True, check=True).stdout.split()[0].rsplit(':', 1)[1]
    env = {**os.environ, 'DATABASE_URL': f'postgresql+psycopg://postgres:{password}@127.0.0.1:{port}/postgres'}
    result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('alembic upgrade head failed:\n' + result.stderr[-4000:])
    head = sql(container, 'select version_num from alembic_version;').split()[2]
    print('Alembic upgrade head passed; revision', head, flush=True)


def backup_restore(container):
    # This container holds only synthetic fixtures. Never export a real database here.
    sql(container, "insert into auth.users(id,email) values('99999999-9999-4999-8999-999999999999','restore@example.invalid');")
    archive = subprocess.run(['docker', 'exec', container, 'pg_dump', '-U', 'postgres', '-d', 'postgres', '-Fc'], capture_output=True, check=True).stdout
    if not 1000 < len(archive) < 10_000_000:
        raise RuntimeError('Unexpected synthetic archive size')
    sql(container, 'create database release_restore;')
    result = subprocess.run(['docker', 'exec', '-i', container, 'pg_restore', '-U', 'postgres', '-d', 'release_restore', '--exit-on-error'], input=archive, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-3000:])
    restored = subprocess.run(['docker', 'exec', container, 'psql', '-XqAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', 'release_restore', '-c',
                               "select count(*) from auth.users where email='restore@example.invalid'; select public.release_schema_ready(); select count(*) from alembic_version;"],
                              capture_output=True, text=True, check=True).stdout.strip()
    if restored != '1\nt\n1':
        raise RuntimeError('Synthetic restore verification failed: ' + restored)
    print('PASS: synthetic pg_dump archive restored into a separate database; fixture, schema and Alembic revision verified.', flush=True)


def main(worker_recovery=False):
    name = 'jobdots-db-check-' + uuid.uuid4().hex[:12]
    password = secrets.token_urlsafe(32)
    created = False
    try:
        result = subprocess.run(['docker', 'run', '--rm', '-d', '--name', name, '--label', 'jobdots.test=database',
                                 '-p', '127.0.0.1::5432', '--memory', '768m', '--cpus', '2', '--pids-limit', '256',
                                 '-e', 'POSTGRES_PASSWORD=' + password, IMAGE], capture_output=True, timeout=300)
        if result.returncode:
            raise RuntimeError('Disposable database startup failed: ' + result.stderr.decode(errors='replace')[-1800:])
        created = True
        for _ in range(60):
            # -h forces TCP, so this only succeeds once the real server (not the init one) is up.
            if subprocess.run(['docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres'], capture_output=True).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Disposable Postgres did not start')
        migrate(name, password)
        for file in sorted((ROOT / 'tests/sql').glob('*.sql')):
            sql(name, file.read_text(encoding='utf-8'))
            print('SQL check passed:', file.name, flush=True)
        if worker_recovery:
            from check_worker_recovery import check
            check(name)
        backup_restore(name)
        print('PASS: Alembic migrations and all SQL checks on isolated PostgreSQL 17 + pgvector.', flush=True)
    finally:
        # The random container is exclusively ours; never prune or stop other resources.
        if created:
            subprocess.run(['docker', 'rm', '-f', name], check=True, capture_output=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-recovery', action='store_true', help='Requires backend dependencies; exercises real Worker process recovery')
    main(parser.parse_args().worker_recovery)
