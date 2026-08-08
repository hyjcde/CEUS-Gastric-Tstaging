/**
 * Browser-side direction-normalized growth / continuity proxies.
 * Mirrors pipeline/agent/signs/direction_growth.py for audit cards.
 * Does not claim pathological wall-layer truth.
 */

export type LumenBBox = { x1: number; y1: number; x2: number; y2: number };

export type DirectionGrowthFeatures = {
  available: boolean;
  status: 'proxy' | 'not_assessable' | 'missing';
  directionSource: string;
  usedFallback: boolean;
  contactArcRatio: number;
  sectorFrac: {
    lumen_facing: number;
    outward_facing: number;
    lateral: number;
  };
  growthGrade: number | null;
  growthLabel: string | null;
  continuityGrade: number | null;
  continuityLabel: string | null;
  morphologyGrade: number | null;
  boundaryGrade: number | null;
  transmuralProxy: number;
  longestArcFrac: number;
  outwardProtrusionP90: number;
  qualityFlags: string[];
  detail: string;
};

const GROWTH_LABELS = ['膨胀型', '局部浸润型', '明显浸润型', '跨壁倾向'] as const;
const CONT_LABELS = [
  '孤立尖刺/无明显连续外凸',
  '局部外凸',
  '外侧壁连续外凸',
  '广泛连续外凸',
] as const;

function centroid(poly: number[][]): [number, number] | null {
  if (!poly || poly.length < 3) return null;
  let a = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x0, y0] = poly[i];
    const [x1, y1] = poly[(i + 1) % poly.length];
    const cross = x0 * y1 - x1 * y0;
    a += cross;
    cx += (x0 + x1) * cross;
    cy += (y0 + y1) * cross;
  }
  a *= 0.5;
  if (Math.abs(a) < 1e-6) {
    const xs = poly.map((p) => p[0]);
    const ys = poly.map((p) => p[1]);
    return [
      xs.reduce((s, v) => s + v, 0) / xs.length,
      ys.reduce((s, v) => s + v, 0) / ys.length,
    ];
  }
  return [cx / (6 * a), cy / (6 * a)];
}

function resampleClosed(poly: number[][], n = 128): number[][] {
  if (!poly || poly.length < 3) return [];
  const closed = [...poly, poly[0]];
  const seg: number[] = [];
  let total = 0;
  for (let i = 0; i < closed.length - 1; i++) {
    const d = Math.hypot(closed[i + 1][0] - closed[i][0], closed[i + 1][1] - closed[i][1]);
    seg.push(d);
    total += d;
  }
  if (total < 1e-6) return Array.from({ length: n }, () => [...poly[0]]);
  const out: number[][] = [];
  for (let k = 0; k < n; k++) {
    const target = (k / n) * total;
    let acc = 0;
    for (let i = 0; i < seg.length; i++) {
      if (acc + seg[i] >= target || i === seg.length - 1) {
        const t = seg[i] < 1e-9 ? 0 : (target - acc) / seg[i];
        const x = closed[i][0] + t * (closed[i + 1][0] - closed[i][0]);
        const y = closed[i][1] + t * (closed[i + 1][1] - closed[i][1]);
        out.push([x, y]);
        break;
      }
      acc += seg[i];
    }
  }
  return out;
}

function movingAverageCircular(x: number[], window: number): number[] {
  const w = window | 1;
  const pad = Math.floor(w / 2);
  const xp = [...x.slice(-pad), ...x, ...x.slice(0, pad)];
  const out: number[] = [];
  for (let i = 0; i < x.length; i++) {
    let s = 0;
    for (let j = 0; j < w; j++) s += xp[i + j];
    out.push(s / w);
  }
  return out;
}

function longestArcFrac(flags: boolean[]): number {
  const n = flags.length;
  if (!n) return 0;
  if (flags.every(Boolean)) return 1;
  if (!flags.some(Boolean)) return 0;
  const start = flags.findIndex((v) => !v);
  const rotated = flags.slice(start).concat(flags.slice(0, start));
  let best = 0;
  let cur = 0;
  for (const v of rotated) {
    if (v) {
      cur += 1;
      best = Math.max(best, cur);
    } else cur = 0;
  }
  return best / n;
}

function emptyFeatures(flags: string[], detail: string): DirectionGrowthFeatures {
  return {
    available: false,
    status: 'missing',
    directionSource: 'missing',
    usedFallback: true,
    contactArcRatio: 0,
    sectorFrac: { lumen_facing: 0, outward_facing: 0, lateral: 0 },
    growthGrade: null,
    growthLabel: null,
    continuityGrade: null,
    continuityLabel: null,
    morphologyGrade: null,
    boundaryGrade: null,
    transmuralProxy: 0,
    longestArcFrac: 0,
    outwardProtrusionP90: 0,
    qualityFlags: flags,
    detail,
  };
}

