export type GeometryPoint = [number, number];

export type LesionLumenGeometry = {
  available: boolean;
  lesionCenter: GeometryPoint | null;
  lumenCenter: GeometryPoint | null;
  closestLesionPoint: GeometryPoint | null;
  closestLumenPoint: GeometryPoint | null;
  distancePx: number | null;
  direction: GeometryPoint | null;
  outwardRadiusPx: number | null;
  lumenFacingRadiusPx: number | null;
  outwardExpansionRatio: number | null;
  circularity: number | null;
  solidity: number | null;
  smoothnessIndex: number | null;
  roughnessIndex: number | null;
  relation: 'overlap' | 'near_lumen' | 'separated' | 'unknown';
  quality: 'high' | 'moderate' | 'low';
};

type SegmentPair = {
  first: GeometryPoint;
  second: GeometryPoint;
  distanceSquared: number;
};

const EMPTY_GEOMETRY: LesionLumenGeometry = {
  available: false,
  lesionCenter: null,
  lumenCenter: null,
  closestLesionPoint: null,
  closestLumenPoint: null,
  distancePx: null,
  direction: null,
  outwardRadiusPx: null,
  lumenFacingRadiusPx: null,
  outwardExpansionRatio: null,
  circularity: null,
  solidity: null,
  smoothnessIndex: null,
  roughnessIndex: null,
  relation: 'unknown',
  quality: 'low',
};

function isPoint(value: unknown): value is GeometryPoint {
  return Array.isArray(value)
    && value.length >= 2
    && Number.isFinite(Number(value[0]))
    && Number.isFinite(Number(value[1]));
}

function cleanPolygon(points: number[][] | null | undefined): GeometryPoint[] {
  return (points || [])
    .filter(isPoint)
    .map((point) => [Number(point[0]), Number(point[1])] as GeometryPoint);
}

export function lumenBoxToPolygon(
  box: { x1: number; y1: number; x2: number; y2: number } | null | undefined,
): GeometryPoint[] {
  if (!box) return [];
  const x1 = Number(box.x1);
  const y1 = Number(box.y1);
  const x2 = Number(box.x2);
  const y2 = Number(box.y2);
  if (![x1, y1, x2, y2].every(Number.isFinite) || x2 <= x1 || y2 <= y1) return [];
  return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]];
}

function signedArea(points: GeometryPoint[]): number {
  let area = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area += current[0] * next[1] - next[0] * current[1];
  }
  return area / 2;
}

function polygonArea(points: GeometryPoint[]): number {
  return Math.abs(signedArea(points));
}

function polygonPerimeter(points: GeometryPoint[]): number {
  let perimeter = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    perimeter += Math.hypot(next[0] - current[0], next[1] - current[1]);
  }
  return perimeter;
}

function polygonCentroid(points: GeometryPoint[]): GeometryPoint | null {
  if (!points.length) return null;
  const area = signedArea(points);
  if (Math.abs(area) < 1e-6) {
    const mean = points.reduce((sum, point) => [sum[0] + point[0], sum[1] + point[1]], [0, 0]);
    return [mean[0] / points.length, mean[1] / points.length];
  }
  let cx = 0;
  let cy = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    const cross = current[0] * next[1] - next[0] * current[1];
    cx += (current[0] + next[0]) * cross;
    cy += (current[1] + next[1]) * cross;
  }
  return [cx / (6 * area), cy / (6 * area)];
}

function convexHull(points: GeometryPoint[]): GeometryPoint[] {
  const sorted = [...points]
    .sort((a, b) => a[0] - b[0] || a[1] - b[1])
    .filter((point, index, all) => index === 0 || point[0] !== all[index - 1][0] || point[1] !== all[index - 1][1]);
  if (sorted.length <= 2) return sorted;
  const cross = (o: GeometryPoint, a: GeometryPoint, b: GeometryPoint) => (
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
  );
  const lower: GeometryPoint[] = [];
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) {
      lower.pop();
    }
    lower.push(point);
  }
  const upper: GeometryPoint[] = [];
  for (const point of [...sorted].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) {
      upper.pop();
    }
    upper.push(point);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

