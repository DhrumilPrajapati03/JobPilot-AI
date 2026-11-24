const AUTH_PARAMS = ['code','error','error_code','error_description','access_token',
  'refresh_token','provider_token','provider_refresh_token','expires_at','expires_in','token_type','type'];

/** Previously issued email fragments are handed to the SDK's setSession once. */
export function legacySessionFromUrl(href: string): {access_token:string;refresh_token:string}|null {
  const url=new URL(href);
  const fragment = new URLSearchParams(url.hash.slice(1));
  if(['error','error_code','error_description'].some(key=>url.searchParams.has(key)||fragment.has(key)))return null;
  const access_token=fragment.get('access_token'), refresh_token=fragment.get('refresh_token');
  return access_token && refresh_token ? {access_token,refresh_token} : null;
}

export function hasAuthCallback(href: string): boolean {
  const url = new URL(href);
  const fragment = new URLSearchParams(url.hash.slice(1));
  return ['code','access_token','error','error_code','error_description'].some(key =>
    url.searchParams.has(key) || fragment.has(key));
}

/** Never redirect a completed login to a caller-supplied external URL. */
export const authReturnUrl = (origin: string) => new URL('/login', origin).href;

/** SDK consumes successful callbacks; remove failed/reused credentials as well. */
export function cleanAuthCallbackUrl(href: string): string {
  const url = new URL(href);
  const fragment = new URLSearchParams(url.hash.slice(1));
  for (const key of AUTH_PARAMS) { url.searchParams.delete(key); fragment.delete(key); }
  url.hash = fragment.toString();
  return url.pathname + url.search + url.hash;
}
