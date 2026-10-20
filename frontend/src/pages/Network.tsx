// ============================================================
// JobPilot — Network: the people you know, for referrals
// ============================================================

import { useRef, useState, type DragEvent, type FormEvent } from 'react';
import { AlertTriangle, ExternalLink, FileUp, Loader2, Plus, Search, Trash2, Users } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { cn } from '@/lib/utils';
import { useAddContact, useContacts, useDeleteContact, useImportConnections, useNetworkCompanies } from '../hooks/use-network';

function ImportCard({ compact }: { compact: boolean }) {
  const importer = useImportConnections();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const onFile = (file: File | undefined) => file && importer.mutate(file);
  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setDragging(false);
    onFile(e.dataTransfer.files?.[0]);
  };
  const result = importer.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{compact ? 'Update from LinkedIn' : 'Import your LinkedIn connections'}</CardTitle>
        {!compact && (
          <ol className="list-decimal space-y-0.5 pl-5 text-sm text-muted-foreground">
            <li>On LinkedIn, open Settings → Data privacy → Get a copy of your data.</li>
            <li>Request the archive. “Connections” only is fastest; the full archive works too but can take up to a day.</li>
            <li>When LinkedIn emails you, drop the downloaded .zip (or Connections.csv from inside it) here.</li>
          </ol>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed px-4 text-center transition-colors hover:bg-muted/40',
            compact ? 'py-4' : 'py-8',
            dragging && 'border-accent bg-accent/5',
          )}
        >
          {importer.isPending ? <Loader2 size={20} className="animate-spin text-muted-foreground" /> : <FileUp size={20} className="text-muted-foreground" />}
          <span className="text-sm font-medium">{importer.isPending ? 'Importing…' : 'Drop the LinkedIn .zip or Connections.csv here, or click to choose'}</span>
          <span className="text-xs text-muted-foreground">Re-importing updates people who changed jobs. Your contacts stay private to you.</span>
          <input
            ref={input}
            type="file"
            accept=".csv,.zip,text/csv,application/zip"
            className="sr-only"
            onChange={(e) => {
              onFile(e.target.files?.[0]);
              e.target.value = '';
            }}
          />
        </label>
        {importer.error && <p className="text-sm text-destructive">{importer.error.message}</p>}
        {result && (
          <p className="text-sm">
            <span className="font-medium text-accent">
              {result.imported} new, {result.updated} updated.
            </span>{' '}
            <span className="text-muted-foreground">
              {result.with_company} have a company listed
              {result.top_companies.length > 0 && `; most at ${result.top_companies.slice(0, 3).map((c) => c.company).join(', ')}`}.
            </span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function AddContactCard() {
  const add = useAddContact();
  const empty = { full_name: '', company: '', position: '', linkedin_url: '', email: '' };
  const [form, setForm] = useState(empty);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate(form, { onSuccess: () => setForm(empty) });
  };
  const field = (key: keyof typeof empty, label: string, placeholder = '') => (
    <div className="space-y-1.5">
      <Label htmlFor={`contact-${key}`}>{label}</Label>
      <Input id={`contact-${key}`} value={form[key]} placeholder={placeholder} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
    </div>
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Add someone you know</CardTitle>
        <p className="text-sm text-muted-foreground">Friends, ex-colleagues or alumni who aren't LinkedIn connections.</p>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <div className="grid gap-3 @md:grid-cols-2">
            {field('full_name', 'Name', 'Priya Sharma')}
            {field('company', 'Company', 'Swiggy')}
            {field('position', 'Role', 'Software Engineer')}
            {field('linkedin_url', 'LinkedIn URL', 'Optional')}
          </div>
          <div className="flex items-center justify-end gap-2">
            {add.error && <span className="text-xs text-destructive">{add.error.message}</span>}
            <Button type="submit" disabled={!form.full_name.trim() || add.isPending}>
              {add.isPending ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Plus size={15} className="mr-1.5" />}
              Add contact
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function Network() {
  const [query, setQuery] = useState('');
  const [company, setCompany] = useState('');
  const companies = useNetworkCompanies();
  const contacts = useContacts(query.trim(), company);
  const remove = useDeleteContact();
  const total = companies.data?.total_contacts ?? 0;
  const setupError = companies.error?.message.includes('migrations') ? companies.error.message : null;
  const highlighted = (companies.data?.companies ?? []).filter((c) => c.applications > 0 || c.followed);
  const others = (companies.data?.companies ?? []).filter((c) => !(c.applications > 0 || c.followed)).slice(0, 24);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Network</h1>
        <p className="text-sm text-muted-foreground">
          {total
            ? `${total.toLocaleString()} contacts at ${companies.data?.total_companies.toLocaleString()} companies. JobPilot checks them for referrals on every application.`
            : 'The people you know, so every application starts with a referral when one is possible.'}
        </p>
      </div>

      {setupError ? (
        <div className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" />
          {setupError}
        </div>
      ) : companies.isLoading ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground">
          <Loader2 className="animate-spin" size={18} />
        </div>
      ) : (
        <>
          <div className="grid gap-4 @4xl:grid-cols-2">
            <ImportCard compact={total > 0} />
            <AddContactCard />
          </div>

          {total > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users size={17} />
                  Where you know people
                </CardTitle>
                {highlighted.length > 0 && (
                  <p className="text-sm text-muted-foreground">Highlighted: companies you've applied to or follow in your job feed.</p>
                )}
              </CardHeader>
              <CardContent className="flex flex-wrap gap-1.5">
                {[...highlighted, ...others].map((c) => {
                  const hot = c.applications > 0 || c.followed;
                  const active = company === c.company;
                  return (
                    <button
                      key={c.company}
                      type="button"
                      onClick={() => setCompany(active ? '' : c.company)}
                      aria-pressed={active}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs',
                        active ? 'border-primary bg-primary text-primary-foreground' : hot ? 'border-accent/40 bg-accent/10 text-accent' : 'bg-card hover:bg-secondary',
                      )}
                      title={[c.applications ? `${c.applications} application${c.applications > 1 ? 's' : ''}` : '', c.followed ? 'in your job feed' : ''].filter(Boolean).join(' · ')}
                    >
                      {c.company}
                      <span className="tabular-nums opacity-70">{c.count}</span>
                    </button>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {total > 0 && (
            <Card>
              <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
                <CardTitle>{company ? `People at ${company}` : 'Contacts'}</CardTitle>
                <div className="relative w-full max-w-xs">
                  <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name, company or role" className="pl-9" aria-label="Search contacts" />
                </div>
              </CardHeader>
              <CardContent>
                {contacts.isLoading ? (
                  <div className="flex h-24 items-center justify-center text-muted-foreground">
                    <Loader2 className="animate-spin" size={18} />
                  </div>
                ) : (
                  <>
                    <ul className="divide-y">
                      {(contacts.data?.contacts ?? []).map((c) => (
                        <li key={c.id} className="group flex items-center gap-3 py-2.5">
                          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-secondary text-xs font-semibold">
                            {c.full_name.charAt(0).toUpperCase()}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium">{c.full_name}</span>
                            <span className="block truncate text-xs text-muted-foreground">{[c.position, c.company].filter(Boolean).join(' · ') || 'No company listed'}</span>
                          </span>
                          {c.linkedin_url && (
                            <a
                              href={c.linkedin_url}
                              target="_blank"
                              rel="noreferrer"
                              className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                              aria-label={`${c.full_name} on LinkedIn`}
                            >
                              <ExternalLink size={14} />
                            </a>
                          )}
                          <button
                            type="button"
                            onClick={() => window.confirm(`Remove ${c.full_name} from your network?`) && remove.mutate(c.id)}
                            className="rounded-md p-1.5 text-muted-foreground opacity-0 hover:bg-secondary hover:text-destructive focus:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
                            aria-label={`Remove ${c.full_name}`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </li>
                      ))}
                    </ul>
                    {contacts.data && contacts.data.total > contacts.data.contacts.length && (
                      <p className="pt-2 text-xs text-muted-foreground">
                        Showing {contacts.data.contacts.length} of {contacts.data.total.toLocaleString()}. Search to narrow it down.
                      </p>
                    )}
                    {contacts.data?.total === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No contacts match.</p>}
                  </>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
