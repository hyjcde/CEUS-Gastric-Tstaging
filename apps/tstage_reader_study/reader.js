/* tstage_reader_study/reader.js
 * 2-pass video-first T-staging reader study.
 * Pass 1: no AI shown.  Pass 2: AI prediction revealed above the choices;
 *          after a choice, show "agree/disagree with AI" feedback badge.
 * Per-pass random case order, identical case set, results appended to
 * localStorage and exportable as JSON.  Keyboard shortcuts supported.
 *
 * No 3rd-party libs.  No backend required.  All data in cases.json.
 */
(function () {
  "use strict";

  const T_LABELS = { T1: "T1 黏膜/黏膜下", T2: "T2 固有肌层", T3: "T3 浆膜下", T4: "T4+ 穿透浆膜" };
  const T_CODE = { T1: 0, T2: 1, T3: 2, T4: 3 };
  const AI_T_TO_BUTTON = { 0: "T1", 1: "T2", 2: "T3", 3: "T4" };
  const BUTTON_TO_AI_T = { T1: 0, T2: 1, T3: 2, T4: 3 };

  const els = {
    passBadge: document.getElementById("passBadge"),
    caseBadge: document.getElementById("caseBadge"),
    armBadge: document.getElementById("armBadge"),
    readerBadge: document.getElementById("readerBadge"),
    aiReveal: document.getElementById("aiReveal"),
    aiValue: document.getElementById("aiValue"),
    aiConf: document.getElementById("aiConf"),
    video: document.getElementById("video"),
    btnPlay: document.getElementById("btnPlay"),
    seek: document.getElementById("seek"),
    time: document.getElementById("time"),
    speed: document.getElementById("speed"),
    choices: Array.from(document.querySelectorAll(".choice")),
    aiFeedback: document.getElementById("aiFeedback"),
    btnSkip: document.getElementById("btnSkip"),
    btnExport: document.getElementById("btnExport"),
    btnHelp: document.getElementById("btnHelp"),
    progressFill: document.getElementById("progressFill"),
    progressText: document.getElementById("progressText"),
    modal: document.getElementById("modal"),
    btnModalStart: document.getElementById("btnModalStart"),
    finishScreen: document.getElementById("finishScreen"),
    finishTitle: document.getElementById("finishTitle"),
    finishSummary: document.getElementById("finishSummary"),
    finishStats: document.getElementById("finishStats"),
    finishTruth: document.getElementById("finishTruth"),
    btnFinishExport: document.getElementById("btnFinishExport"),
    btnFinishPass2: document.getElementById("btnFinishPass2"),
    btnRevealTruth: document.getElementById("btnRevealTruth"),
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
  let results = [];            // accumulated {reader_id, pass, case_id, arm, t_choice, ts}
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
  function updateProgress() {
    const total = caseOrder.length || casesPerSession;
    const done = results.length;
    const pct = Math.round(100 * done / total);
    els.progressFill.style.width = pct + "%";
    els.progressText.textContent = `${done} / ${total}`;
  }
  function setChoice(value) {
    const c = currentCase();
    if (!c || !value) return;
    // ignore duplicate click after auto-advance has already moved on
    if (results.some(r => r.case_id === c.case_id)) return;
    const choice = { reader_id: readerId, pass, case_id: c.case_id, arm: c.arm, t_choice: value, ts: new Date().toISOString() };
    results.push(choice);
    saveLocal();
    // Pass 2: show immediate AI-consistency feedback
    if (pass === 2) {
      const aiButton = AI_T_TO_BUTTON[c.ai_pred];
      const truthButton = (c.pathology_t_stage && c.pathology_t_stage.startsWith("T4")) ? "T4" : c.pathology_t_stage;
      const agreeAI = (value === aiButton);
      els.aiFeedback.classList.remove("agree", "disagree");
      els.aiFeedback.classList.add(agreeAI ? "agree" : "disagree");
      els.aiFeedback.innerHTML = agreeAI
        ? `<span class="verdict">✓ 与 AI 一致</span><span class="detail">你选了 ${T_LABELS[value]}，AI 也判 ${T_LABELS[aiButton]}（置信度 ${(c.ai_max_prob*100).toFixed(1)}%）。</span>`
        : `<span class="verdict">× 与 AI 不一致</span><span class="detail">你选了 ${T_LABELS[value]}，AI 判 ${T_LABELS[aiButton]}（置信度 ${(c.ai_max_prob*100).toFixed(1)}%）。</span>`;
      els.aiFeedback.hidden = false;
    }
    updateProgress();
    setTimeout(next, pass === 2 ? 900 : 220); // longer dwell in pass 2 so reader can read feedback
  }
  function skipCase() {
    const c = currentCase();
    if (!c) return;
    if (results.some(r => r.case_id === c.case_id)) return;
    results.push({ reader_id: readerId, pass, case_id: c.case_id, arm: c.arm, t_choice: "SKIP", ts: new Date().toISOString() });
    saveLocal();
    els.aiFeedback.hidden = true;
    updateProgress();
    next();
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
    els.armBadge.classList.toggle("arm-a", c.arm === "A_ai_clean");
    els.armBadge.classList.toggle("arm-b", c.arm === "B_ai_uncertain");
    els.passBadge.textContent = pass === 1 ? "Pass 1 · 无 AI" : "Pass 2 · 有 AI";
    els.passBadge.classList.toggle("pass1", pass === 1);
    els.passBadge.classList.toggle("pass2", pass === 2);
    // hide AI in pass 1
    els.aiFeedback.hidden = true;
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
    els.aiFeedback.hidden = true;
    cursor += 1;
    if (cursor >= caseOrder.length) { finish(); return; }
    render();
  }

  // ---------- finish / summary ----------
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
  function downloadSummary(suffix = "") {
    const data = summarise();
    const filename = `tstage_reader_${readerId}_pass${pass}${suffix}_${new Date().toISOString().slice(0,10)}.json`;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(URL.revokeObjectURL, 1500);
  }
  function buildTruthTable() {
    // For pass 2 only: show per-case reader choice vs AI vs truth.
    // Truth is taken from cases.json (pathology_t_stage).
    const rows = [];
    let nMatchTruth = 0, nMatchAI = 0, nValid = 0;
    for (const c of caseOrder) {
      const r = results.find(x => x.case_id === c.case_id);
      if (!r || r.t_choice === "SKIP") continue;
      nValid += 1;
      const truth = (c.pathology_t_stage && c.pathology_t_stage.startsWith("T4")) ? "T4" : c.pathology_t_stage;
      const aiBtn = AI_T_TO_BUTTON[c.ai_pred];
      const matchTruth = (r.t_choice === truth);
      const matchAI = (r.t_choice === aiBtn);
      if (matchTruth) nMatchTruth += 1;
      if (matchAI) nMatchAI += 1;
      rows.push({ case_id: c.case_id, choice: r.t_choice, truth, ai: aiBtn, matchTruth, matchAI, arm: c.arm });
    }
    return { rows, nValid, nMatchTruth, nMatchAI };
  }
  function renderFinish() {
    els.finishScreen.hidden = false;
    els.finishTitle.textContent = `Pass ${pass} 完成`;
    const total = caseOrder.length;
    const done = results.length;
    const nSkip = results.filter(r => r.t_choice === "SKIP").length;
    const nValid = done - nSkip;
    els.finishSummary.innerHTML = `本 pass 共 <b>${total}</b> 例，已完成 <b>${done}</b> 例（有效 <b>${nValid}</b> · 跳过 <b>${nSkip}</b>）。`;

    // stats grid
    const stats = [
      { label: "Reader", value: readerId },
      { label: "Pass", value: pass },
      { label: "已完成", value: `${done} / ${total}` },
      { label: "有效 / 跳过", value: `${nValid} / ${nSkip}` },
    ];
    if (pass === 2) {
      const { nValid: nv, nMatchTruth, nMatchAI } = buildTruthTable();
      const accTruth = nv ? (nMatchTruth / nv * 100).toFixed(1) : "—";
      const agreeAI = nv ? (nMatchAI / nv * 100).toFixed(1) : "—";
      stats.push({ label: "医生-病理一致率", value: accTruth + "%", kind: "good" });
      stats.push({ label: "医生-AI 一致率", value: agreeAI + "%", kind: "warn" });
    }
    els.finishStats.innerHTML = stats.map(s =>
      `<div class="stat ${s.kind || ''}"><div class="label">${s.label}</div><div class="value">${s.value}</div></div>`
    ).join("");

    // truth table (pass 2 only) — show all 150 cases
    if (pass === 2) {
      const { rows } = buildTruthTable();
      const trs = rows.map(r => {
        const truthMark = r.matchTruth ? "✓" : "×";
        const aiMark = r.matchAI ? "✓" : "×";
        return `<tr>
          <td class="case">${r.case_id}</td>
          <td>${r.arm === "A_ai_clean" ? "A" : "B"}</td>
          <td class="choice">${r.choice}</td>
          <td>${r.ai}</td>
          <td class="${r.matchAI ? 'match' : 'miss'}">${aiMark}</td>
          <td>${r.truth}</td>
          <td class="${r.matchTruth ? 'match' : 'miss'}">${truthMark}</td>
        </tr>`;
      }).join("");
      els.finishTruth.innerHTML = `<table>
        <thead><tr><th>Case</th><th>Arm</th><th>医生</th><th>AI</th><th>=AI?</th><th>病理</th><th>=病理?</th></tr></thead>
        <tbody>${trs}</tbody>
      </table>`;
    } else {
      els.finishTruth.innerHTML = "";
    }

    // wire download / pass-2 link
    els.btnFinishExport.onclick = () => downloadSummary();
    // truth table is opt-in (per clinical-validation rule: don't surface pathology
    // automatically; only reveal after explicit reader click for self-check)
    els.btnRevealTruth.onclick = () => {
      if (pass === 2) {
        els.finishTruth.hidden = false;
        els.btnRevealTruth.disabled = true;
        els.btnRevealTruth.textContent = "已显示";
      } else {
        els.btnRevealTruth.textContent = "（Pass 1 不含 AI, 无对照表可显示; 跑完 Pass 2 再来）";
        els.btnRevealTruth.disabled = true;
      }
    };
    if (pass === 1) {
      const url = new URL(location.href);
      url.searchParams.set("pass", "2");
      els.btnFinishPass2.href = url.toString();
      els.btnFinishPass2.hidden = false;
    } else {
      els.btnFinishPass2.hidden = true;
    }
  }
  function finish() {
    els.video.pause();
    downloadSummary(); // auto-download on completion
    renderFinish();
  }

  // ---------- modal ----------
  function showModal() { els.modal.hidden = false; }
  function hideModal() {
    els.modal.hidden = true;
    try { sessionStorage.setItem(`tstage_reader:help_dismissed:${readerId}`, "1"); } catch (e) {}
  }

  // ---------- keyboard shortcuts ----------
  function wireKeyboard() {
    document.addEventListener("keydown", (ev) => {
      // ignore if user is typing in an input/select
      const tag = (ev.target && ev.target.tagName) || "";
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (!els.modal.hidden) {
        if (ev.key === "Escape" || ev.key === "Enter") { hideModal(); ev.preventDefault(); }
        return;
      }
      if (!els.finishScreen.hidden) return;
      switch (ev.key) {
        case "1": setChoice("T1"); break;
        case "2": setChoice("T2"); break;
        case "3": setChoice("T3"); break;
        case "4": setChoice("T4"); break;
        case "s": case "S": skipCase(); break;
        case " ": ev.preventDefault(); els.btnPlay.click(); break;
        case "?": showModal(); break;
        case "ArrowRight": next(); break;  // allows manual skip
      }
    });
  }

  // ---------- bootstrap ----------
  async function init() {
    // reader name badge
    els.readerBadge.textContent = `Reader: ${readerId}`;
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
    wireKeyboard();
    els.choices.forEach(b => b.addEventListener("click", () => setChoice(b.dataset.value)));
    els.btnSkip.addEventListener("click", skipCase);
    els.btnExport.addEventListener("click", () => downloadSummary("_partial"));
    els.btnHelp.addEventListener("click", showModal);
    els.btnModalStart.addEventListener("click", hideModal);
    updateProgress();
    // show help modal on first session load for this reader
    let dismissed = false;
    try { dismissed = sessionStorage.getItem(`tstage_reader:help_dismissed:${readerId}`) === "1"; } catch (e) {}
    if (!dismissed) showModal();
    render();
  }
  init();
})();
