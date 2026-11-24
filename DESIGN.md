# JobPilot design system

On 7 November 2026 the user authorized refining Career Desk and revisiting the
landing with detailed research. The selected implementation direction is an
agentic Career Desk: warm reading surfaces, green-charcoal navigation, blue actions,
iris AI assistance, lime completion and amber review. See `DESIGN_RESEARCH.md`.

Workspace direction 02, **The Career Desk**, was selected as the base for refinement:
warm paper surfaces, charcoal navigation, a split opportunity list/detail view,
an application pipeline and a focused copilot. Light/dark and mobile views are
interactive. Prototype scores, employers, profiles and responses are fictional.
No external messages or applications are sent.

Private MagicPath project: `468621492993798144`.
Direction 02 component: `469783964467486720`, revision `469783964467486721`.
The previous component `468621565819490304` is retained for comparison.
The later user instruction authorizes the coordinated landing and app refinement.
Current final design drafts are in [Superdesign](https://superdesign.dev/teams/d7356d19-5c2c-42be-a4c1-56c6037d07de/projects/5f230bd0-9371-4aaa-a86a-2e8465aca118).

## Current implementation checklist

Bound: one React application. The new overview is the only page of its kind; no
majority convention is claimed for it. Existing pages continue to reuse the
Button/Input/Card primitives; WorkflowMap is a new shared capability component.

1. Keep every existing route and action; `/workspace` adds an overview.
2. Show actual data or loading/unavailable states. Never fabricate active agents.
3. A workflow overview describes capabilities; actual execution is labelled by events.
4. Keep match evidence, confirmed-fact limits and approval/submission boundaries.
5. Use shared semantic theme variables in both light and dark; literal palette
   values belong in the theme or deliberate scoped marketing/sidebar theme.
6. Use existing shared controls; headings follow h1 → h2 → h3 in new regions.
7. New surfaces use 16/20/24/28/32px spacing. The legacy project has mixed spacing;
   existing typography/rhythm is not claimed to be a universal convention.
8. New reading copy is 12–15px; metadata 9–12px, with smaller purely illustrative
   marketing labels identified separately. Important instructions stay readable.
9. Keyboard focus, drawer Escape/trap/restoration and mobile back navigation work.
10. Check text contrast (WCAG AA target), reduced motion, errors, empty states and
    viewport overflow separately. Source checks cannot certify visual accessibility.

## Foundations

- Inter/system sans-serif. Comfortable body text; compact metadata stays legible.
- Blue primary actions and navigation; lime is a restrained highlight. Errors,
  warnings and application statuses keep separate semantic colors and text labels.
- Light and dark themes use the same hierarchy. PDF paper stays white.
- Shared tokens live in `frontend/src/index.css`; shared elements live in
  `frontend/src/components/ui`. Never add another page-specific palette.
- Use 8/12/16/24/32px rhythm through Tailwind; existing radius tokens are 6/8/12px.
- One primary next action per region. Secondary actions use outline/ghost styles.

## Page checklists

The landing is the visual reference, not a template for dense workspace layouts.
Each existing route keeps its data/actions while adopting these shared rules:

1. AppShell/Sidebar supply navigation, account controls, title context and mobile drawer.
2. Page heading and description precede controls; use a single descriptive heading.
3. Reuse Button, Card, Input, Label, Badge and Tabs rather than hand-written variants.
4. Label inputs, expose keyboard focus and explain validation beside the field.
5. Make loading, empty, error/retry and success states visible; never render raw provider payloads.
6. Keep lists readable, filters discoverable and horizontal overflow intentional.
7. Preserve account isolation, revision approval and user-controlled submissions.
8. Check narrow/mobile, tablet and desktop in light/dark; honor reduced motion.
9. Independently review each changed region against this checklist; browser tests
   verify behavior. Source review alone does not establish accessibility compliance.

Do not copy marketing hero sizes or tiny illustrative-preview labels into app screens.
The literal palette is defined only by the shared theme; use its semantic tokens.

## Google/GitHub sign-in addition — 8 November

Bound: `/login`, its existing LoginForm and auth controls only. This is an addition
to the existing sign-in page; other page layouts are unchanged. The login page is
the only member of this page family, so no cross-page majority is claimed.

1. Keep the intro, single card, heading and labelled magic-link form/resend flow.
2. Add “Continue with Google” and “Continue with GitHub” above the email form,
   separated by “or use an email link”; use existing Button outline variants.
3. Provider buttons are `type="button"`, full width, equal height (44px minimum),
   with decorative icons; no new icon-only actions or literal page palette.
4. Show which provider is opening, disable competing actions while pending, and
   expose sending/progress status without pretending authentication succeeded.
5. Keep safe inline errors, retry after cancellation/failure and email as fallback.
6. An authenticated callback enters the existing workspace; never accept an
   arbitrary external `next` URL or render raw provider error descriptions.
7. Use the shared theme/type/focus tokens; provider controls use 12px gaps and
   existing 16/24px section spacing. Preserve light/dark/mobile/keyboard behavior.
8. A check-email success view also offers returning to other sign-in methods;
   it must not trap users in email-only login after this addition.
9. Source review and browser fixtures cover local behavior; real Google/GitHub
   consent and account linking require provider setup and separate acceptance.