function pointInPolygon(point: GeometryPoint, polygon: GeometryPoint[]): boolean {
  if (polygon.length < 3) return false;
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const current = polygon[index];
    const prior = polygon[previous];
    const crosses = ((current[1] > point[1]) !== (prior[1] > point[1]))
      && point[0] < ((prior[0] - current[0]) * (point[1] - current[1])) / ((prior[1] - current[1]) || 1e-9) + current[0];
    if (crosses) inside = !inside;
  }
  return inside;
}

function orientation(a: GeometryPoint, b: GeometryPoint, c: GeometryPoint): number {
  const value = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1]);
  return Math.abs(value) < 1e-7 ? 0 : value > 0 ? 1 : 2;
}

function onSegment(a: GeometryPoint, b: GeometryPoint, c: GeometryPoint): boolean {
  return b[0] <= Math.max(a[0], c[0]) + 1e-7
    && b[0] + 1e-7 >= Math.min(a[0], c[0])
    && b[1] <= Math.max(a[1], c[1]) + 1e-7
    && b[1] + 1e-7 >= Math.min(a[1], c[1]);
}

function segmentsIntersect(a: GeometryPoint, b: GeometryPoint, c: GeometryPoint, d: GeometryPoint): boolean {
  const first = orientation(a, b, c);
  const second = orientation(a, b, d);
  const third = orientation(c, d, a);
  const fourth = orientation(c, d, b);
  if (first !== second && third !== fourth) return true;
  return (first === 0 && onSegment(a, c, b))
    || (second === 0 && onSegment(a, d, b))
    || (third === 0 && onSegment(c, a, d))
    || (fourth === 0 && onSegment(c, b, d));
}

function closestPointOnSegment(point: GeometryPoint, start: GeometryPoint, end: GeometryPoint): GeometryPoint {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared <= 1e-9) return [start[0], start[1]];
  const t = Math.max(0, Math.min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / lengthSquared));
  return [start[0] + t * dx, start[1] + t * dy];
}

function closestSegments(
  firstStart: GeometryPoint,
  firstEnd: GeometryPoint,
  secondStart: GeometryPoint,
  secondEnd: GeometryPoint,
): SegmentPair {
  if (segmentsIntersect(firstStart, firstEnd, secondStart, secondEnd)) {
    const midpoint: GeometryPoint = [
      (firstStart[0] + firstEnd[0] + secondStart[0] + secondEnd[0]) / 4,
      (firstStart[1] + firstEnd[1] + secondStart[1] + secondEnd[1]) / 4,
    ];
    return { first: midpoint, second: midpoint, distanceSquared: 0 };
  }
  const candidates = [
    {
      first: closestPointOnSegment(firstStart, secondStart, secondEnd),
      second: firstStart,
    },
    {
      first: closestPointOnSegment(firstEnd, secondStart, secondEnd),
      second: firstEnd,
    },
    {
      first: closestPointOnSegment(secondStart, firstStart, firstEnd),
      second: secondStart,
    },
    {
      first: closestPointOnSegment(secondEnd, firstStart, firstEnd),
      second: secondEnd,
    },
  ].map((pair) => ({
    ...pair,
    distanceSquared: (pair.first[0] - pair.second[0]) ** 2 + (pair.first[1] - pair.second[1]) ** 2,
  }));
  return candidates.reduce((best, candidate) => (
    candidate.distanceSquared < best.distanceSquared ? candidate : best
  ));
}

function closestPolygonPair(first: GeometryPoint[], second: GeometryPoint[]): SegmentPair | null {
  if (first.length < 2 || second.length < 2) return null;
  let best: SegmentPair | null = null;
  for (let firstIndex = 0; firstIndex < first.length; firstIndex += 1) {
    const firstStart = first[firstIndex];
    const firstEnd = first[(firstIndex + 1) % first.length];
    for (let secondIndex = 0; secondIndex < second.length; secondIndex += 1) {
      const secondStart = second[secondIndex];
      const secondEnd = second[(secondIndex + 1) % second.length];
      const candidate = closestSegments(firstStart, firstEnd, secondStart, secondEnd);
      if (!best || candidate.distanceSquared < best.distanceSquared) best = candidate;
    }
  }
  return best;
}

