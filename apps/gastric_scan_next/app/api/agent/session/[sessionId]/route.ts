import fs from 'fs';
import path from 'path';
import { NextResponse } from 'next/server';
import { PROJECT_ROOT } from '@/lib/config';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  try {
    const { sessionId } = await params;
    const sessionPath = path.join(PROJECT_ROOT, 'tmp', 'agent_sessions', `${sessionId}.json`);

    if (!fs.existsSync(sessionPath)) {
      return NextResponse.json({ error: 'Session not found' }, { status: 404 });
    }

    const raw = fs.readFileSync(sessionPath, 'utf-8');
    return NextResponse.json(JSON.parse(raw));
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to read session' },
      { status: 500 },
    );
  }
}
