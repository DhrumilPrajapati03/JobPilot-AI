/** Auth failures are mapped to safe, actionable copy; provider payloads stay private. */
const LOGIN_ERRORS: Record<string, string> = {
  not_linked: 'That account is not linked to JobDots. Sign in with your owner token, then link it in Settings.',
  invalid_state: 'This sign-in attempt expired or was started in another browser. Try again.',
  cancelled: 'Sign-in was cancelled. Try again when you are ready.',
  provider_error: 'The provider did not confirm your account. Try again, or use your owner token.',
  provider_unavailable: 'This sign-in option is not set up on the server yet.',
  sign_in_first: 'Sign in first, then link your account from Settings.',
  invalid_request: 'That sign-in link was not valid. Start again from this page.',
};

export function loginErrorMessage(code: string): string {
  return LOGIN_ERRORS[code] ?? 'Sign-in did not complete. Try again.';
}

/** The API redirects failed logins to /login?auth_error=<code>. */
export function loginErrorFromUrl(href: string): string | null {
  const code = new URL(href).searchParams.get('auth_error');
  return code ? loginErrorMessage(code) : null;
}

export function authErrorMessage(error: unknown, context: 'token' | 'session' = 'session'): string {
  const e = error as { status?: number } | null;
  if (error instanceof TypeError)
    return 'JobDots could not reach the API. Check that the local stack is running, then try again.';
  if (context === 'token' && (e?.status === 401 || e?.status === 403))
    return 'That token was not accepted. Copy OWNER_API_TOKEN from your .env and try again.';
  if (e?.status === 503)
    return 'Sign-in is not configured on the server yet. Set OWNER_EMAIL and OWNER_API_TOKEN.';
  return 'Sign-in could not be checked. Try again shortly.';
}
