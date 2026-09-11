(() => {
  'use strict';

  const storageKey = 'cdp_access_token';

  const decodeClaims = token => {
    const encoded = token.split('.')[1].replaceAll('-', '+').replaceAll('_', '/');
    const padding = '='.repeat((4 - encoded.length % 4) % 4);
    const bytes = Uint8Array.from(atob(encoded + padding), character => character.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  };

  const clear = () => sessionStorage.removeItem(storageKey);

  const current = () => {
    const token = sessionStorage.getItem(storageKey);
    if (!token) return null;
    try {
      const claims = decodeClaims(token);
      if (!claims.exp || claims.exp * 1000 <= Date.now()) {
        clear();
        return null;
      }
      return {token, username: claims.sub, role: claims.role, expiresAt: claims.exp};
    } catch (_error) {
      clear();
      return null;
    }
  };

  const login = async (username, password) => {
    const response = await fetch('/v1/auth/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username, password})
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Login failed');
    sessionStorage.setItem(storageKey, payload.access_token);
    return current();
  };

  const request = async (url, options = {}) => {
    const session = current();
    if (!session) throw new Error('Sign in to continue');
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${session.token}`);
    const response = await fetch(url, {...options, headers, credentials: 'same-origin'});
    if (response.status === 401) clear();
    return response;
  };

  const logout = async () => {
    const session = current();
    if (session) {
      try { await request('/v1/auth/logout', {method: 'POST'}); } catch (_error) { /* local cleanup still applies */ }
    }
    clear();
  };

  window.CDPAuth = {clear, current, login, logout, request};
})();
