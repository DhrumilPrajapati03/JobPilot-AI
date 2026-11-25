const AUTH_PARAMS = ['auth_error'];

/** Remove sign-in result parameters from the address bar after reading them. */
export function cleanAuthCallbackUrl(href: string): string {
  const url = new URL(href);
  for (const key of AUTH_PARAMS) url.searchParams.delete(key);
  return url.pathname + url.search + url.hash;
}
