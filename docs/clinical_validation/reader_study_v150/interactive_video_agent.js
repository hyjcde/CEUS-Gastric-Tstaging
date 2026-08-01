(function () {
  'use strict';

  const STAGES = ['T1', 'T2', 'T3', 'T4+'];
  const TOOL_STEPS = [
    { id: 'interaction', title: '交互读取', detail: '读取框选与点击' },
    { id: 'lumen', title: '胃腔定位', detail: '定位胃腔与壁层方向' },
    { id: 'segmentation', title: '病灶分割', detail: '生成分割轮廓' },
    { id: 'wall', title: '壁层证据', detail: '壁厚与外缘突破风险' },
    { id: 'classification', title: 'T 分期', detail: '分期概率与置信度' },
    { id: 'similarity', title: '相似病例', detail: '检索历史对照' },
    { id: 'fusion', title: '证据融合', detail: '汇总报告与复核建议' },
  ];

  const state = {
    cases: [],
    caseCohort: 'all', // all | t_staging | benign_malignancy
    currentIndex: 0,
    frameIndex: 0,
    interactionMode: 'positive',
    clicks: [],
    box: null,
    dragBox: null,
    analyzing: false,
    lastReport: null,
    keyFrames: [],
    samBackend: null,
    maskPolygon: null,
    boundarySamples: [],
    loupePoint: null,
    trackOnPlay: true,
    trackBusy: false,
    lastTrackMs: 0,
    lastBoundaryMs: 0,
    lastFullReportMs: 0,
    trackRequestId: 0,
    pendingTrack: false,
    llmDebounceTimer: null,
    userEditUntil: 0,
    lastPromptMeta: null,
    maskFlashUntil: 0,
    toastTimer: null,
    reportGenerating: false,
    boundaryReportTimer: null,
    showMaskOverlay: true,
    maskFillOpacity: 0.30,
    lastMaskOverlayPng: null,
    layerResult: null,
    wallPtsManual: null,
    wallOffsetPx: null,
    layerPickImage: null, // {x,y} image pixels for infiltration pick
    layerAnalyzeTimer: null,
    lastPreviewMs: 0,
    deepLink: null,
    callbackUrl: '',
    externalVideo: false,
    externalStill: false,
    stillStream: null,
  };

  if (window.BoundaryWorkbench) {
    window.BoundaryWorkbench.extendState(state);
  }

  const dragState = { active: false, startCanvas: null, startImage: null, pointerId: null };
  const MIN_BOX_PX = 10;
  const MIN_BOX_IMAGE_PX = 12;
  const BOUNDARY_ZOOM = 3.5;
  const BOUNDARY_PATCH_SRC = 72;
  const TRACK_INTERVAL_MS = 500;
  const BOUNDARY_INTERVAL_MS = 1500;
  const FULL_REPORT_INTERVAL_MS = 2500;

  function el(id) {
    return document.getElementById(id);
  }

  function hashSeed(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function seededRandom(seed) {
    let x = seed || 1;
    return function rand() {
      x ^= x << 13;
      x ^= x >>> 17;
      x ^= x << 5;
      return ((x >>> 0) % 10000) / 10000;
    };
  }

  function imageUrl(relPath) {
    if (!relPath) return '';
    if (/^https?:\/\//i.test(relPath) || relPath.startsWith('blob:') || relPath.startsWith('data:')) {
      return relPath;
    }
    // Encode each path segment so 良恶性/… works on Starlette StaticFiles (raw Unicode → 400).
    const clean = String(relPath).replace(/^\//, '');
    const [pathPart, queryPart] = clean.split('?');
    const encodedPath = pathPart
      .split('/')
      .map((seg) => encodeURIComponent(seg))
      .join('/');
    const version = window.READER_CASES?.created_at || '';
    const qs = new URLSearchParams(queryPart || '');
    if (version && /\.(mp4|mov|avi|mkv)$/i.test(pathPart) && !qs.has('v')) {
      qs.set('v', version);
    }
    const q = qs.toString();
    return q ? `${encodedPath}?${q}` : encodedPath;
  }

  function getCases(cohort = state.caseCohort) {
    const all = (window.READER_CASES?.cases || []).filter((item) => item.has_video !== false);
    if (cohort === 't_staging') {
      return all.filter((item) => item.study_mode === 't_staging' || String(item.case_id || '').startsWith('CASE-'));
    }
    if (cohort === 'benign_malignancy') {
      return all.filter((item) => item.study_mode === 'benign_malignancy' || String(item.case_id || '').startsWith('BM-'));
    }
    // all: BM first (task1 order) then T-staging
    const bm = all.filter((item) => item.study_mode === 'benign_malignancy' || String(item.case_id || '').startsWith('BM-'));
    const ts = all.filter((item) => item.study_mode === 't_staging' || String(item.case_id || '').startsWith('CASE-'));
    const rest = all.filter((item) => !bm.includes(item) && !ts.includes(item));
    return [...bm, ...ts, ...rest];
  }

  function setCaseCohort(cohort) {
    const next = ['all', 't_staging', 'benign_malignancy'].includes(cohort) ? cohort : 'all';
    state.caseCohort = next;
    state.cases = getCases(next);
    state.currentIndex = 0;
    state.frameIndex = 0;
    state.clicks = [];
    state.box = null;
    state.dragBox = null;
    state.lastReport = null;
    state.maskPolygon = null;
    state.lastMaskOverlayPng = null;
    document.querySelectorAll('[data-cohort]').forEach((node) => {
      node.classList.toggle('active', node.dataset.cohort === next);
    });
    clearBoundaryDetailPanel();
    renderCaseList();
    if (state.cases.length) {
      loadCurrentVideo();
      renderEmptyAgent(`已切换到「${cohortLabel(next)}」共 ${state.cases.length} 例。点击或框选病灶生成 mask。`);
    } else {
      el('caseList').innerHTML = '<div class="interactive-empty" style="padding:12px">该分组下无视频病例。</div>';
      renderEmptyAgent('无可用病例。');
    }
    clearOverlay();
    updateMaskControlBar();
    updateGenerateReportBtn();
  }

  function cohortLabel(cohort) {
    if (cohort === 't_staging') return 'T分期';
    if (cohort === 'benign_malignancy') return '良恶性';
    return '全部';
  }

  function parseDeepLink() {
    const sp = new URLSearchParams(window.location.search);
    const cohortRaw = (sp.get('cohort') || '').trim();
    const cohort = ['all', 't_staging', 'benign_malignancy'].includes(cohortRaw) ? cohortRaw : '';
    return {
      caseId: (sp.get('case') || '').trim(),
      cohort,
      video: (sp.get('video') || '').trim(),
      title: (sp.get('title') || '').trim(),
      frameId: (sp.get('frame_id') || '').trim(),
      patientId: (sp.get('patient_id') || '').trim(),
      callback: (sp.get('callback') || '').trim(),
      image: (sp.get('image') || '').trim(),
      treatment: (sp.get('treatment') || '').trim(),
    };
  }

  function findCaseIndex(cases, caseId) {
    if (!caseId) return -1;
    const want = caseId.toUpperCase();
    return cases.findIndex((item) => {
      const id = String(item.case_id || '').toUpperCase();
      const display = String(item.display_id || '').toUpperCase();
      return id === want || display === want || id.endsWith(want) || display.includes(want);
    });
  }

  function applyDeepLink() {
    const link = parseDeepLink();
    state.deepLink = link;
    state.callbackUrl = link.callback || '';
    state.externalVideo = false;

    if (link.cohort) {
      state.caseCohort = link.cohort;
      state.cases = getCases(link.cohort);
    }

    if (link.caseId) {
      let idx = findCaseIndex(state.cases, link.caseId);
      if (idx < 0) {
        const all = getCases('all');
        idx = findCaseIndex(all, link.caseId);
        if (idx >= 0) {
          state.caseCohort = 'all';
          state.cases = all;
        }
      }
      if (idx >= 0) {
        state.currentIndex = idx;
        return { mode: 'case', link };
      }
    }

    if (link.video) {
      state.externalVideo = true;
      return { mode: 'video', link };
    }

    if (link.image) {
      state.externalStill = true;
      return { mode: 'image', link };
    }

    return { mode: 'none', link };
  }

  function clearExternalMedia() {
    const video = el('studyVideo');
    if (state.stillStream) {
      try {
        state.stillStream.getTracks().forEach((t) => t.stop());
      } catch {
        /* ignore */
      }
      state.stillStream = null;
    }
    if (video.srcObject) {
      video.srcObject = null;
    }
    state.externalStill = false;
    state.externalVideo = false;
  }

  function loadExternalVideo(url, title) {
    clearExternalMedia();
    state.externalVideo = true;
    const video = el('studyVideo');
    const abs = /^https?:\/\//i.test(url) || url.startsWith('/')
      ? url
      : imageUrl(url);
    // Cross-origin Next stream needs CORS + anonymous for canvas/SAM capture.
    const cross = /^https?:\/\//i.test(abs) && !abs.includes(window.location.host);
    if (cross) video.crossOrigin = 'anonymous';
    else video.removeAttribute('crossorigin');
    video.removeAttribute('src');
    video.src = abs;
    video.playbackRate = window.READER_CASES?.viewer_policy?.default_video_speed || 0.25;
    video.onerror = () => {
      const code = video.error?.code;
      showToast(`视频加载失败（code=${code || '?'}）：${abs.slice(0, 120)}`, 'warn');
      el('videoClock').textContent = '加载失败';
    };
    video.load();
    video.onloadedmetadata = () => {
      state.keyFrames = [];
      el('videoClock').textContent = `00:00 / ${formatClock(video.duration)}`;
      const bar = el('keyframeBar');
      if (bar) bar.innerHTML = '';
      resizeOverlayCanvas();
    };
    video.ontimeupdate = () => {
      el('videoClock').textContent = `${formatClock(video.currentTime)} / ${formatClock(video.duration)}`;
      el('timelineSeek').value = video.duration ? String((video.currentTime / video.duration) * 1000) : '0';
    };
    clearOverlay();
    const label = title || state.deepLink?.patientId || '外部视频';
    el('caseTitle').textContent = label;
    el('frameTitle').textContent = state.deepLink?.frameId || '深链视频';
    state.maskPolygon = null;
    state.layerResult = null;
    updateMaskControlBar();
    updateGenerateReportBtn();
  }

  async function loadExternalImage(url, title) {
    clearExternalMedia();
    state.externalStill = true;
    const abs = /^https?:\/\//i.test(url) || url.startsWith('/')
      ? url
      : imageUrl(url);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    const loaded = new Promise((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error('静图加载失败（检查 CORS / 路径）'));
    });
    img.src = abs;
    await loaded;
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    if (!canvas.width || !canvas.height) throw new Error('静图尺寸无效');
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0);
    const stream = canvas.captureStream(1);
    state.stillStream = stream;
    const video = el('studyVideo');
    video.removeAttribute('src');
    video.srcObject = stream;
    await new Promise((resolve) => {
      const done = () => {
        video.removeEventListener('loadedmetadata', done);
        resolve();
      };
      video.addEventListener('loadedmetadata', done);
      // some browsers fire late
      setTimeout(done, 400);
    });
    try {
      await video.play();
    } catch {
      /* autoplay may be blocked; still frame remains in stream */
    }
    state.keyFrames = [];
    el('videoClock').textContent = '静图帧';
    const bar = el('keyframeBar');
    if (bar) bar.innerHTML = '';
    clearOverlay();
    const label = title || state.deepLink?.patientId || '外部静图';
    el('caseTitle').textContent = label;
    el('frameTitle').textContent = state.deepLink?.frameId || '深链静图';
    state.maskPolygon = null;
    state.layerResult = null;
    updateMaskControlBar();
    updateGenerateReportBtn();
    resizeOverlayCanvas();
  }

  async function postResultToCallback(extra = {}) {
    if (!state.callbackUrl) return;
    const caseItem = currentCase();
    const link = state.deepLink || {};
    const layer = state.layerResult;
    const payload = {
      frame_id: link.frameId || '',
      patient_id: link.patientId || '',
      case_id: caseItem?.case_id || link.caseId || '',
      display_id: caseItem?.display_id || link.title || '',
      ok: Boolean(layer?.ok),
      in_contact: Boolean(layer?.inContact),
      layer: layer?.layer || null,
      layer_label: layer?.layer?.label || null,
      t_hint: layer?.layer?.tHint || null,
      mask_polygon: state.maskPolygon,
      wall_offset_px: state.wallOffsetPx,
      message: layer?.message || '',
      source: 'interactive_video_agent',
      ...extra,
    };
    try {
      const res = await fetch(state.callbackUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        mode: 'cors',
      });
      if (!res.ok) {
        console.warn('callback writeback HTTP', res.status);
        return;
      }
      if (!extra.silent) showToast('已回写工作台', 'ok');
    } catch (err) {
      console.warn('callback writeback failed', err);
    }
  }

  function caseModeBadge(caseItem) {
    if (caseItem.study_mode === 'benign_malignancy' || String(caseItem.case_id || '').startsWith('BM-')) {
      const nature = caseItem.reference_lesion_nature;
      const hint = nature === 'benign' ? '良性' : nature === 'malignant' ? '恶性' : '良恶性';
      return `<span class="case-ref-pt">${hint}</span>`;
    }
    if (caseItem.reference_pt) return `<span class="case-ref-pt">参考 ${caseItem.reference_pt}</span>`;
    return '<span class="case-ref-pt">T分期</span>';
  }

  function currentCase() {
    return state.cases[state.currentIndex];
  }

  function currentFrame() {
    const caseItem = currentCase();
    return caseItem?.frames?.[state.frameIndex] || caseItem?.frames?.[0];
  }

  function videoDisplayTransform(video) {
    const rect = video.getBoundingClientRect();
    const vw = video.videoWidth || 1;
    const vh = video.videoHeight || 1;
    const scale = Math.min(rect.width / vw, rect.height / vh);
    const renderW = vw * scale;
    const renderH = vh * scale;
    const offsetX = (rect.width - renderW) / 2;
    const offsetY = (rect.height - renderH) / 2;
    return { vw, vh, scale, offsetX, offsetY, rect };
  }

  function mapClientToImageCoords(clientX, clientY, video) {
    const t = videoDisplayTransform(video);
    const localX = clientX - t.rect.left;
    const localY = clientY - t.rect.top;
    const x = (localX - t.offsetX) / t.scale;
    const y = (localY - t.offsetY) / t.scale;
    return {
      x,
      y,
      inVideo: x >= 0 && y >= 0 && x <= t.vw && y <= t.vh,
      image_width: t.vw,
      image_height: t.vh,
    };
  }

  function mapImageToCanvas(ix, iy, video) {
    const stage = el('viewerStage').getBoundingClientRect();
    const t = videoDisplayTransform(video);
    const offsetX = t.rect.left - stage.left + t.offsetX;
    const offsetY = t.rect.top - stage.top + t.offsetY;
    return {
      x: offsetX + ix * t.scale,
      y: offsetY + iy * t.scale,
    };
  }

  function canvasRectFromImageBox(box, video) {
    const p1 = mapImageToCanvas(box.x1, box.y1, video);
    const p2 = mapImageToCanvas(box.x2, box.y2, video);
    return {
      x: Math.min(p1.x, p2.x),
      y: Math.min(p1.y, p2.y),
      w: Math.abs(p2.x - p1.x),
      h: Math.abs(p2.y - p1.y),
    };
  }

  function boundaryDirectionsEnabled() {
    return Boolean(state.directionAnnotationsEnabled);
  }

  function applyBoundaryFeatureVisibility() {
    const enabled = boundaryDirectionsEnabled();
    document.querySelectorAll('[data-interaction-mode="inspect"], [data-interaction-mode="boundary"]').forEach((node) => {
      node.classList.toggle('is-hidden', !enabled);
    });
    const lock = document.querySelector('.boundary-lock-label');
    if (lock) lock.classList.toggle('is-hidden', !enabled);
    if (!enabled && (state.interactionMode === 'inspect' || state.interactionMode === 'boundary')) {
      setInteractionMode('positive');
    }
  }

  function updateInteractionModeUi() {
    applyBoundaryFeatureVisibility();
    const overlayWrap = document.querySelector('.interactive-overlay');
    if (overlayWrap) {
      overlayWrap.classList.toggle('box-mode', state.interactionMode === 'box');
      overlayWrap.classList.toggle('inspect-mode', boundaryDirectionsEnabled() && state.interactionMode === 'inspect');
      overlayWrap.classList.toggle('boundary-mode', boundaryDirectionsEnabled() && state.interactionMode === 'boundary');
    }
    const loupe = el('boundaryLoupe');
    if (loupe && (state.interactionMode !== 'inspect' || !boundaryDirectionsEnabled())) {
      loupe.classList.add('hidden');
      state.loupePoint = null;
    }
    const hint = el('viewerHint');
    if (hint) {
      if (boundaryDirectionsEnabled() && state.interactionMode === 'inspect') {
        hint.textContent = '边界检视：移动鼠标局部放大 · 黄圈=外缘 · 青圈=分割边界 · 用于外壁突破判读';
      } else if (state.interactionMode === 'box') {
        hint.textContent = '框选模式：拖拽框住病灶区域 · 松开后可加正负点微调 · 绿=正向 · 红=排除';
      } else if (boundaryDirectionsEnabled() && state.interactionMode === 'boundary') {
        hint.textContent = '自定义方向：点击分割边界 · 沿法向查看壁层剖面 · 快捷键 5';
      } else if (state.interactionMode === 'negative') {
        hint.textContent = '负向点：点击背景或非病灶区域 · 可叠加多个点';
      } else if (state.maskPolygon?.length >= 3) {
        hint.textContent = state.showMaskOverlay
          ? '分割+分层：青黄=病灶 · 绿虚线=胃壁 · Alt+点击选浸润方向 · 壁±调偏移'
          : '分割轮廓已隐藏 · 勾选「显示分割轮廓」可恢复视频叠加';
      } else {
        hint.textContent = '点击或框选病灶 → 自动分割 → 轮廓叠加在视频上';
      }
    }
    updatePromptCounter();
  }

  function updatePromptCounter(extra) {
    const node = el('promptCounter');
    if (!node) return;
    const pos = state.clicks.filter((c) => c.label !== 'negative').length;
    const neg = state.clicks.filter((c) => c.label === 'negative').length;
    const boxText = state.box ? '1 框' : '';
    const pointText = pos || neg ? `${pos} 正 / ${neg} 负` : '';
    const parts = [boxText, pointText].filter(Boolean);
    if (extra?.samScore != null) {
      parts.push(`分割 ${Math.round(extra.samScore * 100)}%`);
    }
    if (extra?.refined) {
      parts.push('精修');
    }
    node.textContent = parts.join(' · ') || '未标注';
  }

  async function refreshLayerAnalysis(options = {}) {
    const panel = el('layerBridgePanel');
    if (!window.LayerBridge || !window.ContactGeom) {
      if (panel) panel.innerHTML = '<div class="interactive-empty">分层库未加载</div>';
      return null;
    }
    if (!state.maskPolygon?.length) {
      state.layerResult = null;
      if (panel) panel.innerHTML = '<div class="interactive-empty">完成分割后，对当前视频帧做像素回声分层</div>';
      return null;
    }
    if (panel && !options.silent) {
      panel.innerHTML = '<div class="interactive-empty">正在分层…</div>';
    }
    try {
      const video = el('studyVideo');
      const frameDataUrl = window.LayerBridge.captureVideoFrameDataUrl(video);
      const result = await window.LayerBridge.analyzeLayersFromMask({
        maskPolygon: state.maskPolygon,
        wallPts: state.wallPtsManual,
        frameDataUrl,
        videoW: video.videoWidth,
        videoH: video.videoHeight,
        wallOffsetPx: state.wallOffsetPx,
        halfWidth: 8,
        pickX: state.layerPickImage?.x,
        pickY: state.layerPickImage?.y,
      });
      state.layerResult = result;
      if (result?.ok && Number.isFinite(result.offsetPx)) {
        state.wallOffsetPx = result.offsetPx;
      }
      window.LayerBridge.renderLayerCard(result, panel);
      bindLayerCardActions();
      redrawOverlay();
      if (result.ok && !options.silent) {
        const hint = result.layer
          ? `分层：${result.layer.label || ''} ${result.layer.tHint || ''}`
          : (result.inContact ? '分层完成' : '未接触胃壁 · 不可分期');
        showToast(hint, result.inContact ? 'ok' : 'warn');
      }
      if (result?.ok && state.callbackUrl) {
        postResultToCallback({ silent: Boolean(options.silent) });
      }
      return result;
    } catch (err) {
      console.error(err);
      state.layerResult = { ok: false, message: err.message || String(err) };
      if (panel) {
        panel.innerHTML = `<div class="interactive-empty">分层失败：${err.message || err}</div>`;
      }
      return state.layerResult;
    }
  }

  function scheduleLayerAnalysis(options = {}) {
    if (state.layerAnalyzeTimer) clearTimeout(state.layerAnalyzeTimer);
    const delay = options.silent ? 350 : 0;
    state.layerAnalyzeTimer = setTimeout(() => {
      state.layerAnalyzeTimer = null;
      refreshLayerAnalysis(options);
    }, delay);
  }

  function bindLayerCardActions() {
    const panel = el('layerBridgePanel');
    if (!panel || panel.dataset.bound === '1') {
      // rebind each render
    }
    panel.querySelectorAll('[data-layer-offset]').forEach((btn) => {
      btn.onclick = () => {
        const delta = Number(btn.dataset.layerOffset) || 0;
        const base = Number.isFinite(state.wallOffsetPx) ? state.wallOffsetPx : 42;
        state.wallOffsetPx = Math.max(10, Math.min(120, base + delta));
        state.wallPtsManual = null;
        refreshLayerAnalysis({ silent: false });
      };
    });
    panel.querySelectorAll('[data-layer-reanalyze]').forEach((btn) => {
      btn.onclick = () => refreshLayerAnalysis({ silent: false });
    });
  }

  function showToast(message, kind) {
    const toast = el('agentToast');
    if (!toast) return;
    if (state.toastTimer) clearTimeout(state.toastTimer);
    toast.textContent = message;
    toast.className = `agent-toast ${kind || ''}`.trim();
    toast.classList.remove('hidden');
    state.toastTimer = setTimeout(() => {
      toast.classList.add('hidden');
      state.toastTimer = null;
    }, 2400);
  }

  function flashMaskUpdate() {
    const stage = el('viewerStage');
    if (!stage) return;
    stage.classList.remove('mask-flash');
    void stage.offsetWidth;
    stage.classList.add('mask-flash');
    state.maskFlashUntil = performance.now() + 550;
    setTimeout(() => {
      if (performance.now() >= state.maskFlashUntil) {
        stage.classList.remove('mask-flash');
      }
    }, 560);
  }

  function setInteractionMode(mode) {
    state.interactionMode = mode;
    document.querySelectorAll('[data-interaction-mode]').forEach((n) => {
      n.classList.toggle('active', n.dataset.interactionMode === mode);
    });
    updateInteractionModeUi();
  }

  function escapeHtml(text) {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatNarrativeHtml(text) {
    if (!text) return '';
    const cleaned = String(text)
      .replace(/\r/g, '')
      .replace(/^#+\s*/gm, '')
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .trim();
    const parts = cleaned.split(/\n+/).map((p) => p.trim()).filter(Boolean);
    if (!parts.length) return '';
    return parts.map((p) => `<p>${escapeHtml(p)}</p>`).join('');
  }

  function pickDisplayNarrative(report) {
    if (report?.llm_report?.narrative) return report.llm_report.narrative;
    if (report?.summary && !/^Case |^SAM2 /i.test(report.summary)) return report.summary;
    return '';
  }

  function scrollClinicalReportIntoView() {
    const hero = el('clinicalReportHero');
    if (!hero) return;
    hero.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function copyClinicalReportText() {
    const narrativeNode = el('clinicalReportNarrative');
    if (!narrativeNode) return;
    const text = (narrativeNode.innerText || '').trim();
    if (!text || narrativeNode.classList.contains('is-placeholder')) {
      showToast('暂无可复制的报告正文', 'warn');
      return;
    }
    navigator.clipboard.writeText(text).then(() => {
      showToast('报告已复制到剪贴板', 'ok');
    }).catch(() => {
      showToast('复制失败，请手动选择正文', 'warn');
    });
  }

  function llmReportConfigured() {
    return Boolean(
      state.samBackend?.llm_report?.configured
      || state.samBackend?.deepseek?.configured
      || state.samBackend?.minimax?.configured
    );
  }

  function updateGenerateReportBtn() {
    const btn = el('generateReportBtn');
    if (!btn) return;
    const canReport = llmReportConfigured() && hasUserPrompt();
    btn.disabled = state.reportGenerating || !canReport;
    btn.title = !llmReportConfigured()
      ? '未配置 DeepSeek / MiniMax 密钥'
      : !hasUserPrompt()
        ? '请先框选或点击病灶'
        : '';
  }

  function bindMaskControls() {
    const toggle = el('showMaskToggle');
    const slider = el('maskOpacitySlider');
    if (toggle) {
      toggle.checked = state.showMaskOverlay;
      toggle.addEventListener('change', () => {
        state.showMaskOverlay = toggle.checked;
        redrawOverlay();
        updateInteractionModeUi();
      });
    }
    if (slider) {
      slider.value = String(Math.round(state.maskFillOpacity * 100));
      slider.addEventListener('input', () => {
        state.maskFillOpacity = Number(slider.value) / 100;
        redrawOverlay();
      });
    }
  }

  function updateMaskControlBar() {
    const bar = el('maskControlBar');
    if (!bar) return;
    bar.classList.toggle('is-hidden', !state.maskPolygon?.length);
  }

  function renderClinicalReport(report, options = {}) {
    const hero = el('clinicalReportHero');
    const stageNode = el('clinicalReportStage');
    const confNode = el('clinicalReportConfidence');
    const narrativeNode = el('clinicalReportNarrative');
    const statusNode = el('clinicalReportStatus');
    const metaNode = el('clinicalReportMeta');
    if (!hero || !stageNode || !narrativeNode) return;

    if (!report) {
      if (stageNode) stageNode.textContent = '—';
      if (narrativeNode) {
        narrativeNode.innerHTML = '<p>选择病例并完成分割后，此处显示 T 分期文字报告。</p>';
        narrativeNode.classList.add('is-placeholder');
      }
      if (metaNode) metaNode.textContent = '';
      return;
    }

    const stage = report?.recommended_stage || (report?.stage_distribution ? topStage(report.stage_distribution)[0] : '—');
    const conf = report?.calibrated_confidence ?? 0;
    const llmError = report?.llm_report?.error;
    const narrative = pickDisplayNarrative(report);
    const loading = Boolean(options.loading);

    hero.classList.toggle('loading', loading);
    hero.classList.toggle('ready', Boolean(narrative) && !loading);

    stageNode.textContent = stage;
    if (confNode) {
      const pct = Math.round(conf * 100);
      confNode.textContent = loading ? '生成中…' : `置信 ${pct}%`;
      confNode.className = `clinical-report-confidence ${conf >= 0.72 && !loading ? '' : 'warn'}`;
    }
    if (statusNode) {
      if (loading) statusNode.textContent = '正在撰写…';
      else if (llmError) statusNode.textContent = '生成失败';
      else if (narrative) statusNode.textContent = '已生成';
      else if (report?.sam_score != null) statusNode.textContent = '已分割 · 可生成报告';
      else statusNode.textContent = '等待分割';
    }
    if (loading) {
      narrativeNode.innerHTML = '<span class="interactive-loading"><span class="interactive-spinner"></span>正在生成 T 分期文字报告，请稍候…</span>';
      narrativeNode.classList.remove('is-placeholder');
    } else if (llmError && !narrative) {
      const err = String(llmError);
      let friendly = err;
      if (err.includes('401')) {
        friendly = 'LLM 鉴权失败：请确认 DeepSeek / MiniMax 密钥已加载，并重启 serve_interactive_sam_agent.py';
      } else if (err.includes('429') || err.includes('用量上限') || err.includes('rate_limit')) {
        friendly = 'LLM 用量已满（MiniMax Token Plan）。已优先尝试 DeepSeek；若仍失败请检查 DEEPSEEK_API_KEY 或升级套餐。';
      }
      narrativeNode.innerHTML = `<p class="report-error">报告生成失败：${escapeHtml(friendly)}</p>`;
      narrativeNode.classList.remove('is-placeholder');
    } else if (narrative) {
      narrativeNode.innerHTML = formatNarrativeHtml(narrative);
      narrativeNode.classList.remove('is-placeholder');
      if (options.scrollIntoView) scrollClinicalReportIntoView();
    } else {
      narrativeNode.innerHTML = '<p>完成病灶分割后，点击「生成文字报告」；完成边界方向判读后亦会自动更新。</p>';
      narrativeNode.classList.add('is-placeholder');
    }
    if (metaNode) {
      const parts = [];
      if (report?.sam_score != null) parts.push(`分割 ${Math.round(report.sam_score * 100)}%`);
      if (state.lastPromptMeta) {
        parts.push(`${state.lastPromptMeta.num_positive} 正 / ${state.lastPromptMeta.num_negative} 负`);
        if (state.lastPromptMeta.has_box) parts.push('已框选');
        if (state.lastPromptMeta.cascade_box) parts.push('级联框');
        if (state.lastPromptMeta.auto_center_point) parts.push('框心点');
      }
      if (report?.elapsed_ms) parts.push(`${report.elapsed_ms} ms`);
      const adjCount = Object.keys(state.boundaryAdjudications || {}).length;
      if (adjCount) parts.push(`边界判读 ${adjCount}`);
      metaNode.textContent = parts.join(' · ');
    }
  }

  function scheduleBoundaryReport() {
    if (!llmReportConfigured()) return;
    const adjCount = Object.keys(state.boundaryAdjudications || {}).length;
    if (!adjCount) return;
    if (state.boundaryReportTimer) clearTimeout(state.boundaryReportTimer);
    state.boundaryReportTimer = setTimeout(() => {
      state.boundaryReportTimer = null;
      generateLlmReport({ auto: true, boundaryTriggered: true });
    }, 2000);
  }

  function markUserEditing() {
    state.userEditUntil = performance.now() + 2500;
  }

  function scheduleLlmReport() {
    if (!llmReportConfigured()) return;
    if (!hasUserPrompt()) return;
    if (state.llmDebounceTimer) clearTimeout(state.llmDebounceTimer);
    state.llmDebounceTimer = setTimeout(() => {
      state.llmDebounceTimer = null;
      generateLlmReport({ auto: true });
    }, 1500);
  }

  async function generateLlmReport(options = {}) {
    if (!state.samBackend) {
      showToast('分割服务未连接，无法生成报告', 'warn');
      return;
    }
    if (!hasUserPrompt() && !options.forceAuto) {
      showToast('请先框选区域或添加标注点', 'warn');
      return;
    }
    if (state.reportGenerating) return;
    state.reportGenerating = true;
    const btn = el('generateReportBtn');
    if (btn) btn.disabled = true;
    renderClinicalReport(state.lastReport || {}, { loading: true });
    showVideoBadge('正在生成报告…', true);
    try {
      const data = await callSamBackend(buildPromptPayload(), { llmReport: true });
      state.maskPolygon = normalizeMaskPolygon(data.mask_polygon, data.frame_size, el('studyVideo')) || state.maskPolygon;
      state.lastPromptMeta = data.prompt_meta || state.lastPromptMeta;
      const report = {
        ...(state.lastReport || {}),
        ...data.report,
        sam_score: data.sam_score,
        elapsed_ms: data.elapsed_ms,
      };
      state.lastReport = report;
      state.lastFullReportMs = performance.now();
      renderReport(report);
      renderClinicalReport(report, { scrollIntoView: true });
      redrawOverlay();
      renderBoundaryDetailPanel();
      showToast(options.auto ? '文字报告已自动更新' : '文字报告已生成', 'ok');
    } catch (err) {
      console.error(err);
      renderClinicalReport({
        ...(state.lastReport || {}),
        llm_report: { error: err.message || '未知错误' },
      }, { loading: false });
      showToast(`报告生成失败：${err.message}`, 'warn');
    } finally {
      state.reportGenerating = false;
      if (btn) btn.disabled = false;
      updateGenerateReportBtn();
      hideVideoBadge();
    }
  }

  function buildPromptPayload() {
    return {
      type: 'prompt',
      box: state.box,
      clicks: state.clicks.map((c) => ({
        x: c.imageX,
        y: c.imageY,
        label: c.label,
      })),
    };
  }

  function hasUserPrompt() {
    return Boolean(state.box) || state.clicks.length > 0;
  }

  function showVideoBadge(text, loading) {
    const badge = el('samVideoBadge');
    if (!badge) return;
    badge.classList.remove('hidden');
    badge.innerHTML = loading
      ? `<span class="interactive-spinner"></span>${text}`
      : text;
  }

  function hideVideoBadge() {
    el('samVideoBadge')?.classList.add('hidden');
  }

  function updateTrackButtonUi() {
    const btn = el('trackPlayBtn');
    if (!btn) return;
    btn.textContent = state.trackOnPlay ? '播放跟踪 · 开' : '播放跟踪 · 关';
    btn.classList.toggle('active', state.trackOnPlay);
  }

  function scheduleVideoTrack(force) {
    const video = el('studyVideo');
    if (!video || video.paused || !state.trackOnPlay || !hasUserPrompt()) return;
    if (performance.now() < state.userEditUntil) return;
    const now = performance.now();
    if (!force && now - state.lastTrackMs < TRACK_INTERVAL_MS) return;
    if (state.trackBusy || state.analyzing) {
      state.pendingTrack = true;
      return;
    }
    state.lastTrackMs = now;
    runSamUpdate({ silent: true, prompt: buildPromptPayload() });
  }

  async function runSamFastUpdate() {
    markUserEditing();
    const prompt = buildPromptPayload();
    const requestId = ++state.trackRequestId;
    showVideoBadge('正在分割…', true);
    try {
      const data = await callSamBackend(prompt, { llmReport: false });
      if (requestId !== state.trackRequestId) return;
      state.maskPolygon = normalizeMaskPolygon(data.mask_polygon, data.frame_size, el('studyVideo'));
      state.lastMaskOverlayPng = data.mask_overlay_png || null;
      state.lastPromptMeta = data.prompt_meta || null;
      updatePromptCounter({
        samScore: data.sam_score,
        refined: Boolean(data.prompt_meta?.refinement_passes),
      });
      redrawOverlay();
      flashMaskUpdate();
      renderBoundaryDetailPanel();
      refreshLayerAnalysis({ silent: false });
      updateInteractionModeUi();
      updateMaskControlBar();
      updateGenerateReportBtn();
      showVideoBadge(
        `分割 ${Math.round((data.sam_score || 0) * 100)}% · ${data.prompt_meta?.num_points || 0} 点${data.prompt_meta?.has_box ? ' · 已框选' : ''}`,
        false,
      );
      showToast(`分割完成 · 质量 ${Math.round((data.sam_score || 0) * 100)}%`, 'ok');
      if (!state.lastReport?.llm_report?.narrative) {
        const hint = llmReportConfigured()
          ? '分割已完成，文字报告将自动更新。'
          : '分割已完成，可点击「生成文字报告」。';
        renderClinicalReport({
          ...(state.lastReport || {}),
          sam_score: data.sam_score,
          summary: hint,
        });
      }
      if (state.lastReport) {
        state.lastReport = {
          ...state.lastReport,
          sam_score: data.sam_score,
          elapsed_ms: data.elapsed_ms,
        };
      }
      scheduleLlmReport();
    } catch (err) {
      console.error(err);
      showVideoBadge(`分割失败：${err.message}`, false);
    }
  }

  function normalizeMaskPolygon(rawPoly, frameSize, video) {
    if (!Array.isArray(rawPoly) || rawPoly.length < 3) return null;
    const width = Number(frameSize?.width || video?.videoWidth || 1);
    const height = Number(frameSize?.height || video?.videoHeight || 1);
    const points = rawPoly
      .filter((point) => Array.isArray(point) && point.length >= 2)
      .map((point) => [Number(point[0]), Number(point[1])])
      .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
    if (points.length < 3) return null;
    const maxX = Math.max(...points.map(([x]) => Math.abs(x)));
    const maxY = Math.max(...points.map(([, y]) => Math.abs(y)));
    const pixelSpace = maxX > 1.5 || maxY > 1.5;
    return points.map(([x, y]) => [
      Math.min(1, Math.max(0, pixelSpace ? x / width : x)),
      Math.min(1, Math.max(0, pixelSpace ? y / height : y)),
    ]);
  }

  function polygonImagePoints(normPoly, video) {
    const vw = video.videoWidth || 1;
    const vh = video.videoHeight || 1;
    const normalized = normalizeMaskPolygon(normPoly, { width: vw, height: vh }, video) || [];
    return normalized.map(([nx, ny]) => [nx * vw, ny * vh]);
  }

  function polygonCentroid(points) {
    if (!points.length) return { x: 0, y: 0 };
    const x = points.reduce((s, p) => s + p[0], 0) / points.length;
    const y = points.reduce((s, p) => s + p[1], 0) / points.length;
    return { x, y };
  }

  function renderBoundaryDetailPanel() {
    if (window.BoundaryWorkbench) {
      window.BoundaryWorkbench.rebuildSectors(state, currentCase()?.case_id);
    }
  }

  function clearBoundaryDetailPanel() {
    if (window.BoundaryWorkbench) {
      window.BoundaryWorkbench.onCaseClear(state);
    }
  }

  function captureVideoFrame(video) {
    const vw = video.videoWidth || 1;
    const vh = video.videoHeight || 1;
    const canvas = document.createElement('canvas');
    canvas.width = vw;
    canvas.height = vh;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, vw, vh);
    return { canvas, ctx, vw, vh };
  }

  function drawPolygonOnCtx(ctx, normPoly, vw, vh, stroke, fill, lineWidth) {
    if (!normPoly?.length) return;
    ctx.beginPath();
    normPoly.forEach(([nx, ny], idx) => {
      const x = nx * vw;
      const y = ny * vh;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    if (fill) {
      ctx.fillStyle = fill;
      ctx.fill();
    }
    if (stroke) {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = lineWidth || 2;
      ctx.stroke();
    }
  }

  function updateBoundaryLoupe(clientX, clientY) {
    const loupe = el('boundaryLoupe');
    const loupeCanvas = el('boundaryLoupeCanvas');
    const video = el('studyVideo');
    const overlay = el('overlayCanvas');
    if (!loupe || !loupeCanvas || state.interactionMode !== 'inspect') return;

    const mapped = mapClientToImageCoords(clientX, clientY, video);
    if (!mapped.inVideo) {
      loupe.classList.add('hidden');
      state.loupePoint = null;
      return;
    }

    const stage = el('viewerStage').getBoundingClientRect();
    const overlayRect = overlay.getBoundingClientRect();
    const localX = clientX - overlayRect.left;
    const localY = clientY - overlayRect.top;
    const loupeSize = 120;
    let left = localX + 18;
    let top = localY + 18;
    if (left + loupeSize > overlayRect.width) left = localX - loupeSize - 18;
    if (top + loupeSize > overlayRect.height) top = localY - loupeSize - 18;
    loupe.style.left = `${Math.max(4, left)}px`;
    loupe.style.top = `${Math.max(4, top)}px`;
    loupe.classList.remove('hidden');

    const { canvas: frameCanvas, vw, vh } = captureVideoFrame(video);
    const half = BOUNDARY_PATCH_SRC / 2;
    const sx = Math.max(0, Math.min(vw - BOUNDARY_PATCH_SRC, mapped.x - half));
    const sy = Math.max(0, Math.min(vh - BOUNDARY_PATCH_SRC, mapped.y - half));
    const ctx = loupeCanvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.clearRect(0, 0, loupeCanvas.width, loupeCanvas.height);
    ctx.drawImage(
      frameCanvas,
      sx,
      sy,
      BOUNDARY_PATCH_SRC,
      BOUNDARY_PATCH_SRC,
      0,
      0,
      loupeCanvas.width,
      loupeCanvas.height,
    );

    if (state.maskPolygon?.length) {
      ctx.save();
      ctx.translate(-sx * BOUNDARY_ZOOM, -sy * BOUNDARY_ZOOM);
      ctx.scale(BOUNDARY_ZOOM, BOUNDARY_ZOOM);
      drawPolygonOnCtx(
        ctx,
        state.maskPolygon,
        vw,
        vh,
        'rgba(251, 191, 36, 0.95)',
        'rgba(103, 212, 255, 0.15)',
        3,
      );
      ctx.restore();
    }

    const cx = (mapped.x - sx) * BOUNDARY_ZOOM;
    const cy = (mapped.y - sy) * BOUNDARY_ZOOM;
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 10, cy);
    ctx.lineTo(cx + 10, cy);
    ctx.moveTo(cx, cy - 10);
    ctx.lineTo(cx, cy + 10);
    ctx.stroke();
    state.loupePoint = { x: mapped.x, y: mapped.y };
  }

  function mapNormToCanvas(nx, ny, video, canvas) {
    const stage = el('viewerStage').getBoundingClientRect();
    const t = videoDisplayTransform(video);
    const offsetX = t.rect.left - stage.left + t.offsetX;
    const offsetY = t.rect.top - stage.top + t.offsetY;
    return {
      x: offsetX + nx * t.vw * t.scale,
      y: offsetY + ny * t.vh * t.scale,
    };
  }

  async function fetchSamStatus() {
    try {
      const res = await fetch('/api/sam/status', { credentials: 'same-origin', cache: 'no-store' });
      if (!res.ok) throw new Error('status failed');
      state.samBackend = await res.json();
      const badge = el('samBackendBadge');
      if (badge) {
        const modelShort = String(state.samBackend.model || '').replace(/^facebook\//, '');
        const mm = llmReportConfigured() ? ' · 报告' : '';
        const ft = state.samBackend.finetune?.val_dice_mask
          ? ` · 微调${Math.round(state.samBackend.finetune.val_dice_mask * 1000) / 10}%`
          : state.samBackend.finetune ? ' · 微调' : '';
        badge.textContent = state.samBackend.cuda
          ? `分割 · ${modelShort}${ft}${mm}`
          : `分割 · CPU${ft}${mm}`;
      }
      updateGenerateReportBtn();
    } catch {
      const badge = el('samBackendBadge');
      if (badge) badge.textContent = '分割离线（演示）';
      state.samBackend = null;
    }
  }

  function formatClock(seconds) {
    if (!Number.isFinite(seconds)) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function stageDistribution(caseItem, click) {
    const seed = hashSeed(`${caseItem.case_id}:${click?.x || 0}:${click?.y || 0}:${state.frameIndex}`);
    const rand = seededRandom(seed);
    const ref = caseItem.reference_pt || 'T2';
    const refIndex = STAGES.indexOf(ref);
    const base = STAGES.map((_, idx) => {
      const dist = Math.abs(idx - (refIndex >= 0 ? refIndex : 1));
      return Math.max(0.04, 1.1 - dist * 0.28 + rand() * 0.08);
    });
    if (click) {
      base[refIndex >= 0 ? refIndex : 1] += 0.08;
    }
    const sum = base.reduce((a, b) => a + b, 0);
    const probs = {};
    STAGES.forEach((stage, idx) => {
      probs[stage] = base[idx] / sum;
    });
    return probs;
  }

  function topStage(probs) {
    return Object.entries(probs).sort((a, b) => b[1] - a[1])[0];
  }

  function buildKeyFrames(video) {
    const duration = Number.isFinite(video.duration) ? video.duration : 12;
    const caseItem = currentCase();
    const rand = seededRandom(hashSeed(`${caseItem.case_id}:keyframes`));
    const count = 3 + Math.floor(rand() * 3);
    const frames = [];
    for (let i = 0; i < count; i += 1) {
      const t = duration * (0.12 + rand() * 0.76);
      frames.push({
        time: t,
        score: 0.55 + rand() * 0.4,
        recommended: i < 2,
      });
    }
    frames.sort((a, b) => a.time - b.time);
    state.keyFrames = frames;
    renderKeyFrames(video);
  }

  function renderCaseList() {
    const list = el('caseList');
    list.innerHTML = state.cases.map((caseItem, idx) => {
      const active = idx === state.currentIndex ? 'active' : '';
      return `<div class="interactive-case-chip ${active}" data-index="${idx}">
        <div class="case-chip-labels">
          <span>${caseItem.display_id || caseItem.case_id}</span>
          <span style="color:var(--muted)">${caseItem.case_id}</span>
        </div>
        ${caseModeBadge(caseItem)}
      </div>`;
    }).join('');
    list.querySelectorAll('.interactive-case-chip').forEach((node) => {
      node.addEventListener('click', () => {
        state.currentIndex = Number(node.dataset.index);
        state.frameIndex = 0;
        state.clicks = [];
        state.box = null;
        state.dragBox = null;
        state.lastReport = null;
        state.maskPolygon = null;
        state.lastMaskOverlayPng = null;
        state.layerResult = null;
        state.wallPtsManual = null;
        state.wallOffsetPx = null;
        state.layerPickImage = null;
        clearBoundaryDetailPanel();
        loadCurrentVideo();
        renderCaseList();
        renderEmptyAgent('已切换病例。可点击「自动分析」或直接在视频上点击病灶。');
        const layerPanel = el('layerBridgePanel');
        if (layerPanel) {
          layerPanel.innerHTML = '<div class="interactive-empty">完成分割后，对当前视频帧做像素回声分层</div>';
        }
        clearOverlay();
        updateMaskControlBar();
        updateGenerateReportBtn();
      });
    });
    const total = state.cases.length;
    el('caseCounter').textContent = total ? `${state.currentIndex + 1} / ${total} · ${cohortLabel(state.caseCohort)}` : '0';
  }

  function renderEmptyAgent(message) {
    el('agentConclusion').innerHTML = `<div class="interactive-empty">${message}</div>`;
    el('agentStages').innerHTML = '';
    el('agentTools').innerHTML = '';
    el('agentEvidence').innerHTML = '';
    el('agentSimilar').innerHTML = '';
    el('reviewFlag').textContent = '待分析';
    el('reviewFlag').className = 'interactive-confidence';
    renderClinicalReport(null);
    updateMaskControlBar();
    updateGenerateReportBtn();
    clearBoundaryDetailPanel();
  }

  function renderKeyFrames(video) {
    const bar = el('keyframeBar');
    const duration = Number.isFinite(video.duration) ? video.duration : 1;
    bar.innerHTML = state.keyFrames.map((frame, idx) => {
      const left = Math.min(98, Math.max(2, (frame.time / duration) * 100));
      const cls = `${frame.recommended ? 'recommended' : ''}`;
      return `<div class="interactive-keyframe-marker ${cls}" data-index="${idx}" style="left:${left}%"
        title="推荐帧 ${formatClock(frame.time)} · score ${frame.score.toFixed(2)}"></div>`;
    }).join('');
    bar.querySelectorAll('.interactive-keyframe-marker').forEach((node) => {
      node.addEventListener('click', () => {
        const idx = Number(node.dataset.index);
        video.currentTime = state.keyFrames[idx].time;
        video.pause();
        bar.querySelectorAll('.interactive-keyframe-marker').forEach((m) => m.classList.remove('active'));
        node.classList.add('active');
      });
    });
  }

  function loadCurrentVideo() {
    clearExternalMedia();
    const video = el('studyVideo');
    const frame = currentFrame();
    if (!frame) return;
    video.removeAttribute('crossorigin');
    const src = imageUrl(frame.video_rel);
    video.removeAttribute('src');
    video.src = src;
    video.playbackRate = window.READER_CASES?.viewer_policy?.default_video_speed || 0.25;
    video.onerror = () => {
      const code = video.error?.code;
      showToast(`视频加载失败（${frame.video_rel || 'unknown'} · code=${code || '?'}）`, 'warn');
      el('videoClock').textContent = '加载失败';
      el('frameTitle').textContent = `视频加载失败 · ${frame.axis_label || ''}`;
    };
    video.load();
    video.onloadedmetadata = () => {
      buildKeyFrames(video);
      el('videoClock').textContent = `00:00 / ${formatClock(video.duration)}`;
      showToast(`视频已加载 · ${formatClock(video.duration)}`, 'ok');
    };
    video.ontimeupdate = () => {
      el('videoClock').textContent = `${formatClock(video.currentTime)} / ${formatClock(video.duration)}`;
      el('timelineSeek').value = video.duration ? String((video.currentTime / video.duration) * 1000) : '0';
      scheduleVideoTrack(false);
    };
    clearOverlay();
    el('caseTitle').textContent = `${currentCase().display_id} · ${currentCase().case_id}`;
    el('frameTitle').textContent = frame.axis_label || `视频 ${state.frameIndex + 1}`;
  }

  function resizeOverlayCanvas() {
    const canvas = el('overlayCanvas');
    const stage = el('viewerStage');
    const rect = stage.getBoundingClientRect();
    canvas.width = Math.round(rect.width);
    canvas.height = Math.round(rect.height);
    redrawOverlay();
  }

  function clearOverlay() {
    state.clicks = [];
    state.box = null;
    state.dragBox = null;
    updatePromptCounter();
    redrawOverlay();
  }

  function drawBoxRect(ctx, rect, dashed) {
    ctx.save();
    ctx.strokeStyle = 'rgba(251, 191, 36, 0.95)';
    ctx.fillStyle = 'rgba(251, 191, 36, 0.12)';
    ctx.lineWidth = 2;
    if (dashed) ctx.setLineDash([6, 4]);
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
    ctx.restore();
  }

  function updateBoundaryGuideBarVisibility() {
    const bar = el('boundaryGuideBar');
    if (bar) {
      const hasMask = state.maskPolygon?.length >= 3;
      bar.classList.toggle('is-hidden', !hasMask || !boundaryDirectionsEnabled());
    }
    updateMaskControlBar();
  }

  function redrawOverlay() {
    const canvas = el('overlayCanvas');
    const ctx = canvas.getContext('2d');
    const video = el('studyVideo');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (state.showMaskOverlay !== false && state.maskPolygon?.length >= 3) {
      const drew = window.BoundaryWorkbench
        ? window.BoundaryWorkbench.drawMaskOnOverlay(state, ctx, video)
        : false;
      if (!drew) {
        ctx.save();
        ctx.beginPath();
        state.maskPolygon.forEach((pt, idx) => {
          const mapped = mapNormToCanvas(pt[0], pt[1], video, canvas);
          if (idx === 0) ctx.moveTo(mapped.x, mapped.y);
          else ctx.lineTo(mapped.x, mapped.y);
        });
        ctx.closePath();
        ctx.fillStyle = 'rgba(103, 212, 255, 0.22)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(251, 191, 36, 0.85)';
        ctx.lineWidth = 5;
        ctx.stroke();
        ctx.strokeStyle = 'rgba(103, 212, 255, 0.95)';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
      }

      if (window.BoundaryWorkbench) {
        window.BoundaryWorkbench.drawOverlayExtras(state, ctx, video);
      } else if (state.boundarySamples.length) {
        state.boundarySamples.forEach((sample) => {
          const mapped = mapImageToCanvas(sample.x, sample.y, video);
          ctx.save();
          ctx.strokeStyle = sample.accent;
          ctx.fillStyle = sample.accent;
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(mapped.x, mapped.y, 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        });
      }

      if (state.layerResult?.ok && window.LayerBridge?.drawLayerOverlay) {
        window.LayerBridge.drawLayerOverlay(state.layerResult, ctx, mapImageToCanvas, video);
      }
    } else if (state.lastReport?.mask) {
      const m = state.lastReport.mask;
      ctx.save();
      ctx.strokeStyle = 'rgba(103, 212, 255, 0.95)';
      ctx.fillStyle = 'rgba(103, 212, 255, 0.18)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(m.cx, m.cy, m.rx, m.ry, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }

    state.clicks.forEach((click, idx) => {
      ctx.save();
      ctx.beginPath();
      ctx.fillStyle = click.label === 'negative' ? 'rgba(248, 113, 113, 0.95)' : 'rgba(92, 227, 161, 0.95)';
      ctx.arc(click.x, click.y, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = '#fff';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(idx + 1), click.x, click.y);
      ctx.restore();
    });

    if (state.box) {
      drawBoxRect(ctx, canvasRectFromImageBox(state.box, video), false);
    }
    if (state.dragBox) {
      drawBoxRect(ctx, canvasRectFromImageBox(state.dragBox, video), true);
    }
    updateBoundaryGuideBarVisibility();
  }

  function deriveMaskFromClick(click, canvas) {
    const rx = Math.max(36, canvas.width * 0.08);
    const ry = Math.max(28, canvas.height * 0.07);
    return { cx: click.x, cy: click.y, rx, ry };
  }

  async function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function renderToolSteps(activeIdx, statuses) {
    el('agentTools').innerHTML = TOOL_STEPS.map((step, idx) => {
      let cls = '';
      if (idx < activeIdx) cls = statuses[idx] || 'done';
      else if (idx === activeIdx) cls = 'running';
      return `<div class="interactive-tool-step ${cls}">
        <div class="interactive-tool-dot"></div>
        <div>
          <div><strong>${step.title}</strong></div>
          <div style="color:var(--muted);margin-top:2px">${step.detail}</div>
        </div>
      </div>`;
    }).join('');
  }

  function renderStageBars(probs) {
    el('agentStages').innerHTML = STAGES.map((stage) => {
      const pct = Math.round((probs[stage] || 0) * 100);
      return `<div class="interactive-stage-row">
        <span>${stage}</span>
        <div class="interactive-stage-bar"><span style="width:${pct}%"></span></div>
        <span>${pct}%</span>
      </div>`;
    }).join('');
  }

  function renderReport(report) {
    const stage = report.recommended_stage || topStage(report.stage_distribution)[0];
    const prob = report.stage_distribution?.[stage] || report.calibrated_confidence || 0;
    const confidenceClass = report.calibrated_confidence >= 0.72 ? 'high' : '';
    const video = el('studyVideo');
    const frameTime = formatClock(video?.currentTime || 0);
    const hasLlm = Boolean(report.llm_report?.narrative);
    const samLine = report.sam_score != null
      ? `<div class="report-meta-line">分割质量 ${(report.sam_score * 100).toFixed(0)}% · 耗时 ${report.elapsed_ms || '—'} ms</div>`
      : '';
    const metaLine = state.lastPromptMeta
      ? `<div class="report-meta-line">交互：${state.lastPromptMeta.num_positive} 正向 / ${state.lastPromptMeta.num_negative} 负向${state.lastPromptMeta.has_box ? ' · 已框选' : ''}</div>`
      : '';
    el('agentConclusion').innerHTML = `
      <div class="report-summary-grid">
        <div class="report-summary-item"><span>推荐分期</span><strong>${stage}</strong></div>
        <div class="report-summary-item"><span>置信度</span><strong>${Math.round((report.calibrated_confidence || prob) * 100)}%</strong></div>
        <div class="report-summary-item"><span>当前帧</span><strong>${frameTime}</strong></div>
        <div class="report-summary-item"><span>复核</span><strong class="${report.review_flag ? 'warn' : 'ok'}">${report.review_flag ? '建议复核' : '可辅助参考'}</strong></div>
      </div>
      ${hasLlm ? '' : `<div class="report-brief-text">${escapeHtml(report.summary || '—')}</div>`}
      ${samLine}${metaLine}`;
    renderClinicalReport(report);
    renderStageBars(report.stage_distribution);
    el('reviewFlag').textContent = report.review_flag ? '建议医生复核' : '可辅助采纳';
    el('reviewFlag').className = `interactive-confidence ${report.review_flag ? '' : 'high'}`;
    const boundaryEvidence = window.BoundaryWorkbench
      ? window.BoundaryWorkbench.getEvidenceItems(state)
      : [];
    const baseEvidence = (report.evidence || []).filter((item) => {
      if (!hasLlm) return true;
      const title = String(item.title || '').toLowerCase();
      return !title.includes('minimax')
        && !title.includes('report')
        && !title.includes('文字报告');
    });
    const allEvidence = [...baseEvidence, ...boundaryEvidence];
    el('agentEvidence').innerHTML = allEvidence.map((item) => `
      <div class="interactive-evidence-item">
        <strong>${item.title}</strong><br>${item.detail}
      </div>`).join('');
    el('agentSimilar').innerHTML = report.similar_cases.map((item) => `
      <div class="interactive-evidence-item">
        <strong>${item.case_id}</strong> · ${item.stage} · 相似度 ${Math.round(item.score * 100)}%<br>
        ${item.note}
      </div>`).join('');
    renderBoundaryDetailPanel();
    redrawOverlay();
  }

  function buildMockReport(caseItem, click, canvas, box) {
    const probs = stageDistribution(caseItem, click || box);
    const [stage, prob] = topStage(probs);
    const mask = click ? deriveMaskFromClick(click, canvas) : null;
    const wallThickness = (2.8 + (hashSeed(caseItem.case_id) % 60) / 10).toFixed(1);
    const normalWall = (2.8 + (hashSeed(`${caseItem.case_id}:normal`) % 8) / 10).toFixed(1);
    const outerRisk = Math.min(0.92, Math.max(0.18, probs.T3 + probs['T4+'] + 0.08)).toFixed(2);
    const video = el('studyVideo');
    const frameTime = formatClock(video.currentTime || 0);
    return {
      recommended_stage: stage,
      stage_distribution: probs,
      calibrated_confidence: Math.min(0.88, Math.max(0.46, prob + (click || box ? 0.04 : -0.06))),
      review_flag: prob < 0.68 || stage === 'T2' || stage === 'T3',
      mask,
      summary: box
        ? `已在 ${frameTime} 处框选病灶并完成分割，T 分期建议已更新。`
        : click
        ? `已在 ${frameTime} 处标注病灶并完成分割，壁层证据与 T 分期建议已更新。`
        : '已扫描关键帧并给出 T 分期建议，请结合边界判读复核。',
      evidence: [
        {
          title: '关键帧',
          detail: `当前分析帧 ${frameTime}；推荐优先查看 ${state.keyFrames.slice(0, 2).map((f) => formatClock(f.time)).join('、') || '—'}。`,
        },
        {
          title: '壁厚证据',
          detail: `病灶处壁厚约 ${wallThickness} mm，邻近正常胃壁约 ${normalWall} mm；外缘突破风险 ${outerRisk}。`,
        },
        ...(state.layerResult?.ok && state.layerResult.layer
          ? [{
              title: '胃壁分层',
              detail: `${state.layerResult.layer.label || ''}（${state.layerResult.layer.tHint || '—'}）；${state.layerResult.inContact ? '接触弧内' : '未接触'}；${state.layerResult.source?.badge || '像素回声分层'}。`,
            }]
          : []),
        {
          title: '交互提示',
          detail: box
            ? `框选区域 (${Math.round(box.x1)},${Math.round(box.y1)})–(${Math.round(box.x2)},${Math.round(box.y2)}) 已参与判读。`
            : click
            ? `标注点 (${Math.round(click.x)}, ${Math.round(click.y)}) 已参与判读。`
            : '尚未标注；可框选区域、添加正负点或自动分析。',
        },
        {
          title: '判读建议',
          detail: stage === 'T2' || stage === 'T3'
            ? 'T2/T3 边界病例，建议结合 AI 高亮帧与壁层证据人工复核。'
            : '当前证据一致性较好，可作为第二意见参考。',
        },
      ],
      similar_cases: [
        { case_id: '病例-023', stage: 'T2', score: 0.84, note: '外缘形态相似，历史证实 T2。' },
        { case_id: '病例-048', stage: 'T3', score: 0.79, note: '外壁突破风险相近，可作边界对照。' },
        { case_id: '病例-071', stage: stage, score: 0.76, note: '病灶位置与层次分布相近。' },
      ],
    };
  }

  function captureFrameDataUrl(video) {
    if (window.LayerBridge?.captureVideoFrameDataUrl) {
      return window.LayerBridge.captureVideoFrameDataUrl(video);
    }
    if (!video?.videoWidth) return null;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.92);
  }

  async function callSamBackend(prompt, options = {}) {
    const caseItem = currentCase();
    const frame = currentFrame();
    const video = el('studyVideo');
    if (!video.videoWidth || !video.videoHeight) {
      throw new Error('Video frame not ready');
    }
    const link = state.deepLink || {};
    const useFrameUpload = true; // workstation GPU has no Aliyun video paths
    const payload = {
      case_id: caseItem?.case_id || link.caseId || link.patientId || 'external',
      video_rel: useFrameUpload ? '' : frame.video_rel,
      frame_time: useFrameUpload ? 0 : (video.currentTime || 0),
      image_width: video.videoWidth,
      image_height: video.videoHeight,
      clicks: [],
      llm_report: Boolean(options.llmReport),
    };
    if (useFrameUpload) {
      const dataUrl = captureFrameDataUrl(video);
      if (!dataUrl) throw new Error('无法截取当前帧');
      payload.frame_png_b64 = dataUrl;
    }
    if (window.BoundaryWorkbench && options.llmReport) {
      payload.boundary_sectors = window.BoundaryWorkbench.getBoundaryContextForApi(state);
    }

    if (prompt?.type === 'prompt' || prompt?.type === 'box' || prompt?.type === 'click') {
      const clicks = prompt.clicks || (prompt.click ? [{
        x: prompt.click.imageX,
        y: prompt.click.imageY,
        label: prompt.click.label,
      }] : state.clicks.map((c) => ({
        x: c.imageX,
        y: c.imageY,
        label: c.label,
      })));
      payload.clicks = clicks;
      const box = prompt.box || state.box;
      if (box) {
        payload.box = {
          x1: box.x1,
          y1: box.y1,
          x2: box.x2,
          y2: box.y2,
        };
      }
    } else {
      payload.clicks = [{
        x: video.videoWidth / 2,
        y: video.videoHeight / 2,
        label: 'positive',
      }];
    }
    const res = await fetch('/api/sam/interactive-analyze', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.status === 401) {
      const next = location.pathname + location.search;
      location.href = '/task1.html?next=' + encodeURIComponent(next || '/interactive_video_agent.html');
      throw new Error('需要登录');
    }
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async function runSamUpdate(options = {}) {
    const silent = Boolean(options.silent);
    const skipAnimation = Boolean(options.skipAnimation);
    const prompt = options.prompt ?? buildPromptPayload();
    const fullReport = options.fullReport ?? !silent;

    if (silent) {
      if (state.trackBusy) {
        state.pendingTrack = true;
        return;
      }
      state.trackBusy = true;
      showVideoBadge('跟踪分割…', true);
    } else if (!skipAnimation) {
      state.analyzing = true;
      el('analyzeBtn').disabled = true;
      showVideoBadge('正在分割…', true);
    } else {
      showVideoBadge('生成报告…', true);
    }

    const link = state.deepLink || {};
    const caseItem = currentCase() || {
      case_id: link.caseId || link.patientId || 'external',
      display_id: link.title || link.patientId || '外部帧',
    };
    const canvas = el('overlayCanvas');
    const requestId = ++state.trackRequestId;

    try {
      if (!silent && !skipAnimation) {
        const statuses = [];
        const hasPrompt = prompt?.type !== 'auto';
        for (let i = 0; i < TOOL_STEPS.length; i += 1) {
          renderToolSteps(i, statuses);
          await sleep(hasPrompt ? 80 : 120);
          statuses[i] = i === 2 && !hasPrompt ? 'warn' : 'done';
        }
        renderToolSteps(TOOL_STEPS.length, statuses);
      }

      let report;
      if (state.samBackend) {
        const data = await callSamBackend(prompt, { llmReport: fullReport && !silent });
        if (requestId !== state.trackRequestId) return;
        state.maskPolygon = normalizeMaskPolygon(data.mask_polygon, data.frame_size, el('studyVideo'));
        state.lastMaskOverlayPng = data.mask_overlay_png || null;
        state.lastPromptMeta = data.prompt_meta || null;
        updatePromptCounter({
          samScore: data.sam_score,
          refined: Boolean(data.prompt_meta?.refinement_passes),
        });
        report = {
          ...data.report,
          sam_score: data.sam_score,
          elapsed_ms: data.elapsed_ms,
        };
      } else {
        const lastClick = state.clicks[state.clicks.length - 1] || null;
        report = buildMockReport(caseItem, lastClick, canvas, state.box);
        state.maskPolygon = null;
      }

      const now = performance.now();
      redrawOverlay();

      if (fullReport || !state.lastReport || now - state.lastFullReportMs >= FULL_REPORT_INTERVAL_MS) {
        state.lastReport = report;
        renderReport(report);
        state.lastFullReportMs = now;
        renderBoundaryDetailPanel();
        state.lastBoundaryMs = now;
        if (state.maskPolygon) flashMaskUpdate();
        if (state.maskPolygon) scheduleLayerAnalysis({ silent: silent });
        if (!silent) hideVideoBadge();
      } else {
        const video = el('studyVideo');
        showVideoBadge(
          `${formatClock(video.currentTime)} · 分割 ${Math.round((report.sam_score || 0) * 100)}%`,
          false,
        );
        if (now - state.lastBoundaryMs >= BOUNDARY_INTERVAL_MS) {
          renderBoundaryDetailPanel();
          state.lastBoundaryMs = now;
          if (state.maskPolygon) scheduleLayerAnalysis({ silent: true });
        }
      }
    } catch (err) {
      console.error(err);
      if (!silent) {
        const lastClick = state.clicks[state.clicks.length - 1] || null;
        const report = buildMockReport(caseItem, lastClick, canvas, state.box);
        state.lastReport = report;
        state.maskPolygon = null;
        renderReport({ ...report, summary: `${report.summary}（分割服务不可用，已切换演示模式：${err.message}）` });
        redrawOverlay();
        hideVideoBadge();
      }
    } finally {
      if (silent) {
        state.trackBusy = false;
        if (state.pendingTrack) {
          state.pendingTrack = false;
          scheduleVideoTrack(true);
        }
      } else {
        state.analyzing = false;
        el('analyzeBtn').disabled = false;
        if (!state.trackBusy) hideVideoBadge();
      }
    }
  }

  async function runAgentAnalysis(prompt) {
    const payload = prompt?.type === 'auto'
      ? prompt
      : (prompt || buildPromptPayload());
    return runSamUpdate({ silent: false, prompt: payload, fullReport: true });
  }

  function bindViewerEvents() {
    const overlayWrap = document.querySelector('.interactive-overlay');
    const overlay = el('overlayCanvas');
    const video = el('studyVideo');
    const seek = el('timelineSeek');
    const target = overlayWrap || overlay;

    function overlayPoint(event) {
      const rect = overlay.getBoundingClientRect();
      return {
        canvasX: event.clientX - rect.left,
        canvasY: event.clientY - rect.top,
        mapped: mapClientToImageCoords(event.clientX, event.clientY, video),
      };
    }

    function imageBoxSize(box) {
      if (!box) return 0;
      return Math.max(
        Math.abs(box.x2 - box.x1),
        Math.abs(box.y2 - box.y1),
      );
    }

    function onWindowBoxPointerMove(event) {
      if (!dragState.active || event.pointerId !== dragState.pointerId) return;
      const pt = overlayPoint(event);
      state.dragBox = {
        x1: dragState.startImage.x,
        y1: dragState.startImage.y,
        x2: pt.mapped.x,
        y2: pt.mapped.y,
      };
      redrawOverlay();
    }

    function cleanupBoxDragListeners() {
      window.removeEventListener('pointermove', onWindowBoxPointerMove);
      window.removeEventListener('pointerup', onWindowBoxPointerUp);
      window.removeEventListener('pointercancel', onWindowBoxPointerUp);
    }

    function onWindowBoxPointerUp(event) {
      if (!dragState.active || event.pointerId !== dragState.pointerId) return;
      finishBoxDrag(event);
      cleanupBoxDragListeners();
    }

    target.addEventListener('pointermove', (event) => {
      if (state.interactionMode === 'inspect') {
        updateBoundaryLoupe(event.clientX, event.clientY);
      }
    });

    target.addEventListener('pointerdown', (event) => {
      // Alt/Meta + click: pick infiltration direction for wall-layer analysis
      if ((event.altKey || event.metaKey) && state.maskPolygon?.length >= 3) {
        const pt = overlayPoint(event);
        if (!pt.mapped.inVideo) return;
        event.preventDefault();
        state.layerPickImage = { x: pt.mapped.x, y: pt.mapped.y };
        refreshLayerAnalysis({ silent: false });
        showToast('已按点击方向重算分层', 'ok');
        return;
      }
      if (state.interactionMode === 'inspect') return;
      if (state.interactionMode === 'boundary') {
        const pt = overlayPoint(event);
        if (!pt.mapped.inVideo || !state.maskPolygon?.length) return;
        event.preventDefault();
        video.pause();
        if (window.BoundaryWorkbench) {
          window.BoundaryWorkbench.handleBoundaryClick(state, pt.mapped.x, pt.mapped.y);
        }
        return;
      }
      if (state.interactionMode === 'box') {
        const pt = overlayPoint(event);
        if (!pt.mapped.inVideo) return;
        event.preventDefault();
        event.stopPropagation();
        dragState.active = true;
        dragState.pointerId = event.pointerId;
        dragState.startCanvas = { x: pt.canvasX, y: pt.canvasY };
        dragState.startImage = { x: pt.mapped.x, y: pt.mapped.y };
        state.dragBox = {
          x1: pt.mapped.x,
          y1: pt.mapped.y,
          x2: pt.mapped.x,
          y2: pt.mapped.y,
        };
        video.pause();
        redrawOverlay();
        window.addEventListener('pointermove', onWindowBoxPointerMove);
        window.addEventListener('pointerup', onWindowBoxPointerUp);
        window.addEventListener('pointercancel', onWindowBoxPointerUp);
        return;
      }

      if (state.interactionMode !== 'positive' && state.interactionMode !== 'negative') return;
      const pt = overlayPoint(event);
      if (!pt.mapped.inVideo) return;
      event.preventDefault();
      const click = {
        x: pt.canvasX,
        y: pt.canvasY,
        imageX: pt.mapped.x,
        imageY: pt.mapped.y,
        label: state.interactionMode === 'negative' ? 'negative' : 'positive',
      };
      state.clicks.push(click);
      video.pause();
      markUserEditing();
      updatePromptCounter();
      redrawOverlay();
      updateGenerateReportBtn();
      showToast(click.label === 'negative' ? '已添加负向点' : '已添加正向点', 'ok');
      runSamFastUpdate();
    });

    function finishBoxDrag(event) {
      if (!dragState.active || event.pointerId !== dragState.pointerId) return;
      dragState.active = false;
      dragState.pointerId = null;
      const pt = overlayPoint(event);
      state.dragBox = null;
      const box = {
        x1: Math.min(dragState.startImage.x, pt.mapped.x),
        y1: Math.min(dragState.startImage.y, pt.mapped.y),
        x2: Math.max(dragState.startImage.x, pt.mapped.x),
        y2: Math.max(dragState.startImage.y, pt.mapped.y),
      };
      if (imageBoxSize(box) < MIN_BOX_IMAGE_PX) {
        redrawOverlay();
        return;
      }
      state.box = box;
      markUserEditing();
      updatePromptCounter();
      redrawOverlay();
      updateGenerateReportBtn();
      showToast('框选已应用', 'ok');
      runSamFastUpdate();
    }

    target.addEventListener('pointercancel', (event) => {
      if (dragState.active && event.pointerId === dragState.pointerId) {
        dragState.active = false;
        dragState.pointerId = null;
        state.dragBox = null;
        cleanupBoxDragListeners();
        redrawOverlay();
      }
    });

    target.addEventListener('pointerleave', () => {
      if (state.interactionMode === 'inspect') {
        el('boundaryLoupe')?.classList.add('hidden');
        state.loupePoint = null;
      }
    });

    seek.addEventListener('input', () => {
      if (!video.duration) return;
      video.currentTime = (Number(seek.value) / 1000) * video.duration;
    });

    window.addEventListener('resize', resizeOverlayCanvas);
    video.addEventListener('loadeddata', resizeOverlayCanvas);
  }

  function bindKeyboardShortcuts() {
    window.addEventListener('keydown', (event) => {
      const tag = (event.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || event.target?.isContentEditable) return;

      if (event.code === 'Space') {
        event.preventDefault();
        el('playPauseBtn')?.click();
        return;
      }
      if (event.key === '1') { setInteractionMode('positive'); showToast('正向点模式', 'ok'); return; }
      if (event.key === '2') { setInteractionMode('negative'); showToast('负向点模式', 'ok'); return; }
      if (event.key === '3') { setInteractionMode('box'); showToast('框选模式', 'ok'); return; }
      if (event.key === '4' && boundaryDirectionsEnabled()) { setInteractionMode('inspect'); showToast('边界检视模式', 'ok'); return; }
      if (event.key === '5' && boundaryDirectionsEnabled()) { setInteractionMode('boundary'); showToast('自定义边界方向', 'ok'); return; }
      if (event.key === '[' && boundaryDirectionsEnabled()) {
        if (window.BoundaryWorkbench) window.BoundaryWorkbench.cycleSector(state, -1);
        return;
      }
      if (event.key === ']' && boundaryDirectionsEnabled()) {
        if (window.BoundaryWorkbench) window.BoundaryWorkbench.cycleSector(state, 1);
        return;
      }
      if (event.key === 'z' && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        el('undoPointBtn')?.click();
        return;
      }
      if (event.key === 'c' && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        el('clearClickBtn')?.click();
        return;
      }
      if (event.key === 'r' && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        el('generateReportBtn')?.click();
        return;
      }
      if (event.key === 'a' && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        el('analyzeBtn')?.click();
      }
    });
  }

  function bindControls() {
    el('analyzeBtn').addEventListener('click', () => runAgentAnalysis({ type: 'auto' }));
    el('generateReportBtn').addEventListener('click', () => generateLlmReport({ auto: false }));
    el('copyReportBtn')?.addEventListener('click', copyClinicalReportText);
    el('clearClickBtn').addEventListener('click', () => {
      state.clicks = [];
      state.box = null;
      state.dragBox = null;
      state.lastReport = null;
      state.maskPolygon = null;
      state.lastMaskOverlayPng = null;
      clearBoundaryDetailPanel();
      clearOverlay();
      renderEmptyAgent('已清除标注。请框选区域或点击病灶。');
      updateMaskControlBar();
      updateGenerateReportBtn();
    });
    el('undoPointBtn').addEventListener('click', () => {
      if (state.clicks.length) {
        state.clicks.pop();
        updatePromptCounter();
        redrawOverlay();
        if (hasUserPrompt()) runSamFastUpdate();
        return;
      }
      if (state.box) {
        state.box = null;
        updatePromptCounter();
        redrawOverlay();
        if (hasUserPrompt()) runSamFastUpdate();
      }
    });
    el('playPauseBtn').addEventListener('click', () => {
      const video = el('studyVideo');
      if (video.paused) {
        video.play();
        if (state.trackOnPlay && hasUserPrompt()) scheduleVideoTrack(true);
      } else {
        video.pause();
        hideVideoBadge();
      }
    });
    el('trackPlayBtn').addEventListener('click', () => {
      state.trackOnPlay = !state.trackOnPlay;
      updateTrackButtonUi();
      if (state.trackOnPlay && !el('studyVideo').paused && hasUserPrompt()) {
        scheduleVideoTrack(true);
      }
    });
    document.querySelectorAll('[data-interaction-mode]').forEach((node) => {
      node.addEventListener('click', () => {
        setInteractionMode(node.dataset.interactionMode);
      });
    });
    document.querySelectorAll('[data-cohort]').forEach((node) => {
      node.addEventListener('click', () => setCaseCohort(node.dataset.cohort));
    });
    bindMaskControls();
    bindKeyboardShortcuts();
    updateGenerateReportBtn();
  }

  async function ensureAuth() {
    // Interactive Agent is a LAN assist tool: do not block on formal reader login.
    // Formal task1/task2 pages still require auth via their own gates.
    const sp = new URLSearchParams(window.location.search);
    const forceAuth = sp.get('auth') === '1';
    try {
      const res = await fetch('/api/me', { credentials: 'same-origin' });
      if (res.ok) return true;
      if (res.status === 404) return true;
      if (!forceAuth) {
        console.warn('[interactive_video_agent] no reader session; continuing as guest');
        const badge = el('samBackendBadge');
        if (badge && !badge.dataset.guestNoted) {
          badge.dataset.guestNoted = '1';
          badge.title = (badge.title || '') + ' · guest (未登录阅片账号)';
        }
        return true;
      }
    } catch {
      return true;
    }
    const next = encodeURIComponent(window.location.pathname.split('/').pop() || 'interactive_video_agent.html');
    window.location.href = `/task1.html?next=${next}`;
    return false;
  }

  async function init() {
    await fetchSamStatus();
    const authed = await ensureAuth();
    if (!authed) return;
    state.cases = getCases(state.caseCohort);
    const deep = applyDeepLink();
    document.querySelectorAll('[data-cohort]').forEach((node) => {
      node.classList.toggle('active', node.dataset.cohort === state.caseCohort);
    });
    if (!state.cases.length && deep.mode !== 'video' && deep.mode !== 'image') {
      el('caseList').innerHTML = '<div class="interactive-empty" style="padding:12px">未找到视频病例。请确认 cases.bundle.js 与 images/、良恶性/ 已就绪。</div>';
      return;
    }
    renderCaseList();
    if (deep.mode === 'video' && deep.link.video) {
      loadExternalVideo(deep.link.video, deep.link.title);
    } else if (deep.mode === 'image' && deep.link.image) {
      try {
        await loadExternalImage(deep.link.image, deep.link.title);
      } catch (err) {
        console.error(err);
        renderEmptyAgent(`静图深链失败：${err.message || err}`);
        showToast(err.message || '静图加载失败', 'warn');
      }
    } else {
      loadCurrentVideo();
    }
    bindViewerEvents();
    bindControls();
    if (window.BoundaryWorkbench) {
      window.BoundaryWorkbench.bindControls(state, {
        el,
        state,
        redrawOverlay,
        showToast,
        renderReport,
        mapImageToCanvas,
        videoDisplayTransform,
        currentCase,
        setInteractionMode,
        scheduleBoundaryReport,
      });
    }
    updateInteractionModeUi();
    updateTrackButtonUi();
    updateMaskControlBar();
    updateGenerateReportBtn();
    let readyMsg = state.samBackend
      ? '就绪。框选或点击病灶后分割，右侧可查看文字报告。'
      : '演示模式（无分割服务）。请启动 scripts/serve_interactive_sam_agent.py。';
    if (deep.mode === 'case') {
      readyMsg = `已定位 ${deep.link.caseId}。框选或点击病灶后分割。`;
    } else if (deep.mode === 'video') {
      readyMsg = '已加载深链视频。框选或点击病灶后分割；分层结果将回写工作台。';
    } else if (deep.mode === 'image') {
      readyMsg = '已加载工作台静图帧。框选或点击病灶后分割；分层结果将回写工作台。';
    }
    if (state.callbackUrl) {
      readyMsg += '（已启用回写）';
    }
    renderEmptyAgent(readyMsg);
    resizeOverlayCanvas();
  }

  window.addEventListener('DOMContentLoaded', init);
})();
