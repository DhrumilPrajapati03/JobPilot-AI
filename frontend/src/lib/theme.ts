// Theme preference: "system" follows the OS; "light"/"dark" set data-theme on <html>.
export type ThemePreference = 'system' | 'light' | 'dark';

const KEY = 'jobpilot-theme';

export function getThemePreference(): ThemePreference {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    return 'system';
  }
}

export function applyTheme(preference: ThemePreference) {
  const root = document.documentElement;
  if (preference === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', preference);
}

export function setThemePreference(preference: ThemePreference) {
  try {
    if (preference === 'system') localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, preference);
  } catch {
    // Storage blocked — the choice still applies for this session.
  }
  applyTheme(preference);
}
