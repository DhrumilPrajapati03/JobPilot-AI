// ============================================================
// JobPilot — Minimal markdown for agent replies
// Paragraphs, lists, tables, quotes, rules, **bold**, *italic*, `code`.
// Renders React nodes only (no innerHTML), so model output can't inject markup.
// ============================================================

import { Fragment, type ReactNode } from 'react';

function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;
  while ((match = pattern.exec(text))) {
    if (match.index > last) nodes.push(<Fragment key={i++}>{text.slice(last, match.index)}</Fragment>);
    const token = match[0];
    if (token.startsWith('**')) nodes.push(<strong key={i++} className="font-semibold text-foreground">{token.slice(2, -2)}</strong>);
    else if (token.startsWith('`')) nodes.push(<code key={i++} className="rounded bg-muted px-1 py-0.5 text-[0.85em] font-mono">{token.slice(1, -1)}</code>);
    else nodes.push(<em key={i++}>{token.slice(1, -1)}</em>);
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(<Fragment key={i++}>{text.slice(last)}</Fragment>);
  return nodes;
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.replace(/\r/g, '').split('\n');
  let list: { ordered: boolean; items: string[] } | null = null;
  let paragraph: string[] = [];
  let table: string[][] | null = null;
  let quote: string[] = [];

  const cells = (row: string) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
  const flushTable = () => {
    if (table && table.length) {
      const [head, ...body] = table;
      blocks.push(
        <div key={blocks.length} className="overflow-x-auto rounded-lg border">
          <table className="w-full text-left text-[0.85rem]">
            <thead className="bg-muted/60 text-xs text-muted-foreground">
              <tr>{head.map((c, i) => <th key={i} className="px-3 py-2 font-medium">{inline(c)}</th>)}</tr>
            </thead>
            <tbody className="divide-y">
              {body.map((row, r) => (
                <tr key={r}>{row.map((c, i) => <td key={i} className="px-3 py-2 align-top">{inline(c)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
    }
    table = null;
  };
  const flushQuote = () => {
    if (quote.length) {
      blocks.push(<blockquote key={blocks.length} className="border-l-2 pl-3 text-muted-foreground">{inline(quote.join(' '))}</blockquote>);
      quote = [];
    }
  };

  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push(<p key={blocks.length}>{inline(paragraph.join(' '))}</p>);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      const items = list.items.map((item, i) => <li key={i}>{inline(item)}</li>);
      blocks.push(
        list.ordered ? (
          <ol key={blocks.length} className="list-decimal space-y-1 pl-5">{items}</ol>
        ) : (
          <ul key={blocks.length} className="list-disc space-y-1 pl-5 marker:text-muted-foreground">{items}</ul>
        ),
      );
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const isTableRow = /^\s*\|.*\|\s*$/.test(line);
    if (isTableRow) {
      flushParagraph();
      flushList();
      flushQuote();
      if (/^\s*\|?\s*:?-{2,}/.test(line.replace(/\|/g, '|'))) continue; // header separator row
      (table ??= []).push(cells(line));
      continue;
    }
    flushTable();
    if (/^\s*>\s?/.test(line)) {
      flushParagraph();
      flushList();
      quote.push(line.replace(/^\s*>\s?/, ''));
      continue;
    }
    flushQuote();
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      flushParagraph();
      flushList();
      blocks.push(<hr key={blocks.length} className="border-border" />);
      continue;
    }
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const heading = /^#{1,4}\s+(.*)$/.exec(line);
    if (bullet || numbered) {
      flushParagraph();
      const ordered = !!numbered;
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? numbered)![1]);
    } else if (heading) {
      flushParagraph();
      flushList();
      blocks.push(<p key={blocks.length} className="font-semibold">{inline(heading[1])}</p>);
    } else if (!line.trim()) {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line.trim());
    }
  }
  flushParagraph();
  flushList();
  flushTable();
  flushQuote();

  return <div className="space-y-2.5 text-[0.92rem] leading-relaxed">{blocks}</div>;
}
