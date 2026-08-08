/** 阅片包交互 Agent（SAM + 胃壁分层）局域网入口 */

const DEFAULT_READING_AGENT_URL = 'http://127.0.0.1:8767/interactive_video_agent.html';

export type ReadingAgentPatientContext = {
  id?: string;
  patient_id?: string;
  phase?: string;
  group?: string;
  image_url?: string;
  video_urls?: Array<{ url?: string; filename?: string }>;
  id_short?: string;
};

export function getReadingAgentBaseUrl(): string {
  const configured = (typeof window === 'undefined'
    ? process.env.READING_AGENT_INTERNAL_URL?.trim() || process.env.NEXT_PUBLIC_READING_AGENT_URL?.trim()
    : process.env.NEXT_PUBLIC_READING_AGENT_URL?.trim());
  const raw = (configured || DEFAULT_READING_AGENT_URL).replace(/\/$/, '');
  // Strip page path so API calls hit http://host:8767/api/...
  const stripped = raw
    .replace(/\/interactive_video_agent\.html$/i, '')
    .replace(/\/ai_assist\.html$/i, '')
    .replace(/\/video_mask_demo\.html$/i, '')
    .replace(/\/direction_demo\.html$/i, '');
  return stripped || 'http://127.0.0.1:8767';
}

export function getReadingAgentPageUrl(): string {
  const configured = process.env.NEXT_PUBLIC_READING_AGENT_URL?.trim();
  if (configured) {
    if (configured.endsWith('.html')) return configured;
    return `${configured.replace(/\/$/, '')}/interactive_video_agent.html`;
  }
  return DEFAULT_READING_AGENT_URL;
}

export function buildReaderAppUrl(patient?: ReadingAgentPatientContext | null): string {
  const params = new URLSearchParams();
  const caseCandidates = [patient?.id, patient?.id_short, patient?.patient_id]
    .filter(Boolean)
    .map((value) => String(value));
  const caseMatch = caseCandidates
    .map((value) => value.match(/\b((?:CASE|BM)-\d+)\b/i))
    .find(Boolean);
  if (caseMatch) {
    const raw = caseMatch[1].toUpperCase();
    const m = raw.match(/^(CASE|BM)-(\d+)$/);
    if (m) params.set('case', `${m[1]}-${m[2].padStart(3, '0')}`);
  }
  const absUrl = (url: string) => {
    if (!url) return '';
    if (typeof window !== 'undefined' && url.startsWith('/')) {
      return `${window.location.origin}${url}`;
    }
    return url;
  };
  const videoUrl = absUrl(patient?.video_urls?.[0]?.url || '');
  if (videoUrl) params.set('video', videoUrl);
  const imageUrl = absUrl(patient?.image_url || '');
  if (imageUrl) params.set('image', imageUrl);
  if (patient?.patient_id) params.set('patient_id', patient.patient_id);
  if (patient?.id) params.set('frame_id', patient.id);
  if (patient?.id_short) params.set('title', patient.id_short);
  const qs = params.toString();
  return qs ? `/reader?${qs}` : '/reader';
}

/**
 * Build deep-link into interactive_video_agent.html.
 * Prefer CASE-/BM- style ids when present in frame id; otherwise pass external video URL.
 */
export function buildReadingAgentUrl(patient?: ReadingAgentPatientContext | null): string {
  const page = getReadingAgentPageUrl();
  const params = new URLSearchParams();

  const caseCandidates = [patient?.id, patient?.id_short, patient?.patient_id]
    .filter(Boolean)
    .map((value) => String(value));
  const caseMatch = caseCandidates
    .map((value) => value.match(/\b((?:CASE|BM)-\d+)\b/i))
    .find(Boolean);
  if (caseMatch) {
    const raw = caseMatch[1].toUpperCase();
    const m = raw.match(/^(CASE|BM)-(\d+)$/);
    if (m) params.set('case', `${m[1]}-${m[2].padStart(3, '0')}`);
  }

  const absUrl = (url: string) => {
    if (!url) return '';
    if (typeof window !== 'undefined' && url.startsWith('/')) {
      return `${window.location.origin}${url}`;
    }
    return url;
  };

  const videoUrl = absUrl(patient?.video_urls?.[0]?.url || '');
  if (videoUrl) params.set('video', videoUrl);

  // 2019 等队列多数无 CASE-/BM- id：始终附带当前帧静图，供 Agent 无视频时加载
  const imageUrl = absUrl(patient?.image_url || '');
  if (imageUrl) params.set('image', imageUrl);

  if (patient?.patient_id) params.set('patient_id', patient.patient_id);
  if (patient?.id) params.set('frame_id', patient.id);
  if (patient?.group) {
    params.set('treatment', patient.group === 'NAC' ? 'nac' : 'surgery');
  }
  if (patient?.id_short) params.set('title', patient.id_short);

  // Tell agent where to POST layer/mask results
  if (typeof window !== 'undefined') {
    params.set('callback', `${window.location.origin}/api/reader-agent/result`);
  }

  const qs = params.toString();
  return qs ? `${page}?${qs}` : page;
}

/** 人机互助方向演示（contact geometry）深链 — F1 */
export function getHumanAssistPageUrl(): string {
  const configured = process.env.NEXT_PUBLIC_HUMAN_ASSIST_URL?.trim();
  if (configured) {
    if (configured.endsWith('.html')) return configured;
    return `${configured.replace(/\/$/, '')}/direction_demo.html`;
  }
  return `${getReadingAgentBaseUrl()}/direction_demo.html`;
}

/**
 * Deep-link into direction_demo.html with ?sample=<key>.
 * Uses patient.id / id_short when they look like sample_key (digits-dash-digits).
 */
export function buildHumanAssistUrl(patient?: ReadingAgentPatientContext | null): string {
  const page = getHumanAssistPageUrl();
  const params = new URLSearchParams();
  const candidates = [patient?.id, patient?.id_short, patient?.patient_id].filter(Boolean) as string[];
  for (const c of candidates) {
    const m = String(c).match(/(\d{5,}-\d+)/);
    if (m) {
      params.set('sample', m[1]);
      break;
    }
  }
  if (patient?.patient_id) params.set('patient_id', patient.patient_id);
  if (patient?.id) params.set('frame_id', patient.id);
  if (patient?.id_short) params.set('title', patient.id_short);
  // Same write-back endpoint as interactive_video_agent (additive; Header still window.open)
  if (typeof window !== 'undefined') {
    params.set('callback', `${window.location.origin}/api/reader-agent/result`);
  }
  const qs = params.toString();
  return qs ? `${page}?${qs}` : page;
}

