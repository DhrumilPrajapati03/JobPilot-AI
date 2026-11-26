// ============================================================
// JobDots — expert identity and presence (plan section 6.2)
// ============================================================
// Avatars come from `bot-avatars` (MIT, Libraries.dev). The library animates three
// states: default (idle), working and sleeping. The plan has nine; the other six are a
// small corner badge with an icon and words (never colour alone) on top of the library's
// state, and the hover text gives the current step.

import type { BotAvatarGlasses, BotAvatarHat, BotAvatarState, BotAvatarType } from 'bot-avatars';

export type ExpertState =
  | 'idle' | 'acknowledged' | 'working' | 'waiting_approval' | 'needs_hand_off'
  | 'blocked' | 'failed' | 'done' | 'paused' | 'draft';

export interface Identity {
  type: BotAvatarType;
  face?: 'eyes' | 'mouth';
  hat?: BotAvatarHat;
  glasses?: BotAvatarGlasses;
  headphones?: boolean;
  bowTie?: boolean;
}

/** One body shape per expert, so each is recognisable at 24 px without reading its name. */
export const IDENTITY: Record<string, Identity> = {
  supervisor: { type: 'star', bowTie: true },
  scout: { type: 'clover' },
  researcher: { type: 'hexagon', glasses: 'round' },
  comp_analyst: { type: 'square' },
  tailor: { type: 'flower', hat: 'beret' },
  answerer: { type: 'blob', face: 'mouth' },
  applicant: { type: 'pill' },
  recon: { type: 'ghost', glasses: 'shades' },
  connector: { type: 'circle' },
  email_outreach: { type: 'cloud' },
  dm_outreach: { type: 'drop' },
  inbox: { type: 'pebble', headphones: true },
  interview_buddy: { type: 'cat', face: 'mouth' },
  reviewer: { type: 'droid', glasses: 'square' },
};

/** Custom experts (Day 14) get a shape no built-in uses, chosen from their id. */
const SPARE: BotAvatarType[] = ['triangle', 'mech', 'alien', 'puddle'];

export function identityFor(expertId: string): Identity {
  if (IDENTITY[expertId]) return IDENTITY[expertId];
  let hash = 0;
  for (const c of expertId) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  return { type: SPARE[hash % SPARE.length] };
}

export interface Presence {
  motion: BotAvatarState;
  /** short badge text; null = no badge */
  badge: string | null;
  /** icon name for the badge (lucide) */
  icon: 'clock' | 'check' | 'alert' | 'hand' | 'ban' | 'x' | 'inbox' | null;
  /** words for screen readers and the hover line when there is no current step */
  label: string;
  dimmed: boolean;
}

export const PRESENCE: Record<ExpertState, Presence> = {
  idle: { motion: 'default', badge: null, icon: null, label: 'Idle', dimmed: false },
  acknowledged: { motion: 'default', badge: 'Queued', icon: 'clock', label: 'Starting soon', dimmed: false },
  working: { motion: 'working', badge: null, icon: null, label: 'Working', dimmed: false },
  waiting_approval: { motion: 'default', badge: 'Approve', icon: 'inbox', label: 'Waiting for your approval', dimmed: false },
  needs_hand_off: { motion: 'default', badge: 'Your turn', icon: 'hand', label: 'Needs you to take over', dimmed: false },
  blocked: { motion: 'default', badge: 'Blocked', icon: 'ban', label: 'Blocked by a policy or budget limit', dimmed: false },
  failed: { motion: 'default', badge: 'Failed', icon: 'x', label: 'The last task failed', dimmed: false },
  done: { motion: 'default', badge: 'Done', icon: 'check', label: 'Just finished', dimmed: false },
  paused: { motion: 'sleeping', badge: null, icon: null, label: 'Paused', dimmed: false },
  draft: { motion: 'sleeping', badge: null, icon: null, label: 'Not built yet', dimmed: true },
};

export function presenceFor(state: string): Presence {
  return PRESENCE[state as ExpertState] ?? PRESENCE.idle;
}

/** Spread blinks and jumps across a row so the roster doesn't move in unison. */
export function seedFor(expertId: string): number {
  let hash = 7;
  for (const c of expertId) hash = (hash * 33 + c.charCodeAt(0)) % 997;
  return hash / 997;
}
