// ============================================================
// JobPilot AI — Tailored resume tab (preview, compare, edit, export)
// ============================================================

import { useState } from 'react';
import { Columns2, Download, FileText, Pencil, Printer, Save, X } from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { Button } from '../ui/button';
import { ResumeEditor, ResumePreview } from './ResumePreview';
import { ResumeDiff } from './ResumeDiff';
import { useDraft } from '../../hooks/use-draft';
import { useAuth } from '../../hooks/use-auth';
import { useProfile, useResume, type Resume } from '../../hooks/use-profile';
import {
  downloadTailoredPdf,
  useUpdateTailoredResume,
  type JobApplication,
  type TailoredResume,
} from '../../hooks/use-applications';
import { cn } from '@/lib/utils';

/** Fill defaults so partially-populated LLM output renders safely. */
export function normalizeResume(content: Partial<Resume> | null | undefined): Resume {
  return {
    name: content?.name ?? '',
    headline: content?.headline ?? '',
    summary: content?.summary ?? '',
    experience: (content?.experience ?? []).map((e) => ({ ...e, bullets: e.bullets ?? [] })),
    skills: { primary: content?.skills?.primary ?? [], secondary: content?.skills?.secondary ?? [] },
    projects: (content?.projects ?? []).map((p) => ({ ...p, description: p.description ?? '', tech: p.tech ?? [] })),
    education: content?.education ?? [],
    certifications: content?.certifications ?? [],
  };
}

type Mode = 'preview' | 'compare' | 'edit';

export function ResumeTab({ application, tailored }: { application: JobApplication; tailored: TailoredResume | null }) {
  const [mode, setMode] = useState<Mode>('preview');
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const { user } = useAuth();
  const { data: profile } = useProfile();
  const { data: baseResume } = useResume();
  const update = useUpdateTailoredResume(application.id);
  const resume = normalizeResume(tailored?.content);
  const { draft, setDraft, dirty, reset } = useDraft(resume);

  if (!tailored) {
    return (
      <Card className="border-dashed p-12 text-center">
        <FileText size={36} className="mx-auto text-muted-foreground/40" />
        <p className="mt-3 text-sm font-semibold text-muted-foreground">No tailored resume for this application.</p>
      </Card>
    );
  }

  const keywords = [...(application.jd_analysis?.required_skills ?? []), ...(application.jd_analysis?.keywords ?? [])];
  const contact = { email: user?.email, location: profile?.location, linkedin_url: profile?.linkedin_url };

  const handleDownload = async () => {
    setExportNote(null);
    setExporting(true);
    const slug = (resume.name || 'resume').replace(/[^A-Za-z0-9]+/g, '_');
    try {
      await downloadTailoredPdf(application.id, `${slug}_${application.company.replace(/[^A-Za-z0-9]+/g, '_')}.pdf`);
    } catch {
      setExportNote('The server PDF engine isn’t available, so your browser’s print dialog opened instead — choose “Save as PDF”.');
      setMode('preview');
      window.setTimeout(() => window.print(), 50);
    } finally {
      setExporting(false);
    }
  };

  const handleSave = () =>
    update.mutate(draft, {
      onSuccess: () => setMode('preview'),
    });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-lg bg-secondary p-0.5" role="tablist" aria-label="Resume view">
          {(
            [
              ['preview', 'Tailored', FileText],
              ['compare', 'Changes', Columns2],
              ['edit', 'Edit', Pencil],
            ] as const
          ).map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              onClick={() => setMode(value)}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                mode === value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {mode === 'edit' ? (
            <>
              {update.error && <span className="text-xs text-destructive">{update.error.message}</span>}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  reset();
                  setMode('preview');
                }}
              >
                <X size={14} className="mr-1.5" />
                Cancel
              </Button>
              <Button size="sm" onClick={handleSave} disabled={!dirty || update.isPending}>
                <Save size={14} className="mr-1.5" />
                {update.isPending ? 'Saving & re-scoring…' : 'Save & re-score'}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={() => window.print()}>
                <Printer size={14} className="mr-1.5" />
                Print
              </Button>
              <Button size="sm" onClick={handleDownload} disabled={exporting}>
                <Download size={14} className="mr-1.5" />
                {exporting ? 'Rendering…' : 'Download PDF'}
              </Button>
            </>
          )}
        </div>
      </div>

      {exportNote && (
        <p className="rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">{exportNote}</p>
      )}

      {mode === 'edit' && (
        <Card>
          <CardContent className="p-5">
            <p className="mb-4 text-xs text-muted-foreground">
              Companies, titles and dates are locked to your base resume. Saving re-runs the ATS keyword check.
            </p>
            <ResumeEditor value={draft} onChange={setDraft} />
          </CardContent>
        </Card>
      )}

      {mode === 'compare' ? (
        baseResume ? (
          <ResumeDiff base={normalizeResume(baseResume)} tailored={resume} keywords={keywords} />
        ) : (
          <Card className="p-8 text-center text-sm text-muted-foreground">Loading base resume…</Card>
        )
      ) : (
        mode === 'preview' && (
          <div className="resume-print-target">
            <ResumePreview resume={resume} contact={contact} keywords={keywords} />
          </div>
        )
      )}
    </div>
  );
}
