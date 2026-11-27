// JobDots — contacts CRM: who Recon found, how to reach them, and where each one stands.
import { useState } from 'react';
import { useContactMutations, useContacts } from '../../jobdots/api';
import { Chip } from '../../jobdots/cards';

const ROLE: Record<string, string> = { recruiter: 'Recruiter', hiring_manager: 'Hiring manager', ceo: 'CEO', cto: 'CTO', employee: 'Engineer', unknown: 'Unknown' };
const STAGE: Record<string, string> = {
  unknown: 'New', discovered: 'Found', classified: 'Found', invite_proposed: 'Invitation drafted', invite_approved: 'Invitation approved',
  invite_sent: 'Invitation sent', accepted: 'Connected', message_proposed: 'Message drafted', message_approved: 'Message approved',
  message_sent: 'Contacted', replied: 'Replied', no_reply: 'No reply', follow_up: 'Follow-up due', closed: 'Closed',
};

export default function Contacts() {
  const [q, setQ] = useState('');
  const [imported, setImported] = useState(false);
  const contacts = useContacts(q, imported);
  const { update } = useContactMutations();
  return (
    <div className="jd-page">
      <header className="jd-page-head"><h1>Contacts</h1>
        <div className="jd-filters">
          <input className="jd-input" placeholder="Search name, company, title or email" aria-label="Search contacts" value={q} onChange={e => setQ(e.target.value)} />
          <label className="jd-check"><input type="checkbox" checked={imported} onChange={e => setImported(e.target.checked)} /> Include your imported connections</label>
        </div>
      </header>
      {contacts.isLoading ? <p className="jd-meta">Loading contacts…</p> : !contacts.data?.length ? <p className="jd-empty">No contacts yet. Recon adds people when it works on a case.</p> :
        <table className="jd-table"><thead><tr><th>Person</th><th>Company</th><th>Role</th><th>Where it stands</th><th>Contact</th></tr></thead><tbody>
          {contacts.data.map(c => <tr key={c.id}>
            <td>{c.linkedin_url ? <a href={c.linkedin_url} target="_blank" rel="noreferrer">{c.name || 'Unnamed'}</a> : c.name || 'Unnamed'}<span className="jd-meta">{c.title}</span></td>
            <td>{c.company}</td>
            <td>{ROLE[c.role_class] ?? c.role_class}{c.connected && <span className="jd-meta">Your connection</span>}</td>
            <td><Chip tone={c.do_not_contact ? 'warn' : ['invite_sent', 'message_sent', 'accepted', 'replied'].includes(c.stage) ? 'ok' : 'quiet'}>{c.do_not_contact ? 'Do not contact' : STAGE[c.stage] ?? c.stage}</Chip></td>
            <td>{c.email && <span className="jd-meta">{c.email}{c.email_source ? ` (${c.email_source.replace(/_/g, ' ')})` : ''}</span>}
              <label className="jd-check"><input type="checkbox" checked={c.do_not_contact} disabled={update.isPending}
                onChange={e => update.mutate({ id: c.id, changes: { do_not_contact: e.target.checked } })} /> Do not contact</label></td>
          </tr>)}</tbody></table>}
    </div>
  );
}
