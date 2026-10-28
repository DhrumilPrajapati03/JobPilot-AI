import { useQuery } from '@tanstack/react-query';
import api from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';

export interface ExecutionHistory {
  sessions: {id: string; page_url: string; document_id: string | null; created_at: string}[];
  documents: {id: string; name: string; sha256: string; size_bytes: number; resume_version: number}[];
  events: {id: number; session_id: string; kind: string; created_at: string; details: {summary?: {total: number; filled: number; preserved: number; review: number; required_missing: number; invalid: number}; document_sha256?: string; truncated?: boolean}}[];
}

const labels: Record<string, string> = {
  form_prepared: 'Form preparation checked',
  submission_attempted: 'Submission attempt observed',
  submission_confirmation_observed: 'Browser confirmation observed · not independently verified',
  user_reported_submitted: 'User reported submitted · not independently verified',
};

export function EvidenceView({data}: {data: ExecutionHistory}) {
  return <div className="space-y-3 text-sm">
    <p className="text-xs text-muted-foreground">Preparation checks, submission attempts, browser confirmations and your reports are separate records. A selected file or completed form does not prove employer acceptance.</p>
    {!data.events.length && <p>No submission evidence recorded. Existing application status may be manually reported.</p>}
    <ol className="space-y-3">{data.events.map(event => {
      const summary = event.details.summary;
      const session = data.sessions.find(s => s.id === event.session_id);
      const document = data.documents.find(d => d.id === session?.document_id);
      return <li key={event.id} className="rounded-md border p-3">
        <p className="font-medium">{labels[event.kind] || 'Application observation'}</p>
        <p className="text-xs text-muted-foreground">{new Date(event.created_at).toLocaleString()}</p>
        {summary && <p className="mt-1 text-xs">{summary.filled} filled and checked; {summary.preserved} preserved; {summary.review} need review; {summary.required_missing} required missing or invalid. {summary.total} fields inspected.</p>}
        {event.details.truncated && <p className="text-xs text-warning">Inspection reached the 150-field limit. Additional fields require manual review.</p>}
        {event.kind === 'submission_attempted' && <p className="mt-1 text-xs">The user attempted submission. The employer outcome remains unknown.</p>}
        {event.kind === 'form_prepared' && document && <p className="mt-1 break-all text-xs text-muted-foreground">Frozen résumé: {document.name}, version {document.resume_version}. SHA-256: {document.sha256}. {event.details.document_sha256 ? 'Matching PDF selected in browser; upload acceptance unverified.' : 'PDF selection not verified.'}</p>}
      </li>;
    })}</ol>
    {data.events.length >= 200 && <p className="text-xs text-muted-foreground">Showing the latest 200 observations from the latest 20 sessions.</p>}
  </div>;
}

export function ExecutionEvidence({applicationId}: {applicationId: string}) {
  const history = useQuery<ExecutionHistory>({queryKey:['execution-evidence',applicationId], queryFn:() => api.get(`/applications/${applicationId}/execution`), refetchInterval:15000});
  return <Card><CardHeader className="p-4 pb-2"><CardTitle className="text-sm">Preparation &amp; submission evidence</CardTitle></CardHeader><CardContent className="p-4 pt-0">
    {history.isPending ? <p className="text-xs">Loading observations…</p> : history.isError ? <p className="text-xs text-warning">Evidence could not be loaded. No submission conclusion can be drawn.</p> : <EvidenceView data={history.data} />}
  </CardContent></Card>;
}
