import asyncio
from fastapi import HTTPException
from app.agents.research import ResearchAgent
from app.services.runs import PermanentRunError


def owned(db, uid, app_id):
    rows = db.table('job_applications').select('*').eq('user_id', uid).eq('id', app_id).execute().data
    if not rows:
        raise HTTPException(404, 'Application not found')
    return rows[0]


async def execute(ctx):
    db, uid, inputs = ctx.store.client, ctx.run['user_id'], ctx.run['inputs']
    try:
        application = await asyncio.to_thread(owned, db, uid, inputs['application_id'])
    except HTTPException:
        raise PermanentRunError('This application was removed. Start new research deliberately.') from None
    async def collect():
        result = await ResearchAgent().research(application.get('company') or 'Company', inputs['urls'])
        if not result['sources']:
            raise PermanentRunError('No readable sources. Check the public URLs and request new research.')
        return result
    package = await ctx.stage('company_sources', 'Reading the supplied company sources', collect)
    async def save():
        return await asyncio.to_thread(ctx.store.rpc, 'save_company_research', p_run_id=ctx.run['id'], p_token=ctx.token,
            p_application_id=inputs['application_id'], p_company=package['company'], p_sources=package['sources'], p_warnings=package['warnings'])
    return await ctx.stage('company_research_saved', 'Saving cited company source excerpts', save)
