"""Fail startup on unsafe release configuration, without revealing values."""
from urllib.parse import urlsplit
from app.config import settings


def validate_production(config=settings):
    if config.APP_ENV != 'production':
        return
    failures = []
    if config.DEBUG: failures.append('DEBUG must be false')
    if config.EXECUTION_MODE != 'durable': failures.append('EXECUTION_MODE must be durable')
    if not config.USAGE_LIMITS_ENABLED: failures.append('USAGE_LIMITS_ENABLED must be true')
    database_url=urlsplit(config.DATABASE_URL)
    if database_url.scheme not in ('postgresql','postgresql+psycopg') or not database_url.hostname or not database_url.path.strip('/'):
        failures.append('DATABASE_URL must be a postgresql:// URL with a host and database name')
    if not config.OWNER_EMAIL.strip(): failures.append('OWNER_EMAIL is required')
    secrets=('SECRET_KEY','OBSERVABILITY_TOKEN','CRON_SECRET','OWNER_API_TOKEN')
    for key in secrets:
        if len(getattr(config,key))<32 or 'change-me' in getattr(config,key): failures.append(key+' must be a unique random value of at least 32 characters')
    if len({getattr(config,key) for key in secrets})!=len(secrets): failures.append('Backend secrets must use separate random values')
    origins=[v.strip().rstrip('/') for v in config.FRONTEND_URL.split(',') if v.strip()]
    if not origins or any(urlsplit(v).scheme!='https' or not urlsplit(v).netloc or urlsplit(v).username or urlsplit(v).password or urlsplit(v).path or urlsplit(v).query or urlsplit(v).fragment or '*' in v for v in origins):
        failures.append('FRONTEND_URL must contain exact HTTPS origins')
    providers={'groq':config.GROQ_API_KEY,'openai':config.OPENAI_API_KEY,'anthropic':config.ANTHROPIC_API_KEY}
    configured=lambda key:bool(key) and not key.startswith('your-')
    if config.LLM_PROVIDER not in {'auto',*providers}: failures.append('LLM_PROVIDER is unsupported')
    elif config.LLM_PROVIDER!='auto' and not configured(providers[config.LLM_PROVIDER]): failures.append('The selected generation provider needs its API key')
    elif config.LLM_PROVIDER=='auto' and not any(configured(v) for v in providers.values()): failures.append('A generation provider must be configured')
    if config.AGENT_PROVIDER!='auto' and (config.AGENT_PROVIDER not in providers or not configured(providers[config.AGENT_PROVIDER])): failures.append('The selected chat provider needs its API key')
    if config.MAILBOX_ENABLED and not (config.COMPOSIO_API_KEY and config.COMPOSIO_GMAIL_AUTH_CONFIG_ID): failures.append('Mailbox configuration is incomplete')
    if config.MAIL_SEND_ENABLED and not config.MAILBOX_ENABLED: failures.append('Sending requires mailbox connections')
    if failures: raise RuntimeError('Production configuration rejected: '+'; '.join(failures))
