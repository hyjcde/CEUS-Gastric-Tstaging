/** Build same-origin media URL for reader study videos served via SAM static root proxy. */
export function readerMediaUrl(relPath: string, version?: string): string {
  if (!relPath) return '';
  if (/^https?:\/\//i.test(relPath) || relPath.startsWith('blob:') || relPath.startsWith('data:')) {
    return relPath;
  }
  const params = new URLSearchParams();
  params.set('rel', relPath.replace(/^\//, ''));
  if (version) params.set('v', version);
  return `/api/reader/media?${params.toString()}`;
}
