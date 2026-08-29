/** Cine clock and frame index for the reader seek bar. */

export const DEFAULT_CINE_FPS = 25;

export type WallLayerTarget = 1 | 2 | 3;

export function formatCineClock(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00.000';
  const totalMs = Math.round(sec * 1000);
  const m = Math.floor(totalMs / 60000);
  const s = Math.floor((totalMs % 60000) / 1000);
  const ms = totalMs % 1000;
  return `${m}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

/** Phone cine bar: leave the scrubber as much width as possible. */
export function formatCineClockShort(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00';
  const totalSec = Math.floor(sec);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** 1-based frame index. t=0 is frame 1. */
export function cineFrameIndex(sec: number, fps = DEFAULT_CINE_FPS): number {
  const rate = Number.isFinite(fps) && fps > 1 ? fps : DEFAULT_CINE_FPS;
  if (!Number.isFinite(sec) || sec < 0) return 1;
  return Math.max(1, Math.floor(sec * rate + 1e-9) + 1);
}

export function formatCineLabel(sec: number, fps = DEFAULT_CINE_FPS): string {
  return `${formatCineClock(sec)} / ${cineFrameIndex(sec, fps)}`;
}

export function cineFpsOrDefault(fps?: number): number {
  return Number.isFinite(fps) && (fps as number) > 1 ? (fps as number) : DEFAULT_CINE_FPS;
}

/** Start time of a 1-based cine frame. */
export function cineTimeForFrame(frameIndex: number, fps = DEFAULT_CINE_FPS): number {
  const rate = cineFpsOrDefault(fps);
  const index = Math.max(1, Math.floor(Number(frameIndex) || 1));
  return (index - 1) / rate;
}

export function snapCineTimeToFrame(sec: number, fps = DEFAULT_CINE_FPS): number {
  return cineTimeForFrame(cineFrameIndex(sec, fps), fps);
}

/** Map a pointer X on the scrub bar to a cine time. */
export function cineTimeFromClientX(
  clientX: number,
  rect: { left: number; width: number },
  duration: number,
): number {
  const width = Number(rect.width);
  const left = Number(rect.left);
  const span = Number.isFinite(duration) && duration > 0 ? duration : 0;
  if (!Number.isFinite(width) || width <= 0 || span <= 0) return 0;
  const ratio = Math.min(1, Math.max(0, (clientX - left) / width));
  return ratio * span;
}

export function stepCineTime(
  sec: number,
  deltaFrames: number,
  fps = DEFAULT_CINE_FPS,
  duration?: number,
): number {
  const next = cineTimeForFrame(cineFrameIndex(sec, fps) + Math.trunc(deltaFrames || 0), fps);
  if (duration != null && Number.isFinite(duration) && duration >= 0) {
    return Math.max(0, Math.min(duration, next));
  }
  return Math.max(0, next);
}

export function formatKeyframeTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0.000s';
  return `${sec.toFixed(3)}s`;
}

const COMMON_CINE_FPS = [15, 20, 24, 25, 30, 50, 60];

/** Snap a noisy estimate to a cine rate doctors actually use. */
export function snapCineFps(raw: number, fallback = DEFAULT_CINE_FPS): number {
  if (!Number.isFinite(raw) || raw < 8 || raw > 90) return fallback;
  let best = fallback;
  let bestDist = Infinity;
  for (const candidate of COMMON_CINE_FPS) {
    const dist = Math.abs(candidate - raw);
    if (dist < bestDist) {
      bestDist = dist;
      best = candidate;
    }
  }
  return bestDist <= 1.8 ? best : Math.round(raw * 10) / 10;
}

/** Estimate fps from requestVideoFrameCallback mediaTime samples. */
export function estimateCineFpsFromMediaTimes(times: number[]): number | null {
  const deltas: number[] = [];
  for (let index = 1; index < times.length; index += 1) {
    const delta = Number(times[index]) - Number(times[index - 1]);
    if (Number.isFinite(delta) && delta > 0.008 && delta < 0.2) deltas.push(delta);
  }
  if (deltas.length < 3) return null;
  const mean = deltas.reduce((sum, value) => sum + value, 0) / deltas.length;
  if (mean <= 0) return null;
  return snapCineFps(1 / mean);
}
