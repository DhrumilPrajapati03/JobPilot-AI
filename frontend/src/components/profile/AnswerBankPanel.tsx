// ============================================================
// JobPilot — Answer bank for application screening questions
// ============================================================

import { useMemo, useState } from 'react';
import { AlertCircle, Loader2, Lock, Plus, Save, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { useAnswers, useDeleteAnswer, useSaveAnswers, type AnswerCategory, type SavedAnswer } from '../../hooks/use-answers';
import { cn } from '@/lib/utils';

interface Field {
  question: string;
  category: AnswerCategory;
  options?: string[];
  placeholder?: string;
  type?: 'text' | 'number';
  sensitive?: boolean;
}

const YES_NO = ['Yes', 'No'];
const DECLINE = 'Decline to self-identify';

const SECTIONS: { title: string; hint?: string; fields: Field[] }[] = [
  {
    title: 'Contact & links',
    fields: [
      { question: 'Phone number', category: 'contact', placeholder: 'e.g. +91 98765 43210' },
      { question: 'City and country of residence', category: 'contact', placeholder: 'e.g. Pune, India' },
      { question: 'LinkedIn profile URL', category: 'contact', placeholder: 'e.g. https://linkedin.com/in/…' },
      { question: 'GitHub URL', category: 'contact', placeholder: 'e.g. https://github.com/…' },
      { question: 'Portfolio or personal website', category: 'contact', placeholder: 'e.g. https://…' },
    ],
  },
  {
    title: 'Work authorisation',
    fields: [
      { question: 'Are you legally authorized to work in the country of this job?', category: 'work_auth', options: YES_NO },
      { question: 'Will you now or in the future require visa sponsorship?', category: 'work_auth', options: YES_NO },
      { question: 'Countries you are authorized to work in', category: 'work_auth', placeholder: 'e.g. India, Germany (Blue Card)' },
    ],
  },
  {
    title: 'Availability & pay',
    fields: [
      { question: 'Notice period', category: 'availability', placeholder: 'e.g. 30 days' },
      { question: 'Earliest start date', category: 'availability', placeholder: 'e.g. Immediately / 1 Dec 2026' },
      { question: 'Are you willing to relocate?', category: 'availability', options: ['Yes', 'No', 'Depends on the role'] },
      { question: 'Expected salary', category: 'compensation', placeholder: 'e.g. ₹35 LPA / $150,000' },
      { question: 'Total years of professional experience', category: 'experience', type: 'number', placeholder: 'e.g. 5' },
    ],
  },
  {
    title: 'Voluntary self-identification',
    hint: 'Marked sensitive: used only to fill forms and never sent to an AI model.',
    fields: [
      { question: 'Gender', category: 'eeo', sensitive: true, options: [DECLINE, 'Woman', 'Man', 'Non-binary'] },
      { question: 'Race / ethnicity', category: 'eeo', sensitive: true, options: [DECLINE, 'Asian', 'Black or African American', 'Hispanic or Latino', 'White', 'Two or more races', 'Other'] },
      { question: 'Veteran status', category: 'eeo', sensitive: true, options: [DECLINE, 'I am not a veteran', 'I am a veteran'] },
      { question: 'Disability status', category: 'eeo', sensitive: true, options: [DECLINE, 'No, I do not have a disability', 'Yes, I have a disability'] },
    ],
  },
];

const STANDARD = new Set(SECTIONS.flatMap((s) => s.fields.map((f) => f.question)));
const skillQuestion = (skill: string) => `Years of experience with ${skill}`;

interface CustomRow {
  id?: string;
  key: string;
  question: string;
  answer: string;
}

export function AnswerBankPanel({ skills }: { skills: string[] }) {
  const { data: saved, isLoading, error } = useAnswers();
  const save = useSaveAnswers();
  const remove = useDeleteAnswer();
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [custom, setCustom] = useState<CustomRow[] | null>(null);

  const savedByQuestion = useMemo(() => new Map((saved ?? []).map((a) => [a.question, a])), [saved]);
  const skillFields: Field[] = skills.slice(0, 12).map((s) => ({ question: skillQuestion(s), category: 'experience', type: 'number', placeholder: '0' }));
  const skillQuestions = new Set(skillFields.map((f) => f.question));
  const customRows: CustomRow[] =
    custom ??
    (saved ?? [])
      .filter((a) => !STANDARD.has(a.question) && !skillQuestions.has(a.question) && !a.question.startsWith('Years of experience with '))
      .map((a) => ({ id: a.id, key: a.id ?? a.question, question: a.question, answer: a.answer }));

  const valueOf = (field: Field) => edits[field.question] ?? savedByQuestion.get(field.question)?.answer ?? (field.sensitive ? DECLINE : '');
  const setValue = (question: string, value: string) => setEdits((e) => ({ ...e, [question]: value }));
  const dirty = Object.keys(edits).length > 0 || custom !== null;

  if (isLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Loader2 className="animate-spin text-muted-foreground" size={20} />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm">
        <AlertCircle size={16} className="mt-0.5 shrink-0 text-warning" />
        <span>{error.message}</span>
      </div>
    );
  }

  const allFields = [...SECTIONS.flatMap((s) => s.fields), ...skillFields];

  const onSave = () => {
    const rows: SavedAnswer[] = allFields
      .filter((f) => edits[f.question] !== undefined || (f.sensitive && !savedByQuestion.has(f.question)))
      .map((f) => ({ question: f.question, answer: valueOf(f), category: f.category, sensitive: !!f.sensitive }));
    customRows
      .filter((r) => r.question.trim())
      .forEach((r) => rows.push({ question: r.question.trim(), answer: r.answer, category: 'custom', sensitive: false }));
    save.mutate(rows, {
      onSuccess: () => {
        setEdits({});
        setCustom(null);
      },
    });
  };

  const renderField = (field: Field) => {
    const id = `qa-${field.question.replace(/\W+/g, '-').toLowerCase()}`;
    const value = valueOf(field);
    return (
      <div key={field.question} className="grid gap-1.5 sm:grid-cols-[1fr_minmax(0,1.1fr)] sm:items-center sm:gap-4">
        <label htmlFor={id} className="flex items-center gap-1.5 text-sm">
          {field.question}
          {field.sensitive && <Lock size={12} className="text-muted-foreground" aria-label="Sensitive" />}
        </label>
        {field.options ? (
          <select
            id={id}
            value={value}
            onChange={(e) => setValue(field.question, e.target.value)}
            className="h-9 rounded-md border border-input bg-card px-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {!field.sensitive && <option value="">—</option>}
            {field.options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        ) : (
          <Input
            id={id}
            type={field.type ?? 'text'}
            min={field.type === 'number' ? 0 : undefined}
            value={value}
            placeholder={field.placeholder}
            onChange={(e) => setValue(field.question, e.target.value)}
          />
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Saved answers to the questions application forms ask again and again. They'll be used to fill forms for you later; for now the
        assistant can look them up.
      </p>

      {SECTIONS.map((section) => (
        <Card key={section.title}>
          <CardHeader>
            <CardTitle>{section.title}</CardTitle>
            {section.hint && <p className="text-sm text-muted-foreground">{section.hint}</p>}
          </CardHeader>
          <CardContent className="space-y-3">{section.fields.map(renderField)}</CardContent>
        </Card>
      ))}

      <Card>
        <CardHeader>
          <CardTitle>Years of experience by skill</CardTitle>
          <p className="text-sm text-muted-foreground">From the primary skills in your resume.</p>
        </CardHeader>
        <CardContent className="space-y-3">
          {skillFields.length ? skillFields.map(renderField) : <p className="text-sm text-muted-foreground">Add primary skills on the Skills tab first.</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle>Your own questions</CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCustom([...customRows, { key: `new-${Date.now()}`, question: '', answer: '' }])}
          >
            <Plus size={14} className="mr-1" />
            Add question
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {customRows.length === 0 && <p className="text-sm text-muted-foreground">e.g. “Why do you want to work here?” or “Describe a project you’re proud of.”</p>}
          {customRows.map((row, i) => (
            <div key={row.key} className="space-y-2 rounded-lg border p-3">
              <div className="flex items-center gap-2">
                <Input
                  value={row.question}
                  placeholder="Question"
                  aria-label="Question"
                  onChange={(e) => setCustom(customRows.map((r, j) => (j === i ? { ...r, question: e.target.value } : r)))}
                />
                <button
                  type="button"
                  onClick={() => {
                    if (row.id) remove.mutate(row.id);
                    setCustom(customRows.filter((_, j) => j !== i));
                  }}
                  className="rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-destructive"
                  aria-label="Delete question"
                >
                  <Trash2 size={15} />
                </button>
              </div>
              <Textarea
                rows={3}
                value={row.answer}
                placeholder="Your answer"
                aria-label="Answer"
                onChange={(e) => setCustom(customRows.map((r, j) => (j === i ? { ...r, answer: e.target.value } : r)))}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <div className={cn('sticky bottom-0 -mx-1 flex items-center justify-end gap-2 bg-background/90 px-1 py-3 backdrop-blur', !dirty && 'hidden')}>
        {save.error && <span className="text-xs text-destructive">{save.error.message}</span>}
        <Button
          variant="ghost"
          onClick={() => {
            setEdits({});
            setCustom(null);
          }}
          disabled={save.isPending}
        >
          Discard
        </Button>
        <Button onClick={onSave} disabled={save.isPending}>
          {save.isPending ? <Loader2 size={15} className="mr-1.5 animate-spin" /> : <Save size={15} className="mr-1.5" />}
          Save answers
        </Button>
      </div>
    </div>
  );
}
