import type { MatchDetails } from '../../hooks/use-discovery';

export function MatchExplanation({ details }: { details?: MatchDetails }) {
  if (!details?.version) return null;
  const eligibility = details.eligibility;
  return <details className="mt-2 text-xs">
    <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Why this match · {eligibility?.status === 'review' ? 'Eligibility needs review' : eligibility?.status === 'ineligible' ? 'Eligibility conflict' : 'No eligibility conflict found'}</summary>
    <div className="mt-2 space-y-2 rounded-md bg-muted/50 p-3">
      <p>This is a ranking score, not a hiring probability. Eligibility conflicts override similarity.</p>
      {details.components && <dl className="grid grid-cols-3 gap-2">
        <div><dt className="text-muted-foreground">Role relevance</dt><dd>{Math.round(details.components.title)}%</dd></div>
        <div><dt className="text-muted-foreground">Skill coverage</dt><dd>{Math.round(details.components.skills)}%</dd></div>
        <div><dt className="text-muted-foreground">Meaning similarity</dt><dd>{details.components.semantic === null ? 'Not used' : `${Math.round(details.components.semantic)}%`}</dd></div>
      </dl>}
      {details.components?.semantic === null && <p>Local semantic scoring was unavailable or disabled; this score uses role and skill overlap.</p>}
      <ul className="space-y-1">{details.reasons?.map(reason => <li key={reason}>{reason}</li>)}</ul>
      {!details.identity?.complete && <p className="text-warning">Resume facts still need your review. Automatic drafting waits until all current facts are confirmed.</p>}
      <ul className="space-y-2">{eligibility?.checks.map(check => <li key={check.dimension}>
        <p><span className="font-medium capitalize">{check.dimension.replaceAll('_',' ')}:</span> {check.reason}</p>
        {check.evidence && <blockquote className="mt-0.5 border-l-2 pl-2 text-muted-foreground">{check.evidence}</blockquote>}
      </li>)}</ul>
      <p className="text-muted-foreground">Based on the last scan and your declared preferences. Confirmed facts are user declarations.</p>
    </div>
  </details>;
}
