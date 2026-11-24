/** Auth failures are mapped to safe, actionable copy; provider payloads stay private. */
export function authErrorMessage(error: unknown, context: 'email'|'oauth'|'session' = 'email'): string {
  const e = error as {code?: string; status?: number; name?: string; details?: {code?:string;error?:string}} | null;
  const code = e?.code || e?.details?.code || '';
  if (['access_denied','user_cancelled','user_canceled'].includes(code) || e?.details?.error === 'access_denied')
    return 'Sign-in was canceled. Try again or use another sign-in method.';
  if (['provider_disabled','oauth_provider_not_supported'].includes(code))
    return 'This sign-in provider is not available yet. Try another method or an email link.';
  if (e?.status === 429 || ['over_email_send_rate_limit', 'over_request_rate_limit'].includes(code))
    return 'Too many sign-in requests. Wait a few minutes, then try again.';
  if (['email_address_invalid', 'validation_failed'].includes(code) && context === 'email')
    return 'Enter a valid email address and try again.';
  if (code === 'email_address_not_authorized')
    return 'Sign-in email is unavailable for this address. Contact support to check email delivery.';
  if (error instanceof TypeError || code === 'network_error')
    return 'We could not reach the sign-in service. Check your connection and try again.';
  if (context === 'session' || ['flow_state_not_found','flow_state_expired','bad_code_verifier','otp_expired'].includes(code) || e?.name === 'AuthPKCEGrantCodeExchangeError')
    return 'This sign-in attempt expired or could not be verified. Try again in the same browser that started sign-in.';
  if (context === 'oauth')
    return 'We could not complete sign-in. Try again or use another sign-in method.';
  return 'We could not send your sign-in link. Try again shortly. If this continues, contact support.';
}
