/**
 * Navigate through the browser when a full route transition is required.
 *
 * The current Next.js development runtime can fetch an RSC response for
 * `router.push` or `router.replace` without committing the browser URL. A
 * native navigation keeps deep links and the visible page in sync.
 */
export function navigateTo(url: string, options: { replace?: boolean } = {}) {
  if (typeof window === 'undefined') return;
  const target = new URL(url, window.location.href);
  if (target.href === window.location.href) return;
  if (options.replace) {
    window.location.replace(target.href);
  } else {
    window.location.assign(target.href);
  }
}
