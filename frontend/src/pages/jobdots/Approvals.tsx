// JobDots — Approvals inbox: the same approval cards as in case threads, stacked by kind.
import { usePending } from '../../jobdots/api';
import { ApprovalDeck } from '../../jobdots/cards';

const GROUPS: [string, string][] = [['create_calendar_event', 'Calendar events'], ['send_email', 'Emails'], ['send_linkedin_invite', 'LinkedIn invitations'], ['send_linkedin_dm', 'LinkedIn messages'], ['referral_request', 'Referral asks']];

export default function Approvals() {
  const pending = usePending();
  const all = pending.data ?? [];
  const waiting = all.filter(a => a.status === 'reviewed');
  const blocked = all.filter(a => a.status === 'blocked');
  const unknown = all.filter(a => a.status === 'send_unknown');
  return (
    <div className="jd-page">
      <header className="jd-page-head"><h1>Approvals</h1>
        <p className="jd-lede">Nothing leaves JobDots without your approval here, in a case or in Telegram. Approved emails are sent by Courier; approved LinkedIn items wait in the side panel's queue for you to send.</p></header>
      {pending.isLoading && <p className="jd-meta">Checking for drafts…</p>}
      {!pending.isLoading && all.length === 0 && <p className="jd-empty">Nothing waiting for you.</p>}
      {GROUPS.map(([kind, title]) => {
        const list = waiting.filter(a => a.kind === kind);
        return list.length ? <section key={kind}><h2>{title} ({list.length})</h2><ApprovalDeck actions={list} showCase /></section> : null;
      })}
      {unknown.length > 0 && <section><h2>Check these first</h2>
        <p className="jd-meta">JobDots couldn't confirm whether these went out. Look in your Gmail Sent folder before sending them again.</p>
        <ApprovalDeck actions={unknown} showCase /></section>}
      {blocked.length > 0 && <section><h2>Blocked by the Reviewer ({blocked.length})</h2>
        <p className="jd-meta">Each says why. Discard it, or ask the expert for a new draft from the case.</p>
        <ApprovalDeck actions={blocked} showCase /></section>}
    </div>
  );
}
