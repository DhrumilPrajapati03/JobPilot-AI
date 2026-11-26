// ============================================================
// JobDots — ExpertAvatar: identity + live state in one place (plan section 6.2)
// ============================================================
// The avatar IS the status indicator: no spinners or status dots for agent activity.
// bot-avatars draws the body and its motion (idle, working, sleeping); the six other
// states add one small badge. Reduced motion is handled by the library (still pose).

import { BotAvatar } from 'bot-avatars';
import { Ban, Check, Clock, Hand, Inbox, X } from 'lucide-react';
import { identityFor, presenceFor, seedFor } from './presence';

const ICONS = { clock: Clock, check: Check, alert: Ban, hand: Hand, ban: Ban, x: X, inbox: Inbox } as const;

interface Props {
  expert: string;            // agent_spec id
  name?: string;
  state?: string;            // roster state from /api/v1/experts
  step?: string;             // latest run_step summary (hover text)
  approvals?: number;        // pending approvals (shown on the waiting badge)
  size?: number;
  interactive?: boolean;     // pointer follow + click hop; off where a click opens the thread
}

export function ExpertAvatar({ expert, name, state = 'idle', step, approvals = 0, size = 36, interactive = false }: Props) {
  const identity = identityFor(expert);
  const presence = presenceFor(state);
  const badge = state === 'waiting_approval' && approvals ? `${approvals} to approve` : presence.badge;
  const Icon = presence.icon ? ICONS[presence.icon] : null;
  const label = `${name ?? expert}: ${step || presence.label}`;
  return (
    <span className="expert-avatar" role="img" aria-label={label} title={label} data-state={state}
          style={{ width: size, height: size, opacity: presence.dimmed ? 0.55 : 1 }}>
      <BotAvatar aria-hidden="true" type={identity.type} face={identity.face} hat={identity.hat}
                 glasses={identity.glasses} headphones={identity.headphones} bowTie={identity.bowTie}
                 state={presence.motion} size={size} seed={seedFor(expert)} interactive={interactive} />
      {badge && size >= 32 && (
        <span className="expert-avatar-badge" data-kind={presence.icon ?? undefined}>
          {Icon && <Icon size={10} aria-hidden="true" />}
          <span>{badge}</span>
        </span>
      )}
      {badge && size < 32 && <span className="expert-avatar-dot" data-kind={presence.icon ?? undefined} aria-hidden="true" />}
    </span>
  );
}

export default ExpertAvatar;
