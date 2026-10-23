// Edit these exact origins together with manifest.json for a different deployment.
// Never trust an arbitrary *.onrender.com page to replace an extension credential.
globalThis.JOBPILOT_POLICY = Object.freeze({
  appOrigins: ['http://localhost:5173', 'http://127.0.0.1:5173', 'https://jobpilot-web.onrender.com'],
  apiOrigins: ['http://localhost:8000', 'http://127.0.0.1:8000', 'https://jobpilot-api.onrender.com'],
  origin(value) {
    try {
      const url = new URL(value);
      if (url.username || url.password) return null;
      return url.origin;
    } catch { return null; }
  },
  apiBase(value) {
    try {
      const url = new URL(value);
      return this.apiOrigins.includes(url.origin) && !url.username && !url.password &&
        url.pathname === '/' && !url.search && !url.hash ? url.origin : null;
    } catch { return null; }
  },
});
