import { NextResponse } from 'next/server';
import { probeAgentLlmEnv } from '@/lib/agent-python-env';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Public readiness probe for Python Agent LLM wiring (A6). No secrets. */
export async function GET() {
  return NextResponse.json({
    ...probeAgentLlmEnv(),
    requirement_id: 'A6',
  });
}
