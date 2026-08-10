import { NextRequest, NextResponse } from 'next/server';

const READER_ONLY_MODE = process.env.NEXT_PUBLIC_READER_ONLY === '1';

const READER_API_PREFIXES = [
  '/api/agent/nninteractive',
  '/api/agent/sam-interactive',
  '/api/agent/lesion-segmentation',
  '/api/agent/lumen-detection',
  '/api/agent/video/propagate',
  '/api/agent/video/keyframes',
  '/api/agent/dino/features',
  '/api/agent/artifacts',
  '/api/explainable/analyze',
  '/api/reader-agent/result',
  '/api/reader-audit/events',
  '/api/reader/account',
  '/api/reader/history',
  '/api/reader/agent/analyze',
  '/api/reader/cases',
  '/api/reader/media',
  '/api/patients/mask-overrides',
  '/api/patients/lumen-overrides',
] as const;

function isExactOrChild(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

function isPublicAsset(pathname: string): boolean {
  return pathname.startsWith('/_next/')
    || pathname === '/favicon.ico'
    || /\.(?:css|js|mjs|map|png|jpe?g|webp|svg|ico|woff2?|ttf)$/i.test(pathname);
}

function isAllowedReaderPath(pathname: string): boolean {
  if (pathname.startsWith('/api/')) {
    return READER_API_PREFIXES.some((prefix) => isExactOrChild(pathname, prefix));
  }
  // Public auth mount strips `/workbench` → `/`. Keep root + main app pages allowed.
  if (
    pathname === '/'
    || pathname === '/reader'
    || pathname.startsWith('/reader/')
    || pathname === '/workbench'
    || pathname.startsWith('/workbench/')
    || pathname === '/profile'
    || pathname.startsWith('/profile/')
    || pathname === '/reports'
    || pathname.startsWith('/reports/')
    || pathname === '/annotate'
    || pathname.startsWith('/annotate/')
  ) return true;
  if (isPublicAsset(pathname)) return true;
  return false;
}

export function proxy(request: NextRequest) {
  if (!READER_ONLY_MODE || isAllowedReaderPath(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  if (request.nextUrl.pathname.startsWith('/api/')) {
    return NextResponse.json(
      { ok: false, error: 'This route is unavailable in the public reader deployment.' },
      { status: 404 },
    );
  }

  return new NextResponse('Not Found', { status: 404 });
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
