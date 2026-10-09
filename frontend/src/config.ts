// Every value here is public. Production builds must select an HTTPS backend.
export function apiBaseUrl(configured: string | undefined, production: boolean): string {
  const value = configured?.trim() || (production ? '' : 'http://127.0.0.1:18080');
  if (!value) throw new Error('Public API URL is missing');
  const url = new URL(value);
  const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/'
    || (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback && !production))) {
    throw new Error('Invalid public API URL');
  }
  return url.origin;
}
