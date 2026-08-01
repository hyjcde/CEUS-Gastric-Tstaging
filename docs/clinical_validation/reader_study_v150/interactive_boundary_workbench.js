(function () {
  'use strict';

  const SECTOR_DEFS = [
    { id: 'outer', label: '浆膜外缘', short: '外', note: 'T3/T4+ 关键 · 浆膜侧突破', accent: '#fbbf24' },
    { id: 'cranial', label: '头侧', short: '头', note: '头侧壁层层次', accent: '#67d4ff' },
    { id: 'caudal', label: '足侧', short: '足', note: '足侧壁层层次', accent: '#67d4ff' },
    { id: 'luminal', label: '腔侧', short: '腔', note: '对照正常胃壁', accent: '#5ce3a1' },
    { id: 'deep', label: '深部', short: '深', note: '局部最厚/最深侵犯', accent: '#c084fc' },
    { id: 'curvature', label: '高曲率', short: '曲', note: '轮廓不规则 · 突破可疑', accent: '#f87171' },
    { id: 'custom', label: '自定义', short: '自', note: '在边界模式点击分割轮廓边缘', accent: '#e2e8f0' },
  ];

  const ADJ_OPTIONS = [
    { id: 'continuous', label: '连续', cls: 'adj-ok' },
    { id: 'suspicious', label: '可疑', cls: 'adj-warn' },
    { id: 'breakthrough', label: '明确突破', cls: 'adj-danger' },
    { id: 'indeterminate', label: '无法判断', cls: 'adj-muted' },
  ];

  const PATCH_SRC = 88;
  const DEFAULT_ZOOM = 8;
  const PX_PER_MM = 2.4;
  // 解剖方向（头/足侧等）需结合扫查方向校准；暂关，先保证 mask 清晰可见。
  const DIRECTION_ANNOTATIONS_ENABLED = false;

  let ctxRef = null;

  function extendState(state) {
    Object.assign(state, {
      boundarySectors: [],
      selectedBoundaryId: 'outer',
      boundaryAdjudications: {},
      boundaryLockTrack: true,
      boundaryDetailZoom: DEFAULT_ZOOM,
      boundaryGuides: {
        contour: true,
        normal: true,
        serosa: true,
        breakthrough: true,
        normalWall: true,
      },
      customBoundaryIdx: null,
      boundaryFrameCache: null,
      boundaryUserPickedDirection: false,
      directionAnnotationsEnabled: DIRECTION_ANNOTATIONS_ENABLED,
    });
  }

  function pointInPolygon(points, x, y) {
    let inside = false;
    for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
      const xi = points[i][0];
      const yi = points[i][1];
      const xj = points[j][0];
      const yj = points[j][1];
      const intersect = ((yi > y) !== (yj > y))
        && (x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-9) + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  function rayWallThicknessPx(points, idx, c, steps) {
    const p = points[idx];
    const { nx, ny } = pointNormalOutward(points, idx, c);
    let inward = 0;
    for (let s = 1; s <= steps; s += 1) {
      const x = p[0] - nx * s;
      const y = p[1] - ny * s;
      if (!pointInPolygon(points, x, y)) break;
      inward = s;
    }
    let outward = 0;
    for (let s = 1; s <= Math.floor(steps / 3); s += 1) {
      const x = p[0] + nx * s;
      const y = p[1] + ny * s;
      if (pointInPolygon(points, x, y)) outward = s;
      else break;
    }
    return inward + outward;
  }

  function pickDeepIdx(points, c) {
    let bestIdx = 0;
    let bestTh = -1;
    const step = Math.max(1, Math.floor(points.length / 48));
    for (let idx = 0; idx < points.length; idx += step) {
      const th = rayWallThicknessPx(points, idx, c, 48);
      if (th > bestTh) {
        bestTh = th;
        bestIdx = idx;
      }
    }
    return bestIdx;
  }

  function getCachedFrame(state, video) {
    const t = video.currentTime;
    const cache = state.boundaryFrameCache;
    if (cache && Math.abs(cache.time - t) < 0.001 && cache.canvas) {
      return cache;
    }
    const cap = captureVideoFrame(video);
    state.boundaryFrameCache = { time: t, canvas: cap.canvas, vw: cap.vw, vh: cap.vh };
    return state.boundaryFrameCache;
  }

  function invalidateFrameCache(state) {
    state.boundaryFrameCache = null;
  }

  function el(id) {
    return document.getElementById(id);
  }

  function polygonImagePoints(normPoly, video) {
    const vw = video.videoWidth || 1;
    const vh = video.videoHeight || 1;
    if (!Array.isArray(normPoly)) return [];
    const points = normPoly
      .filter((point) => Array.isArray(point) && point.length >= 2)
      .map((point) => [Number(point[0]), Number(point[1])])
      .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
    const maxX = Math.max(...points.map(([x]) => Math.abs(x)), 0);
    const maxY = Math.max(...points.map(([, y]) => Math.abs(y)), 0);
    const pixelSpace = maxX > 1.5 || maxY > 1.5;
    return points.map(([x, y]) => [
      pixelSpace ? (x / vw) * vw : x * vw,
      pixelSpace ? (y / vh) * vh : y * vh,
    ]);
  }

  function polygonCentroid(points) {
    if (!points.length) return { x: 0, y: 0 };
    const x = points.reduce((s, p) => s + p[0], 0) / points.length;
    const y = points.reduce((s, p) => s + p[1], 0) / points.length;
    return { x, y };
  }

  function pointNormalOutward(points, idx, c) {
    const n = points.length;
    const prev = points[(idx - 1 + n) % n];
    const curr = points[idx];
    const next = points[(idx + 1) % n];
    const tx = next[0] - prev[0];
    const ty = next[1] - prev[1];
    const len = Math.hypot(tx, ty) || 1;
    let nx = -ty / len;
    let ny = tx / len;
    const mx = curr[0] - c.x;
    const my = curr[1] - c.y;
    if (nx * mx + ny * my < 0) {
      nx = -nx;
      ny = -ny;
    }
    return { nx, ny };
  }

  function curvatureAt(points, idx) {
    const n = points.length;
    const p0 = points[(idx - 1 + n) % n];
    const p1 = points[idx];
    const p2 = points[(idx + 1) % n];
    const a = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]);
    const b = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
    const c = Math.hypot(p2[0] - p0[0], p2[1] - p0[1]);
    if (a * b * c === 0) return 0;
    const area2 = Math.abs((p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0]));
    return (4 * area2) / (a * b * c);
  }

  function pickIdx(points, c, mode) {
    let bestIdx = 0;
    let bestVal = mode.startsWith('min') ? Infinity : -Infinity;
    points.forEach((p, idx) => {
      let v;
      if (mode === 'max_dist') v = Math.hypot(p[0] - c.x, p[1] - c.y);
      else if (mode === 'min_dist') v = Math.hypot(p[0] - c.x, p[1] - c.y);
      else if (mode === 'min_y') v = p[1];
      else if (mode === 'max_y') v = p[1];
      else if (mode === 'max_curv') v = curvatureAt(points, idx);
      else if (mode === 'max_thick') {
        const inward = Math.hypot(p[0] - c.x, p[1] - c.y);
        v = inward;
      }
      else v = 0;
      const better = mode.startsWith('min') ? v < bestVal : v > bestVal;
      if (better) {
        bestVal = v;
        bestIdx = idx;
      }
    });
    return bestIdx;
  }

  function arcIndices(points, idx, span) {
    const n = points.length;
    const half = Math.max(2, Math.floor(span / 2));
    const out = [];
    for (let i = -half; i <= half; i += 1) {
      out.push((idx + i + n) % n);
    }
    return out;
  }

  function estimateMetrics(sectorId, points, idx, c, caseId, luminalWallPx) {
    const thicknessPx = rayWallThicknessPx(points, idx, c, 56);
    const wallMm = +(Math.max(1.5, thicknessPx / PX_PER_MM).toFixed(1));
    const normalMm = luminalWallPx != null
      ? +(Math.max(2.2, luminalWallPx / PX_PER_MM).toFixed(1))
      : +(Math.max(2.5, wallMm * 0.42 + 1.1).toFixed(1));
    const ratio = +(wallMm / normalMm).toFixed(2);
    const curv = curvatureAt(points, idx);
    let risk = 0.15 + Math.min(0.42, curv * 3.2) + Math.max(0, ratio - 1.35) * 0.28;
    if (sectorId === 'outer' || sectorId === 'curvature') risk += 0.14;
    if (sectorId === 'deep') risk += 0.08;
    if (sectorId === 'luminal') risk *= 0.45;
    risk = Math.min(0.96, Math.max(0.06, risk));
    return { wallMm, normalMm, ratio, breakthroughRisk: risk, curvature: curv, thicknessPx };
  }

  function buildWallProfile(points, sector, steps) {
    const profile = [];
    const span = 28;
    for (let i = 0; i <= steps; i += 1) {
      const t = i / steps;
      const d = span * (t - 0.35);
      const x = sector.x + sector.nx * d;
      const y = sector.y + sector.ny * d;
      profile.push({ t, inside: pointInPolygon(points, x, y) });
    }
    return profile;
  }

  function buildBoundarySectors(normPoly, video, caseId, customIdx) {
    const points = polygonImagePoints(normPoly, video);
    if (points.length < 6) return [];
    const c = polygonCentroid(points);
    const picks = {
      outer: pickIdx(points, c, 'max_dist'),
      cranial: pickIdx(points, c, 'min_y'),
      caudal: pickIdx(points, c, 'max_y'),
      luminal: pickIdx(points, c, 'min_dist'),
      deep: pickDeepIdx(points, c),
      curvature: pickIdx(points, c, 'max_curv'),
    };
    const luminalThPx = rayWallThicknessPx(points, picks.luminal, c, 40);
    const used = new Set();
    const sectors = SECTOR_DEFS.filter((d) => d.id !== 'custom').map((def) => {
      let idx = picks[def.id];
      if (used.has(idx)) {
        idx = (idx + Math.ceil(points.length / 6)) % points.length;
      }
      used.add(idx);
      const p = points[idx];
      const normal = pointNormalOutward(points, idx, c);
      const metrics = estimateMetrics(def.id, points, idx, c, caseId, luminalThPx);
      return {
        ...def,
        x: p[0],
        y: p[1],
        idx,
        nx: normal.nx,
        ny: normal.ny,
        arcIdx: arcIndices(points, idx, 18),
        ...metrics,
      };
    });
    if (customIdx != null && customIdx >= 0 && customIdx < points.length) {
      const def = SECTOR_DEFS.find((d) => d.id === 'custom');
      const p = points[customIdx];
      const normal = pointNormalOutward(points, customIdx, c);
      const metrics = estimateMetrics('custom', points, customIdx, c, caseId, luminalThPx);
      sectors.push({
        ...def,
        x: p[0],
        y: p[1],
        idx: customIdx,
        nx: normal.nx,
        ny: normal.ny,
        arcIdx: arcIndices(points, customIdx, 18),
        ...metrics,
      });
    }
    return sectors;
  }

  function nearestBoundaryIdx(normPoly, video, ix, iy) {
    const points = polygonImagePoints(normPoly, video);
    let best = 0;
    let bestD = Infinity;
    points.forEach((p, idx) => {
      const d = Math.hypot(p[0] - ix, p[1] - iy);
      if (d < bestD) {
        bestD = d;
        best = idx;
      }
    });
    return best;
  }

  function getSelectedSector(state) {
    return state.boundarySectors.find((s) => s.id === state.selectedBoundaryId)
      || state.boundarySectors[0]
      || null;
  }

  function captureVideoFrame(video) {
    const vw = video.videoWidth || 1;
    const vh = video.videoHeight || 1;
    const canvas = document.createElement('canvas');
    canvas.width = vw;
    canvas.height = vh;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, vw, vh);
    return { canvas, vw, vh };
  }

  function drawLocalContour(ctx, points, arcIdx, sx, sy, zoom, stroke, width, dash) {
    ctx.save();
    ctx.beginPath();
    arcIdx.forEach((pi, i) => {
      const p = points[pi];
      const x = (p[0] - sx) * zoom;
      const y = (p[1] - sy) * zoom;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = stroke;
    ctx.lineWidth = width;
    if (dash) ctx.setLineDash(dash);
    ctx.stroke();
    ctx.restore();
  }

  function renderDetailCanvas(state, video, normPoly) {
    const canvas = el('boundaryDetailCanvas');
    const empty = el('boundaryDetailEmpty');
    const sector = getSelectedSector(state);
    if (!canvas || !sector || !normPoly?.length || video.readyState < 2) {
      if (empty) empty.classList.remove('hidden');
      return;
    }
    if (empty) empty.classList.add('hidden');
    const zoom = state.boundaryDetailZoom || DEFAULT_ZOOM;
    const patchSize = Math.max(40, Math.round(PATCH_SRC * DEFAULT_ZOOM / zoom));
    const { canvas: frameCanvas, vw, vh } = getCachedFrame(state, video);
    const points = polygonImagePoints(normPoly, video);
    const half = patchSize / 2;
    const sx = Math.max(0, Math.min(vw - patchSize, sector.x - half));
    const sy = Math.max(0, Math.min(vh - patchSize, sector.y - half));
    const outW = canvas.width;
    const outH = canvas.height;
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.clearRect(0, 0, outW, outH);
    ctx.drawImage(frameCanvas, sx, sy, patchSize, patchSize, 0, 0, outW, outH);

    const z = outW / patchSize;
    const g = state.boundaryGuides;

    if (g.contour) {
      drawLocalContour(ctx, points, sector.arcIdx, sx, sy, z, 'rgba(251, 191, 36, 0.95)', 2.5, [6, 4]);
    }
    if (g.breakthrough && sector.breakthroughRisk > 0.45) {
      drawLocalContour(ctx, points, sector.arcIdx, sx, sy, z, 'rgba(248, 113, 113, 0.9)', 4, null);
    }
    const cx = (sector.x - sx) * z;
    const cy = (sector.y - sy) * z;
    const nx = sector.nx;
    const ny = sector.ny;
    const len = 36;
    if (g.normal) {
      ctx.save();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx - nx * 10, cy - ny * 10);
      ctx.lineTo(cx + nx * len, cy + ny * len);
      ctx.stroke();
      ctx.restore();
    }
    if (g.serosa) {
      const ox = cx + nx * 14;
      const oy = cy + ny * 14;
      ctx.save();
      ctx.strokeStyle = 'rgba(103, 212, 255, 0.95)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(ox - ny * 20, oy + nx * 20);
      ctx.lineTo(ox + ny * 20, oy - nx * 20);
      ctx.stroke();
      ctx.restore();
    }
    if (g.normalWall) {
      const ix = cx - nx * 18;
      const iy = cy - ny * 18;
      ctx.save();
      ctx.strokeStyle = 'rgba(92, 227, 161, 0.85)';
      ctx.setLineDash([4, 3]);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(ix - ny * 18, iy + nx * 18);
      ctx.lineTo(ix + ny * 18, iy - nx * 18);
      ctx.stroke();
      ctx.restore();
    }
    ctx.save();
    ctx.strokeStyle = 'rgba(226, 232, 240, 0.75)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(cx - ny * 24, cy + nx * 24);
    ctx.lineTo(cx + ny * 24, cy - nx * 24);
    ctx.stroke();
    ctx.restore();
    ctx.save();
    ctx.strokeStyle = sector.accent;
    ctx.fillStyle = sector.accent;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.restore();
  }

  function renderThumb(state, video, normPoly, sector) {
    const zoom = 3.5;
    const { canvas: frameCanvas, vw, vh } = getCachedFrame(state, video);
    const half = 72 / 2;
    const sx = Math.max(0, Math.min(vw - 72, sector.x - half));
    const sy = Math.max(0, Math.min(vh - 72, sector.y - half));
    const outSize = Math.round(72 * zoom);
    const patch = document.createElement('canvas');
    patch.width = outSize;
    patch.height = outSize;
    const ctx = patch.getContext('2d');
    ctx.drawImage(frameCanvas, sx, sy, 72, 72, 0, 0, outSize, outSize);
    const points = polygonImagePoints(normPoly, video);
    ctx.save();
    ctx.translate(-sx * zoom, -sy * zoom);
    ctx.scale(zoom, zoom);
    drawLocalContour(ctx, points, sector.arcIdx, 0, 0, 1, 'rgba(103,212,255,0.9)', 2, null);
    ctx.restore();
    return patch.toDataURL('image/png');
  }

  function directionsEnabled(state) {
    return Boolean(state.directionAnnotationsEnabled);
  }

  function renderMaskOnlyPanel(state) {
    const row = el('boundaryCompass');
    const deep = el('boundaryDetailDeep');
    const grid = el('boundaryDetailGrid');
    const headHint = el('boundaryDetailHint');
    const n = state.maskPolygon?.length || 0;
    const score = state.lastReport?.sam_score;
    const scoreTxt = score != null ? ` · 质量 ${Math.round(score * 100)}%` : '';
    if (row) {
      row.innerHTML = `<div class="boundary-mask-status">
        <span class="boundary-mask-badge">分割轮廓</span>
        <span class="boundary-mask-meta">${n} 顶点${scoreTxt}</span>
        <span class="boundary-mask-hint">视频叠加；解剖方向标注待完善</span>
      </div>`;
    }
    if (deep) deep.classList.add('is-hidden');
    if (grid) grid.innerHTML = '';
    if (headHint) headHint.textContent = '当前仅显示分割轮廓';
    const empty = el('boundaryDetailEmpty');
    if (empty) empty.classList.add('hidden');
  }

  function renderCompass(state) {
    const row = el('boundaryCompass');
    if (!row) return;
    if (!state.boundarySectors.length) {
      row.innerHTML = '<div class="interactive-boundary-empty">完成分割后显示六个方向 + 自定义</div>';
      return;
    }
    const sorted = [...state.boundarySectors].sort((a, b) => {
      if (a.id === 'custom') return 1;
      if (b.id === 'custom') return -1;
      return b.breakthroughRisk - a.breakthroughRisk;
    });
    row.innerHTML = sorted.map((s) => {
      const active = s.id === state.selectedBoundaryId ? 'active' : '';
      const high = s.breakthroughRisk >= 0.6 ? 'risk-high' : '';
      const adj = state.boundaryAdjudications[s.id];
      const adjTag = adj ? `<span class="boundary-compass-adj ${ADJ_OPTIONS.find((a) => a.id === adj)?.cls || ''}">${ADJ_OPTIONS.find((a) => a.id === adj)?.label || adj}</span>` : '';
      return `<button type="button" class="boundary-compass-chip ${active} ${high}" data-boundary-id="${s.id}" style="--sector-accent:${s.accent}">
        <span class="boundary-compass-short">${s.short}</span>
        <span class="boundary-compass-label">${s.label}</span>
        <span class="boundary-compass-risk">突破 ${Math.round(s.breakthroughRisk * 100)}%</span>
        ${adjTag}
      </button>`;
    }).join('');
    if (!state.boundarySectors.some((s) => s.id === 'custom')) {
      row.innerHTML += `<button type="button" class="boundary-compass-chip boundary-compass-custom" data-boundary-pick="custom" style="--sector-accent:#e2e8f0">
        <span class="boundary-compass-short">+</span>
        <span class="boundary-compass-label">自定义方向</span>
        <span class="boundary-compass-risk">快捷键 5 · 点边界</span>
      </button>`;
    }
    row.querySelectorAll('[data-boundary-pick="custom"]').forEach((node) => {
      node.addEventListener('click', () => {
        ctxRef.setInteractionMode('boundary');
        ctxRef.showToast('请在视频边界上点击设置自定义方向', 'ok');
      });
    });
    row.querySelectorAll('[data-boundary-id]').forEach((node) => {
      node.addEventListener('click', () => {
        state.selectedBoundaryId = node.dataset.boundaryId;
        state.boundaryUserPickedDirection = true;
        renderAll(state, ctxRef);
        ctxRef.redrawOverlay();
        ctxRef.showToast(`已选方向 · ${node.querySelector('.boundary-compass-label')?.textContent || ''}`, 'ok');
      });
    });
  }

  function renderThumbs(state, video, normPoly) {
    const grid = el('boundaryDetailGrid');
    if (!grid) return;
    if (!state.boundarySectors.length) {
      grid.innerHTML = '';
      return;
    }
    grid.innerHTML = state.boundarySectors.map((s) => {
      const dataUrl = renderThumb(state, video, normPoly, s);
      const active = s.id === state.selectedBoundaryId ? 'active' : '';
      return `<div class="interactive-boundary-card boundary-thumb-card ${active}" data-boundary-id="${s.id}">
        <img src="${dataUrl}" alt="${s.label}" />
        <div class="interactive-boundary-card-title">${s.label}
          <span class="interactive-boundary-card-note">${s.note} · 风险 ${Math.round(s.breakthroughRisk * 100)}%</span>
        </div>
      </div>`;
    }).join('');
    grid.querySelectorAll('[data-boundary-id]').forEach((node) => {
      node.addEventListener('click', () => {
        state.selectedBoundaryId = node.dataset.boundaryId;
        state.boundaryUserPickedDirection = true;
        renderAll(state, ctxRef);
        ctxRef.redrawOverlay();
      });
    });
  }

  function renderProfileChart(state, video, normPoly, sector) {
    const canvas = el('boundaryProfileCanvas');
    if (!canvas || !sector || !normPoly?.length) return;
    const points = polygonImagePoints(normPoly, video);
    const profile = buildWallProfile(points, sector, 24);
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = 'rgba(255,255,255,0.04)';
    ctx.fillRect(0, 0, w, h);
    const pad = 6;
    const innerW = w - pad * 2;
    const barH = h - pad * 2;
    profile.forEach((bin, i) => {
      const x = pad + (i / profile.length) * innerW;
      const bw = innerW / profile.length + 1;
      if (bin.inside) {
        ctx.fillStyle = i / profile.length > 0.55 ? 'rgba(248,113,113,0.75)' : 'rgba(103,212,255,0.55)';
        ctx.fillRect(x, pad + barH * 0.25, bw, barH * 0.5);
      }
    });
    ctx.strokeStyle = 'rgba(92,227,161,0.9)';
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(pad + innerW * 0.35, pad);
    ctx.lineTo(pad + innerW * 0.35, h - pad);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '8px sans-serif';
    ctx.fillText('腔侧', pad + 2, h - 2);
    ctx.fillText('浆膜侧', pad + innerW * 0.58, h - 2);
  }

  function renderDetailSide(state, video, normPoly) {
    const sector = getSelectedSector(state);
    const title = el('boundaryDetailTitle');
    const metrics = el('boundaryDetailMetrics');
    const adjWrap = el('boundaryAdjButtons');
    if (!sector) {
      if (title) title.textContent = '—';
      if (metrics) metrics.innerHTML = '';
      if (adjWrap) adjWrap.innerHTML = '';
      return;
    }
    if (title) title.textContent = `${sector.label} · ${sector.short}`;
    if (metrics) {
      metrics.innerHTML = `
        <div class="boundary-metric"><span>局部壁厚</span><strong>${sector.wallMm} mm</strong></div>
        <div class="boundary-metric"><span>邻近正常壁</span><strong>${sector.normalMm} mm</strong></div>
        <div class="boundary-metric"><span>厚度比</span><strong>${sector.ratio}×</strong></div>
        <div class="boundary-metric"><span>突破风险</span><strong class="${sector.breakthroughRisk > 0.6 ? 'risk-high' : ''}">${Math.round(sector.breakthroughRisk * 100)}%</strong></div>
        <div class="boundary-metric"><span>曲率</span><strong>${sector.curvature.toFixed(3)}</strong></div>`;
    }
    if (adjWrap) {
      adjWrap.innerHTML = ADJ_OPTIONS.map((opt) => {
        const active = state.boundaryAdjudications[sector.id] === opt.id ? 'active' : '';
        return `<button type="button" class="boundary-adj-btn ${opt.cls} ${active}" data-adj="${opt.id}">${opt.label}</button>`;
      }).join('');
      adjWrap.querySelectorAll('[data-adj]').forEach((btn) => {
        btn.addEventListener('click', () => {
          state.boundaryAdjudications[sector.id] = btn.dataset.adj;
          renderAll(state, ctxRef);
          if (state.lastReport) ctxRef.renderReport(state.lastReport);
          ctxRef.showToast(`已记录 · ${sector.label} · ${btn.textContent}`, 'ok');
          if (ctxRef.scheduleBoundaryReport) ctxRef.scheduleBoundaryReport();
        });
      });
    }
    const zoomVal = el('boundaryZoomValue');
    const slider = el('boundaryZoomSlider');
    if (zoomVal) zoomVal.textContent = String(state.boundaryDetailZoom);
    if (slider && Number(slider.value) !== state.boundaryDetailZoom) {
      slider.value = String(state.boundaryDetailZoom);
    }
    if (video && normPoly) renderProfileChart(state, video, normPoly, sector);
  }

  function renderWorkbenchAgent(state) {
    const node = el('boundaryWorkbenchAgent');
    if (!node) return;
    if (!directionsEnabled(state)) {
      if (!state.maskPolygon?.length) {
        node.innerHTML = '<div class="interactive-empty">分割完成后在此显示轮廓摘要</div>';
        return;
      }
      const n = state.maskPolygon.length;
      const score = state.lastReport?.sam_score;
      const scoreLine = score != null ? `分割质量 ${Math.round(score * 100)}%。` : '';
      node.innerHTML = `<div class="boundary-wb-summary">分割轮廓已加载（${n} 顶点）</div>
        <div class="boundary-wb-note">${scoreLine}请结合视频叠加复核病灶范围。</div>`;
      return;
    }
    if (!state.boundarySectors.length) {
      node.innerHTML = '<div class="interactive-empty">分割完成后汇总各方向突破判读</div>';
      return;
    }
    const rows = state.boundarySectors.map((s) => {
      const adj = state.boundaryAdjudications[s.id];
      const adjLabel = ADJ_OPTIONS.find((a) => a.id === adj)?.label || '未判读';
      const cls = ADJ_OPTIONS.find((a) => a.id === adj)?.cls || 'adj-muted';
      return `<div class="boundary-wb-row">
        <span class="boundary-wb-dir" style="color:${s.accent}">${s.label}</span>
        <span class="boundary-wb-risk">${Math.round(s.breakthroughRisk * 100)}%</span>
        <span class="boundary-wb-adj ${cls}">${adjLabel}</span>
      </div>`;
    }).join('');
    const done = Object.keys(state.boundaryAdjudications).length;
    node.innerHTML = `
      <div class="boundary-wb-summary">已判读 ${done} / ${state.boundarySectors.length} 个方向</div>
      ${rows}
      <div class="boundary-wb-note">医生判读将写入 Evidence 并影响文字报告引用。</div>`;
  }

  function renderAll(state, ref) {
    if (!ref) return;
    const video = el('studyVideo');
    const normPoly = state.maskPolygon;
    if (!normPoly?.length || video.readyState < 2) {
      clearPanels(state);
      return;
    }
    if (!directionsEnabled(state)) {
      state.boundarySectors = [];
      state.boundarySamples = [];
      renderMaskOnlyPanel(state);
      renderWorkbenchAgent(state);
      return;
    }
    const deep = el('boundaryDetailDeep');
    if (deep) deep.classList.remove('is-hidden');
    const headHint = el('boundaryDetailHint');
    if (headHint) headHint.textContent = '选择方向深读 · [ ] 切换 · 判读后自动更新报告';
    state.boundarySamples = state.boundarySectors;
    renderCompass(state);
    renderDetailSide(state, video, normPoly);
    renderDetailCanvas(state, video, normPoly);
    renderThumbs(state, video, normPoly);
    renderWorkbenchAgent(state);
  }

  function clearPanels(state) {
    state.boundarySectors = [];
    state.boundarySamples = [];
    const row = el('boundaryCompass');
    if (row) {
      row.innerHTML = directionsEnabled(state)
        ? '<div class="interactive-boundary-empty">完成分割后显示六个方向 + 自定义</div>'
        : '<div class="interactive-boundary-empty">完成分割后显示 mask 轮廓</div>';
    }
    const deep = el('boundaryDetailDeep');
    if (deep && !directionsEnabled(state)) deep.classList.add('is-hidden');
    const grid = el('boundaryDetailGrid');
    if (grid) grid.innerHTML = '';
    const empty = el('boundaryDetailEmpty');
    if (empty) empty.classList.remove('hidden');
    renderWorkbenchAgent(state);
  }

  function rebuildSectors(state, caseId) {
    const video = el('studyVideo');
    if (!state.maskPolygon?.length || video.readyState < 2) {
      clearPanels(state);
      return;
    }
    if (!directionsEnabled(state)) {
      state.boundarySectors = [];
      state.boundarySamples = [];
      invalidateFrameCache(state);
      renderMaskOnlyPanel(state);
      renderWorkbenchAgent(state);
      return;
    }
    state.boundarySectors = buildBoundarySectors(
      state.maskPolygon,
      video,
      caseId,
      state.customBoundaryIdx,
    );
    if (!state.boundaryUserPickedDirection && state.boundarySectors.length) {
      const top = [...state.boundarySectors].sort((a, b) => b.breakthroughRisk - a.breakthroughRisk)[0];
      if (top) state.selectedBoundaryId = top.id;
    } else if (!state.boundarySectors.find((s) => s.id === state.selectedBoundaryId)) {
      state.selectedBoundaryId = state.boundarySectors[0]?.id || 'outer';
    }
    invalidateFrameCache(state);
    state.boundarySamples = state.boundarySectors;
    renderAll(state, ctxRef);
  }

  function drawMaskOnOverlay(state, ctx, video) {
    if (!state.maskPolygon?.length || state.maskPolygon.length < 3) return false;
    const showDirs = directionsEnabled(state);
    const sel = showDirs ? getSelectedSector(state) : null;
    const pts = polygonImagePoints(state.maskPolygon, video);
    ctx.save();
    ctx.beginPath();
    pts.forEach((p, idx) => {
      const mapped = ctxRef.mapImageToCanvas(p[0], p[1], video);
      if (idx === 0) ctx.moveTo(mapped.x, mapped.y);
      else ctx.lineTo(mapped.x, mapped.y);
    });
    ctx.closePath();
    ctx.fillStyle = showDirs && sel
      ? 'rgba(103, 212, 255, 0.14)'
      : `rgba(103, 212, 255, ${state.maskFillOpacity ?? 0.30})`;
    ctx.fill();
    if (showDirs && sel) {
      ctx.beginPath();
      sel.arcIdx.forEach((pi, i) => {
        const m = ctxRef.mapImageToCanvas(pts[pi][0], pts[pi][1], video);
        if (i === 0) ctx.moveTo(m.x, m.y);
        else ctx.lineTo(m.x, m.y);
      });
      ctx.closePath();
      ctx.fillStyle = 'rgba(103, 212, 255, 0.32)';
      ctx.fill();
    }
    ctx.strokeStyle = 'rgba(251, 191, 36, 0.92)';
    ctx.lineWidth = showDirs ? 4 : 5;
    ctx.stroke();
    ctx.strokeStyle = 'rgba(103, 212, 255, 0.98)';
    ctx.lineWidth = showDirs ? 2 : 3;
    ctx.stroke();
    ctx.restore();
    return true;
  }

  function getBoundaryContextForApi(state) {
    if (!directionsEnabled(state)) return [];
    return state.boundarySectors.map((s) => ({
      sector_id: s.id,
      label: s.label,
      adjudication: state.boundaryAdjudications[s.id] || '',
      wall_mm: s.wallMm,
      normal_mm: s.normalMm,
      breakthrough_risk: s.breakthroughRisk,
      thickness_ratio: s.ratio,
    }));
  }

  function cycleSector(state, delta) {
    if (!state.boundarySectors.length) return;
    const ids = state.boundarySectors.map((s) => s.id);
    const idx = Math.max(0, ids.indexOf(state.selectedBoundaryId));
    const next = (idx + delta + ids.length) % ids.length;
    state.selectedBoundaryId = ids[next];
    state.boundaryUserPickedDirection = true;
    renderAll(state, ctxRef);
    ctxRef.redrawOverlay();
  }

  function drawOverlayExtras(state, ctx, video) {
    if (!directionsEnabled(state)) return;
    if (!state.maskPolygon?.length || !state.boundarySectors.length) return;
    const selected = state.selectedBoundaryId;
    state.boundarySectors.forEach((s) => {
      const mapped = ctxRef.mapImageToCanvas(s.x, s.y, video);
      const isSel = s.id === selected;
      ctx.save();
      ctx.beginPath();
      ctx.arc(mapped.x, mapped.y, isSel ? 9 : 6, 0, Math.PI * 2);
      ctx.fillStyle = isSel ? s.accent : `${s.accent}99`;
      ctx.fill();
      if (isSel) {
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
        if (state.boundaryGuides.normal) {
          const t = ctxRef.videoDisplayTransform(video);
          const scale = t.scale;
          const nx = s.nx * scale * 28;
          const ny = s.ny * scale * 28;
          ctx.strokeStyle = 'rgba(255,255,255,0.85)';
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(mapped.x, mapped.y);
          ctx.lineTo(mapped.x + nx, mapped.y + ny);
          ctx.stroke();
        }
      }
      ctx.fillStyle = '#fff';
      ctx.font = '9px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(s.short.slice(0, 2), mapped.x, mapped.y + 3);
      ctx.restore();
    });
    if (selected && state.boundaryLockTrack) {
      const sel = getSelectedSector(state);
      if (sel && state.maskPolygon.length >= 3) {
        const pts = polygonImagePoints(state.maskPolygon, video);
        ctx.save();
        ctx.beginPath();
        sel.arcIdx.forEach((pi, i) => {
          const m = ctxRef.mapImageToCanvas(pts[pi][0], pts[pi][1], video);
          if (i === 0) ctx.moveTo(m.x, m.y);
          else ctx.lineTo(m.x, m.y);
        });
        ctx.strokeStyle = sel.accent;
        ctx.lineWidth = 4;
        ctx.stroke();
        ctx.restore();
      }
    }
  }

  function getEvidenceItems(state) {
    if (!state.boundarySectors.length) return [];
    return state.boundarySectors
      .filter((s) => state.boundaryAdjudications[s.id])
      .map((s) => {
        const adj = ADJ_OPTIONS.find((a) => a.id === state.boundaryAdjudications[s.id]);
        return {
          title: `边界方向 · ${s.label}`,
          detail: `局部壁厚 ${s.wallMm} mm vs 正常 ${s.normalMm} mm（${s.ratio}×）；AI 突破风险 ${Math.round(s.breakthroughRisk * 100)}%；医生判读：${adj?.label || '—'}。${s.note}`,
        };
      });
  }

  function handleBoundaryClick(state, ix, iy) {
    if (!directionsEnabled(state)) return false;
    if (!state.maskPolygon?.length) return false;
    const video = el('studyVideo');
    state.customBoundaryIdx = nearestBoundaryIdx(state.maskPolygon, video, ix, iy);
    state.selectedBoundaryId = 'custom';
    state.boundaryUserPickedDirection = true;
    rebuildSectors(state, ctxRef.currentCase()?.case_id);
    ctxRef.redrawOverlay();
    ctxRef.showToast('已设自定义边界方向', 'ok');
    return true;
  }

  function bindControls(state, ref) {
    ctxRef = ref;
    const slider = el('boundaryZoomSlider');
    if (slider) {
      slider.addEventListener('input', () => {
        state.boundaryDetailZoom = Number(slider.value);
        const video = el('studyVideo');
        renderDetailCanvas(state, video, state.maskPolygon);
        renderDetailSide(state, video, state.maskPolygon);
      });
    }
    const lock = el('boundaryLockTrack');
    if (lock) {
      lock.addEventListener('change', () => {
        state.boundaryLockTrack = lock.checked;
        ref.redrawOverlay();
      });
    }
    document.querySelectorAll('#boundaryGuideBar [data-guide]').forEach((input) => {
      input.addEventListener('change', () => {
        state.boundaryGuides[input.dataset.guide] = input.checked;
        renderDetailCanvas(state, el('studyVideo'), state.maskPolygon);
        ref.redrawOverlay();
      });
    });
  }

  function onCaseClear(state) {
    state.boundaryAdjudications = {};
    state.customBoundaryIdx = null;
    state.selectedBoundaryId = 'outer';
    state.boundaryUserPickedDirection = false;
    invalidateFrameCache(state);
    clearPanels(state);
  }

  window.BoundaryWorkbench = {
    extendState,
    bindControls,
    rebuildSectors,
    renderAll,
    clearPanels,
    drawMaskOnOverlay,
    drawOverlayExtras,
    getEvidenceItems,
    getBoundaryContextForApi,
    handleBoundaryClick,
    cycleSector,
    onCaseClear,
    ADJ_OPTIONS,
  };
})();
