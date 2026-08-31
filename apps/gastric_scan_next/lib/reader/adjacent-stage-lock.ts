/**
 * Doctor-chosen adjacent-stage lock. Renormalizes frozen T probs inside the
 * pair only. Does not change Assist weights or unlock definite cT.
 */

export type AdjacentTProb = { T1?: number | null; T2?: number | null; T3?: number | null; T4?: number | null };

export type AdjacentPair = 't1_t2' | 't2_t3' | 't3_t4';
export type AdjacentStage = 'T1' | 'T2' | 'T3' | 'T4';

export const ADJACENT_PAIR_OPTIONS: Array<{
  id: AdjacentPair;
  left: AdjacentStage;
  right: AdjacentStage;
  layers: 1 | 2 | 3;
  zh: string;
  en: string;
  hintZh: string;
  hintEn: string;
}> = [
  {
    id: 't1_t2',
    left: 'T1',
    right: 'T2',
    layers: 3,
    zh: 'T1 / T2',
    en: 'T1 / T2',
    hintZh: '浅层与固有肌界面。经腹更难，可后做。',
    hintEn: 'Shallow / MP interface. Harder on TAUS; later version.',
  },
  {
    id: 't2_t3',
    left: 'T2',
    right: 'T3',
    layers: 2,
    zh: 'T2 / T3',
    en: 'T2 / T3',
    hintZh: '固有肌外缘是否突破。',
    hintEn: 'Is the MP outer edge breached?',
  },
  {
    id: 't3_t4',
    left: 'T3',
    right: 'T4',
    layers: 1,
    zh: 'T3 / T4',
    en: 'T3 / T4',
    hintZh: '浆膜最外缘是否连续。第一版主任务。',
    hintEn: 'Is the outermost serosa continuous? First-version task.',
  },
];

export type AdjacentLockResult = {
  pair: AdjacentPair;
  left: AdjacentStage;
  right: AdjacentStage;
  leftProb: number;
  rightProb: number;
  lockedChoice: AdjacentStage;
  lockedShare: number;
  frozenTop1: AdjacentStage | null;
  outsideLock: boolean;
  noteZh: string;
  noteEn: string;
};

