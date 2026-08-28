import { NextRequest, NextResponse } from 'next/server';
import { isLocalWallLabQueue } from '@/lib/cohort';
import { isTrustedPublicUpstream } from '@/lib/reader/local-access';
import { requireAppAuth } from '@/lib/reader/require-app-auth';
import { canBrowseWorkbenchQueues } from '@/lib/reader/queue-access';

export function denyPublicQueueUnlessPrivileged(
  request: NextRequest,
  queueId?: string | null,
): NextResponse | null {
  if (process.env.NEXT_PUBLIC_READER_ONLY !== '1') return null;
  const queue = String(queueId || '').trim();
  if (!queue || queue === 'reader:reader_v150') return null;
  if (isTrustedPublicUpstream(request.headers)) return null;
  const access = requireAppAuth(request);
  if (!access.ok) return access.response;
  if (canBrowseWorkbenchQueues(access.accountId)) return null;
  return NextResponse.json(
    {
      ok: false,
      error: 'public workbench queues are limited to admin, jmr, why, test, and zml',
      code: 'public_queue_restricted',
    },
    { status: 403 },
  );
}

/** Wall-lab 4-case queue is LAN / next-dev only. Never serve it to the public site. */
export function denyLocalWallLabOnPublic(request: NextRequest, queueId?: string | null): NextResponse | null {
  if (!isLocalWallLabQueue(queueId)) return null;
  const fromPublicTunnel = (
    request.headers.get('x-agent-upstream-admit') === '1'
    || request.headers.get('x-doctor-session-token') === 'public-upstream'
  );
  if (process.env.NEXT_PUBLIC_READER_ONLY === '1' || fromPublicTunnel) {
    return NextResponse.json(
      {
        ok: false,
        error: 'local wall-lab queue is not on the public workbench',
        code: 'local_queue_only',
      },
      { status: 404 },
    );
  }
  return null;
}
