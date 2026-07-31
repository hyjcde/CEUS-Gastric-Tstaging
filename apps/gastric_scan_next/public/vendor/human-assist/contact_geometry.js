/*! Shared contact / wall-thickness geometry for direction + video demos */
(function (global) {
  'use strict';

  /** Tunables (2026-07-12 clinical review). */
  const CFG = {
    CONTACT_THR_PX: 8,
    MIN_LAYERS: 2,
    TARGET_LAYERS: 3,
    MAX_LAYERS: 5,
    CHANNEL_DIV: 5,
    SEARCH_HALF: 28,
    GUIDE_OPACITY: 0.58,
    GUIDE_STROKE: 0.85,
    OCC_FILL_OPACITY: 0.12,
    /** Min wall px per layer band — below this, fewer edges (avoid fake equal-split on thin remain). */
    MIN_PX_PER_LAYER: 3.5,
  };

  /** Max interface count that can fit in a channel of given remain (px). */
  function maxEdgesForRemain(remainPx) {
    const rem = Math.max(0, remainPx || 0);
    const byPx = Math.floor(rem / CFG.MIN_PX_PER_LAYER);
    return Math.max(1, Math.min(CFG.MAX_LAYERS, byPx));
  }

  /**
   * Merge / thin edge fracs so consecutive interfaces are ≥ minPx apart along remain.
   * Prevents 4–5 white ticks jammed into a 6px destroyed wall channel.
   */
  function adaptEdgeFracsToRemain(edgeFracs, remainPx, opts) {
    const o = opts || {};
    const rem = Math.max(1, remainPx || 1);
    const minPx = o.minPx != null ? o.minPx : CFG.MIN_PX_PER_LAYER;
    const cap = o.maxEdges != null ? o.maxEdges : maxEdgesForRemain(rem);
    const sorted = (edgeFracs || [])
      .map((f) => Math.max(0.06, Math.min(0.94, f)))
      .sort((a, b) => a - b);
    if (!sorted.length) return [];
    const minDf = Math.max(0.08, minPx / rem);
    const merged = [];
    sorted.forEach((f) => {
      if (!merged.length || f - merged[merged.length - 1] >= minDf) merged.push(f);
      else {
        // keep midpoint of too-close pair (true cluster merge)
        merged[merged.length - 1] = (merged[merged.length - 1] + f) / 2;
      }
    });
    if (merged.length <= cap) return merged;
    // Keep most evenly spaced subset of size `cap` (preserve lumen/serosa span)
    if (cap === 1) return [merged[Math.floor(merged.length / 2)]];
    const out = [];
    for (let k = 0; k < cap; k++) {
      const idx = Math.round((k / (cap - 1)) * (merged.length - 1));
      const f = merged[idx];
      if (!out.length || Math.abs(out[out.length - 1] - f) > 1e-4) out.push(f);
    }
    return out;
  }

  function ptsPath(pts, closed) {
    if (!pts?.length) return '';
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) d += `L${pts[i][0]},${pts[i][1]}`;
    return closed ? d + 'Z' : d;
  }

  function smoothPath(pts, closed = true) {
    if (!pts || pts.length < 3) return ptsPath(pts, closed);
    const n = pts.length;
    let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)} `;
    for (let i = 0; i < (closed ? n : n - 1); i++) {
      const p0 = pts[(i - 1 + n) % n],
        p1 = pts[i],
        p2 = pts[(i + 1) % n],
        p3 = pts[(i + 2) % n];
      for (let t = 0; t < 1; t += 0.34) {
        const t2 = t * t,
          t3 = t2 * t;
        const x =
          0.5 *
          (2 * p1[0] +
            (-p0[0] + p2[0]) * t +
            (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
            (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3);
        const y =
          0.5 *
          (2 * p1[1] +
            (-p0[1] + p2[1]) * t +
            (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
            (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3);
        d += `L${x.toFixed(1)},${y.toFixed(1)} `;
      }
    }
    return d + (closed ? 'Z' : '');
  }

  function unit(vx, vy) {
    const n = Math.hypot(vx, vy) || 1;
    return [vx / n, vy / n];
  }

  function bandPath(a, b) {
    if (!a.length || !b.length) return '';
    return (
      smoothPath(a, false) +
      ' ' +
      smoothPath(b.slice().reverse(), false).replace(/^M/, 'L') +
      ' Z'
    );
  }

  function arcLen(a, b) {
    return Math.hypot(b[0] - a[0], b[1] - a[1]);
  }

  function percentile(sorted, p) {
    if (!sorted.length) return 0;
    const i = Math.min(sorted.length - 1, Math.max(0, Math.floor(sorted.length * p)));
    return sorted[i];
  }

  /** Length-weighted contact ratio along wall polyline. */
  function contactRatioByLength(wall, contactIdx) {
    const n = wall.length;
    if (n < 2) return 0;
    const set = new Set(contactIdx || []);
    let total = 0,
      contact = 0;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const L = arcLen(wall[i], wall[j]);
      total += L;
      if (set.has(i) || set.has(j)) contact += L;
    }
    return total > 0 ? contact / total : 0;
  }

  /**
   * Local wall thickness at index i:
   * median of nearby wall→lesion distances that look "intact" (above contact thr),
   * floored by current remain so penetration never exceeds ~100% spuriously.
   */
  function localWallThickness(wallDists, contactIdx, i, half = 18) {
    const n = wallDists.length;
    const ci = new Set(contactIdx || []);
    const samples = [];
    for (let k = -half; k <= half; k++) {
      const j = (i + k + n * 20) % n;
      if (ci.has(j)) continue;
      const d = wallDists[j];
      if (d != null && d > 1.5) samples.push(d);
    }
    samples.sort((a, b) => a - b);
    let local;
    if (samples.length >= 3) local = percentile(samples, 0.6);
    else {
      const far = wallDists
        .map((d, j) => (ci.has(j) ? null : d))
        .filter((x) => x != null && x > 1)
        .sort((a, b) => a - b);
      local = far.length ? percentile(far, 0.75) : Math.max(...wallDists, 12);
    }
    const remain = Math.max(0, wallDists[i] || 0);
    return Math.max(local, remain, 4);
  }

  function penetrationAt(wallDists, contactIdx, i, opts = {}) {
    const remain = Math.max(0, wallDists[i] || 0);
    const thick = localWallThickness(wallDists, contactIdx, i);
    const wall = opts.wall_pts;
    const les = opts.lesion_poly;
    const dirs = opts.wall_dirs;
    let extent = Math.max(0, thick - remain); // occupied within wall
    let overshoot = 0;
    // If lesion extends past estimated outer wall along the wall→lesion ray, ratio can exceed 100%.
    if (wall && les && dirs && dirs[i]) {
      const w = wall[i];
      const [ux, uy] = dirs[i];
      let maxProj = 0;
      for (const q of les) {
        const proj = (q[0] - w[0]) * ux + (q[1] - w[1]) * uy;
        if (proj > maxProj) maxProj = proj;
      }
      extent = Math.max(extent, maxProj);
      overshoot = Math.max(0, maxProj - thick);
    }
    const ratio = thick > 0 ? extent / thick : 0;
    return {
      remain,
      thick,
      extent,
      overshoot,
      ratio, // may be > 1
      pct: Math.round(ratio * 100),
    };
  }

  function formatPenPct(pen) {
    if (!pen) return '—';
    const pct = pen.pct != null ? pen.pct : Math.round((pen.ratio || 0) * 100);
    if (pen.ratio >= 1.0) return pct > 100 ? `${Math.min(200, pct)}%` : '100%';
    return `${pct}%`;
  }

  /** Clinical 5-layer table (lumen→serosa). Soft T hints only. */
  const LAYER_TABLE = [
    { max: 0.2, code: 'L1', name: '黏膜层', short: '黏膜', tHint: 'T1a', tone: 'cool', color: '#0ea5e9' },
    { max: 0.4, code: 'L2', name: '黏膜肌层', short: '黏膜肌', tHint: 'T1a', tone: 'cool', color: '#8b5cf6' },
    { max: 0.6, code: 'L3', name: '黏膜下层', short: '黏膜下', tHint: 'T1b', tone: 'warm', color: '#14b8a6' },
    { max: 0.8, code: 'L4', name: '固有肌层', short: '固有肌', tHint: 'T2', tone: 'warm', color: '#22c55e' },
    { max: 1.0, code: 'L5', name: '浆膜/浆膜下', short: '浆膜', tHint: 'T3–T4a', tone: 'hot', color: '#f43f5e' },
  ];

  /** Saturated palette for band fills / interface strokes (never near-white). */
  const LAYER_BAND_COLS = ['#0284c7', '#7c3aed', '#0d9488', '#16a34a', '#e11d48', '#ea580c'];
  const LAYER_LINE_COLS = ['#38bdf8', '#a78bfa', '#2dd4bf', '#4ade80', '#fb7185', '#fb923c'];

  function layerColorsForFracs(edgeFracs) {
    const bands = clinicalBandLabels(edgeFracs);
    const bandCols = bands.map((b, i) => b.color || LAYER_BAND_COLS[i % LAYER_BAND_COLS.length]);
    const lineCols = (edgeFracs || []).map((f, i) => {
      const hit = layerAtFrac(f);
      return hit.color || LAYER_LINE_COLS[i % LAYER_LINE_COLS.length];
    });
    return { bandCols, lineCols, bands };
  }

  function wallIdxDist(a, b, n) {
    const d = Math.abs((a | 0) - (b | 0));
    return Math.min(d, n - d);
  }

  /**
   * Where to DRAW layers: stay near the pick (infiltrate site).
   * Never jump to a far wall pocket even if echo there is clearer.
   */
  function layerDrawCenter(g, pickIdx, fromIdx, opts) {
    const o = opts || {};
    const n = g?.wall_pts?.length || 0;
    if (!n || pickIdx == null) return pickIdx;
    const maxIdx = o.maxIdx != null ? o.maxIdx : 12;
    const maxPx = o.maxPx != null ? o.maxPx : 72;
    if (fromIdx == null || fromIdx === pickIdx) return pickIdx;
    if (wallIdxDist(fromIdx, pickIdx, n) > maxIdx) return pickIdx;
    const a = g.wall_pts[pickIdx], b = g.wall_pts[fromIdx];
    if (!a || !b) return pickIdx;
    const dist = Math.hypot(a[0] - b[0], a[1] - b[1]);
    if (dist > maxPx) return pickIdx;
    // Prefer nearby thicker wall only when pick channel is collapsed
    const remP = g.wall_dists[pickIdx] || 0;
    const remF = g.wall_dists[fromIdx] || 0;
    if (remP < 8 && remF > remP + 3) return fromIdx;
    return pickIdx;
  }

  function layerAtFrac(frac) {
    const f = Math.max(0, Math.min(1, frac == null ? 0 : frac));
    return LAYER_TABLE.find((x) => f < x.max) || LAYER_TABLE[LAYER_TABLE.length - 1];
  }

  /**
   * Map occupied wall-thickness ratio → gastric US layer + soft T hint.
   * Geometric aid only (not pathology gold standard).
   * Lumen/mucosa side = 0 → serosa = 1.
   */
  function layerJudgment(ratioOrPen) {
    const ratio =
      typeof ratioOrPen === 'number'
        ? ratioOrPen
        : ratioOrPen && ratioOrPen.ratio != null
          ? ratioOrPen.ratio
          : 0;
    const r = Math.max(0, ratio || 0);
    const pct = Math.round(Math.min(200, r * 100));
    if (r >= 1.0) {
      return {
        code: 'X',
        name: '浆膜外/超出壁厚',
        short: '浆膜外',
        label: '达浆膜外（几何）',
        detail: `占壁厚 ${pct}% · 参考 T4？（非病理金标准）`,
        tHint: 'T4?',
        tone: 'hot',
        pct,
        ratio: r,
      };
    }
    const hit = layerAtFrac(r);
    return {
      code: hit.code,
      name: hit.name,
      short: hit.short,
      label: `达${hit.name}（${hit.code}）`,
      detail: `占壁厚约 ${pct}% · 参考 ${hit.tHint}（非病理金标准）`,
      tHint: hit.tHint,
      tone: hit.tone,
      pct,
      ratio: r,
    };
  }

  /** Name each echo band between edge fracs (lumen→serosa). */
  function clinicalBandLabels(edgeFracs) {
    const edges = (edgeFracs && edgeFracs.length ? edgeFracs.slice() : []).sort((a, b) => a - b);
    const fracs = [0, ...edges, 1];
    const bands = [];
    for (let i = 0; i < fracs.length - 1; i++) {
      const f0 = fracs[i], f1 = fracs[i + 1];
      const mid = (f0 + f1) / 2;
      const hit = layerAtFrac(mid);
      bands.push({
        i: i + 1,
        f0, f1, mid,
        code: hit.code,
        name: hit.name,
        short: hit.short,
        tHint: hit.tHint,
        color: hit.color,
        tone: hit.tone,
      });
    }
    return bands;
  }

  /**
   * Doctor-facing source badge for layer plan (hide raw echo_fused etc.).
   * dashed=true → draw imaginary / equal-split guides as dashed warm lines.
   */
  function layerSourceInfo(analysis) {
    if (!analysis) {
      return { badge: '待分析', tone: 'cool', dashed: false, detail: '点选接触点后显示分层', confidence: '—' };
    }
    const src = analysis.source || '';
    const n = (analysis.edgeFracs && analysis.edgeFracs.length) || analysis.nLayers || 0;
    const noisy = !!analysis.localNoisy;
    if (src === 'echo_fused') {
      return {
        badge: '像素分层（去噪）',
        tone: 'cool',
        dashed: false,
        detail: `${n} 层界 · 多射线中值融合`,
        confidence: noisy ? '浸润区噪声抑制' : '回声层界较清晰',
      };
    }
    if (src === 'echo_dp' || src === 'echo_pixel') {
      return {
        badge: '通道像素分层',
        tone: 'cool',
        dashed: false,
        detail: `${n} 层界 · 沿浸润通道`,
        confidence: noisy ? '局部噪声偏高' : '通道内可见层界',
      };
    }
    if (src === 'pixel_extend') {
      return {
        badge: '相邻胃壁延伸',
        tone: 'warm',
        dashed: false,
        detail: `浸润处层次不清 · 自相邻清晰壁段映射 ${n} 层`,
        confidence: '优先相邻胃壁（临床常用）',
      };
    }
    if (src === 'channel_extend') {
      return {
        badge: '通道等分延伸',
        tone: 'warm',
        dashed: true,
        detail: `未见清晰层界 · 假想等分 ${n} 层`,
        confidence: '假想参考 · 请结合邻壁核对',
      };
    }
    if (analysis.imaginary) {
      return {
        badge: '假想分层',
        tone: 'warm',
        dashed: true,
        detail: `未见稳定回声层界 · 壁内假想 ${n} 层`,
        confidence: '假想参考 · 非像素实测',
      };
    }
    return {
      badge: '几何分层',
      tone: 'cool',
      dashed: false,
      detail: `${n} 层界`,
      confidence: '几何辅助',
    };
  }

  /**
   * Vertical wall-thickness stack for side panel (lumen top → serosa bottom).
   * Captions/legend English; clinical names can be passed via opts.lang='zh'.
   */
  function wallStackSvg(edgeFracs, occFrac, opts = {}) {
    const w = opts.w || 168;
    const h = opts.h || 168;
    const zh = opts.lang !== 'en';
    const bands = clinicalBandLabels(edgeFracs);
    const occ = Math.max(0, Math.min(1.2, occFrac == null ? 0 : occFrac));
    const padT = 18, padB = 18, padL = 10, padR = 58;
    const barX = padL, barW = 28;
    const barY = padT, barH = h - padT - padB;
    let html = `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" xmlns="http://www.w3.org/2000/svg" style="display:block">`;
    html += `<text x="${barX + barW / 2}" y="12" text-anchor="middle" fill="#94a3b8" font-size="9">${zh ? '腔侧' : 'Lumen'}</text>`;
    html += `<text x="${barX + barW / 2}" y="${h - 4}" text-anchor="middle" fill="#94a3b8" font-size="9">${zh ? '浆膜' : 'Serosa'}</text>`;
    bands.forEach((b) => {
      const y0 = barY + b.f0 * barH;
      const y1 = barY + b.f1 * barH;
      const bh = Math.max(1.5, y1 - y0);
      const reached = occ > b.f0;
      const full = occ >= b.f1;
      const op = reached ? (full ? 0.85 : 0.55) : 0.22;
      html += `<rect x="${barX}" y="${y0.toFixed(1)}" width="${barW}" height="${bh.toFixed(1)}" fill="${b.color}" opacity="${op}" stroke="#0f172a" stroke-width="0.6"/>`;
      const ty = y0 + bh / 2 + 3;
      html += `<text x="${barX + barW + 6}" y="${ty.toFixed(1)}" fill="${reached ? '#e2e8f0' : '#64748b'}" font-size="10" font-weight="${reached && !full ? 700 : 500}">${b.code} ${zh ? b.short : b.code}</text>`;
    });
    // lesion front
    const fy = barY + Math.min(1, occ) * barH;
    html += `<line x1="${barX - 3}" y1="${fy.toFixed(1)}" x2="${barX + barW + 3}" y2="${fy.toFixed(1)}" stroke="#fb7185" stroke-width="2.2"/>`;
    html += `<text x="${barX + barW + 6}" y="${Math.min(h - 22, fy + 3).toFixed(1)}" fill="#fb7185" font-size="9" font-weight="700">${zh ? '灶前缘' : 'Lesion front'}</text>`;
    // occupied wash
    if (occ > 0.01) {
      const oh = Math.min(barH, Math.min(1, occ) * barH);
      html += `<rect x="${barX}" y="${barY}" width="${barW}" height="${oh.toFixed(1)}" fill="#fb7185" opacity="0.18" stroke="none"/>`;
    }
    html += `</svg>`;
    return html;
  }

  function contactStatus(remain, thick, thrPx = CFG.CONTACT_THR_PX, ratio = null, opts = {}) {
    // opts.inContact === false → never claim layer / T stage
    if (opts && opts.inContact === false) {
      return { code: 'none', label: '无接触', tone: 'cool', layer: null, inContact: false };
    }
    if (opts && opts.inContact === true && ratio != null) {
      const layer = layerJudgment(ratio);
      return { code: layer.code, label: layer.label, tone: layer.tone, layer, inContact: true };
    }
    const r = Math.max(0, remain || 0);
    const t = Math.max(r, thick || r, 1);
    if (r <= thrPx) return { code: 'touch', label: '贴住/近贴', tone: 'hot', inContact: true };
    if (r / t <= 0.25) return { code: 'near', label: '接近', tone: 'warm', inContact: true };
    return { code: 'gap', label: '有间隙', tone: 'cool', inContact: false };
  }


  /** Point-in-polygon (ray casting). */
  function pointInPoly(p, poly) {
    if (!poly || poly.length < 3) return false;
    const x = p[0], y = p[1];
    let inside = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const xi = poly[i][0], yi = poly[i][1];
      const xj = poly[j][0], yj = poly[j][1];
      const inter = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-12) + xi;
      if (inter) inside = !inside;
    }
    return inside;
  }

  function dist2(a, b) {
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2;
  }

  /**
   * From a click (esp. on/near lesion): find wall index of deepest local infiltration.
   * Returns { idx, mode: 'lesion'|'wall'|'deep', score }.
   */
  function findInfiltrationFromClick(g, x, y, opts = {}) {
    if (!g?.wall_pts?.length) return null;
    const p = [x, y];
    const n = g.wall_pts.length;
    const les = g.lesion_poly || [];
    const contact = g.contact_idx && g.contact_idx.length ? g.contact_idx : null;

    // nearest wall / lesion distances
    let nearWall = 0, dw = 1e18, nearLesPt = 0, dl = 1e18;
    for (let i = 0; i < n; i++) {
      const d = dist2(g.wall_pts[i], p);
      if (d < dw) { dw = d; nearWall = i; }
      if (g.wall_lesion_pts?.[i]) {
        const d2v = dist2(g.wall_lesion_pts[i], p);
        if (d2v < dl) { dl = d2v; nearLesPt = i; }
      }
    }
    let dLesEdge = 1e18;
    for (const q of les) {
      const d = dist2(q, p);
      if (d < dLesEdge) dLesEdge = d;
    }
    const inLes = pointInPoly(p, les);
    const preferLesion = inLes || dLesEdge < dw * 0.85 || (opts.preferLesion && dLesEdge < dw + 400);

    if (preferLesion) {
      // Candidates: contact indices (or all), scored by proximity of lesion-face to click + depth
      const cand = contact || Array.from({ length: n }, (_, i) => i);
      let best = nearLesPt, bestScore = 1e18;
      cand.forEach((i) => {
        const lp = g.wall_lesion_pts[i];
        if (!lp) return;
        const prox = Math.sqrt(dist2(lp, p));
        const rem = g.wall_dists[i] != null ? g.wall_dists[i] : 50;
        // deeper (smaller remain) + closer lesion face to click
        const score = prox + rem * 0.08; // doctor click location first; depth is AI hint elsewhere
        if (score < bestScore) { bestScore = score; best = i; }
      });
      // Doctor picks facing wall; optional local deepen only if explicitly requested
      if (opts.autoDeepen) {
        const half = opts.refineHalf != null ? opts.refineHalf : 10;
        let deep = best, deepRem = g.wall_dists[best] != null ? g.wall_dists[best] : 1e9;
        for (let k = -half; k <= half; k++) {
          const i = (best + k + n * 20) % n;
          if (contact && !contact.includes(i) && k !== 0) continue;
          const rem = g.wall_dists[i];
          if (rem == null) continue;
          if (rem < deepRem) { deepRem = rem; deep = i; }
        }
        return { idx: deep, mode: 'lesion', seed: best, remain: deepRem };
      }
      // Prefer proximity to click (doctor intent), lightly bias toward deeper contact
      return { idx: best, mode: 'lesion', seed: best, remain: g.wall_dists[best] };
    }

    // Wall click: nearest wall, optionally snap to deeper neighbor on contact
    let idx = nearWall;
    if (contact && contact.length) {
      let best = idx, bd = 1e18;
      contact.forEach((i) => {
        const d = dist2(g.wall_pts[i], p);
        if (d < bd) { bd = d; best = i; }
      });
      if (Math.sqrt(bd) < Math.sqrt(dw) + 25) idx = best;
    }
    return { idx, mode: 'wall', remain: g.wall_dists[idx] };
  }


  /** Whether wall index i is in contact with lesion (for gating layer/T output). */
  function isContactPoint(g, i, thrPx) {
    if (!g || i == null || i < 0) return false;
    const thr = thrPx != null ? thrPx : CFG.CONTACT_THR_PX;
    if (g.contact_idx && g.contact_idx.includes(i)) return true;
    const d = g.wall_dists && g.wall_dists[i];
    return d != null && d <= thr;
  }

  /** Equal-split fracs for N layer interfaces (1/N … 1). */
  function equalFracs(nDiv) {
    const n = Math.max(CFG.MIN_LAYERS, Math.min(CFG.MAX_LAYERS, nDiv | 0));
    const out = [];
    for (let k = 1; k <= n; k++) out.push(k / n);
    return out;
  }

  /**
   * Adaptive layer interfaces from echo curve.
   * - pick strongest gradient peaks (2..MAX)
   * - if too few, pad with imaginary equal splits (imaginary=true)
   * - if too many, keep top MAX by strength
   */
  function resolveLayerFracs(values, preferN) {
    const n = values?.length || 0;
    if (n < 8) {
      return { edgeFracs: equalFracs(CFG.TARGET_LAYERS), nLayers: CFG.TARGET_LAYERS, imaginary: true, stable: false };
    }
    const want = Math.max(CFG.MIN_LAYERS, Math.min(CFG.MAX_LAYERS, preferN || CFG.MAX_LAYERS));
    const g = [];
    for (let i = 1; i < n - 1; i++) g.push({ i, v: Math.abs(values[i + 1] - values[i - 1]) });
    g.sort((a, b) => b.v - a.v);
    const med = g.length ? g[Math.floor(g.length * 0.5)].v : 0;
    const thr = Math.max(med * 1.15, 2.5);
    const minSep = Math.max(2, Math.floor(n / (want * 2.4)));
    const picked = [];
    for (const cand of g) {
      if (picked.length >= CFG.MAX_LAYERS) break;
      if (cand.v < thr && picked.length >= CFG.MIN_LAYERS) continue;
      if (picked.some((p) => Math.abs(p - cand.i) < minSep)) continue;
      picked.push(cand.i);
    }
    picked.sort((a, b) => a - b);
    let fracs = picked.map((i) => i / (n - 1));
    let imaginary = false;
    let stable = fracs.length >= CFG.TARGET_LAYERS;
    if (fracs.length < CFG.MIN_LAYERS) {
      fracs = equalFracs(CFG.TARGET_LAYERS);
      imaginary = true;
      stable = false;
    } else if (fracs.length < want) {
      // pad imaginary splits into largest gaps
      imaginary = true;
      while (fracs.length < want) {
        let bestGap = 0, bestAt = 0;
        const seq = [0, ...fracs, 1];
        for (let k = 0; k < seq.length - 1; k++) {
          const gap = seq[k + 1] - seq[k];
          if (gap > bestGap) { bestGap = gap; bestAt = (seq[k] + seq[k + 1]) / 2; }
        }
        fracs.push(bestAt);
        fracs.sort((a, b) => a - b);
      }
    }
    if (fracs[fracs.length - 1] < 0.98) fracs.push(1);
    fracs = [...new Set(fracs.map((f) => Math.round(f * 1000) / 1000))].sort((a, b) => a - b);
    if (fracs.length > CFG.MAX_LAYERS) fracs = equalFracs(CFG.MAX_LAYERS);
    return { edgeFracs: fracs, nLayers: fracs.length, imaginary, stable };
  }

  function polyCentroid(pts) {
    if (!pts?.length) return [0, 0];
    let sx = 0, sy = 0;
    pts.forEach((p) => { sx += p[0]; sy += p[1]; });
    return [sx / pts.length, sy / pts.length];
  }

  function angDiff(a, b) {
    let d = a - b;
    while (d > Math.PI) d -= 2 * Math.PI;
    while (d < -Math.PI) d += 2 * Math.PI;
    return Math.abs(d);
  }

  /**
   * Find nearby wall index with clearer channel (larger remain) for extension anchor.
   * Geometry-only fallback when echo image is unavailable.
   */
  function findAdjacentClearIdx(g, center, half) {
    if (!g?.wall_dists?.length) return center;
    const n = g.wall_dists.length;
    const H = half != null ? half : CFG.SEARCH_HALF;
    let best = center, bestScore = -1;
    for (let k = -H; k <= H; k++) {
      const i = (center + k + n * 20) % n;
      const rem = g.wall_dists[i];
      if (rem == null) continue;
      // prefer non-contact or thicker remaining channel for visible layers
      const score = rem + (g.contact_idx && g.contact_idx.includes(i) ? 0 : 8);
      if (score > bestScore) { bestScore = score; best = i; }
    }
    return best;
  }

  /** Echo clarity for adjacent-wall search (higher = clearer layered wall). */
  function echoClarityScore(analysis) {
    if (!analysis?.values?.length) return 0;
    let score = 0;
    const nL = analysis.edgeFracs?.length || 0;
    score += Math.min(5, nL);
    if (!analysis.imaginary) score += 3.5;
    if (analysis.stable) score += 1.5;
    const cents = analysis.cents || [];
    if (cents.length >= 2) {
      const span = Math.max(...cents) - Math.min(...cents);
      score += Math.min(4, span / 35);
    }
    const vals = analysis.values;
    let gSum = 0;
    for (let i = 1; i < vals.length - 1; i++) gSum += Math.abs(vals[i + 1] - vals[i - 1]);
    score += Math.min(3, gSum / Math.max(1, vals.length) / 12);
    return score;
  }

  /**
   * G5: search adjacent wall within ±maxAngleDeg around lesion centroid for ≥minLayers echo layers.
   * Returns {idx, analysis, score, nLayers} or null.
   */
  function findAdjacentLayeredWall(imgData, iw, ih, g, pickIdx, opts) {
    const o = opts || {};
    if (!imgData || !g?.wall_pts?.length || pickIdx == null) return null;
    const n = g.wall_pts.length;
    const H = o.searchHalf != null ? o.searchHalf : CFG.SEARCH_HALF;
    const minLayers = o.minLayers != null ? o.minLayers : CFG.TARGET_LAYERS;
    const maxAng = ((o.maxAngleDeg != null ? o.maxAngleDeg : 45) * Math.PI) / 180;
    const kCl = o.kClusters != null ? o.kClusters : CFG.MAX_LAYERS;
    const lesionC = polyCentroid(g.lesion_poly);
    const p0 = g.wall_pts[pickIdx];
    const ang0 = Math.atan2(p0[1] - lesionC[1], p0[0] - lesionC[0]);
    const rem0 = g.wall_dists[pickIdx] || 0;
    const maxPx = o.maxDistPx != null ? o.maxDistPx : 72;
    let best = null;
    for (let k = -H; k <= H; k++) {
      if (k === 0) continue;
      const i = (pickIdx + k + n * 20) % n;
      const pi = g.wall_pts[i];
      const rem = g.wall_dists[i];
      const d = g.wall_dirs?.[i];
      if (!pi || rem == null || rem < 5 || !d) continue;
      // Spatial nearness — avoid opposite-side wall pocket along a wrapping contour
      const distPx = Math.hypot(pi[0] - p0[0], pi[1] - p0[1]);
      if (distPx > maxPx) continue;
      // Prefer adjacent clearer wall: usually larger remain than destroyed infiltrate site
      if (rem < rem0 * 0.85 && rem < 10) continue;
      const angi = Math.atan2(pi[1] - lesionC[1], pi[0] - lesionC[0]);
      if (angDiff(angi, ang0) > maxAng) continue;
      const a = analyzeEchoRay(imgData, iw, ih, pi, d, rem, rem, {
        maxLayers: kCl,
        allowPad: false,
        nbhd: o.nbhd != null ? o.nbhd : 1,
        lateral: o.lateral != null ? o.lateral : 1,
      });
      const nL = a?.realPeakCount || a?.pixelEdges?.length || a?.edgeFracs?.length || 0;
      if (nL < minLayers || a?.imaginary) continue;
      const score = echoClarityScore(a) + rem * 0.04 - Math.abs(k) * 0.03 + nL * 0.8 - distPx * 0.02;
      if (!best || score > best.score) best = { idx: i, analysis: a, score, nLayers: nL };
    }
    return best;
  }

  /**
   * G4: carry adjacent **pixel-derived** fracs along channel (× local remain at draw time).
   * Equal-split ONLY if adjacent has no real pixel edges.
   */
  function extendLayersAlongChannel(g, pickIdx, adj, nDiv) {
    const src = adj?.analysis?.pixelEdges?.length
      ? adj.analysis.pixelEdges
      : adj?.analysis?.edgeFracs;
    const real = !!(src && src.length >= CFG.MIN_LAYERS && !(adj?.analysis?.imaginary));
    let fracs;
    if (src && src.length) {
      fracs = src.slice().sort((a, b) => a - b).slice(0, CFG.MAX_LAYERS);
    } else {
      const N = Math.max(CFG.MIN_LAYERS, Math.min(CFG.MAX_LAYERS, nDiv || CFG.CHANNEL_DIV));
      fracs = channelEqualFracs(N);
    }
    fracs = fracs.map((f) => Math.max(0.08, Math.min(0.92, f))).sort((a, b) => a - b);
    return {
      edgeFracs: fracs,
      nLayers: fracs.length,
      imaginary: !real,
      source: real ? 'pixel_extend' : 'channel_extend',
      fromIdx: adj?.idx != null ? adj.idx : findAdjacentClearIdx(g, pickIdx),
      stable: real && fracs.length >= CFG.TARGET_LAYERS,
      pixelFromAdjacent: real,
    };
  }

  /**
   * Channel-equal-split fracs (meeting rule): N divisions of local channel width.
   * Drawing depths use channelWidth (= remain), not full thick — keeps lines between orange & green.
   */
  function channelEqualFracs(nDiv) {
    return equalFracs(nDiv || CFG.CHANNEL_DIV);
  }

  /**
   * Build display plan at pick index: contact gate + fracs + channel depth.
   */
  function buildLayerPlan(g, pickIdx, echoAnalysis) {
    const inContact = isContactPoint(g, pickIdx);
    const remain = g.wall_dists[pickIdx];
    const thick = localWallThickness(g.wall_dists, g.contact_idx, pickIdx);
    const channel = Math.max(4, remain || thick * 0.5);
    let edgeFracs, imaginary, stable, nLayers, source;
    if (echoAnalysis && echoAnalysis.edgeFracs?.length) {
      edgeFracs = echoAnalysis.edgeFracs;
      imaginary = !!echoAnalysis.imaginary;
      stable = !!echoAnalysis.stable;
      nLayers = echoAnalysis.nLayers || edgeFracs.length;
      source = 'echo';
    } else {
      const r = resolveLayerFracs(echoAnalysis?.values, CFG.MAX_LAYERS);
      edgeFracs = r.edgeFracs;
      imaginary = r.imaginary;
      stable = r.stable;
      nLayers = r.nLayers;
      source = imaginary ? 'imaginary' : 'echo';
    }
    // If echo unstable at contact point, try adjacent clearer wall + channel equal split
    if ((!stable || imaginary) && g.wall_pts) {
      const adj = findAdjacentClearIdx(g, pickIdx);
      if (adj !== pickIdx && (g.wall_dists[adj] || 0) > channel * 0.85) {
        const ext = extendLayersAlongChannel(g, pickIdx, { idx: adj, nLayers: CFG.CHANNEL_DIV }, CFG.CHANNEL_DIV);
        edgeFracs = ext.edgeFracs;
        imaginary = true;
        source = 'channel_extend';
        nLayers = edgeFracs.length;
        stable = false;
      }
    }
    const pen = penetrationAt(g.wall_dists, g.contact_idx, pickIdx, {
      wall_pts: g.wall_pts, lesion_poly: g.lesion_poly, wall_dirs: g.wall_dirs,
    });
    return {
      inContact,
      remain,
      thick,
      channel,
      edgeFracs,
      imaginary,
      stable,
      nLayers,
      source,
      pen,
      ratio: pen.ratio,
    };
  }

  /** Soft-drag a contour: neighbors follow with spatial Gaussian (doctor-friendly edit). */
  function softDeform(pts, anchorIdx, newX, newY, sigmaPx) {
    if (!pts || !pts.length || anchorIdx < 0 || anchorIdx >= pts.length) return;
    const ax = pts[anchorIdx][0];
    const ay = pts[anchorIdx][1];
    const dx = newX - ax;
    const dy = newY - ay;
    if (Math.abs(dx) < 1e-6 && Math.abs(dy) < 1e-6) return;
    const sigma = sigmaPx || Math.max(18, Math.min(40, Math.sqrt(pts.length) * 3.2));
    const inv = 1 / (2 * sigma * sigma);
    for (let j = 0; j < pts.length; j++) {
      const ddx = pts[j][0] - ax;
      const ddy = pts[j][1] - ay;
      const w = Math.exp(-(ddx * ddx + ddy * ddy) * inv);
      if (w < 0.015) continue;
      pts[j][0] += dx * w;
      pts[j][1] += dy * w;
    }
  }

  /** Evenly sample control-point indices along a closed contour. */
  function controlIndices(n, count) {
    if (n <= 0) return [];
    const k = Math.max(1, Math.min(n, count | 0));
    if (k >= n) return Array.from({ length: n }, (_, i) => i);
    const out = [];
    for (let i = 0; i < k; i++) out.push(Math.round((i * n) / k) % n);
    return [...new Set(out)];
  }

  /**
   * Wall tangent normal at index i, oriented toward a point (usually lesion).
   * Prefer geometric wall normal over wall→nearest-lesion dirs (more stable layers).
   */
  function wallNormalAt(wall, i, toward) {
    const n = wall.length;
    if (!n) return [0, 1];
    const a = wall[(i - 1 + n) % n];
    const b = wall[(i + 1) % n];
    const p = wall[i];
    let [nx, ny] = unit(-(b[1] - a[1]), b[0] - a[0]);
    if (toward) {
      const vx = toward[0] - p[0];
      const vy = toward[1] - p[1];
      if (nx * vx + ny * vy < 0) {
        nx = -nx;
        ny = -ny;
      }
    }
    return [nx, ny];
  }

  /** Convert desired on-screen px → SVG user units for a zoom crop of size vw shown in panelCssPx. */
  function zoomUserStroke(vw, panelCssPx, screenPx) {
    const panel = Math.max(120, panelCssPx || 320);
    const u = Math.max(vw, 1) / panel;
    const px = screenPx != null ? screenPx : 1.15;
    // Keep ~1 CSS px; allow sub-pixel user units when strongly zoomed
    return Math.max(0.12, px * u);
  }

  /**
   * Thin layer ticks in the orange→green channel only.
   * Depths are fractions of remain (wall→lesion gap), along wall_dirs.
   */
  function quartileGuidesSvg(p, dir, thick, sw, remain, edgeFracs, opts = {}) {
    const [ux, uy] = unit(dir[0], dir[1]);
    const [nx, ny] = [-uy, ux];
    const strokeScale = opts.strokeScale != null ? opts.strokeScale : 0.55;
    const opacity = opts.opacity != null ? opts.opacity : CFG.GUIDE_OPACITY;
    const lw = opts.pxStroke != null
      ? opts.pxStroke
      : Math.max(0.45, CFG.GUIDE_STROKE * sw * strokeScale);
    const rem = Math.max(0, remain != null ? remain : 0);
    // Channel = actual gap between wall (orange) and lesion (green)
    if (rem < 2) return '';
    const channel = rem;
    const half = opts.tickHalf != null
      ? opts.tickHalf
      : Math.max(5, Math.min(14, channel * 0.45));
    let fracs = edgeFracs && edgeFracs.length
      ? edgeFracs.slice().sort((a, b) => a - b).slice(0, CFG.MAX_LAYERS)
      : channelEqualFracs(Math.min(CFG.CHANNEL_DIV, channel < 14 ? 3 : CFG.CHANNEL_DIV));
    if (channel < 12 && fracs.length > 3) {
      fracs = [1 / 3, 2 / 3, 1];
    }
    // Keep ticks strictly inside the gap (not on contours)
    fracs = fracs.map((f) => Math.max(0.12, Math.min(0.88, f)));
    const colors = ['#facc15', '#94a3b8', '#fbbf24', '#64748b', '#f59e0b'];
    let html = '';
    fracs.forEach((f, i) => {
      const depth = channel * f;
      const x = p[0] + ux * depth;
      const y = p[1] + uy * depth;
      const c = colors[i % colors.length];
      html += `<line x1="${(x - nx * half).toFixed(1)}" y1="${(y - ny * half).toFixed(1)}" x2="${(x + nx * half).toFixed(1)}" y2="${(y + ny * half).toFixed(1)}" stroke="${c}" stroke-width="${lw.toFixed(2)}" opacity="${opacity}"/>`;
    });
    // Mark wall edge (orange side) lightly
    html += `<line x1="${(p[0] - nx * half).toFixed(1)}" y1="${(p[1] - ny * half).toFixed(1)}" x2="${(p[0] + nx * half).toFixed(1)}" y2="${(p[1] + ny * half).toFixed(1)}" stroke="#fff" stroke-width="${(lw * 1.05).toFixed(2)}" opacity="${opacity * 0.85}"/>`;
    // Optional soft fill for occupied wall (beyond channel into estimated thick) — keep subtle
    const showOcc = opts.showOcc !== false && opts.inContact !== false;
    const t = Math.max(thick || rem, rem);
    if (showOcc && t > rem + 2) {
      const sx = p[0] + ux * rem;
      const sy = p[1] + uy * rem;
      const ex = p[0] + ux * Math.min(t, rem + (t - rem) * 0.35);
      const ey = p[1] + uy * Math.min(t, rem + (t - rem) * 0.35);
      const hw = half * 0.35;
      html += `<path d="M${(sx - nx * hw).toFixed(1)},${(sy - ny * hw).toFixed(1)} L${(sx + nx * hw).toFixed(1)},${(sy + ny * hw).toFixed(1)} L${(ex + nx * hw).toFixed(1)},${(ey + ny * hw).toFixed(1)} L${(ex - nx * hw).toFixed(1)},${(ey - ny * hw).toFixed(1)} Z" fill="#fb7185" opacity="${CFG.OCC_FILL_OPACITY}"/>`;
    }
    return html;
  }

  /**
   * Layer arcs ONLY along the contact neighborhood near the pick.
   * Each point offset along wall→lesion (wall_dirs) by frac × local remain
   * so lines sit in the middle of the orange–green channel — never into lumen or mass.
   * opts: { pxStroke, opacity, half already via arg }
   */
  function wallLayerArcsSvg(g, center, half = 8, edgeFracs, opts = {}) {
    const o = Object.assign({ half: half, showBands: false }, opts || {});
    return channelLayerCurvesSvg(g, center, edgeFracs, o);
  }

  /** Full-frame overview inset (for zoom panel corner). Image scaled into box; crop rect marked. */
  function overviewInsetSvg(imgW, imgH, crop, box, strokeU) {
    if (!imgW || !imgH || !crop || !box) return '';
    const { x: bx, y: by, w: bw, h: bh } = box;
    const sw = strokeU != null ? strokeU : 1;
    const sx = bx + (crop.x / imgW) * bw;
    const sy = by + (crop.y / imgH) * bh;
    const swid = Math.max(2, (crop.w / imgW) * bw);
    const shgt = Math.max(2, (crop.h / imgH) * bh);
    return `<g class="overview-inset">
      <rect x="${bx.toFixed(1)}" y="${by.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" fill="#000" stroke="#475569" stroke-width="${(sw * 1.1).toFixed(2)}" opacity=".92"/>
      <image href="${box.href || ''}" xlink:href="${box.href || ''}" x="${bx}" y="${by}" width="${bw}" height="${bh}" preserveAspectRatio="none" opacity=".9"/>
      <rect x="${sx.toFixed(1)}" y="${sy.toFixed(1)}" width="${swid.toFixed(1)}" height="${shgt.toFixed(1)}" fill="none" stroke="#f87171" stroke-width="${(sw * 1.2).toFixed(2)}" opacity=".95"/>
    </g>`;
  }

  function computeGeometry(wall, les) {
    if (!wall || wall.length < 3 || !les || les.length < 3) return null;
    const n = wall.length;
    const wall_lesion_pts = [],
      wall_dists = [],
      wall_dirs = [];
    for (let i = 0; i < n; i++) {
      const w = wall[i];
      let best = les[0],
        bd = 1e18;
      for (const q of les) {
        const d = (q[0] - w[0]) ** 2 + (q[1] - w[1]) ** 2;
        if (d < bd) {
          bd = d;
          best = q;
        }
      }
      const dist = Math.sqrt(bd);
      const [ux, uy] = unit(best[0] - w[0], best[1] - w[1]);
      wall_lesion_pts.push([best[0], best[1]]);
      wall_dists.push(dist);
      wall_dirs.push([ux, uy]);
    }
    const thr = Math.max(8, Math.min(...wall_dists) * 2.5 + 4);
    const contact_idx = wall_dists.map((d, i) => (d <= thr ? i : -1)).filter((i) => i >= 0);
    let deep = 0;
    wall_dists.forEach((d, i) => {
      if (d < wall_dists[deep]) deep = i;
    });
    const contact_ratio = contactRatioByLength(wall, contact_idx);
    const far = wall_dists
      .filter((_, i) => !contact_idx.includes(i) && wall_dists[i] > 1)
      .sort((a, b) => a - b);
    const ref_thickness = far.length >= 5 ? percentile(far, 0.75) : Math.max(wall_dists.reduce((a, b) => a + b, 0) / n, 12);
    return {
      wall_pts: wall,
      lesion_poly: les,
      wall_lesion_pts,
      wall_dists,
      wall_dirs,
      contact_idx,
      contact_ratio,
      deep_idx: deep,
      min_remain_px: wall_dists[deep],
      mean_remain_px: wall_dists.reduce((a, b) => a + b, 0) / n,
      ref_thickness,
    };
  }

  function localArcIndices(n, center, half) {
    const out = [];
    for (let k = -half; k <= half; k++) out.push((center + k + n * 10) % n);
    return out;
  }

  function contactArcPath(g) {
    const wall = g.wall_pts;
    const ci = (g.contact_idx || []).slice().sort((a, b) => a - b);
    if (!ci.length) return '';
    let arc = '',
      seg = [];
    const flush = () => {
      if (seg.length >= 2) arc += smoothPath(seg.map((j) => wall[j]), false) + ' ';
      else if (seg.length === 1) {
        const p = wall[seg[0]];
        arc += `M${p[0]},${p[1]} `;
      }
      seg = [];
    };
    for (const i of ci) {
      if (!seg.length || i === seg[seg.length - 1] + 1) seg.push(i);
      else {
        flush();
        seg = [i];
      }
    }
    flush();
    return arc.trim();
  }

  function thicknessBand(g, center, half = 12) {
    const idxs = localArcIndices(g.wall_pts.length, center, half);
    return bandPath(
      idxs.map((i) => g.wall_pts[i]),
      idxs.map((i) => g.wall_lesion_pts[i])
    );
  }

  /** Contact if remain is within threshold of local thickness (near-touch). */
  /** @deprecated alias */
  function contactStatusLegacy(remain, thick, thrPx = 6) {
    return contactStatus(remain, thick, thrPx, null);
  }

  /**
   * Mini remain-thickness profile along local wall arc (English labels).
   * Returns SVG markup for a 280x56 strip.
   */
  function remainProfileSvg(g, centerIdx, half = 18, w = 280, h = 56) {
    if (!g?.wall_dists?.length) return '';
    const n = g.wall_dists.length;
    const idxs = localArcIndices(n, centerIdx, half);
    const vals = idxs.map((i) => Math.max(0, g.wall_dists[i]));
    const maxV = Math.max(...vals, 1);
    const pad = 8;
    const plotW = w - pad * 2;
    const plotH = h - 22;
    const step = plotW / Math.max(1, vals.length - 1);
    let d = '';
    vals.forEach((v, k) => {
      const x = pad + k * step;
      const y = pad + plotH * (1 - v / maxV);
      d += (k ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1);
    });
    const mid = Math.floor(vals.length / 2);
    const mx = pad + mid * step;
    const my = pad + plotH * (1 - vals[mid] / maxV);
    const ci = new Set(g.contact_idx || []);
    let contactMarks = '';
    idxs.forEach((i, k) => {
      if (!ci.has(i)) return;
      const x = pad + k * step;
      contactMarks += `<line x1="${x.toFixed(1)}" y1="${pad}" x2="${x.toFixed(1)}" y2="${pad + plotH}" stroke="#5ec8d8" stroke-width="1.2" opacity=".35"/>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" xmlns="http://www.w3.org/2000/svg" style="display:block;background:#000;border:1px solid #222;border-radius:6px">
      ${contactMarks}
      <path d="${d}" fill="none" stroke="#f0a35e" stroke-width="1.8"/>
      <circle cx="${mx.toFixed(1)}" cy="${my.toFixed(1)}" r="2" fill="#fff" stroke="#e07a6a" stroke-width="1"/>
    </svg>`;
  }

  /** SVG fragment: thickness ruler along lumen→lesion ray (no text). */
  function thicknessRulerSvg(p, lp, remain, thick, penRatio, sw) {
    const [ux, uy] = unit(lp[0] - p[0], lp[1] - p[1]);
    const [nx, ny] = [-uy, ux];
    const barLen = Math.max(thick, remain, 8);
    const occRatio = Math.max(0, penRatio || 0);
    const occupied = Math.min(barLen * Math.max(occRatio, (barLen - remain) / Math.max(barLen, 1e-6)), barLen * 1.25);
    const off = Math.max(6, 8 * sw);
    const barW = Math.max(1.1, 2.2 * sw);
    const ox = p[0] + nx * off;
    const oy = p[1] + ny * off;
    const endX = ox + ux * barLen;
    const endY = oy + uy * barLen;
    const midX = ox + ux * Math.min(occupied, barLen);
    const midY = oy + uy * Math.min(occupied, barLen);
    const tipX = lp[0] + ux * Math.max(4, remain * 0.06);
    const tipY = lp[1] + uy * Math.max(4, remain * 0.06);
    // Screen-space tiny dots (~1.1 / 0.9 CSS px) — avoid large floors that hide echo at zoom
    const rPick = Math.max(0.14, 1.05 * sw);
    const rLes = Math.max(0.12, 0.9 * sw);
    const rayW = Math.max(0.35, 0.85 * sw);
    return `
      <line x1="${p[0]}" y1="${p[1]}" x2="${tipX}" y2="${tipY}" stroke="#ff6b6b" stroke-width="${rayW.toFixed(2)}" stroke-dasharray="${(3.2 * sw).toFixed(1)} ${(2.2 * sw).toFixed(1)}" marker-end="url(#zArrow)" opacity=".75"/>
      <line x1="${ox}" y1="${oy}" x2="${endX}" y2="${endY}" stroke="#334155" stroke-width="${barW.toFixed(2)}" stroke-linecap="round" opacity=".7"/>
      <line x1="${ox}" y1="${oy}" x2="${midX}" y2="${midY}" stroke="#f0a35e" stroke-width="${barW.toFixed(2)}" stroke-linecap="round" opacity=".8"/>
      <line x1="${midX}" y1="${midY}" x2="${endX}" y2="${endY}" stroke="#5ec8d8" stroke-width="${barW.toFixed(2)}" stroke-linecap="round" opacity=".75"/>
      <circle cx="${p[0]}" cy="${p[1]}" r="${rPick.toFixed(2)}" fill="#fff" stroke="#e07a6a" stroke-width="${Math.max(0.25, 0.55 * sw).toFixed(2)}" opacity=".92"/>
      <circle cx="${lp[0]}" cy="${lp[1]}" r="${rLes.toFixed(2)}" fill="#6fbf8f" stroke="#fff" stroke-width="${Math.max(0.2, 0.45 * sw).toFixed(2)}" opacity=".9"/>
    `;
  }

  function sampleGray(imgData, iw, ih, x, y) {
    const xi = Math.max(0, Math.min(iw - 1, Math.round(x)));
    const yi = Math.max(0, Math.min(ih - 1, Math.round(y)));
    const i = (yi * iw + xi) * 4;
    return 0.299 * imgData.data[i] + 0.587 * imgData.data[i + 1] + 0.114 * imgData.data[i + 2];
  }

  /** Mean gray in a small neighborhood (nearby pixels for stabler 5-layer clustering). */
  function sampleGrayNbhd(imgData, iw, ih, x, y, rad) {
    const r = rad != null ? rad : 1;
    if (r <= 0) return sampleGray(imgData, iw, ih, x, y);
    let s = 0, c = 0;
    const x0 = Math.round(x), y0 = Math.round(y);
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (dx * dx + dy * dy > r * r + 0.25) continue;
        s += sampleGray(imgData, iw, ih, x0 + dx, y0 + dy);
        c++;
      }
    }
    return c ? s / c : sampleGray(imgData, iw, ih, x, y);
  }

  function smooth1d(arr, win) {
    const w = Math.max(1, win | 0);
    const out = new Array(arr.length);
    for (let i = 0; i < arr.length; i++) {
      let s = 0, c = 0;
      for (let k = -w; k <= w; k++) {
        const j = i + k;
        if (j < 0 || j >= arr.length) continue;
        s += arr[j];
        c++;
      }
      out[i] = s / c;
    }
    return out;
  }

  /** Odd-window median filter — robust to US speckle near infiltrate. */
  function median1d(arr, win) {
    const w = Math.max(1, win | 0);
    const out = new Array(arr.length);
    const buf = [];
    for (let i = 0; i < arr.length; i++) {
      buf.length = 0;
      for (let k = -w; k <= w; k++) {
        const j = i + k;
        if (j < 0 || j >= arr.length) continue;
        buf.push(arr[j]);
      }
      buf.sort((a, b) => a - b);
      out[i] = buf[Math.floor(buf.length / 2)];
    }
    return out;
  }

  /**
   * Denoise channel echo profile for noisy infiltrate neighborhood:
   * lateral already averaged → 1D median → light box smooth.
   */
  function denoiseEchoProfile(raw, opts) {
    const o = opts || {};
    const n = raw?.length || 0;
    if (n < 4) return { values: (raw || []).slice(), noise: 0, snr: 0 };
    const medWin = o.medWin != null ? o.medWin : Math.max(1, Math.min(5, Math.floor(n / 24)));
    const smWin = o.smWin != null ? o.smWin : Math.max(1, Math.min(4, Math.floor(n / 30)));
    const med = median1d(raw, medWin);
    const values = smooth1d(med, smWin);
    // noise ≈ MAD of residual (raw - smooth)
    const resid = [];
    for (let i = 0; i < n; i++) resid.push(Math.abs(raw[i] - values[i]));
    const rr = resid.slice().sort((a, b) => a - b);
    const mad = rr[Math.floor(rr.length / 2)] || 0;
    const noise = mad * 1.4826;
    let vmin = values[0], vmax = values[0];
    values.forEach((v) => { if (v < vmin) vmin = v; if (v > vmax) vmax = v; });
    const snr = (vmax - vmin) / Math.max(noise, 1e-3);
    return { values, noise, snr, mad };
  }

  /** Median of numbers (for lateral strip). */
  function medianOf(arr) {
    if (!arr?.length) return 0;
    const a = arr.slice().sort((x, y) => x - y);
    return a[Math.floor(a.length / 2)];
  }

  /** 1D k-means on intensity values → cluster id per sample. */
  function kmeans1d(values, k, iters) {
    const n = values.length;
    const kk = Math.max(2, Math.min(k || 5, n));
    const sorted = values.slice().sort((a, b) => a - b);
    let cents = [];
    for (let i = 0; i < kk; i++) cents.push(sorted[Math.floor(((i + 0.5) / kk) * (n - 1))]);
    let labels = new Array(n).fill(0);
    for (let it = 0; it < (iters || 12); it++) {
      for (let i = 0; i < n; i++) {
        let best = 0, bd = 1e18;
        for (let c = 0; c < kk; c++) {
          const d = Math.abs(values[i] - cents[c]);
          if (d < bd) { bd = d; best = c; }
        }
        labels[i] = best;
      }
      const sum = new Array(kk).fill(0), cnt = new Array(kk).fill(0);
      for (let i = 0; i < n; i++) { sum[labels[i]] += values[i]; cnt[labels[i]]++; }
      for (let c = 0; c < kk; c++) if (cnt[c]) cents[c] = sum[c] / cnt[c];
    }
    // order clusters by mean intensity (bright/dark alternation for US layers)
    const order = cents.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v).map((x) => x.i);
    const remap = new Array(kk);
    order.forEach((old, neu) => { remap[old] = neu; });
    labels = labels.map((L) => remap[L]);
    cents = order.map((i) => cents[i]);
    return { labels, cents };
  }

  /**
   * Optimal 1D change-point (DP) + noise-aware BIC (K=2..maxK).
   * Higher noise → stronger K penalty → fewer spurious layers in infiltrate zone.
   */
  function optimalChangePointFracs(values, maxK, opts) {
    const y = values;
    const N = y?.length || 0;
    if (N < 16) return { fracs: [], K: 0, means: [], bic: Infinity };
    const o = opts || {};
    const Kmax = Math.max(2, Math.min(CFG.MAX_LAYERS, maxK || CFG.MAX_LAYERS));
    const noise = o.noise != null ? o.noise : 0;
    const snr = o.snr != null ? o.snr : 8;
    // Noisy infiltrate: larger min segment + heavier BIC penalty
    const noisy = snr < 5.5 || noise > 12;
    const bicMul = noisy ? 3.6 : (snr < 8 ? 2.8 : 2.2);
    const minSeg = Math.max(noisy ? 5 : 3, Math.floor(N / (noisy ? 14 : 22)));
    const cost = Array.from({ length: N + 1 }, () => new Array(N + 1).fill(0));
    for (let i = 0; i < N; i++) {
      let s = 0, s2 = 0;
      for (let j = i + 1; j <= N; j++) {
        const v = y[j - 1];
        s += v; s2 += v * v;
        const m = j - i;
        cost[i][j] = s2 - (s * s) / m;
      }
    }
    const INF = 1e100;
    let best = { bic: INF, K: 2, cps: [] };
    for (let K = 2; K <= Kmax; K++) {
      const dp = Array.from({ length: K + 1 }, () => new Array(N + 1).fill(INF));
      const bp = Array.from({ length: K + 1 }, () => new Array(N + 1).fill(-1));
      dp[0][0] = 0;
      for (let k = 1; k <= K; k++) {
        for (let j = k * minSeg; j <= N; j++) {
          for (let t = (k - 1) * minSeg; t <= j - minSeg; t++) {
            const val = dp[k - 1][t] + cost[t][j];
            if (val < dp[k][j]) { dp[k][j] = val; bp[k][j] = t; }
          }
        }
      }
      const sse = dp[K][N];
      if (!(sse < INF / 2)) continue;
      const bic = N * Math.log(Math.max(sse / N, 1e-9)) + K * Math.log(N) * bicMul;
      const cps = [];
      let k = K, j = N;
      while (k > 0) {
        const t = bp[k][j];
        if (t <= 0) break;
        if (t < N) cps.push(t);
        j = t; k--;
      }
      cps.sort((a, b) => a - b);
      if (bic < best.bic) best = { bic, K, cps };
    }
    // Merge weak cuts: require mean jump > noise floor
    const cuts = [0, ...best.cps, N];
    const means = [];
    for (let i = 0; i < cuts.length - 1; i++) {
      let s = 0, c = 0;
      for (let t = cuts[i]; t < cuts[i + 1]; t++) { s += y[t]; c++; }
      means.push(c ? s / c : 0);
    }
    const jumpThr = Math.max(6, noise * (noisy ? 2.2 : 1.4));
    const keepCuts = [];
    for (let i = 1; i < cuts.length - 1; i++) {
      const jump = Math.abs(means[i] - means[i - 1]);
      if (jump >= jumpThr) keepCuts.push(cuts[i]);
    }
    let fracs = keepCuts
      .map((i) => i / (N - 1))
      .filter((f) => f > 0.07 && f < 0.93);
    const merged = [];
    const minGap = noisy ? 0.08 : 0.05;
    fracs.forEach((f) => {
      if (!merged.length || Math.abs(merged[merged.length - 1] - f) > minGap) merged.push(f);
    });
    fracs = merged.slice(0, CFG.MAX_LAYERS);
    // recompute means on kept cuts
    const cuts2 = [0, ...keepCuts, N];
    const means2 = [];
    for (let i = 0; i < cuts2.length - 1; i++) {
      let s = 0, c = 0;
      for (let t = cuts2[i]; t < cuts2[i + 1]; t++) { s += y[t]; c++; }
      means2.push(c ? s / c : 0);
    }
    return {
      fracs,
      K: Math.max(1, fracs.length),
      means: means2.length ? means2 : means,
      bic: best.bic,
      cps: keepCuts,
      noisy,
      jumpThr,
    };
  }

  /** Gradient-peak interfaces along depth — secondary pixel cue. */
  function gradientEdgeFracs(values, maxEdges) {
    const n = values?.length || 0;
    if (n < 8) return [];
    const sm = smooth1d(values, Math.max(1, Math.min(3, Math.floor(n / 20))));
    const g = new Array(n).fill(0);
    for (let i = 1; i < n - 1; i++) g[i] = Math.abs(sm[i + 1] - sm[i - 1]);
    let mean = 0;
    for (let i = 1; i < n - 1; i++) mean += g[i];
    mean /= Math.max(1, n - 2);
    let varr = 0;
    for (let i = 1; i < n - 1; i++) varr += (g[i] - mean) * (g[i] - mean);
    const std = Math.sqrt(varr / Math.max(1, n - 2));
    const prom = Math.max(1.6, mean * 0.45 + std * 0.28);
    const minSep = Math.max(2, Math.floor(n / ((maxEdges || CFG.MAX_LAYERS) * 2.6)));
    const cands = [];
    for (let i = 2; i < n - 2; i++) {
      if (g[i] < prom) continue;
      if (g[i] >= g[i - 1] && g[i] >= g[i + 1]) cands.push({ i, v: g[i] });
    }
    cands.sort((a, b) => b.v - a.v);
    const picked = [];
    for (const cand of cands) {
      if (picked.length >= (maxEdges || CFG.MAX_LAYERS)) break;
      if (picked.some((p) => Math.abs(p - cand.i) < minSep)) continue;
      picked.push(cand.i);
    }
    picked.sort((a, b) => a - b);
    return picked.map((i) => i / (n - 1));
  }

  /**
   * Contiguous intensity runs along ray → spatial cluster boundaries (pixel-based).
   * Does NOT remap by global intensity (avoids flickering label switches).
   */
  function runBoundaryFracs(values, maxEdges) {
    const n = values?.length || 0;
    if (n < 8) return [];
    const sm = smooth1d(values, 2);
    // adaptive threshold: merge if |Δ| small vs local range
    let vmin = sm[0], vmax = sm[0];
    sm.forEach((v) => { if (v < vmin) vmin = v; if (v > vmax) vmax = v; });
    const thr = Math.max(6, (vmax - vmin) * 0.12);
    const labels = new Array(n).fill(0);
    let cur = 0;
    for (let i = 1; i < n; i++) {
      if (Math.abs(sm[i] - sm[i - 1]) > thr) cur++;
      labels[i] = cur;
    }
    // merge tiny runs into neighbors
    const minLen = Math.max(2, Math.floor(n / 18));
    let i = 0;
    while (i < n) {
      let j = i;
      while (j < n && labels[j] === labels[i]) j++;
      if (j - i < minLen && i > 0) {
        for (let k = i; k < j; k++) labels[k] = labels[i - 1];
      }
      i = j;
    }
    return clusterBoundaryFracs(labels, n, maxEdges || CFG.MAX_LAYERS);
  }

  /** Merge two frac lists (pixel evidence), keep strongest unique positions. */
  function mergePixelFracs(a, b, maxEdges) {
    const all = [...(a || []), ...(b || [])].sort((x, y) => x - y);
    const out = [];
    all.forEach((f) => {
      if (!out.length || Math.abs(out[out.length - 1] - f) > 0.05) out.push(f);
      else if (Math.abs(f - 0.5) < Math.abs(out[out.length - 1] - 0.5)) out[out.length - 1] = f;
    });
    return out.slice(0, maxEdges || CFG.MAX_LAYERS);
  }

  /**
   * Wall indices near pick whose wall→lesion direction agrees with the pick ray.
   * Prevents layer curves from wrapping onto far wall segments outside the channel.
   */
  function channelAlignedIndices(g, center, half, minDot) {
    if (!g?.wall_pts?.length || center == null) return [];
    const n = g.wall_pts.length;
    const d0 = g.wall_dirs?.[center];
    if (!d0) return localArcIndices(n, center, half || 6);
    const md = minDot != null ? minDot : 0.72;
    const rem0 = g.wall_dists[center] || 0;
    const H = half != null ? half : 7;
    const out = [];
    for (let k = -H; k <= H; k++) {
      const i = (center + k + n * 20) % n;
      const rem = g.wall_dists[i];
      const d = g.wall_dirs[i];
      if (rem == null || rem < 2.5 || !d) continue;
      if (rem > rem0 * 2.2 + 10 || rem < rem0 * 0.35) continue;
      const dot = d[0] * d0[0] + d[1] * d0[1];
      if (dot < md) continue;
      out.push(i);
    }
    if (out.length >= 2) return out;
    return localArcIndices(n, center, Math.min(4, H)).filter((i) => {
      const rem = g.wall_dists[i];
      const d = g.wall_dirs[i];
      return rem != null && rem >= 2.5 && d && d[0] * d0[0] + d[1] * d0[1] >= 0.4;
    });
  }

  /** Interfaces where adjacent samples switch k-means label (channel layers). */
  function clusterBoundaryFracs(labels, n, maxEdges) {
    if (!labels || labels.length < 4) return [];
    const edges = [];
    for (let i = 1; i < labels.length; i++) {
      if (labels[i] !== labels[i - 1]) edges.push(i / (n - 1));
    }
    const merged = [];
    edges.forEach((f) => {
      if (!merged.length || Math.abs(merged[merged.length - 1] - f) > 0.06) merged.push(f);
    });
    return merged.slice(0, maxEdges || CFG.MAX_LAYERS);
  }

  function consensusFracs(lists, targetN) {
    const nn = Math.max(CFG.MIN_LAYERS, Math.min(CFG.MAX_LAYERS, targetN || CFG.TARGET_LAYERS));
    const slots = Array.from({ length: nn }, () => []);
    lists.forEach((fr) => {
      const sorted = fr.slice().sort((a, b) => a - b);
      for (let s = 0; s < nn; s++) {
        if (!sorted.length) {
          slots[s].push((s + 1) / (nn + 1));
          continue;
        }
        const idx = Math.min(sorted.length - 1, Math.round((s / Math.max(1, nn - 1)) * (sorted.length - 1)));
        slots[s].push(sorted[idx]);
      }
    });
    return slots.map((arr) => {
      arr.sort((a, b) => a - b);
      return Math.max(0.12, Math.min(0.88, arr[Math.floor(arr.length / 2)]));
    });
  }

  /**
   * Sample echo ONLY inside orange→green channel (length = remain).
   * Noise-robust near infiltrate: lateral median strip → 1D median+smooth → noise-aware DP.
   */
  function analyzeEchoRay(imgData, iw, ih, p, dir, thickPx, remain, opts) {
    const o = opts || {};
    const rem = Math.max(4, remain != null ? remain : (thickPx || 20) * 0.5);
    const [ux, uy] = unit(dir[0], dir[1]);
    const [nx, ny] = [-uy, ux];
    const sampleLen = rem;
    const n = Math.max(48, Math.min(140, Math.round(sampleLen * 3.5)));
    const nb = o.nbhd != null ? o.nbhd : 1;
    // Wider lateral for infiltrate noise; use median across strip (not mean)
    const lateral = o.lateral != null ? o.lateral : Math.max(2, Math.min(5, Math.round(3 + (rem < 12 ? 1 : 0))));
    const raw = [];
    for (let i = 0; i < n; i++) {
      const t = (i / (n - 1)) * sampleLen;
      const cx = p[0] + ux * t, cy = p[1] + uy * t;
      const samples = [];
      for (let s = -lateral; s <= lateral; s++) {
        samples.push(sampleGrayNbhd(imgData, iw, ih, cx + nx * s, cy + ny * s, nb));
      }
      raw.push(medianOf(samples));
    }
    const den = denoiseEchoProfile(raw, {
      medWin: o.medWin != null ? o.medWin : (rem < 14 ? 3 : 2),
      smWin: o.smWin != null ? o.smWin : (rem < 14 ? 3 : 2),
    });
    const values = den.values;
    // Hard cap by physical remain: thin infiltrate channel cannot host 4–5 interfaces
    const byRemain = maxEdgesForRemain(rem);
    const maxEdges = Math.max(
      1,
      Math.min(CFG.MAX_LAYERS, o.maxLayers || o.preferLayers || CFG.MAX_LAYERS, byRemain)
    );
    const allowPad = o.allowPad === true;
    // Prefer fewer layers when SNR is poor (infiltrate noise)
    const kCap = den.snr < 5 ? Math.min(maxEdges, 2) : (den.snr < 7 ? Math.min(maxEdges, 3) : maxEdges);

    const dp = optimalChangePointFracs(values, kCap, { noise: den.noise, snr: den.snr });
    const gradFracs = den.snr >= 6 ? gradientEdgeFracs(values, kCap) : [];
    const runFracs = den.snr >= 5.5 ? runBoundaryFracs(values, kCap) : [];
    let edgeFracs = dp.fracs && dp.fracs.length
      ? dp.fracs.slice()
      : mergePixelFracs(gradFracs, runFracs, kCap);
    // Only merge gradient cues when signal is clean enough
    if (edgeFracs.length < CFG.TARGET_LAYERS && den.snr >= 7) {
      edgeFracs = mergePixelFracs(edgeFracs, mergePixelFracs(gradFracs, runFracs, kCap), kCap);
    }
    let pixelEdges = edgeFracs.slice();
    let imaginary = false;
    let stable = edgeFracs.length >= CFG.TARGET_LAYERS && dp.fracs.length >= 2 && den.snr >= 6;

    const cuts = [0, ...(dp.cps || edgeFracs.map((f) => Math.round(f * (n - 1)))), n];
    const uniqCuts = [...new Set(cuts)].sort((a, b) => a - b);
    const labels = new Array(n).fill(0);
    for (let s = 0; s < uniqCuts.length - 1; s++) {
      for (let t = uniqCuts[s]; t < uniqCuts[s + 1]; t++) labels[t] = s;
    }
    const cents = dp.means && dp.means.length ? dp.means.slice() : [];
    if (!cents.length) {
      for (let s = 0; s < uniqCuts.length - 1; s++) {
        let sum = 0, c = 0;
        for (let t = uniqCuts[s]; t < uniqCuts[s + 1]; t++) { sum += values[t]; c++; }
        cents.push(c ? sum / c : 0);
      }
    }
    const km = { labels, cents };

    if (edgeFracs.length < CFG.MIN_LAYERS && allowPad && byRemain >= CFG.MIN_LAYERS) {
      const padded = resolveLayerFracs(values, Math.max(CFG.MIN_LAYERS, kCap));
      edgeFracs = padded.edgeFracs;
      imaginary = true;
      stable = false;
    } else if (edgeFracs.length < 1) {
      imaginary = true;
      stable = false;
    }

    edgeFracs = adaptEdgeFracsToRemain(edgeFracs, rem, { maxEdges: kCap });
    pixelEdges = adaptEdgeFracsToRemain(
      pixelEdges && pixelEdges.length ? pixelEdges : edgeFracs,
      rem,
      { maxEdges: kCap }
    );
    {
      const u = [];
      const minGap = den.snr < 6 ? 0.07 : 0.04;
      edgeFracs.forEach((f) => {
        if (!u.length || Math.abs(u[u.length - 1] - f) > minGap) u.push(f);
      });
      edgeFracs = u.slice(0, kCap);
      pixelEdges = edgeFracs.slice();
    }

    const thick = Math.max(rem, thickPx || rem);
    const occFrac = Math.max(0, Math.min(1.35, (thick - rem) / Math.max(thick, 1e-6)));
    const ratioHint = edgeFracs.length
      ? Math.min(1.05, edgeFracs[Math.min(edgeFracs.length - 1, Math.floor(edgeFracs.length * 0.65))])
      : 0.5;
    return {
      values,
      raw,
      labels: km.labels,
      cents: km.cents,
      edgeFracs,
      pixelEdges,
      gradFracs,
      runFracs,
      dpFracs: dp.fracs,
      dpMeans: dp.means,
      dpK: dp.K,
      noise: den.noise,
      snr: den.snr,
      noisy: !!dp.noisy || den.snr < 5.5,
      thick,
      n,
      sampleLen,
      remain: rem,
      occFrac,
      frontIdx: n - 1,
      reached: edgeFracs.length,
      ratioHint,
      nLayers: edgeFracs.length,
      imaginary,
      stable,
      source: imaginary ? 'imaginary' : 'echo_dp',
      realPeakCount: pixelEdges.length,
    };
  }

  /**
   * 1D k-means keeping spatial contiguity bias: init by depth quantiles (not intensity sort remap).
   */
  function kmeans1dSpatial(values, k, iters) {
    const n = values.length;
    const kk = Math.max(2, Math.min(k || 5, n));
    // init centroids from depth-bin means (preserves wall layer order)
    let cents = [];
    for (let c = 0; c < kk; c++) {
      const a = Math.floor((c / kk) * n);
      const b = Math.floor(((c + 1) / kk) * n);
      let s = 0, cnt = 0;
      for (let i = a; i < b; i++) { s += values[i]; cnt++; }
      cents.push(cnt ? s / cnt : values[Math.min(n - 1, a)]);
    }
    let labels = new Array(n).fill(0);
    for (let it = 0; it < (iters || 12); it++) {
      for (let i = 0; i < n; i++) {
        let best = 0, bd = 1e18;
        for (let c = 0; c < kk; c++) {
          const d = Math.abs(values[i] - cents[c]);
          // slight preference for cluster index near depth fraction
          const depthBias = Math.abs(c / Math.max(1, kk - 1) - i / Math.max(1, n - 1)) * 8;
          const dd = d + depthBias;
          if (dd < bd) { bd = dd; best = c; }
        }
        labels[i] = best;
      }
      // enforce contiguity: majority filter
      const lab2 = labels.slice();
      for (let i = 1; i < n - 1; i++) {
        if (labels[i - 1] === labels[i + 1] && labels[i] !== labels[i - 1]) lab2[i] = labels[i - 1];
      }
      labels = lab2;
      const sum = new Array(kk).fill(0), cnt = new Array(kk).fill(0);
      for (let i = 0; i < n; i++) { sum[labels[i]] += values[i]; cnt[labels[i]]++; }
      for (let c = 0; c < kk; c++) if (cnt[c]) cents[c] = sum[c] / cnt[c];
    }
    return { labels, cents };
  }

  /**
   * Multi-ray channel clustering around pick → consensus **pixel** edge fracs.
   * Near infiltrate (thin / noisy): median-fuse neighboring rays OR extend from clearer adjacent wall.
   */
  function analyzeChannelNeighborhood(imgData, iw, ih, g, center, half, opts) {
    const o = opts || {};
    const maxLayers = Math.max(
      CFG.MIN_LAYERS,
      Math.min(CFG.MAX_LAYERS, o.maxLayers || o.preferLayers || CFG.MAX_LAYERS)
    );
    const rayOpts = {
      maxLayers,
      allowPad: false,
      nbhd: o.nbhd != null ? o.nbhd : 1,
      lateral: o.lateral != null ? o.lateral : 3,
    };
    const rem0 = g.wall_dists[center] || 0;
    const H = half != null ? half : 8;
    const idxs = channelAlignedIndices(g, center, H, 0.68);
    const centerIdx = idxs.includes(center) ? center : (idxs[Math.floor(idxs.length / 2)] ?? center);

    // Collect per-ray analyses; skip ultra-thin remain (pure noise / destroyed)
    const rayAnas = [];
    let centerAnalysis = null;
    idxs.forEach((i) => {
      const rem = g.wall_dists[i];
      if (rem == null || rem < 5) return;
      const a = analyzeEchoRay(imgData, iw, ih, g.wall_pts[i], g.wall_dirs[i], rem, rem, rayOpts);
      if (!a) return;
      const w = Math.max(0.2, (a.snr || 1) * Math.sqrt(rem));
      rayAnas.push({ i, a, rem, w, edges: a.pixelEdges?.length ? a.pixelEdges : a.edgeFracs });
      if (i === centerIdx) centerAnalysis = a;
    });
    if (!centerAnalysis) {
      const rem = Math.max(5, rem0);
      centerAnalysis = analyzeEchoRay(
        imgData, iw, ih, g.wall_pts[center], g.wall_dirs[center], rem, rem, rayOpts
      );
    }

    // Build multi-ray median profile (same sample count) from clearer rays — kills infiltrate speckle
    let fusedProfile = null;
    const usable = rayAnas.filter((r) => r.rem >= 8 && (r.a.snr || 0) >= 4.5 && r.a.values?.length >= 24);
    if (usable.length >= 3) {
      const nRef = usable.reduce((s, r) => s + r.a.values.length, 0) / usable.length | 0;
      const nF = Math.max(40, Math.min(120, nRef));
      const stack = Array.from({ length: nF }, () => []);
      usable.forEach((r) => {
        const v = r.a.values;
        for (let k = 0; k < nF; k++) {
          const t = k / (nF - 1);
          const j = Math.min(v.length - 1, Math.round(t * (v.length - 1)));
          stack[k].push(v[j]);
        }
      });
      const fusedRaw = stack.map((col) => medianOf(col));
      const den = denoiseEchoProfile(fusedRaw, { medWin: 2, smWin: 2 });
      const kCap = den.snr < 5.5 ? Math.min(maxLayers, 3) : maxLayers;
      const dp = optimalChangePointFracs(den.values, kCap, { noise: den.noise, snr: den.snr });
      fusedProfile = { values: den.values, edges: dp.fracs, snr: den.snr, noise: den.noise, dp };
    }

    let edgeFracs = (centerAnalysis.pixelEdges?.length
      ? centerAnalysis.pixelEdges
      : centerAnalysis.edgeFracs) || [];
    let imaginary = !!centerAnalysis.imaginary || rem0 < 5;
    let source = imaginary ? 'imaginary' : (centerAnalysis.source || 'echo_dp');
    let fromIdx = center;
    let stable = !!centerAnalysis.stable && !imaginary && edgeFracs.length >= 2;
    const localNoisy = !!(centerAnalysis.noisy || (centerAnalysis.snr != null && centerAnalysis.snr < 5.5) || rem0 < 10);

    // Prefer fused multi-ray median edges when local is noisy
    if (fusedProfile?.edges?.length >= 2 && (localNoisy || edgeFracs.length < 2)) {
      edgeFracs = fusedProfile.edges.slice();
      source = 'echo_fused';
      imaginary = false;
      stable = fusedProfile.snr >= 6 && edgeFracs.length >= 2;
      centerAnalysis.values = fusedProfile.values;
      centerAnalysis.noise = fusedProfile.noise;
      centerAnalysis.snr = fusedProfile.snr;
      // rebuild soft labels for profile
      const n = fusedProfile.values.length;
      const cps = fusedProfile.dp.cps || edgeFracs.map((f) => Math.round(f * (n - 1)));
      const cuts = [0, ...cps, n];
      const labels = new Array(n).fill(0);
      for (let s = 0; s < cuts.length - 1; s++) {
        for (let t = cuts[s]; t < cuts[s + 1]; t++) if (t < n) labels[t] = s;
      }
      centerAnalysis.labels = labels;
      centerAnalysis.cents = fusedProfile.dp.means || [];
    } else if (rayAnas.length >= 2) {
      // SNR-weighted consensus of edge fracs
      const lists = rayAnas.filter((r) => r.edges?.length >= 2).map((r) => r.edges);
      if (lists.length >= 2) {
        const avgN = Math.round(lists.reduce((s, f) => s + f.length, 0) / lists.length);
        const targetN = Math.max(CFG.MIN_LAYERS, Math.min(maxLayers, localNoisy ? Math.min(avgN, 3) : avgN));
        edgeFracs = consensusFracs(lists, targetN);
        source = 'echo_dp';
        imaginary = false;
        stable = !localNoisy && edgeFracs.length >= CFG.TARGET_LAYERS;
      }
    }

    // Adjacent clear wall when still thin / noisy / few edges
    const clarity = echoClarityScore({ ...centerAnalysis, edgeFracs });
    const needExtend = o.skipExtend
      ? false
      : (rem0 < 10 || localNoisy || (centerAnalysis.realPeakCount || edgeFracs.length) < 2 || clarity < 4.5);
    if (needExtend) {
      const adj = findAdjacentLayeredWall(imgData, iw, ih, g, center, {
        searchHalf: o.searchHalf != null ? o.searchHalf : CFG.SEARCH_HALF,
        minLayers: 2,
        maxAngleDeg: o.maxAngleDeg != null ? o.maxAngleDeg : 55,
        kClusters: maxLayers,
        nbhd: rayOpts.nbhd,
        lateral: Math.max(3, rayOpts.lateral),
      });
      if (adj && (rem0 < 10 || !fusedProfile || (adj.analysis?.snr || 0) > (fusedProfile.snr || 0) + 0.8)) {
        const ext = extendLayersAlongChannel(g, center, adj, adj.nLayers || maxLayers);
        edgeFracs = ext.edgeFracs;
        imaginary = ext.imaginary;
        source = ext.source;
        fromIdx = ext.fromIdx;
        stable = ext.stable;
        centerAnalysis.adjacent = adj;
        if (adj.analysis?.values) {
          centerAnalysis.values = adj.analysis.values;
          centerAnalysis.labels = adj.analysis.labels;
          centerAnalysis.cents = adj.analysis.cents;
          centerAnalysis.gradFracs = adj.analysis.gradFracs;
          centerAnalysis.pixelEdges = adj.analysis.pixelEdges;
          centerAnalysis.snr = adj.analysis.snr;
          centerAnalysis.noise = adj.analysis.noise;
        }
      } else if (!edgeFracs.length) {
        const geoAdj = findAdjacentClearIdx(g, center);
        const remA = g.wall_dists[geoAdj];
        if (remA >= 8) {
          const aAdj = analyzeEchoRay(
            imgData, iw, ih, g.wall_pts[geoAdj], g.wall_dirs[geoAdj], remA, remA, rayOpts
          );
          const ext = extendLayersAlongChannel(g, center, { idx: geoAdj, analysis: aAdj, nLayers: aAdj.edgeFracs.length }, maxLayers);
          edgeFracs = ext.edgeFracs;
          imaginary = ext.imaginary;
          source = ext.source;
          fromIdx = ext.fromIdx;
        }
      }
    }
    if (!edgeFracs.length) {
      const nEq = Math.max(1, Math.min(CFG.TARGET_LAYERS, maxEdgesForRemain(Math.max(rem0, 8))));
      edgeFracs = equalFracs(nEq).map((f) => Math.max(0.15, Math.min(0.85, f)));
      imaginary = true;
      source = 'imaginary';
    }
    // Critical: thin remain at infiltrate cannot host 4–5 interfaces from fused/adjacent profiles
    const adaptRem =
      fromIdx === center
        ? Math.max(1, rem0)
        : Math.max(1, g.wall_dists[fromIdx] || rem0);
    edgeFracs = adaptEdgeFracsToRemain(edgeFracs, adaptRem);
    if (!edgeFracs.length) {
      edgeFracs = adaptEdgeFracsToRemain(
        equalFracs(Math.max(1, maxEdgesForRemain(adaptRem))),
        adaptRem
      );
      imaginary = true;
      source = source || 'imaginary';
    }
    centerAnalysis.edgeFracs = edgeFracs;
    centerAnalysis.pixelEdges = edgeFracs.slice();
    centerAnalysis.imaginary = imaginary;
    centerAnalysis.source = source;
    centerAnalysis.alignedCount = idxs.length;
    centerAnalysis.nLayers = edgeFracs.length;
    // Keep draw center near pick; fromIdx may still record echo source
    centerAnalysis.fromIdx = layerDrawCenter(g, center, fromIdx);
    centerAnalysis.sourceIdx = fromIdx;
    centerAnalysis.stable = stable;
    centerAnalysis.clarity = clarity;
    centerAnalysis.localNoisy = localNoisy;
    centerAnalysis.fused = !!fusedProfile;
    return centerAnalysis;
  }

  /**
   * Layer fills + clear interface curves inside orange→green channel strip.
   * Depth = edgeFrac × local remain. Visible clustering for doctor reading.
   * (Does not touch the yellow AI-deepest hint marker.)
   */
  function channelLayerCurvesSvg(g, center, edgeFracs, opts = {}) {
    try {
      if (!g?.wall_pts || center == null) return '';
      const half = opts.half != null ? opts.half : 8;
      const cpt = g.wall_pts[center];
      const maxSpanPx = opts.maxSpanPx != null ? opts.maxSpanPx : 56;
      let idxs = channelAlignedIndices(
        g,
        center,
        half,
        opts.minDot != null ? opts.minDot : 0.6
      ).filter((i) => {
        if ((g.wall_dists[i] || 0) < 2.5) return false;
        if (!cpt || !g.wall_pts[i]) return false;
        // Keep arcs local — avoid wrapping around lesion to a far pocket
        return Math.hypot(g.wall_pts[i][0] - cpt[0], g.wall_pts[i][1] - cpt[1]) <= maxSpanPx;
      });
      if (idxs.length < 2) {
        const n = g.wall_pts.length;
        const wide = [];
        for (let k = -Math.min(8, half + 2); k <= Math.min(8, half + 2); k++) {
          const i = (center + k + n * 20) % n;
          if ((g.wall_dists[i] || 0) < 3 || !g.wall_pts[i] || !cpt) continue;
          if (Math.hypot(g.wall_pts[i][0] - cpt[0], g.wall_pts[i][1] - cpt[1]) > maxSpanPx) continue;
          wide.push(i);
        }
        if (wide.length < 2) return '';
        idxs = wide;
      }
      let fracs = edgeFracs && edgeFracs.length
        ? edgeFracs.slice().sort((a, b) => a - b).slice(0, CFG.MAX_LAYERS)
        : null;
      if (!fracs || !fracs.length) return '';
      const centerRem = (g.wall_dists[center] != null) ? g.wall_dists[center] : 12;
      fracs = adaptEdgeFracsToRemain(fracs, centerRem);
      if (!fracs.length) return '';
      fracs = fracs.map((f) => Math.max(0.06, Math.min(0.94, f)));
      const dashed = !!(opts.dashed || opts.imaginary);
      // Always use distinct clinical hues (dash = imaginary; color = layer id)
      const { bandCols, lineCols } = layerColorsForFracs(fracs);
      const showBands = opts.showBands !== false;
      const bandAlpha = showBands ? (opts.bandOpacity != null ? opts.bandOpacity : 0.30) : 0;
      const showLines = opts.showLines !== false;
      const lineOp = opts.opacity != null ? opts.opacity : 0.95;
      const swBase = opts.pxStroke != null ? opts.pxStroke : Math.max(0.7, CFG.GUIDE_STROKE * 1.35);
      const dashAttr = dashed ? ` stroke-dasharray="${(swBase * 3.2).toFixed(1)} ${(swBase * 2.2).toFixed(1)}"` : '';
      const uid = `L${center}_${fracs.length}_${Math.round((fracs[0] || 0) * 1000)}_${dashed ? 'd' : 's'}`;
      let html = `<defs>`;
      const bandFracs = [0, ...fracs, 1];
      if (bandAlpha > 0.01) {
        for (let b = 0; b < bandFracs.length - 1; b++) {
          const c0 = bandCols[b % bandCols.length] || LAYER_BAND_COLS[b % LAYER_BAND_COLS.length];
          html += `<linearGradient id="lg${uid}_${b}" gradientUnits="objectBoundingBox" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${c0}" stop-opacity="${(bandAlpha * 0.55).toFixed(3)}"/>
            <stop offset="100%" stop-color="${c0}" stop-opacity="${bandAlpha.toFixed(3)}"/>
          </linearGradient>`;
        }
      }
      html += `</defs>`;
      if (bandAlpha > 0.01) {
        for (let b = 0; b < bandFracs.length - 1; b++) {
          const f0 = bandFracs[b], f1 = bandFracs[b + 1];
          if (f1 - f0 < 0.015) continue;
          const outer = [], inner = [];
          idxs.forEach((i) => {
            const w = g.wall_pts[i];
            const rem = g.wall_dists[i];
            const d = g.wall_dirs[i];
            if (!w || rem == null || !d) return;
            outer.push([w[0] + d[0] * rem * f0, w[1] + d[1] * rem * f0]);
            inner.push([w[0] + d[0] * rem * f1, w[1] + d[1] * rem * f1]);
          });
          if (outer.length < 2) continue;
          const ring = outer.concat(inner.slice().reverse());
          html += `<path d="${smoothPath(ring, true)}" fill="url(#lg${uid}_${b})" stroke="none"/>`;
        }
      }
      if (showLines) {
        fracs.forEach((f, fi) => {
          const pts = [];
          idxs.forEach((i) => {
            const w = g.wall_pts[i];
            const rem = g.wall_dists[i];
            const d = g.wall_dirs[i];
            if (!w || rem == null || rem < 2.5 || !d) return;
            pts.push([w[0] + d[0] * rem * f, w[1] + d[1] * rem * f]);
          });
          if (pts.length < 2) return;
          const col = lineCols[fi] || LAYER_LINE_COLS[fi % LAYER_LINE_COLS.length];
          const sw = swBase * (fi === 0 || fi === fracs.length - 1 ? 1.2 : 1);
          html += `<path d="${smoothPath(pts, false)}" fill="none" stroke="#0f172a" stroke-width="${(sw * 2.0).toFixed(2)}" opacity="0.4" stroke-linecap="round"${dashAttr}/>`;
          html += `<path d="${smoothPath(pts, false)}" fill="none" stroke="${col}" stroke-width="${sw.toFixed(2)}" opacity="${lineOp}" stroke-linecap="round"${dashAttr}/>`;
        });
      }
      return html;
    } catch (_) {
      return '';
    }
  }

  /**
   * Hairline interface ticks on the wall→lesion ray (colored per layer).
   * Uses exact remain — never pad beyond orange→green channel.
   */
  function channelStripOverlaySvg(p, lp, edgeFracs, rem, opts = {}) {
    if (!p || !lp || !edgeFracs?.length) return '';
    const [ux, uy] = unit(lp[0] - p[0], lp[1] - p[1]);
    const [nx, ny] = [-uy, ux];
    const R = Math.max(2.5, rem || 0);
    const half = opts.halfWidth != null
      ? opts.halfWidth
      : Math.max(2.2, Math.min(6.5, R * 0.22));
    const fracs = adaptEdgeFracsToRemain(edgeFracs, R, {
      maxEdges: opts.maxEdges != null ? opts.maxEdges : maxEdgesForRemain(R),
    });
    if (!fracs.length) return '';
    const dashed = !!(opts.dashed || opts.imaginary);
    const { bandCols, lineCols } = layerColorsForFracs(fracs);
    const showBands = opts.showBands !== false;
    const showLines = opts.showLines !== false;
    const bandAlpha = showBands ? (opts.bandOpacity != null ? opts.bandOpacity : 0.22) : 0;
    const bandFracs = [0, ...fracs, 1];
    const sw = opts.pxStroke != null ? opts.pxStroke : Math.max(0.45, Math.min(1.1, R * 0.07));
    let html = '';
    if (bandAlpha > 0.01) {
      for (let b = 0; b < bandFracs.length - 1; b++) {
        const f0 = bandFracs[b], f1 = bandFracs[b + 1];
        if (f1 - f0 < 0.02) continue;
        const col = bandCols[b] || LAYER_BAND_COLS[b % LAYER_BAND_COLS.length];
        const a = [p[0] + ux * R * f0 - nx * half, p[1] + uy * R * f0 - ny * half];
        const b1 = [p[0] + ux * R * f0 + nx * half, p[1] + uy * R * f0 + ny * half];
        const c = [p[0] + ux * R * f1 + nx * half, p[1] + uy * R * f1 + ny * half];
        const d = [p[0] + ux * R * f1 - nx * half, p[1] + uy * R * f1 - ny * half];
        html += `<path d="M${a[0].toFixed(1)},${a[1].toFixed(1)} L${b1[0].toFixed(1)},${b1[1].toFixed(1)} L${c[0].toFixed(1)},${c[1].toFixed(1)} L${d[0].toFixed(1)},${d[1].toFixed(1)} Z" fill="${col}" opacity="${bandAlpha}" stroke="none"/>`;
      }
    }
    if (showLines) {
      const dash = dashed ? ` stroke-dasharray="${(sw * 3).toFixed(1)} ${(sw * 2).toFixed(1)}"` : '';
      fracs.forEach((f, fi) => {
        const col = lineCols[fi] || LAYER_LINE_COLS[fi % LAYER_LINE_COLS.length];
        const x0 = p[0] + ux * R * f - nx * half;
        const y0 = p[1] + uy * R * f - ny * half;
        const x1 = p[0] + ux * R * f + nx * half;
        const y1 = p[1] + uy * R * f + ny * half;
        html += `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" stroke="#0f172a" stroke-width="${(sw * 1.8).toFixed(2)}" opacity=".35"${dash}/>`;
        html += `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" stroke="${col}" stroke-width="${sw.toFixed(2)}" opacity=".95"${dash}/>`;
      });
    }
    return html;
  }

  /** Echo intensity curve + cluster coloring. Axis: lumen → serosa; pink = lesion front. */
  function echoClusterSvg(analysis, w, h) {
    if (!analysis || !analysis.values) return '';
    w = w || 280; h = h || 96;
    const vals = analysis.values;
    const n = vals.length;
    const padL = 8, padR = 8, padT = 10, padB = 22;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;
    const vmin = Math.min(...vals), vmax = Math.max(...vals);
    const span = Math.max(1, vmax - vmin);
    const dashed = !!(analysis.imaginary || analysis.source === 'channel_extend');
    const cols = dashed
      ? ['#fdba74', '#fbbf24', '#fcd34d', '#fb923c', '#f59e0b']
      : ['#38bdf8', '#818cf8', '#22d3ee', '#a78bfa', '#34d399'];
    let bands = '';
    for (let i = 0; i < n - 1; i++) {
      const x0 = padL + (i / (n - 1)) * plotW;
      const x1 = padL + ((i + 1) / (n - 1)) * plotW;
      const c = cols[(analysis.labels[i] || 0) % cols.length];
      bands += `<rect x="${x0.toFixed(1)}" y="${padT}" width="${Math.max(1, x1 - x0).toFixed(1)}" height="${plotH}" fill="${c}" opacity=".32"/>`;
    }
    let edges = '';
    const edgeList = (analysis.pixelEdges && analysis.pixelEdges.length)
      ? analysis.pixelEdges
      : (analysis.dpFracs && analysis.dpFracs.length ? analysis.dpFracs : (analysis.edgeFracs || []));
    const dash = dashed ? ' stroke-dasharray="3 2"' : '';
    edgeList.forEach((f) => {
      const x = padL + f * plotW;
      edges += `<line x1="${x.toFixed(1)}" y1="${padT}" x2="${x.toFixed(1)}" y2="${padT + plotH}" stroke="#0f172a" stroke-width="2.2" opacity=".35"${dash}/>`;
      edges += `<line x1="${x.toFixed(1)}" y1="${padT}" x2="${x.toFixed(1)}" y2="${padT + plotH}" stroke="${dashed ? '#fde68a' : '#f8fafc'}" stroke-width="1.3" opacity=".95"${dash}/>`;
    });
    // curve
    let d = '';
    vals.forEach((v, i) => {
      const x = padL + (i / (n - 1)) * plotW;
      const y = padT + plotH * (1 - (v - vmin) / span);
      d += (i ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1);
    });
    // lesion front marker
    const fx = padL + Math.min(1, analysis.occFrac || 0) * plotW;
    const front = `<line x1="${fx.toFixed(1)}" y1="${padT}" x2="${fx.toFixed(1)}" y2="${padT + plotH}" stroke="#fb7185" stroke-width="2.2"/>`;
    const axisY = padT + plotH + 12;
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" xmlns="http://www.w3.org/2000/svg" style="display:block;background:#000;border:1px solid #222;border-radius:6px">
      ${bands}${edges}
      <path d="${d}" fill="none" stroke="#e2e8f0" stroke-width="1.8"/>
      ${front}
      <circle cx="${fx.toFixed(1)}" cy="${(padT + plotH * 0.5).toFixed(1)}" r="2" fill="#fb7185" stroke="#fff" stroke-width="0.8"/>
      <text x="${padL}" y="${axisY}" fill="#64748b" font-size="9">Lumen</text>
      <text x="${padL + plotW}" y="${axisY}" fill="#64748b" font-size="9" text-anchor="end">Serosa</text>
      <text x="${fx.toFixed(1)}" y="${Math.max(padT + 9, axisY - 14)}" fill="#fb7185" font-size="9" text-anchor="middle">Lesion front</text>
    </svg>`;
  }

  /** Load image URL / dataURL → ImageData (async). */
  function loadImageData(url) {
    return new Promise((resolve) => {
      if (!url) { resolve(null); return; }
      const finish = (img) => {
        try {
          const w = img.naturalWidth || img.width;
          const h = img.naturalHeight || img.height;
          const c = document.createElement('canvas');
          c.width = w; c.height = h;
          const ctx = c.getContext('2d', { willReadFrequently: true });
          ctx.drawImage(img, 0, 0);
          resolve({ data: ctx.getImageData(0, 0, w, h), w, h });
        } catch (_) { resolve(null); }
      };
      // Prefer createImageBitmap when available (faster decode / less main-thread jank)
      if (typeof createImageBitmap === 'function' && typeof fetch === 'function') {
        fetch(url, { credentials: 'same-origin', cache: 'force-cache' })
          .then((r) => (r.ok ? r.blob() : Promise.reject()))
          .then((blob) => createImageBitmap(blob))
          .then((bmp) => {
            try {
              const c = document.createElement('canvas');
              c.width = bmp.width; c.height = bmp.height;
              const ctx = c.getContext('2d', { willReadFrequently: true });
              ctx.drawImage(bmp, 0, 0);
              const data = ctx.getImageData(0, 0, bmp.width, bmp.height);
              if (bmp.close) bmp.close();
              resolve({ data, w: bmp.width, h: bmp.height });
            } catch (_) { resolve(null); }
          })
          .catch(() => {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => finish(img);
            img.onerror = () => resolve(null);
            img.src = url;
          });
        return;
      }
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => finish(img);
      img.onerror = () => resolve(null);
      img.src = url;
    });
  }

  global.ContactGeom = {
    CFG,
    ptsPath,
    smoothPath,
    unit,
    bandPath,
    computeGeometry,
    contactRatioByLength,
    localWallThickness,
    penetrationAt,
    formatPenPct,
    layerJudgment,
    LAYER_TABLE,
    LAYER_BAND_COLS,
    LAYER_LINE_COLS,
    layerAtFrac,
    clinicalBandLabels,
    layerColorsForFracs,
    layerDrawCenter,
    wallIdxDist,
    layerSourceInfo,
    wallStackSvg,
    maxEdgesForRemain,
    adaptEdgeFracsToRemain,
    softDeform,
    controlIndices,
    contactStatus,
    isContactPoint,
    pointInPoly,
    findInfiltrationFromClick,
    equalFracs,
    channelEqualFracs,
    resolveLayerFracs,
    findAdjacentClearIdx,
    findAdjacentLayeredWall,
    extendLayersAlongChannel,
    echoClarityScore,
    polyCentroid,
    optimalChangePointFracs,
    denoiseEchoProfile,
    median1d,
    buildLayerPlan,
    wallNormalAt,
    zoomUserStroke,
    overviewInsetSvg,
    quartileGuidesSvg,
    localArcIndices,
    contactArcPath,
    thicknessBand,
    thicknessRulerSvg,
    remainProfileSvg,
    wallLayerArcsSvg,
    channelAlignedIndices,
    channelLayerCurvesSvg,
    channelStripOverlaySvg,
    analyzeChannelNeighborhood,
    clusterBoundaryFracs,
    analyzeEchoRay,
    echoClusterSvg,
    loadImageData,
    gradientEdgeFracs,
  };
})(typeof window !== 'undefined' ? window : globalThis);