/**
 * Compute direction-aware growth/continuity proxies from lesion polygon.
 * Prefer wall polygon centroid as lumen/inward reference when lumen bbox absent.
 */
export function computeDirectionGrowthFromPolygons(
  lesionPoly: number[][],
  opts?: {
    lumenBBox?: LumenBBox | null;
    wallPoly?: number[][] | null;
    frameSize?: { width: number; height: number } | null;
  },
): DirectionGrowthFeatures {
  if (!lesionPoly || lesionPoly.length < 3) {
    return emptyFeatures(['missing_lesion_polygon'], '病灶轮廓缺失');
  }
  const lesionC = centroid(lesionPoly);
  if (!lesionC) return emptyFeatures(['bad_lesion_centroid'], '病灶中心不可用');

  const flags: string[] = [];
  let lumenC: [number, number] | null = null;
  let directionSource = 'missing';
  let usedFallback = false;

  const bbox = opts?.lumenBBox;
  if (bbox && bbox.x2 > bbox.x1 && bbox.y2 > bbox.y1) {
    lumenC = [0.5 * (bbox.x1 + bbox.x2), 0.5 * (bbox.y1 + bbox.y2)];
    directionSource = 'lumen_bbox_center';
  } else if (opts?.wallPoly && opts.wallPoly.length >= 3) {
    lumenC = centroid(opts.wallPoly);
    if (lumenC) directionSource = 'wall_polygon_centroid';
  }
  if (!lumenC) {
    const h = opts?.frameSize?.height ?? Math.max(...lesionPoly.map((p) => p[1]), lesionC[1] + 40);
    lumenC = [lesionC[0], Math.min(h - 1, lesionC[1] + 40)];
    directionSource = 'fallback_deep_axis';
    usedFallback = true;
    flags.push('direction_fallback_deep_axis');
  }

  const ox = lesionC[0] - lumenC[0];
  const oy = lesionC[1] - lumenC[1];
  const onorm = Math.hypot(ox, oy) || 1;
  const ou: [number, number] = [ox / onorm, oy / onorm];

  const pts = resampleClosed(lesionPoly, 128);
  const dRaw = pts.map((p) => Math.hypot(p[0] - lesionC[0], p[1] - lesionC[1]));
  const dS = movingAverageCircular(dRaw, 7);
  const meanD = dS.reduce((s, v) => s + v, 0) / dS.length + 1e-6;
  const protrusion = dS.map((d) => (d - meanD) / meanD);
  const pStd = Math.sqrt(protrusion.reduce((s, v) => s + v * v, 0) / protrusion.length) || 1e-3;

  let nLumen = 0;
  let nOut = 0;
  let nLat = 0;
  const outwardMask: boolean[] = [];
  const highOut: boolean[] = [];
  const outProtrusions: number[] = [];
  for (let i = 0; i < pts.length; i++) {
    const rx = pts[i][0] - lesionC[0];
    const ry = pts[i][1] - lesionC[1];
    const rn = Math.hypot(rx, ry) || 1;
    const cosOut = (rx / rn) * ou[0] + (ry / rn) * ou[1];
    const cosIn = -cosOut;
    const outThr = Math.cos((60 * Math.PI) / 180);
    let sector: 'lumen_facing' | 'outward_facing' | 'lateral' = 'lateral';
    if (cosOut >= outThr) sector = 'outward_facing';
    if (cosIn >= outThr) sector = 'lumen_facing';
    if (cosOut >= outThr && cosIn >= outThr) {
      sector = cosOut >= cosIn ? 'outward_facing' : 'lumen_facing';
    }
    if (sector === 'lumen_facing') nLumen += 1;
    else if (sector === 'outward_facing') nOut += 1;
    else nLat += 1;
    const isOut = sector === 'outward_facing';
    outwardMask.push(isOut);
    const isHigh = protrusion[i] >= 0.75 * pStd;
    highOut.push(isHigh && isOut);
    if (isOut) outProtrusions.push(protrusion[i]);
  }

  const longest = longestArcFrac(highOut);
  const highFrac = highOut.filter(Boolean).length / highOut.length;
  outProtrusions.sort((a, b) => a - b);
  const p90 = outProtrusions.length
    ? outProtrusions[Math.min(outProtrusions.length - 1, Math.floor(0.9 * (outProtrusions.length - 1)))]
    : 0;
  const meanProj = (() => {
    let s = 0;
    let c = 0;
    for (let i = 0; i < pts.length; i++) {
      if (!highOut[i] && !outwardMask[i]) continue;
      const rx = pts[i][0] - lesionC[0];
      const ry = pts[i][1] - lesionC[1];
      const rn = Math.hypot(rx, ry) || 1;
      s += (rx / rn) * ou[0] + (ry / rn) * ou[1];
      c += 1;
    }
    return c ? s / c : 0;
  })();

  const transmural = Math.min(
    1,
    0.4 * Math.min(Math.max(p90, 0) / 0.35, 1)
      + 0.35 * Math.min(longest / 0.3, 1)
      + 0.25 * Math.min(Math.max(meanProj, 0), 1),
  );

  let growthGrade = 0;
  if (transmural >= 0.72 || (longest >= 0.28 && p90 >= 0.3)) growthGrade = 3;
  else if (transmural >= 0.48 || (longest >= 0.18 && p90 >= 0.2)) growthGrade = 2;
  else if (transmural >= 0.28 || p90 >= 0.12) growthGrade = 1;

  let continuityGrade = 0;
  if (longest >= 0.3 && highFrac >= 0.18) continuityGrade = 3;
  else if (longest >= 0.18) continuityGrade = 2;
  else if (longest >= 0.08 || highFrac >= 0.1) continuityGrade = 1;

  // Rough solidity via bbox fill.
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  let area = 0;
  for (let i = 0; i < lesionPoly.length; i++) {
    const a = lesionPoly[i];
    const b = lesionPoly[(i + 1) % lesionPoly.length];
    area += a[0] * b[1] - b[0] * a[1];
    minX = Math.min(minX, a[0]);
    maxX = Math.max(maxX, a[0]);
    minY = Math.min(minY, a[1]);
    maxY = Math.max(maxY, a[1]);
  }
  area = Math.abs(area) / 2;
  const bboxArea = Math.max((maxX - minX) * (maxY - minY), 1e-6);
  const solidity = Math.min(area / bboxArea, 1);
  const irreg = 0.45 * (1 - solidity) + 0.3 * Math.min(pStd / 0.25, 1) + 0.25 * Math.min(longest / 0.25, 1);
  const morphGrade = irreg >= 0.55 ? 2 : irreg >= 0.28 ? 1 : 0;
  const bIrreg = 0.5 * irreg + 0.5 * Math.min(longest / 0.35, 1);
  const boundaryGrade = bIrreg >= 0.7 ? 3 : bIrreg >= 0.45 ? 2 : bIrreg >= 0.25 ? 1 : 0;

  // Contact arc proxy vs wall poly if present.
  let contactArcRatio = 0;
  if (opts?.wallPoly && opts.wallPoly.length >= 2) {
    let near = 0;
    for (const wp of opts.wallPoly) {
      let mind = Infinity;
      for (const lp of lesionPoly) {
        mind = Math.min(mind, Math.hypot(wp[0] - lp[0], wp[1] - lp[1]));
      }
      if (mind <= 12) near += 1;
    }
    contactArcRatio = near / opts.wallPoly.length;
  } else {
    contactArcRatio = usedFallback ? 0 : 0.05;
  }
  if (contactArcRatio < 0.02) flags.push('contact_arc_too_short');

  const assessable = !usedFallback && contactArcRatio >= 0.02;
  const status = assessable ? 'proxy' : 'not_assessable';
  if (!assessable) flags.push('direction_or_contact_unreliable');

  return {
    available: true,
    status,
    directionSource,
    usedFallback,
    contactArcRatio,
    sectorFrac: {
      lumen_facing: nLumen / pts.length,
      outward_facing: nOut / pts.length,
      lateral: nLat / pts.length,
    },
    growthGrade: assessable ? growthGrade : null,
    growthLabel: assessable ? GROWTH_LABELS[growthGrade] : null,
    continuityGrade: assessable ? continuityGrade : null,
    continuityLabel: assessable ? CONT_LABELS[continuityGrade] : null,
    morphologyGrade: assessable ? morphGrade : null,
    boundaryGrade: assessable ? boundaryGrade : null,
    transmuralProxy: transmural,
    longestArcFrac: longest,
    outwardProtrusionP90: p90,
    qualityFlags: flags,
    detail: assessable
      ? `方向=${directionSource}; 生长代理=${GROWTH_LABELS[growthGrade]}; 连续弧=${(longest * 100).toFixed(0)}%`
      : `方向/接触不可靠（${directionSource}），生长与连续性不可评`,
  };
}
