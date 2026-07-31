/*! Bridge SAM mask → ContactGeom 胃壁分层 (video frame).
 * SAM maskPolygon is normalized [0,1]; ContactGeom uses image pixels.
 */
(function (global) {
  'use strict';

  function polyCentroid(pts) {
    if (global.ContactGeom?.polyCentroid) return global.ContactGeom.polyCentroid(pts);
    let x = 0;
    let y = 0;
    pts.forEach((p) => {
      x += p[0];
      y += p[1];
    });
    return [x / Math.max(1, pts.length), y / Math.max(1, pts.length)];
  }

  function maskToNormPts(maskPolygon) {
    if (!Array.isArray(maskPolygon) || maskPolygon.length < 3) return [];
    return maskPolygon.map((pt) => {
      if (Array.isArray(pt)) return [Number(pt[0]), Number(pt[1])];
      return [Number(pt.x), Number(pt.y)];
    }).filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
  }

  /** Convert normalized [0,1] polygon to image pixels. */
  function normToImagePts(normPts, videoW, videoH) {
    const vw = videoW || 1;
    const vh = videoH || 1;
    return normPts.map(([nx, ny]) => [nx * vw, ny * vh]);
  }

  function imageToNormPts(imgPts, videoW, videoH) {
    const vw = Math.max(1, videoW || 1);
    const vh = Math.max(1, videoH || 1);
    return imgPts.map(([x, y]) => [x / vw, y / vh]);
  }

  /**
   * Estimate lumen-side wall as a parallel curve of the lesion (pixel space).
   * Offset scales with lesion size for stable ContactGeom ratios.
   */
  function estimateWallFromLesion(lesPts, offsetPx, lumenPrefer) {
    const n = lesPts.length;
    if (n < 3) return [];
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    lesPts.forEach(([x, y]) => {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    });
    const diag = Math.hypot(maxX - minX, maxY - minY) || 80;
    const offset = Number.isFinite(offsetPx) ? offsetPx : Math.max(18, Math.min(72, diag * 0.28));
    const prefer = lumenPrefer || [0, -1];
    const wall = [];
    for (let i = 0; i < n; i += 1) {
      const prev = lesPts[(i - 1 + n) % n];
      const next = lesPts[(i + 1) % n];
      const p = lesPts[i];
      let nx = -(next[1] - prev[1]);
      let ny = next[0] - prev[0];
      const len = Math.hypot(nx, ny) || 1;
      nx /= len;
      ny /= len;
      if (nx * prefer[0] + ny * prefer[1] < 0) {
        nx = -nx;
        ny = -ny;
      }
      wall.push([p[0] + nx * offset, p[1] + ny * offset]);
    }
    return { wallPts: wall, offsetPx: offset };
  }

  function captureVideoFrameDataUrl(video) {
    if (!video?.videoWidth) return null;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.92);
  }

  function resampleClosed(pts, targetN) {
    if (!pts?.length) return [];
    const n = Math.max(12, targetN || 64);
    const seg = [];
    let total = 0;
    for (let i = 0; i < pts.length; i += 1) {
      const a = pts[i];
      const b = pts[(i + 1) % pts.length];
      const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
      seg.push(d);
      total += d;
    }
    if (total < 1e-6) return pts.slice();
    const out = [];
    for (let k = 0; k < n; k += 1) {
      let dist = (k / n) * total;
      for (let i = 0; i < pts.length; i += 1) {
        if (dist <= seg[i] || i === pts.length - 1) {
          const t = seg[i] > 0 ? dist / seg[i] : 0;
          const a = pts[i];
          const b = pts[(i + 1) % pts.length];
          out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
          break;
        }
        dist -= seg[i];
      }
    }
    return out;
  }

  async function analyzeLayersFromMask(opts) {
    const G = global.ContactGeom;
    if (!G) return { ok: false, message: 'ContactGeom 未加载' };
    const videoW = opts.videoW || opts.video?.videoWidth || 0;
    const videoH = opts.videoH || opts.video?.videoHeight || 0;
    if (!videoW || !videoH) return { ok: false, message: '视频尺寸未知' };

    const normLes = maskToNormPts(opts.maskPolygon);
    if (normLes.length < 3) return { ok: false, message: '病灶轮廓不足' };
    let lesPts = normToImagePts(normLes, videoW, videoH);
    lesPts = resampleClosed(lesPts, Math.min(160, Math.max(48, lesPts.length)));

    let wallPts;
    let wallEstimated = true;
    let offsetPx = opts.wallOffsetPx;
    if (opts.wallPts && opts.wallPts.length >= 3) {
      // Accept either normalized or pixel wall; heuristic: max<=1.5 → norm
      const maxAbs = Math.max(...opts.wallPts.flatMap((p) => [Math.abs(p[0]), Math.abs(p[1])]));
      wallPts = maxAbs <= 1.5
        ? normToImagePts(opts.wallPts, videoW, videoH)
        : opts.wallPts.map((p) => [Number(p[0]), Number(p[1])]);
      wallEstimated = false;
    } else {
      const est = estimateWallFromLesion(lesPts, offsetPx, opts.lumenPrefer);
      wallPts = est.wallPts;
      offsetPx = est.offsetPx;
    }
    wallPts = resampleClosed(wallPts, Math.min(120, Math.max(40, wallPts.length)));
    if (wallPts.length < 3) return { ok: false, message: '胃壁外缘估计失败' };

    const geom = G.computeGeometry(wallPts, lesPts);
    let pickIdx = Number.isInteger(opts.pickIdx) ? opts.pickIdx : null;
    if (pickIdx == null && Number.isFinite(opts.pickX) && Number.isFinite(opts.pickY)) {
      const hit = G.findInfiltrationFromClick(geom, opts.pickX, opts.pickY, { preferLesion: true });
      pickIdx = hit?.idx;
    }
    if (pickIdx == null) {
      pickIdx = Number.isInteger(geom.deep_idx) ? geom.deep_idx : 0;
    }
    pickIdx = Math.max(0, Math.min(wallPts.length - 1, pickIdx));

    const pen = G.penetrationAt(geom.wall_dists, geom.contact_idx, pickIdx, {
      wall_pts: geom.wall_pts,
      lesion_poly: geom.lesion_poly,
      wall_dirs: geom.wall_dirs,
    });
    const inContact = G.isContactPoint(geom, pickIdx);

    let analysis = null;
    if (opts.frameDataUrl) {
      const echo = await G.loadImageData(opts.frameDataUrl);
      if (echo?.data) {
        analysis = G.analyzeChannelNeighborhood(
          echo.data,
          echo.w,
          echo.h,
          geom,
          pickIdx,
          opts.halfWidth ?? 8,
          { maxLayers: 5 },
        );
        if (analysis && inContact) {
          analysis.ratioHint = analysis.imaginary
            ? pen.ratio
            : (0.55 * pen.ratio + 0.45 * (analysis.ratioHint || pen.ratio));
        }
      }
    }

    const ratio = analysis?.ratioHint ?? pen.ratio;
    const layer = inContact ? G.layerJudgment(ratio) : null;
    const source = analysis ? G.layerSourceInfo(analysis) : null;
    const plan = G.buildLayerPlan(geom, pickIdx, analysis || undefined);
    const wallPt = geom.wall_pts[pickIdx];
    const lesPt = geom.wall_lesion_pts?.[pickIdx] || wallPt;
    const dir = geom.wall_dirs?.[pickIdx] || [0, -1];

    return {
      ok: true,
      videoW,
      videoH,
      wallPts,
      lesPts,
      wallNorm: imageToNormPts(wallPts, videoW, videoH),
      lesNorm: imageToNormPts(lesPts, videoW, videoH),
      geom,
      pickIdx,
      pickPoint: wallPt,
      channelEnd: lesPt,
      channelDir: dir,
      inContact,
      pen,
      analysis,
      layer,
      source,
      plan,
      wallEstimated,
      offsetPx,
    };
  }

  function renderLayerCard(result, mountEl) {
    if (!mountEl) return;
    if (!result?.ok) {
      mountEl.innerHTML = `<div class="interactive-empty">${result?.message || '分层未就绪'}</div>`;
      return;
    }
    const G = global.ContactGeom;
    const layer = result.layer;
    const src = result.source;
    const pen = result.pen || {};
    const contactText = result.inContact ? '接触弧内 · 可分期' : '未接触 · 不可分期';
    const layerText = layer ? `${layer.label || ''} · ${layer.tHint || ''}` : '—';
    const badge = src?.badge || (result.wallEstimated ? '胃壁外缘为分割外推' : '手绘/预置胃壁');
    const pct = G?.formatPenPct ? G.formatPenPct(pen) : `${Math.round((pen.ratio || 0) * 100)}%`;
    const edges = result.analysis?.edgeFracs?.length || 0;
    const tone = layer?.tone || '#8b93a1';
    let stack = '';
    try {
      const fracs = result.analysis?.edgeFracs || result.plan?.edgeFracs || [];
      const occ = Number.isFinite(result.pen?.ratio) ? result.pen.ratio : (result.analysis?.ratioHint || 0);
      if (G?.wallStackSvg && fracs.length) {
        stack = G.wallStackSvg(fracs, occ, { w: 220, h: 140 }) || '';
      }
    } catch (_) {
      stack = '';
    }
    mountEl.innerHTML = `
      <div class="layer-bridge-grid">
        <div class="layer-bridge-hero" style="border-color:${tone}66">
          <div class="layer-bridge-hero-label">达层读数</div>
          <div class="layer-bridge-hero-value" style="color:${tone}">${layerText}</div>
        </div>
        ${stack ? `<div class="layer-bridge-stack">${stack}</div>` : ''}
        <div class="layer-bridge-row"><span>接触</span><strong>${contactText}</strong></div>
        <div class="layer-bridge-row"><span>占壁厚</span><strong>${pct}</strong></div>
        <div class="layer-bridge-row"><span>层界</span><strong>${edges} 条</strong></div>
        <div class="layer-bridge-row"><span>胃壁偏移</span><strong>${Math.round(result.offsetPx || 0)} px</strong></div>
        <div class="layer-bridge-actions">
          <button type="button" class="btn" data-layer-offset="-8" title="胃壁更近">壁−</button>
          <button type="button" class="btn" data-layer-offset="8" title="胃壁更远">壁+</button>
          <button type="button" class="btn" data-layer-reanalyze="1">重算分层</button>
        </div>
        <div class="layer-bridge-note">${badge}。视频上点击可选浸润方向；粉线=病灶前沿。</div>
      </div>`;
  }

  function drawLayerOverlay(result, ctx, mapImageToCanvas, video) {
    if (!result?.ok || !result.wallPts?.length) return false;
    const wall = result.wallPts;
    ctx.save();
    ctx.beginPath();
    wall.forEach((p, i) => {
      const m = mapImageToCanvas(p[0], p[1], video);
      if (i === 0) ctx.moveTo(m.x, m.y);
      else ctx.lineTo(m.x, m.y);
    });
    ctx.closePath();
    ctx.strokeStyle = 'rgba(111, 191, 143, 0.95)';
    ctx.lineWidth = 2.5;
    ctx.setLineDash([5, 4]);
    ctx.stroke();
    ctx.setLineDash([]);

    // contact arc highlight
    const contact = result.geom?.contact_idx || [];
    if (contact.length >= 2) {
      ctx.beginPath();
      let started = false;
      contact.forEach((i) => {
        const p = wall[i];
        if (!p) return;
        const m = mapImageToCanvas(p[0], p[1], video);
        if (!started) {
          ctx.moveTo(m.x, m.y);
          started = true;
        } else ctx.lineTo(m.x, m.y);
      });
      ctx.strokeStyle = 'rgba(240, 163, 94, 0.95)';
      ctx.lineWidth = 3.5;
      ctx.stroke();
    }

    if (result.pickPoint && result.channelEnd) {
      const a = mapImageToCanvas(result.pickPoint[0], result.pickPoint[1], video);
      const b = mapImageToCanvas(result.channelEnd[0], result.channelEnd[1], video);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = 'rgba(94, 200, 216, 0.95)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(a.x, a.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(111, 191, 143, 0.95)';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(b.x, b.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(224, 122, 106, 0.95)';
      ctx.fill();
    }
    ctx.restore();
    return true;
  }

  global.LayerBridge = {
    estimateWallFromLesion,
    maskToNormPts,
    normToImagePts,
    imageToNormPts,
    captureVideoFrameDataUrl,
    analyzeLayersFromMask,
    renderLayerCard,
    drawLayerOverlay,
    polyCentroid,
    resampleClosed,
  };
})(typeof window !== 'undefined' ? window : globalThis);