function finite(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export function frozenTop1(t: AdjacentTProb | null | undefined): AdjacentStage | null {
  if (!t) return null;
  const ranked: Array<[AdjacentStage, number]> = [
    ['T1', finite(t.T1)],
    ['T2', finite(t.T2)],
    ['T3', finite(t.T3)],
    ['T4', finite(t.T4)],
  ];
  ranked.sort((a, b) => b[1] - a[1]);
  if (ranked[0][1] <= 0) return null;
  return ranked[0][0];
}

export function pairMeta(pair: AdjacentPair) {
  return ADJACENT_PAIR_OPTIONS.find((item) => item.id === pair) || ADJACENT_PAIR_OPTIONS[2];
}

export function parseAdjacentPair(value: unknown): AdjacentPair | null {
  if (value === 't1_t2' || value === 't2_t3' || value === 't3_t4') return value;
  return null;
}

export function parseWallLayerTarget(value: unknown): 1 | 2 | 3 | null {
  const n = Number(value);
  if (n === 1 || n === 2 || n === 3) return n;
  return null;
}

export function lockAdjacentStage(
  t: AdjacentTProb | null | undefined,
  pair: AdjacentPair,
): AdjacentLockResult {
  const meta = pairMeta(pair);
  const leftProb = finite(t?.[meta.left]);
  const rightProb = finite(t?.[meta.right]);
  const sum = leftProb + rightProb;
  const lockedChoice = rightProb > leftProb ? meta.right : meta.left;
  const lockedShare = sum > 0 ? (lockedChoice === meta.right ? rightProb : leftProb) / sum : 0.5;
  const top = frozenTop1(t);
  const outsideLock = Boolean(top && top !== meta.left && top !== meta.right);
  const pct = Math.round(lockedShare * 100);
  const noteZh = outsideLock
    ? `四分类给出 ${top}，已超出您锁定的 ${meta.zh}。按锁定范围，倾向 ${lockedChoice}（${pct}%）。冻结数字未改。`
    : `在您锁定的 ${meta.zh} 中，倾向 ${lockedChoice}（${pct}%）。四分类数字未改。`;
  const noteEn = outsideLock
    ? `Four-class top-1 is ${top}, outside your ${meta.en} lock. Inside the lock the tendency is ${lockedChoice} (${pct}%). Frozen numbers unchanged.`
    : `Inside your ${meta.en} lock the tendency is ${lockedChoice} (${pct}%). Four-class numbers unchanged.`;
  return {
    pair,
    left: meta.left,
    right: meta.right,
    leftProb,
    rightProb,
    lockedChoice,
    lockedShare,
    frozenTop1: top,
    outsideLock,
    noteZh,
    noteEn,
  };
}

export type KeyframeContinuityFrame = {
  timeSec?: number;
  interrupts?: Array<{
    layer: number;
    interrupted?: boolean;
    verdict?: string;
    nameZh?: string;
  }>;
  ticks?: Array<{ layer: number; status?: string; nameZh?: string }>;
};

export function serosaInterrupted(frame: KeyframeContinuityFrame): boolean | null {
  const hit = (frame.interrupts || []).find((item) => item.layer === 5)
    || (frame.ticks || []).find((item) => item.layer === 5);
  if (!hit) return null;
  const verdict = 'verdict' in hit ? String(hit.verdict || '') : '';
  if (verdict === 'cannot_judge') return null;
  if (verdict === 'interrupted') return true;
  if (verdict === 'continuous') return false;
  if (verdict === 'suspected') return true;
  if ('interrupted' in hit) return Boolean(hit.interrupted);
  const status = 'status' in hit ? hit.status : undefined;
  if (status === 'unseen') return null;
  return status === 'absent' || status === 'imaginary' || status === 'thinned';
}

export function compareKeyframeContinuity(frames: KeyframeContinuityFrame[]): {
  scored: number;
  interrupted: number;
  continuous: number;
  mixed: boolean;
  noteZh: string;
  noteEn: string;
} {
  const flags = frames.map(serosaInterrupted);
  const judged = flags.filter((value): value is boolean => value != null);
  const skipped = flags.length - judged.length;
  const interrupted = judged.filter(Boolean).length;
  const continuous = judged.length - interrupted;
  const mixed = interrupted > 0 && continuous > 0;
  const noteZh = !flags.length
    ? '其他关键帧还没有浆膜草稿。传到其他帧后再对照。'
    : !judged.length
      ? `${flags.length} 帧浆膜均无法判断。不要强迫输出连续或中断。`
      : interrupted >= 2
        ? `${judged.length} 帧中 ${interrupted} 帧在相近位置支持中断。`
        : interrupted === 1 && judged.length >= 2
          ? `${judged.length} 帧中仅 1 帧提示中断，更可能是伪像或切面因素。`
          : mixed
            ? `${judged.length} 帧中 ${interrupted} 帧中断、${continuous} 帧连续${skipped ? `，另 ${skipped} 帧无法判断` : ''}。`
            : interrupted
              ? `${judged.length} 帧浆膜均提示中断。`
              : `${judged.length} 帧浆膜均提示连续。`;
  const noteEn = !flags.length
    ? 'No other keyframe has a serosa draft yet. Copy the trajectory, then compare.'
    : !judged.length
      ? `${flags.length} frames are unanalyzable. Do not force continuous or interrupted.`
      : interrupted >= 2
        ? `${interrupted} of ${judged.length} frames support interruption at a similar location.`
        : interrupted === 1 && judged.length >= 2
          ? `Only 1 of ${judged.length} frames suggests interruption; more likely artifact or plane.`
          : mixed
            ? `${interrupted} of ${judged.length} frames interrupted, ${continuous} continuous${skipped ? `, ${skipped} unanalyzable` : ''}.`
            : interrupted
              ? `All ${judged.length} frames suggest serosa interruption.`
              : `All ${judged.length} frames suggest a continuous serosa.`;
  return {
    scored: judged.length,
    interrupted,
    continuous,
    mixed,
    noteZh,
    noteEn,
  };
}

export const ADJACENT_LOCK_EVENT = 'gastric:adjacent-lock';
export const WALL_ASSIST_DRAFT_EVENT = 'gastric:wall-assist-draft';
export const WALL_INTERRUPT_OVERRIDE_EVENT = 'gastric:wall-interrupt-override';
export const WALL_PROMPT_META_EVENT = 'gastric:wall-prompt-meta';
export const DEPTH_SCREEN_EVENT = 'gastric:depth-screen';

export type AdjacentLockEventDetail = {
  pair: AdjacentPair | null;
  source?: string;
};

export type WallInterruptOverrideDetail = {
  layer: number;
};

export type WallPromptMetaDetail = {
  visibility?: 'clear' | 'blurry' | 'unseen';
  anchorMode?: 'bilateral' | 'unilateral' | 'unanalyzable';
};

export type DepthScreenEventDetail = {
  screen: 'shallow_clear' | 'outer_clear' | 'boundary_unclear' | null;
  confidence?: 'high' | 'mid' | 'low' | null;
};

export type WallFateDraft = {
  id?: string;
  nameZh?: string;
  nameEn?: string;
  verdict?: string;
  labelZh?: string;
  labelEn?: string;
};

export type WallClusterDraft = {
  available?: boolean;
  pattern?: string;
  brightDarkBright?: boolean;
  offsets?: number[];
  means?: number[];
};

export type WallAssistDraftDetail = {
  targetLayers?: 1 | 2 | 3 | null;
  adjacentPair?: AdjacentPair | null;
  visibility?: 'clear' | 'blurry' | 'unseen' | null;
  anchorMode?: 'bilateral' | 'unilateral' | 'unanalyzable' | null;
  focusCount?: number;
  spanCount?: number;
  proposedDeepestCount?: number;
  deepestDisagree?: boolean;
  autoAnchors?: 'ok' | 'failed' | null;
  ticks?: Array<{ layer: number; nameZh: string; nameEn?: string; labelZh: string; status?: string }>;
  interrupts?: Array<{
    layer: number;
    nameZh: string;
    nameEn?: string;
    interrupted: boolean;
    verdict?: string;
    doctorOverride?: boolean;
  }>;
  fates?: WallFateDraft[];
  remainPx?: number | null;
  overshootPx?: number | null;
  thicknessPx?: number | null;
  extraserosal?: boolean;
  method?: string | null;
  cluster?: WallClusterDraft | null;
  noteZh?: string;
  noteEn?: string;
  echoNoteZh?: string;
  echoNoteEn?: string;
  echoPatternZh?: string;
  echoPatternEn?: string;
  echoDoctorPatternZh?: string;
  echoDoctorPatternEn?: string;
  echoAiPatternZh?: string;
  echoAiPatternEn?: string;
  keyframes?: KeyframeContinuityFrame[];
  keyframeCount?: number;
};

export type WallStagingFusion = {
  pair: AdjacentPair | null;
  lean: AdjacentStage | null;
  agree: 'agree' | 'disagree' | 'unclear' | 'no_lock' | 'no_wall';
  noteZh: string;
  noteEn: string;
};

function tokenOf(value: unknown): string {
  return String(value || '').trim().toLowerCase();
}

function isBrokenToken(token: string): boolean {
  return token === 'interrupted'
    || token === 'suspected'
    || token === 'suspected_interrupt'
    || token === 'lost'
    || token === 'absent'
    || token === 'vanished';
}

function isIntactToken(token: string): boolean {
  return token === 'continuous'
    || token === 'present'
    || token === 'intact'
    || token === 'displaced';
}

function isFusedToken(token: string): boolean {
  return token === 'fused' || token === 'thinned' || token === 'thin';
}

type WallStagingDraftInput = {
  targetLayers?: 1 | 2 | 3 | number | null;
  adjacentPair?: AdjacentPair | null;
  interrupts?: Array<{ layer?: number; interrupted?: boolean; verdict?: string }>;
  ticks?: Array<{ layer?: number; status?: string }>;
  fates?: WallFateDraft[];
  remainPx?: number | null;
  extraserosal?: boolean;
  cluster?: WallClusterDraft | null;
};

function layerToken(
  detail: WallStagingDraftInput | null | undefined,
  id: 'mucosa' | 'muscularis' | 'serosa',
  layer: number,
): string {
  const fate = (detail?.fates || []).find((item) => tokenOf(item.id) === id);
  if (fate?.verdict) return tokenOf(fate.verdict);
  const interrupt = (detail?.interrupts || []).find((item) => Number(item.layer) === layer);
  if (interrupt?.verdict) return tokenOf(interrupt.verdict);
  if (interrupt) return interrupt.interrupted ? 'interrupted' : 'continuous';
  const tick = (detail?.ticks || []).find((item) => Number(item.layer) === layer);
  return tokenOf(tick?.status);
}

export function inferAdjacentPair(detail: {
  adjacentPair?: AdjacentPair | null;
  targetLayers?: 1 | 2 | 3 | number | null;
} | null | undefined): AdjacentPair | null {
  if (!detail) return null;
  if (detail.adjacentPair) return detail.adjacentPair;
  return parseWallLayerTarget(detail.targetLayers) === 1
    ? 't3_t4'
    : parseWallLayerTarget(detail.targetLayers) === 2
      ? 't2_t3'
      : parseWallLayerTarget(detail.targetLayers) === 3
        ? 't1_t2'
        : null;
}

/** Wall-layer draft vs adjacent lock. Does not change frozen probabilities. */
export function fuseWallDraftIntoStaging(
  detail: WallStagingDraftInput | null | undefined,
  pair?: AdjacentPair | null,
  lockedChoice?: AdjacentStage | null,
): WallStagingFusion {
  const empty: WallStagingFusion = {
    pair: null,
    lean: null,
    agree: 'no_wall',
    noteZh: '',
    noteEn: '',
  };
  if (!detail) return empty;
  const mucosa = layerToken(detail, 'mucosa', 1);
  const muscle = layerToken(detail, 'muscularis', 4);
  const serosa = layerToken(detail, 'serosa', 5);
  const hasWall = Boolean(mucosa || muscle || serosa || detail.cluster?.available || detail.remainPx != null);
  if (!hasWall) return empty;
  const resolved = pair || inferAdjacentPair(detail);
  let lean: AdjacentStage | null = null;
  if (resolved === 't3_t4') {
    if (detail.extraserosal || isBrokenToken(serosa)) lean = 'T4';
    else if (isIntactToken(serosa)) lean = 'T3';
  } else if (resolved === 't2_t3') {
    if (isBrokenToken(serosa) || isBrokenToken(muscle) || isFusedToken(muscle) || muscle === 'displaced' || serosa === 'displaced') {
      lean = 'T3';
    } else if ((muscle === 'continuous' || muscle === 'present' || muscle === 'intact') && !isBrokenToken(serosa)) {
      lean = 'T2';
    }
  } else if (resolved === 't1_t2') {
    if (isBrokenToken(muscle) || isFusedToken(muscle) || isBrokenToken(mucosa) || isFusedToken(mucosa)) lean = 'T2';
    else if (isIntactToken(mucosa) && isIntactToken(muscle)) lean = 'T1';
  }
  const pairLabel = resolved ? pairMeta(resolved).zh : '';
  const pairLabelEn = resolved ? pairMeta(resolved).en : '';
  const agree: WallStagingFusion['agree'] = !resolved
    ? 'no_lock'
    : lean == null
      ? 'unclear'
      : lockedChoice && lean === lockedChoice
        ? 'agree'
        : lockedChoice && lean !== lockedChoice
          ? 'disagree'
          : 'unclear';
  const clusterZh = detail.cluster?.available
    ? (detail.cluster.pattern === 'bright-dark-bright'
      ? '走廊像素呈亮-暗-亮'
      : detail.cluster.pattern === 'dark-bright-dark'
        ? '走廊像素呈暗-亮-暗'
        : '走廊像素已按层次聚类')
    : '';
  const clusterEn = detail.cluster?.available
    ? (detail.cluster.pattern === 'bright-dark-bright'
      ? 'corridor pixels are bright-dark-bright'
      : detail.cluster.pattern === 'dark-bright-dark'
        ? 'corridor pixels are dark-bright-dark'
        : 'corridor pixels clustered by layer')
    : '';
  const remainZh = Number.isFinite(Number(detail.remainPx))
    ? `余厚约 ${Number(detail.remainPx).toFixed(0)} px（非毫米）`
    : '';
  const remainEn = Number.isFinite(Number(detail.remainPx))
    ? `remain about ${Number(detail.remainPx).toFixed(0)} px (not mm)`
    : '';
  const bitsZh = [clusterZh, remainZh].filter(Boolean).join('，');
  const bitsEn = [clusterEn, remainEn].filter(Boolean).join('; ');
  const lockZh = resolved
    ? (lean
      ? (agree === 'agree'
        ? `胃壁聚类对照${pairLabel}，与锁内倾向 ${lockedChoice} 一致，支持 ${lean}`
        : agree === 'disagree'
          ? `胃壁聚类对照${pairLabel}，更支持 ${lean}，与锁内倾向 ${lockedChoice} 不一致`
          : `胃壁聚类对照${pairLabel}，更支持 ${lean}`)
      : `胃壁聚类已并入${pairLabel}推理，本帧还不够判断锁内倾向`)
    : (lean
      ? `胃壁聚类已并入分期推理，本帧更支持 ${lean}`
      : '胃壁聚类已并入分期推理，本帧还不够判断相邻期');
  const lockEn = resolved
    ? (lean
      ? (agree === 'agree'
        ? `Wall clustering vs ${pairLabelEn} agrees with the in-lock tendency ${lockedChoice}, supporting ${lean}`
        : agree === 'disagree'
          ? `Wall clustering vs ${pairLabelEn} supports ${lean}, unlike the in-lock tendency ${lockedChoice}`
          : `Wall clustering vs ${pairLabelEn} supports ${lean}`)
      : `Wall clustering is in the ${pairLabelEn} reasoning; this frame is not enough for an in-lock lean`)
    : (lean
      ? `Wall clustering is in the staging reasoning; this frame leans ${lean}`
      : 'Wall clustering is in the staging reasoning; this frame is not enough for an adjacent-pair lean');
  const suffixZh = bitsZh ? `（${bitsZh}；草稿，不定 cT）` : '（草稿，不定 cT）';
  const suffixEn = bitsEn ? ` (${bitsEn}; draft, not a definite cT)` : ' (draft, not a definite cT)';
  return {
    pair: resolved,
    lean,
    agree,
    noteZh: `${lockZh}${suffixZh}。`,
    noteEn: `${lockEn}${suffixEn}.`,
  };
}

function tickStatusLabel(status: string | undefined, zh: boolean): string {
  if (status === 'absent' || status === 'vanished') return zh ? '消失' : 'absent';
  if (status === 'thinned' || status === 'thin') return zh ? '疑似中断' : 'suspected';
  if (status === 'imaginary') return zh ? '假想' : 'imaginary';
  if (status === 'present' || status === 'continuous') return zh ? '还在' : 'present';
  if (status === 'interrupted') return zh ? '中断' : 'interrupted';
  if (status === 'fused') return zh ? '与灶融合' : 'fused';
  if (status === 'displaced') return zh ? '受压绕行' : 'displaced';
  if (status === 'suspected_interrupt' || status === 'suspected') return zh ? '疑似中断' : 'suspected';
  if (status === 'unseen' || status === 'cannot_judge' || status === 'missing') return zh ? '无法判断' : 'cannot judge';
  return status || (zh ? '未分出' : 'unresolved');
}

function interruptProse(
  item: { interrupted?: boolean; verdict?: string },
  zh: boolean,
): string {
  if (item.verdict === 'cannot_judge') return zh ? '无法判断' : 'cannot judge';
  if (item.verdict === 'suspected') return zh ? '疑似中断' : 'suspected';
  if (item.verdict === 'interrupted' || item.interrupted) return zh ? '中断' : 'interrupted';
  return zh ? '连续' : 'continuous';
}

/** Local template sentences from wall ticks. Does not change Assist probabilities. */
export function buildWallDraftProse(detail: WallAssistDraftDetail | null | undefined, zh: boolean): string {
  if (!detail) return '';
  const parts: string[] = [];
  if (detail.targetLayers) {
    const anatomy = detail.targetLayers === 1
      ? (zh ? '浆膜预期走行线' : 'expected serosal trajectory')
      : detail.targetLayers === 2
        ? (zh ? '固有肌预期走行线' : 'expected MP trajectory')
        : (zh ? '浅层界面预期走行线' : 'expected shallow-interface trajectory');
    parts.push(zh
      ? `医生画了${anatomy}（解剖先验，不是中断答案，不定 cT）。`
      : `Doctor drew the ${anatomy} (anatomical prior, not a continuity answer; not a definite cT).`);
  }
  if (detail.visibility === 'unseen' || detail.anchorMode === 'unanalyzable') {
    parts.push(zh
      ? '当前切面看不清，输出无法判断。看不清不等于中断。'
      : 'This plane is not analyzable. Not seen is not interruption.');
  } else if (detail.visibility === 'blurry') {
    parts.push(zh ? '可见度模糊，连续性只作疑似。' : 'Visibility is blurry; continuity is only suspected.');
  }
  if (detail.anchorMode === 'unilateral') {
    parts.push(zh ? '单侧锚定，路径估计可靠性较低。' : 'One-flank prompt; path estimate is less reliable.');
  }
  if ((detail.spanCount || 0) === 1) {
    parts.push(zh ? '只留了 1 段预期线，还缺对侧。' : 'Only 1 expected-line span; the other flank is still missing.');
  } else if ((detail.spanCount || 0) >= 2) {
    parts.push(zh ? `已留 ${detail.spanCount} 段预期线。` : `${detail.spanCount} expected-line spans kept.`);
  }
  if ((detail.focusCount || 0) > 0) {
    parts.push(zh
      ? '已确认最深浸润区，开始分析。'
      : 'Deepest-invasion region confirmed; analysis has started.');
  } else if ((detail.proposedDeepestCount || 0) > 0) {
    parts.push(zh
      ? '已有 AI 最深区建议，待医生选择后才开始分析。'
      : 'An AI deepest-region suggestion is waiting. Analysis starts after the doctor selects it.');
  }
  if (detail.autoAnchors === 'failed') {
    parts.push(zh
      ? '自动双侧锚点不够稳，短线为手绘回退。'
      : 'Auto flanks were not stable; painted short lines are the fallback.');
  }
  const fates = detail.fates || [];
  if (fates.length) {
    parts.push(zh
      ? `层次命运：${fates.map((item) => item.labelZh || `${item.nameZh || ''}${tickStatusLabel(item.verdict, true)}`).filter(Boolean).join('，')}。`
      : `Layer fates: ${fates.map((item) => item.labelEn || `${item.nameEn || item.nameZh || ''} ${tickStatusLabel(item.verdict, false)}`).filter(Boolean).join(', ')}.`);
  }
  for (const tick of fates.length ? [] : (detail.ticks || [])) {
    const name = zh ? tick.nameZh : (tick.nameEn || tick.nameZh);
    parts.push(zh
      ? `${name}${tickStatusLabel(tick.status, true)}。`
      : `${name} ${tickStatusLabel(tick.status, false)}.`);
  }
  for (const item of detail.interrupts || []) {
    const name = zh ? item.nameZh : (item.nameEn || item.nameZh);
    parts.push(zh
      ? `${name}沿预期线提示${interruptProse(item, true)}。`
      : `${name} ${interruptProse(item, false)} along the expected trajectory.`);
  }
  if (zh && detail.noteZh) parts.push(detail.noteZh);
  if (!zh && detail.noteEn) parts.push(detail.noteEn);
  if (zh && detail.echoNoteZh) parts.push(detail.echoNoteZh);
  else if (!zh && detail.echoNoteEn) parts.push(detail.echoNoteEn);
  else {
    const doctorEcho = zh ? detail.echoDoctorPatternZh : (detail.echoDoctorPatternEn || detail.echoDoctorPatternZh);
    const aiEcho = zh ? detail.echoAiPatternZh : (detail.echoAiPatternEn || detail.echoAiPatternZh);
    if (doctorEcho) {
      parts.push(zh
        ? `医生最深区回声：${doctorEcho}。不是全图超分。`
        : `Doctor deepest-region echo: ${doctorEcho}. Not full-image super-resolution.`);
    }
    if (aiEcho) {
      parts.push(zh
        ? `AI 候选区回声：${aiEcho}。草稿，不定 cT。`
        : `AI candidate echo: ${aiEcho}. Draft, not a definite cT.`);
    } else if (detail.echoPatternZh) {
      parts.push(zh
        ? `浸润最深窄带回声区：${detail.echoPatternZh}。不是全图超分。`
        : `Deepest-band echo regions: ${detail.echoPatternEn || detail.echoPatternZh}. Not full-image super-resolution.`);
    }
  }
  const count = detail.keyframeCount ?? detail.keyframes?.length ?? 0;
  if (count > 0 && count < 2) {
    parts.push(zh
      ? '当前只有 1 个关键帧。T 分期最好再标 1–2 帧，以浸润最深为主。'
      : 'Only 1 keyframe so far. T-staging works better with 2–3 frames, deepest invasion first.');
  } else if ((detail.keyframes || []).length) {
    const continuity = compareKeyframeContinuity(detail.keyframes || []);
    if (continuity.scored > 0) parts.push(zh ? continuity.noteZh : continuity.noteEn);
  }
  return parts.join(zh ? '' : ' ');
}
