// ============================================================
// JobDots — browser session (plan section 4.1)
// ============================================================
// The API keeps the session in an HttpOnly cookie, so the frontend never sees a token.
// Every request sends the cookie (credentials: 'include') and our CSRF header; the API
// refuses cookie-authenticated writes without it.

export const CSRF_HEADER = 'X-JobDots-Request';

export function sessionInit(init: RequestInit = {}): RequestInit {
  // Callers pass plain header objects; keep them and add ours.
  const headers = { ...(init.headers as Record<string, string> | undefined), [CSRF_HEADER]: '1' };
  return { ...init, headers, credentials: 'include' };
}

export function sessionFetch(input: string, init: RequestInit = {}): Promise<Response> {
  return fetch(input, sessionInit(init));
}
