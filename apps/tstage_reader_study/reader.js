/* tstage_reader_study/reader.js
 * 2-pass video-first T-staging reader study.
 * Pass 1: no AI shown.  Pass 2: AI prediction revealed above the choices.
 * Per-pass random case order, identical case set, results appended to
 * localStorage and exportable as JSON.
 *
 * No 3rd-party libs.  No backend required.  All data in cases.json.
 */
(function () {
  "use strict";

  const T_LABELS = { T1: "T1 黏膜/黏膜下", T2: "T2 固有肌层", T3: "T3 浆膜下", T4: "T4+ 穿透浆膜" };
  const AI_T_TO_BUTTON = { 0: "T1", 1: "T2", 2: "T3", 3: "T4" };

  const els = {
    passBadge: document.getElementById("passBadge"),
    caseBadge: document.getElementById("caseBadge"),
    armBadge: document.getElementById("armBadge"),
    aiReveal: document.getElementById("aiReveal"),
    aiValue: document.getElementById("aiValue"),
    aiConf: document.getElementById("aiConf"),
    video: document.getElementById("video"),
    btnPlay: document.getElementById("btnPlay"),
    seek: document.getElementById("seek"),
    time: document.getElementById("time"),
    speed: document.getElementById("speed"),
    choices: Array.from(document.querySelectorAll(".choice")),
    btnSkip: document.getElementById("btnSkip"),
    btnExport: document.getElementById("btnExport"),
  };

  // ---------- session state ----------
  const params = new URLSearchParams(location.search);
  const readerId = (params.get("reader") || "anon").trim();
  const forcedPass = parseInt(params.get("pass"), 10);
  const casesPerSession = 150;

  let casesAll = [];           // raw case list (150)
  let caseOrder = [];          // shuffled per-pass order
  let cursor = 0;              // index into caseOrder
  let pass = (forcedPass === 2) ? 2 : 1;
  let results = [];            // accumulated {reader_id, pass, case_id, arm, t_choice, ...}
  const storageKey = `tstage_reader:${readerId}:pass${pass}`;

  // ---------- helpers ----------
  function shuffle(arr, seed) {
    // mulberry32 deterministic shuffle
    let t = seed >>> 0;
    function rnd() { t += 0x6D2B79F5; let r = t; r = Math.imul(r ^ (r >>> 15), r | 1); r ^= r + Math.imul(r ^ (r >>> 7), r | 61); return ((r ^ (r >>> 14)) >>> 0) / 4294967296; }
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }
  function fmtTime(s) {
    if (!isFinite(s)) return "0:00";
    const m = Math.floor(s / 60);
    const r = Math.floor(s % 60);
    return `${m}:${String(r).padStart(2, "0")}`;
  }
  function setChoice(value) {
    if (!value) return;
    const c = casesAll.find(x => x.case_id === currentCase().case_id);
    if (!c) return;
    const choice = { reader_id: readerId, pass, case_id: c.case_id, arm: c.arm, t_choice: value, ts: new Date().toISOString() };
    results.push(choice);
    saveLocal();
    // advance after a short visual lock
    setTimeout(next, 220);
  }
  function currentCase() { return caseOrder[cursor]; }
  function saveLocal() {
    try { localStorage.setItem(storageKey, JSON.stringify(results)); } catch (e) {}
  }
  function loadLocal() {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) results = JSON.parse(raw);
    } catch (e) { results = []; }
  }

  // ---------- video player ----------
  function loadVideo(c) {
    const vids = c.videos || [];
    if (vids.length === 0) {
      els.video.removeAttribute("src");
      els.video.load();
      return;
    }
    const v = vids[0];
    // try served URL; fall back to file:// when running under start.sh / start.bat
    const rel = `public/cases_videos/${encodeURIComponent(c.case_id)}/${encodeURIComponent(v.stem)}`;
    // If the video file isn't bundled in public/cases_videos, the browser will
    // fire an error event; we then fall back to the absolute file:// URL.
    els.video.src = rel;
    els.video.dataset.absolutePath = v.path || "";
    els.video.load();
  }
  function wireVideo() {
    els.video.addEventListener("loadedmetadata", () => {
      els.seek.max = String(Math.max(1, Math.floor(els.video.duration * 10)));
      els.time.textContent = `${fmtTime(els.video.currentTime)} / ${fmtTime(els.video.duration)}`;
    });
    els.video.addEventListener("timeupdate", () => {
      els.seek.value = String(Math.floor(els.video.currentTime * 10));
      els.time.textContent = `${fmtTime(els.video.currentTime)} / ${fmtTime(els.video.duration)}`;
    });
    els.video.addEventListener("ended", () => { els.btnPlay.textContent = "重播"; });
    els.video.addEventListener("error", () => {
      // Fallback: file:// for offline mode
      const abs = els.video.dataset.absolutePath;
      if (abs) {
        console.warn("video not served, falling back to file://", abs);
        els.video.src = "file://" + abs;
        els.video.load();
      }
    });
    els.btnPlay.addEventListener("click", () => {
      if (els.video.paused) { els.video.play(); els.btnPlay.textContent = "暂停"; }
      else { els.video.pause(); els.btnPlay.textContent = "播放"; }
    });
    els.seek.addEventListener("input", () => {
      els.video.currentTime = Number(els.seek.value) / 10;
    });
    els.speed.addEventListener("change", () => {
      els.video.playbackRate = Number(els.speed.value);
    });
    els.video.playbackRate = Number(els.speed.value);
  }

  // ---------- case render ----------
  function render() {
    const c = currentCase();
    if (!c) { finish(); return; }
    els.caseBadge.textContent = `${c.case_id} / 150`;
    els.armBadge.textContent = c.arm === "A_ai_clean" ? "Arm A · AI 准确" : "Arm B · AI 困难";
    els.passBadge.textContent = pass === 1 ? "Pass 1 · 无 AI" : "Pass 2 · 有 AI";
    els.passBadge.classList.toggle("pass1", pass === 1);
    els.passBadge.classList.toggle("pass2", pass === 2);
    // hide AI in pass 1
    if (pass === 1) {
      els.aiReveal.hidden = true;
    } else {
      const aiT = AI_T_TO_BUTTON[c.ai_pred];
      els.aiValue.textContent = T_LABELS[aiT] || `T${c.ai_pred + 1}`;
      els.aiConf.textContent = `置信度 ${(c.ai_max_prob * 100).toFixed(1)}%`;
      els.aiReveal.hidden = false;
    }
    // reset choice buttons
    els.choices.forEach(b => b.classList.remove("selected"));
    loadVideo(c);
    // auto play
    els.video.play().then(() => { els.btnPlay.textContent = "暂停"; }).catch(() => { els.btnPlay.textContent = "播放"; });
  }
  function next() {
    cursor += 1;
    if (cursor >= caseOrder.length) { finish(); return; }
    render();
  }
  function finish() {
    els.video.pause();
    const summary = summarise();
    const blob = new Blob([JSON.stringify(summary, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `tstage_reader_${readerId}_pass${pass}_${new Date().toISOString().slice(0,10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(URL.revokeObjectURL, 1500);
    document.body.innerHTML = `<div style="padding:40px;font-family:sans-serif;color:#fff;background:#0f1115;height:100vh;">
      <h1>Pass ${pass} 完成</h1>
      <p>本 pass 共 <b>${caseOrder.length}</b> 例，已完成 <b>${results.length}</b> 例。</p>
      <p>结果已自动下载；请将 JSON 文件发给研究团队。</p>
      ${pass === 1 ? '<p>下一步请刷新页面，按 Pass 2 重新登录开始第二轮 (有 AI)。</p>' : ''}
    </div>`;
  }
  function summarise() {
    const by_case = new Map(results.map(r => [r.case_id, r]));
    return {
      reader_id: readerId, pass,
      generated_at: new Date().toISOString(),
      n_cases: caseOrder.length,
      n_completed: results.length,
      results: results,
      case_order: caseOrder.map(c => c.case_id),
    };
  }

  // ---------- bootstrap ----------
  async function init() {
    try {
      const res = await fetch("public/cases.json", { cache: "no-cache" });
      casesAll = await res.json();
    } catch (e) {
      alert("无法加载 cases.json — 请通过 start.sh / start.bat 启动本地服务器。");
      return;
    }
    // Shuffle per pass: pass 1 uses seed 1, pass 2 uses seed 2 (different order)
    caseOrder = shuffle(casesAll, pass === 1 ? 0xC0FFEE : 0xBADF00D).slice(0, casesPerSession);
    loadLocal();
    wireVideo();
    els.choices.forEach(b => b.addEventListener("click", () => setChoice(b.dataset.value)));
    els.btnSkip.addEventListener("click", () => { results.push({ reader_id: readerId, pass, case_id: currentCase().case_id, t_choice: "SKIP", ts: new Date().toISOString() }); saveLocal(); next(); });
    els.btnExport.addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(summarise(), null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `tstage_reader_${readerId}_pass${pass}_partial.json`;
      a.click();
    });
    render();
  }
  init();
})();
