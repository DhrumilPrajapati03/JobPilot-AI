-- Recon and the contacts CRM (plan sections 2.1, 2.4, 6; Day 6).

-- Where each contact detail came from, and the identity used to merge duplicates.
alter table public.contact
  add column github text not null default '',
  add column email_source text not null default '' check (email_source in
    ('', 'job_description', 'hunter', 'you', 'imported', 'public_page')),
  add column sources jsonb not null default '[]'::jsonb,     -- [{url, what, at}], newest last, bounded in code
  add column do_not_contact boolean not null default false,
  add column linkedin_slug text generated always as
    (lower(substring(linkedin_url from 'linkedin\.com/in/([^/?#]+)'))) stored;

-- Existing addresses: imported ones are marked as such, ones you typed as yours.
update public.contact set email_source = case when legacy then 'imported' when source = 'you' then 'you' else '' end
  where email <> '' and email_source = '';

-- One contact per LinkedIn profile (the imported connections have no duplicates).
create unique index contact_linkedin_slug_key on public.contact (user_id, linkedin_slug) where linkedin_slug is not null;
create index contact_email_idx on public.contact (user_id, lower(email)) where email <> '';
create index contact_company_idx on public.contact (user_id, lower(company));