function percentile(values: number[], fraction: number): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * fraction;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function computeLesionLumenGeometry(
  lesionInput: number[][] | null | undefined,
  lumenInput: number[][] | null | undefined,
  lumenBox?: { x1: number; y1: number; x2: number; y2: number } | null,
): LesionLumenGeometry {
  const lesion = cleanPolygon(lesionInput);
  const lumen = cleanPolygon(lumenInput);
  const lumenShape = lumen.length >= 3 ? lumen : lumenBoxToPolygon(lumenBox);
  if (lesion.length < 3 || lumenShape.length < 3) return { ...EMPTY_GEOMETRY };

  const lesionCenter = polygonCentroid(lesion);
  const lumenCenter = polygonCentroid(lumenShape);
  if (!lesionCenter || !lumenCenter) return { ...EMPTY_GEOMETRY };

  const centerDx = lesionCenter[0] - lumenCenter[0];
  const centerDy = lesionCenter[1] - lumenCenter[1];
  const centerDistance = Math.hypot(centerDx, centerDy);
  const direction: GeometryPoint | null = centerDistance > 1e-6
    ? [centerDx / centerDistance, centerDy / centerDistance]
    : null;
  const closest = closestPolygonPair(lesion, lumenShape);
  const overlaps = pointInPolygon(lesion[0], lumenShape)
    || pointInPolygon(lumenShape[0], lesion)
    || lesion.some((point, index) => {
      const nextLesionPoint = lesion[(index + 1) % lesion.length];
      return lumenShape.some((lumenPoint, lumenIndex) => (
        segmentsIntersect(
          point,
          nextLesionPoint,
          lumenPoint,
          lumenShape[(lumenIndex + 1) % lumenShape.length],
        )
      ));
    });
  const distancePx = overlaps ? 0 : closest ? Math.sqrt(closest.distanceSquared) : null;

  const radial = direction
    ? lesion.map((point) => {
      const dx = point[0] - lesionCenter[0];
      const dy = point[1] - lesionCenter[1];
      const radius = Math.hypot(dx, dy);
      return { radius, projection: radius > 1e-6 ? (dx * direction[0] + dy * direction[1]) / radius : 0 };
    })
    : [];
  const allRadii = radial.map((item) => item.radius).filter((value) => Number.isFinite(value));
  const meanRadius = allRadii.length
    ? allRadii.reduce((sum, value) => sum + value, 0) / allRadii.length
    : null;
  const outwardRadii = radial.filter((item) => item.projection >= 0.25).map((item) => item.radius);
  const inwardRadii = radial.filter((item) => item.projection <= -0.25).map((item) => item.radius);
  const outwardRadiusPx = percentile(outwardRadii.length ? outwardRadii : allRadii, 0.9);
  const lumenFacingRadiusPx = percentile(inwardRadii.length ? inwardRadii : allRadii, 0.9);
  const outwardExpansionRatio = meanRadius && outwardRadiusPx != null && lumenFacingRadiusPx != null
    ? (outwardRadiusPx - lumenFacingRadiusPx) / meanRadius
    : null;

  const area = polygonArea(lesion);
  const perimeter = polygonPerimeter(lesion);
  const circularity = area > 1e-6 && perimeter > 1e-6
    ? clamp01((4 * Math.PI * area) / (perimeter * perimeter))
    : null;
  const hullArea = polygonArea(convexHull(lesion));
  const solidity = hullArea > 1e-6 ? clamp01(area / hullArea) : null;
  const smoothnessIndex = circularity != null && solidity != null
    ? clamp01(circularity * 0.65 + solidity * 0.35)
    : circularity ?? solidity;
  const roughnessIndex = smoothnessIndex == null ? null : 1 - smoothnessIndex;

  const relation = overlaps
    ? 'overlap'
    : distancePx != null && distancePx <= Math.max(6, meanRadius ? meanRadius * 0.08 : 6)
      ? 'near_lumen'
      : distancePx != null
        ? 'separated'
        : 'unknown';
  const quality = lesion.length >= 24 && lumenShape.length >= 12
    ? 'high'
    : lesion.length >= 8 && lumenShape.length >= 4
      ? 'moderate'
      : 'low';

  return {
    available: true,
    lesionCenter,
    lumenCenter,
    closestLesionPoint: closest?.first || null,
    closestLumenPoint: closest?.second || null,
    distancePx,
    direction,
    outwardRadiusPx,
    lumenFacingRadiusPx,
    outwardExpansionRatio,
    circularity,
    solidity,
    smoothnessIndex,
    roughnessIndex,
    relation,
    quality,
  };
}
