import { useEffect, useRef, useState } from 'react';
import { useMailbox, useMailAction, useSyncMailbox } from '../../hooks/use-mailbox';
import api from '../../lib/api';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/card';
import { Button } from '../ui/button';

export function GmailConnection() {
  const status=useMailbox(); const sync=useSyncMailbox(); const started=useRef(false); const [result,setResult]=useState('');
  const complete=useMailAction<string>(uri=>api.post('/email/connection/complete',{session_uri:uri}));
  const connect=useMailAction<void>(async()=>{
    const response=await api.post<{redirect_url:string}>('/email/connection',{});
    const url=new URL(response.redirect_url);
    if (url.protocol!=='https:' || !url.hostname.endsWith('.composio.dev')) throw new Error('Invalid Gmail connection link');
    window.location.assign(response.redirect_url);
  });
  const disconnect=useMailAction<void>(async()=>{
    const response=await api.delete<{provider_revoked:boolean}>('/email/connection');
    setResult(response.provider_revoked?'Gmail disconnected.':'Gmail disconnected in JobPilot. Also remove its access in your Google account settings.');
    return response;
  });
  useEffect(()=>{
    const url=new URL(window.location.href); const uri=url.searchParams.get('session_uri');
    if (!uri || started.current) return;
    started.current=true; url.searchParams.delete('session_uri'); window.history.replaceState(window.history.state,'',url.pathname+url.search+url.hash);
    complete.mutate(uri);
  },[complete]);
  const error=status.error || complete.error || connect.error || disconnect.error || sync.error;
  return <Card><CardHeader><CardTitle>Your Gmail account</CardTitle>
    <p className="text-sm text-muted-foreground">Approve each exact email and attachment before sending. JobPilot synchronizes only conversations it tracks; replies never trigger automatic sends.</p>
    <p className="text-xs text-muted-foreground">Disconnecting stops queued sends. An in-flight message may already have been accepted by Gmail.</p>
  </CardHeader><CardContent className="space-y-3">
    {status.data?.connection ? <><p className="text-sm">Connected: <strong>{status.data.connection.email}</strong></p>
      {!status.data.send_enabled && <p className="text-sm text-muted-foreground">Sending is not enabled yet. You can prepare and review drafts.</p>}
      <div className="flex gap-2"><Button variant="outline" disabled={sync.isPending} onClick={()=>sync.mutate()}>{sync.isPending?'Synchronizing…':'Synchronize tracked conversations'}</Button>
      <Button variant="ghost" disabled={disconnect.isPending} onClick={()=>disconnect.mutate()}>Disconnect Gmail</Button></div>
    </> : <><p className="text-sm text-muted-foreground">{status.data?.configured?'Connect the account you want to send from.':'Gmail connection is not available yet.'}</p>
      <Button disabled={!status.data?.configured || connect.isPending || complete.isPending} onClick={()=>connect.mutate()}>{complete.isPending?'Verifying your account…':'Connect Gmail'}</Button></>}
    {sync.isSuccess && <p role="status" className="text-sm">{sync.data.errors?`${sync.data.errors} conversations could not be synchronized. Check your connection.`:sync.data.has_more?'This batch finished; remaining conversations continue in the background.':'Tracked conversations checked. Inspect replies in the application email view.'}</p>}
    {result && <p role="status" className="text-sm">{result}</p>}
    {error && <p role="alert" className="text-sm text-destructive">{error.message}</p>}
  </CardContent></Card>;
}
