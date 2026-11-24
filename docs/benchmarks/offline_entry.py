"""Credential-free Python entry point; deny non-loopback socket connections.

Usage (from backend): .venv/Scripts/python.exe ../docs/benchmarks/offline_entry.py tests/run_offline.py ...
The guard is inherited by imports, not by child processes. No model downloads.
"""
import ipaddress
import os
import runpy
import sys
import tempfile

for key in list(os.environ):
    if any(word in key.upper() for word in ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'SUPABASE', 'SENTRY_DSN')):
        os.environ.pop(key, None)
os.environ.update(APP_ENV='test', DEBUG='false', DISCOVERY_AUTO_SCAN='false',
                  MAILBOX_ENABLED='false', MAIL_SEND_ENABLED='false',
                  HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                  LANGCHAIN_TRACING_V2='false', LANGSMITH_TRACING='false',
                  ANONYMIZED_TELEMETRY='false', PYTHONIOENCODING='utf-8')
os.environ['CHROMA_PATH'] = tempfile.mkdtemp(prefix='jobpilot-audit-chroma-')


def guard(event, args):
    if event == 'socket.connect':
        address = args[1]
        if isinstance(address, tuple):
            try:
                local = ipaddress.ip_address(address[0]).is_loopback
            except ValueError:
                local = address[0] == 'localhost'
            if not local:
                raise RuntimeError('Offline audit blocked non-loopback connection')


sys.addaudithook(guard)
from pydantic_settings.sources import DotEnvSettingsSource
from unittest.mock import patch

target = sys.argv[1]
sys.argv = sys.argv[1:]
with patch.object(DotEnvSettingsSource, '__call__', return_value={}):
    runpy.run_path(target, run_name='__main__')
