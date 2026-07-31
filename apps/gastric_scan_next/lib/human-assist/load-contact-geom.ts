/** Load ContactGeom + LayerBridge (migrated from reader_study_v150 human-assist). */

export type LayerJudgment = {
  label?: string;
  tHint?: string;
  tone?: string;
  level?: number;
  [key: string]: unknown;
};

export type PenetrationResult = {
  remain?: number;
  thick?: number;
  ratio?: number;
  extent?: number;
  overshoot?: number;
  [key: string]: unknown;
};

export type LayerAnalyzeResult = {
  ok: boolean;
  message?: string;
  videoW?: number;
  videoH?: number;
  wallPts?: number[][];
  lesPts?: number[][];
  pickIdx?: number;
  pickPoint?: number[];
  channelEnd?: number[];
  channelDir?: number[];
  inContact?: boolean;
  pen?: PenetrationResult;
  layer?: LayerJudgment | null;
  source?: { badge?: string; [key: string]: unknown } | null;
  plan?: { edgeFracs?: number[]; [key: string]: unknown };
  analysis?: { edgeFracs?: number[]; ratioHint?: number; imaginary?: boolean; [key: string]: unknown } | null;
  wallEstimated?: boolean;
  offsetPx?: number;
  geom?: {
    contact_idx?: number[];
    contact_ratio?: number;
    deep_idx?: number;
    [key: string]: unknown;
  };
};

type LayerBridgeApi = {
  analyzeLayersFromMask: (opts: Record<string, unknown>) => Promise<LayerAnalyzeResult>;
  estimateWallFromLesion: (...args: unknown[]) => unknown;
  captureVideoFrameDataUrl: (video: HTMLVideoElement) => string | null;
  renderLayerCard: (result: LayerAnalyzeResult, mountEl: HTMLElement) => void;
  drawLayerOverlay: (
    result: LayerAnalyzeResult,
    ctx: CanvasRenderingContext2D,
    mapImageToCanvas: (x: number, y: number, video?: HTMLVideoElement | null) => { x: number; y: number },
    video?: HTMLVideoElement | null,
  ) => boolean;
};

type ContactGeomApi = {
  formatPenPct?: (pen: PenetrationResult) => string;
  wallStackSvg?: (fracs: number[], occ: number, opts?: { w?: number; h?: number }) => string;
  computeGeometry?: (...args: unknown[]) => unknown;
  layerJudgment?: (ratio: number) => LayerJudgment;
  isContactPoint?: (...args: unknown[]) => boolean;
  penetrationAt?: (...args: unknown[]) => PenetrationResult;
  [key: string]: unknown;
};

declare global {
  interface Window {
    ContactGeom?: ContactGeomApi;
    LayerBridge?: LayerBridgeApi;
  }
}

let loadPromise: Promise<void> | null = null;

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-human-assist="${src}"]`) as HTMLScriptElement | null;
    if (existing) {
      if (existing.dataset.loaded === '1') resolve();
      else existing.addEventListener('load', () => resolve(), { once: true });
      return;
    }
    const s = document.createElement('script');
    s.src = src;
    s.async = false;
    s.dataset.humanAssist = src;
    s.onload = () => {
      s.dataset.loaded = '1';
      resolve();
    };
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(s);
  });
}

export async function ensureHumanAssistGeometry(): Promise<{
  ContactGeom: ContactGeomApi;
  LayerBridge: LayerBridgeApi;
}> {
  if (typeof window === 'undefined') {
    throw new Error('human-assist geometry is browser-only');
  }
  if (window.ContactGeom && window.LayerBridge) {
    return { ContactGeom: window.ContactGeom, LayerBridge: window.LayerBridge };
  }
  if (!loadPromise) {
    loadPromise = (async () => {
      await loadScript('/vendor/human-assist/contact_geometry.js');
      await loadScript('/vendor/human-assist/interactive_layer_bridge.js');
    })();
  }
  await loadPromise;
  if (!window.ContactGeom || !window.LayerBridge) {
    throw new Error('ContactGeom / LayerBridge failed to initialize');
  }
  return { ContactGeom: window.ContactGeom, LayerBridge: window.LayerBridge };
}

/** Convert pixel polygon → normalized [0,1] for LayerBridge.analyzeLayersFromMask. */
export function toNormPolygon(pts: number[][], width: number, height: number): number[][] {
  const w = Math.max(1, width);
  const h = Math.max(1, height);
  return pts.map(([x, y]) => [x / w, y / h]);
}

export function formatPenetration(ContactGeom: ContactGeomApi, pen?: PenetrationResult | null): string {
  if (!pen) return '—';
  if (ContactGeom.formatPenPct) return ContactGeom.formatPenPct(pen);
  const r = Number(pen.ratio);
  return Number.isFinite(r) ? `${Math.round(r * 100)}%` : '—';
}
