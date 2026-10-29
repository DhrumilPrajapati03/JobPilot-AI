"""Read-only onboarding derived from saved, owner-scoped data."""
from app.services import identity


def status(db, uid):
    profiles = db.table('user_profiles').select('id,work_preferences').eq('id',uid).execute().data
    resumes = db.table('resumes').select('*').eq('user_id',uid).eq('version','base').execute().data
    resume = resumes[0] if resumes else {}
    skills = resume.get('skills') or {}
    has_content = bool(resume.get('headline') or resume.get('summary') or resume.get('experience') or resume.get('projects') or
                       skills.get('primary') or skills.get('secondary') or resume.get('education'))
    vault = identity.load_vault(db,uid,resume)
    prefs = (profiles[0].get('work_preferences') if profiles else None) or {}
    has_roles = bool([r for r in prefs.get('preferred_roles',[]) if isinstance(r,str) and r.strip()])
    sources = db.table('job_sources').select('id').eq('user_id',uid).eq('enabled',True).limit(1).execute().data
    steps = [
        {'id':'resume','title':'Import or write your base résumé','href':'/profile?tab=personal','done':has_content,'required':True},
        {'id':'facts','title':'Review and confirm your saved facts','href':'/profile?tab=facts','done':has_content and vault['complete'],'required':True},
        {'id':'preferences','title':'Choose your target roles and work preferences','href':'/profile?tab=preferences','done':has_roles,'required':True},
        {'id':'sources','title':'Follow a job board to start discovery','href':'/jobs','done':bool(sources),'required':False},
    ]
    required = [s for s in steps if s['required']]
    return {'ready_for_matching':all(s['done'] for s in required),'steps':steps,'confirmed_facts':vault['confirmed_count'],
            'total_facts':vault['total'],'next_step':next((s['id'] for s in steps if not s['done']),None),
            'note':'Facts are confirmed by you. Gmail is optional; preparation and outreach always require review.'}
