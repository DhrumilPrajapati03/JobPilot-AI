from datetime import datetime,timezone
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from app.services.auth import CurrentUser,get_current_user
from app.db import get_db

router=APIRouter()
Kind=Literal['email','dm','cover_letter']


class TemplateUpdate(BaseModel):
    content:str=Field(max_length=10000)
    expected_updated_at:str|None=None


@router.get('')
def list_templates(user:CurrentUser=Depends(get_current_user)):
    try:
        return {'templates':get_db(user.id).table('writing_templates').select('kind,content,updated_at').eq('user_id',user.id).execute().data}
    except Exception:
        raise HTTPException(503,'Templates are unavailable. Check the release migration and try again.') from None


@router.put('/{kind}')
def save_template(kind:Kind,request:TemplateUpdate,user:CurrentUser=Depends(get_current_user)):
    db=get_db(user.id)
    row={'user_id':user.id,'kind':kind,'content':request.content,'updated_at':datetime.now(timezone.utc).isoformat()}
    try:
        if request.expected_updated_at:
            result=db.table('writing_templates').update(row).eq('user_id',user.id).eq('kind',kind).eq('updated_at',request.expected_updated_at).execute().data
            if not result:raise HTTPException(409,'This template changed. Reload the saved version before replacing it.')
        else:
            if db.table('writing_templates').select('kind').eq('user_id',user.id).eq('kind',kind).execute().data:
                raise HTTPException(409,'A saved template already exists. Reload it before editing.')
            result=db.table('writing_templates').insert(row).execute().data
        return {'template':result[0]}
    except HTTPException:raise
    except Exception as exc:
        if getattr(exc,'code','')=='23505':raise HTTPException(409,'A saved template already exists. Reload it before editing.') from None
        raise HTTPException(503,'The template could not be saved. Please try again.') from None
