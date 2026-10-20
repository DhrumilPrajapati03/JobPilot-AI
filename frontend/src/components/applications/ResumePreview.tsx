// ============================================================
// JobPilot AI — Resume paper preview + inline editor
// ============================================================

import { Fragment, type ReactNode } from 'react';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import type { Resume } from '../../hooks/use-profile';

interface Contact {
  email?: string;
  location?: string;
  linkedin_url?: string;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Wraps JD keywords found in the text so reviewers can see what matched. */
function Highlight({ text, keywords }: { text: string; keywords: string[] }) {
  const terms = keywords.filter((k) => k.trim().length > 1);
  if (!text || terms.length === 0) return <>{text}</>;
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join('|')})`, 'gi');
  const lower = new Set(terms.map((t) => t.toLowerCase()));
  return (
    <>
      {text.split(pattern).map((part, i) =>
        lower.has(part.toLowerCase()) ? (
          <mark key={i} className="resume-keyword">
            {part}
          </mark>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="resume-section">
      <h3 className="resume-section-title">{title}</h3>
      {children}
    </section>
  );
}

export function ResumePreview({
  resume,
  contact,
  keywords = [],
}: {
  resume: Resume;
  contact?: Contact;
  keywords?: string[];
}) {
  const contactLine = [contact?.email, contact?.location].filter(Boolean).join('  ·  ');
  const hl = (text: string) => <Highlight text={text} keywords={keywords} />;

  return (
    <article className="resume-paper">
      <header className="resume-header">
        <h2 className="resume-name">{resume.name || 'Your Name'}</h2>
        {resume.headline && <p className="resume-headline">{hl(resume.headline)}</p>}
        {(contactLine || contact?.linkedin_url) && (
          <p className="resume-contact">
            {contactLine}
            {contact?.linkedin_url && (
              <>
                {contactLine && '  ·  '}
                <a href={contact.linkedin_url} target="_blank" rel="noreferrer">
                  LinkedIn
                </a>
              </>
            )}
          </p>
        )}
      </header>

      {resume.summary && (
        <Section title="Summary">
          <p>{hl(resume.summary)}</p>
        </Section>
      )}

      {resume.experience?.length > 0 && (
        <Section title="Experience">
          {resume.experience.map((job, i) => (
            <div key={i} className="resume-entry">
              <div className="resume-entry-head">
                <strong>{job.role}</strong>
                <span>{job.duration}</span>
              </div>
              <div className="resume-entry-sub">{job.company}</div>
              <ul>
                {job.bullets.map((bullet, j) => (
                  <li key={j}>{hl(bullet)}</li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {(resume.skills?.primary?.length > 0 || resume.skills?.secondary?.length > 0) && (
        <Section title="Skills">
          {resume.skills.primary.length > 0 && (
            <p>
              <strong>Primary: </strong>
              {hl(resume.skills.primary.join(', '))}
            </p>
          )}
          {resume.skills.secondary.length > 0 && (
            <p>
              <strong>Additional: </strong>
              {hl(resume.skills.secondary.join(', '))}
            </p>
          )}
        </Section>
      )}

      {resume.projects?.length > 0 && (
        <Section title="Projects">
          {resume.projects.map((project, i) => (
            <div key={i} className="resume-entry">
              <div className="resume-entry-head">
                <strong>{project.name}</strong>
                <span>{project.tech.join(', ')}</span>
              </div>
              <p>{hl(project.description)}</p>
            </div>
          ))}
        </Section>
      )}

      {resume.education?.length > 0 && (
        <Section title="Education">
          {resume.education.map((edu, i) => (
            <div key={i} className="resume-entry">
              <div className="resume-entry-head">
                <strong>{edu.degree}</strong>
                <span>{edu.year}</span>
              </div>
              <div className="resume-entry-sub">{edu.institution}</div>
            </div>
          ))}
        </Section>
      )}

      {resume.certifications?.length > 0 && (
        <Section title="Certifications">
          <ul>
            {resume.certifications.map((cert, i) => (
              <li key={i}>{[cert.name, cert.issuer, cert.year].filter(Boolean).join(' — ')}</li>
            ))}
          </ul>
        </Section>
      )}
    </article>
  );
}

const splitList = (value: string) =>
  value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

const splitLines = (value: string) =>
  value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

/** Edits the wording of a tailored resume. Facts (companies, dates) stay read-only. */
export function ResumeEditor({ value, onChange }: { value: Resume; onChange: (next: Resume) => void }) {
  const set = (patch: Partial<Resume>) => onChange({ ...value, ...patch });

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <label className="text-xs font-semibold text-muted-foreground">Headline</label>
        <Input value={value.headline} onChange={(e) => set({ headline: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <label className="text-xs font-semibold text-muted-foreground">Summary</label>
        <Textarea rows={4} value={value.summary} onChange={(e) => set({ summary: e.target.value })} />
      </div>

      {value.experience.map((job, i) => (
        <div key={i} className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">
            {job.role} · {job.company} <span className="font-normal">({job.duration}) — one bullet per line</span>
          </label>
          <Textarea
            rows={Math.max(3, job.bullets.length + 1)}
            defaultValue={job.bullets.join('\n')}
            onChange={(e) =>
              set({
                experience: value.experience.map((exp, j) =>
                  j === i ? { ...exp, bullets: splitLines(e.target.value) } : exp,
                ),
              })
            }
          />
        </div>
      ))}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">Primary skills (comma separated)</label>
          <Textarea
            rows={3}
            defaultValue={value.skills.primary.join(', ')}
            onChange={(e) => set({ skills: { ...value.skills, primary: splitList(e.target.value) } })}
          />
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">Additional skills (comma separated)</label>
          <Textarea
            rows={3}
            defaultValue={value.skills.secondary.join(', ')}
            onChange={(e) => set({ skills: { ...value.skills, secondary: splitList(e.target.value) } })}
          />
        </div>
      </div>

      {value.projects.map((project, i) => (
        <div key={i} className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">Project · {project.name}</label>
          <Textarea
            rows={2}
            value={project.description}
            onChange={(e) =>
              set({
                projects: value.projects.map((p, j) => (j === i ? { ...p, description: e.target.value } : p)),
              })
            }
          />
        </div>
      ))}
    </div>
  );
}
