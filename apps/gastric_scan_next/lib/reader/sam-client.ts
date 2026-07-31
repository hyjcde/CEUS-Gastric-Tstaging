import type { SamAnalyzeResult, SamBackendStatus, SamBox, SamClick } from '@/lib/reader/types';

export async function fetchSamStatus(): Promise<SamBackendStatus> {
  const res = await fetch('/api/agent/sam-interactive', { cache: 'no-store' });
  if (!res.ok) {
    return { available: false, error: `HTTP ${res.status}` };
  }
  return res.json() as Promise<SamBackendStatus>;
}

export type SamAnalyzePayload = {
  case_id: string;
  video_rel?: string;
  frame_time?: number;
  frame_png_b64?: string;
  image_width: number;
  image_height: number;
  clicks?: SamClick[];
  box?: SamBox | null;
  llm_report?: boolean;
};

export async function runSamAnalyze(payload: SamAnalyzePayload): Promise<SamAnalyzeResult> {
  const res = await fetch('/api/agent/sam-interactive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || data?.ok === false) {
    const err =
      data?.error ||
      (data?.result as { detail?: string })?.detail ||
      `SAM HTTP ${res.status}`;
    throw new Error(String(err));
  }
  const result = data.result as SamAnalyzeResult | undefined;
  if (!result) throw new Error('empty SAM result');
  return result;
}

export function captureVideoFrameB64(video: HTMLVideoElement): string {
  const c = document.createElement('canvas');
  c.width = video.videoWidth;
  c.height = video.videoHeight;
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('canvas unavailable');
  ctx.drawImage(video, 0, 0);
  return c.toDataURL('image/jpeg', 0.92).replace(/^data:image\/\w+;base64,/, '');
}

export function llmReportConfigured(status: SamBackendStatus | null): boolean {
  const s = status?.status;
  return Boolean(
    s?.llm_report?.configured || s?.deepseek?.configured || s?.minimax?.configured,
  );
}
