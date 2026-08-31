import { decodeSite, formatSize } from '@/lib/clinical-history-display';
import type { Patient } from '@/types';
import type { SamReport } from '@/lib/reader/types';
import {
  fuseWallDraftIntoStaging,
  type AdjacentPair,
  type AdjacentStage,
  type WallClusterDraft,
  type WallFateDraft,
} from '@/lib/reader/adjacent-stage-lock';

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function signText(report: SamReport | null | undefined, path: string): string {
  const field = path.split('.').reduce<unknown>(
    (current, key) => (asRecord(current)?.[key]),
    report?.signs,
  );
  const value = asRecord(field)?.value ?? field;
  const text = String(value ?? '').trim();
  return text && text !== '____' ? text : '';
}

function numberText(value: unknown): string {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? String(Number(n.toFixed(1))).replace(/\.0$/, '') : '';
}

function siteText(patient: Patient | null | undefined, zh: boolean): string {
  const clinical = asRecord(patient?.clinical);
  return decodeSite(clinical?.location || clinical?.site || clinical?.tumor_location, zh)
    || decodeSite(patient?.clinical?.location, zh);
}

function sizeParts(report: SamReport | null | undefined, patient: Patient | null | undefined) {
  const clinical = asRecord(patient?.clinical);
  const tumor = asRecord(clinical?.tumorSize) || asRecord(patient?.clinical?.tumorSize);
  const length = numberText(signText(report, 'size.length'))
    || numberText(tumor?.length)
    || numberText(clinical?.tumor_length_cm);
  const thickness = numberText(signText(report, 'size.thickness'))
    || numberText(tumor?.thickness)
    || numberText(clinical?.tumor_thickness_cm);
  return { length, thickness };
}

function pending(zh: boolean): string {
  return zh ? '待复核' : 'pending review';
}

export type JudgmentWallDraft = {
  targetLayers?: number | null;
  adjacentPair?: AdjacentPair | null;
  interrupts?: Array<{
    layer?: number;
    nameZh?: string;
    nameEn?: string;
    interrupted?: boolean;
    verdict?: string;
  }>;
  ticks?: Array<{ layer?: number; nameZh?: string; nameEn?: string; status?: string }>;
  fates?: WallFateDraft[];
  remainPx?: number | null;
  extraserosal?: boolean;
  cluster?: WallClusterDraft | null;
  echoPatternZh?: string | null;
  echoPatternEn?: string | null;
  echoDoctorPatternZh?: string | null;
  echoDoctorPatternEn?: string | null;
  echoAiPatternZh?: string | null;
  echoAiPatternEn?: string | null;
};

function tickStatusLabel(status: string | undefined, zh: boolean): string {
  const token = String(status || '').trim().toLowerCase();
  if (token === 'absent' || token === 'vanished') return zh ? '消失' : 'absent';
  if (token === 'thinned' || token === 'thin') return zh ? '变薄' : 'thinned';
  if (token === 'imaginary') return zh ? '假想' : 'imaginary';
  if (token === 'present' || token === 'continuous') return zh ? '还在' : 'present';
  if (token === 'interrupted') return zh ? '中断' : 'interrupted';
  if (token === 'unseen' || token === 'blurred' || token === 'fuzzy') return zh ? '模糊' : 'blurred';
  if (token === 'fused') return zh ? '与灶融合' : 'fused';
  if (token === 'displaced') return zh ? '受压绕行' : 'displaced';
  if (token === 'suspected_interrupt' || token === 'suspected') return zh ? '疑似中断' : 'suspected';
  if (token === 'cannot_judge' || token === 'missing') return zh ? '无法判断' : 'cannot judge';
  return status || '';
}

export function wallDraftToDoctorSigns(
  draft: JudgmentWallDraft | null | undefined,
  zh = true,
): { layer_structure?: string; serosa_change?: string } {
  if (!draft) return {};
  const wallBits = (draft.interrupts || [])
    .map((item) => {
      const name = zh ? (item.nameZh || '') : (item.nameEn || item.nameZh || '');
      if (!name) return '';
      const verdict = item.verdict === 'cannot_judge'
        ? (zh ? '无法判断' : 'cannot judge')
        : item.verdict === 'suspected'
          ? (zh ? '疑似中断' : 'suspected')
          : item.verdict === 'interrupted' || item.interrupted
            ? (zh ? '中断' : 'interrupted')
            : (zh ? '连续' : 'continuous');
      return zh ? `${name}${verdict}` : `${name} ${verdict}`;
    })
    .filter(Boolean);
  const tickBits = (draft.ticks || [])
    .map((item) => {
      const name = zh ? (item.nameZh || '') : (item.nameEn || item.nameZh || '');
      const status = tickStatusLabel(item.status, zh);
      if (!name || !status) return '';
      return `${name}${zh ? '' : ' '}${status}`;
    })
    .filter(Boolean);
  const echoDoctor = zh
    ? String(draft.echoDoctorPatternZh || '').trim()
    : String(draft.echoDoctorPatternEn || draft.echoDoctorPatternZh || '').trim();
  const echoAi = zh
    ? String(draft.echoAiPatternZh || '').trim()
    : String(draft.echoAiPatternEn || draft.echoAiPatternZh || '').trim();
  const echoPrimary = zh
    ? String(draft.echoPatternZh || '').trim()
    : String(draft.echoPatternEn || draft.echoPatternZh || '').trim();
  const echo = [echoDoctor && (zh ? `医生最深区回声${echoDoctor}` : `doctor deepest echo ${echoDoctor}`),
    echoAi && (zh ? `AI 候选区回声${echoAi}` : `AI candidate echo ${echoAi}`),
    !echoDoctor && !echoAi ? echoPrimary : '']
    .filter(Boolean)
    .join(zh ? '，' : '; ');
  const fateBits = (draft.fates || [])
    .map((item) => {
      const name = zh ? (item.nameZh || '') : (item.nameEn || item.nameZh || '');
      const status = tickStatusLabel(item.verdict, zh) || (zh ? item.labelZh : item.labelEn);
      if (!name || !status) return '';
      return `${name}${zh ? '' : ' '}${status}`;
    })
    .filter(Boolean);
  const cluster = draft.cluster?.available
    ? (zh
      ? (draft.cluster.pattern === 'bright-dark-bright'
        ? '走廊像素亮-暗-亮'
        : draft.cluster.pattern === 'dark-bright-dark'
          ? '走廊像素暗-亮-暗'
          : '走廊像素已按层次聚类')
      : (draft.cluster.pattern === 'bright-dark-bright'
        ? 'corridor bright-dark-bright'
        : draft.cluster.pattern === 'dark-bright-dark'
          ? 'corridor dark-bright-dark'
          : 'corridor clustered by layer'))
    : '';
  const remain = Number.isFinite(Number(draft.remainPx))
    ? (zh
      ? `余厚约 ${Number(draft.remainPx).toFixed(0)} px`
      : `remain about ${Number(draft.remainPx).toFixed(0)} px`)
    : '';
  const fusion = fuseWallDraftIntoStaging({
    targetLayers: draft.targetLayers === 1 || draft.targetLayers === 2 || draft.targetLayers === 3
      ? draft.targetLayers
      : null,
    adjacentPair: draft.adjacentPair,
    interrupts: draft.interrupts,
    ticks: draft.ticks,
    fates: draft.fates,
    remainPx: draft.remainPx,
    extraserosal: draft.extraserosal,
    cluster: draft.cluster,
  });
  const parts = fateBits.length ? [...fateBits] : [...wallBits, ...tickBits];
  if (cluster) parts.push(cluster);
  if (remain) parts.push(remain);
  if (echo) {
    parts.push(zh
      ? `窄带回声${echo}（局部，不是全图超分）`
      : `deepest-band echo ${echo} (local, not full-image super-resolution)`);
  }
  if (fusion.noteZh || fusion.noteEn) parts.push(zh ? fusion.noteZh.replace(/。$/, '') : fusion.noteEn.replace(/\.$/, ''));
  const targetName = draft.targetLayers === 1
    ? (zh ? '浆膜预期走行线' : 'expected serosal trajectory')
    : draft.targetLayers === 2
      ? (zh ? '固有肌预期走行线' : 'expected MP trajectory')
      : draft.targetLayers === 3
        ? (zh ? '浅层界面预期走行线' : 'expected shallow-interface trajectory')
        : (zh ? '预期走行线' : 'expected trajectory');
  const layer_structure = parts.length
    ? (zh
      ? `邻近胃壁草稿（${targetName}）：${parts.join('，')}（不定 cT）`
      : `adjacent-wall draft (${targetName}): ${parts.join(', ')} (not a definite cT)`)
    : '';
  const serosaBit = wallBits.find((item) => /浆膜|serosa/i.test(item))
    || tickBits.find((item) => /浆膜|serosa/i.test(item));
  const serosa_change = serosaBit
    ? (zh ? `${serosaBit}（草稿，不定 cT）` : `${serosaBit} (draft, not a definite cT)`)
    : '';
  return {
    ...(layer_structure ? { layer_structure } : {}),
    ...(serosa_change ? { serosa_change } : {}),
  };
}

function stageTokenLoose(value?: string | null): string {
  const raw = String(value || '').trim().toUpperCase().replace('T4+', 'T4');
  const match = raw.match(/\bT([1-4])/);
  return match ? `T${match[1]}` : '';
}

function looksLikeFrozenT4WallSeed(text: string): boolean {
  return /浆膜连续性中断|邻近器官侵犯|serosa continuity interrupt|T4a|T4b/i.test(text)
    && !/草稿|不定 cT|draft|not a definite/i.test(text);
}

/** Signs sent to guideline / fusion. Wall draft wins; frozen T4 serosa seed is dropped after a non-T4 lock. */
export function mergeJudgmentDoctorSigns(input: {
  signs?: Record<string, string> | null;
  wallDraft?: JudgmentWallDraft | null;
  headline?: string | null;
  frozenTop1?: string | null;
  zh?: boolean;
}): Record<string, string> {
  const zh = input.zh !== false;
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(input.signs || {})) {
    const text = String(value || '').trim();
    if (text) out[key] = text;
  }
  const wall = wallDraftToDoctorSigns(input.wallDraft, zh);
  if (wall.layer_structure) out.layer_structure = wall.layer_structure;
  if (wall.serosa_change) out.serosa_change = wall.serosa_change;
  const headline = stageTokenLoose(input.headline);
  const frozen = stageTokenLoose(input.frozenTop1);
  const dropT4Seed = Boolean(headline && headline !== 'T4' && frozen === 'T4');
  if (dropT4Seed) {
    if (!wall.layer_structure && looksLikeFrozenT4WallSeed(out.layer_structure || '')) {
      delete out.layer_structure;
    }
    if (!wall.serosa_change && looksLikeFrozenT4WallSeed(out.serosa_change || '')) {
      delete out.serosa_change;
    }
  }
  return out;
}

export function buildAssistJudgmentProse(input: {
  studyMode?: string | null;
  report?: SamReport | null;
  patient?: Patient | null;
  aiValue?: string;
  zh?: boolean;
  wallDraft?: JudgmentWallDraft | null;
  adjacentLock?: {
    pair?: AdjacentPair | null;
    pairZh?: string;
    pairEn?: string;
    lockedChoice?: string;
    outsideLock?: boolean;
    frozenTop1?: string | null;
  } | null;
}): string {
  const zh = input.zh !== false;
  const report = input.report || null;
  const site = siteText(input.patient, zh);
  const { length, thickness } = sizeParts(report, input.patient);
  const sizeLine = formatSize(length ? Number(length) : null, thickness ? Number(thickness) : null)
    || (length || thickness
      ? (zh
        ? `大小约${length || '____'} cm，最大厚度${thickness || '____'} cm`
        : `about ${length || '____'} cm, thickness ${thickness || '____'} cm`)
      : '');
  const morphology = signText(report, 'morphology');
  const boundary = signText(report, 'boundary');
  const growth = signText(report, 'growth_pattern');
  const wallSigns = wallDraftToDoctorSigns(input.wallDraft, zh);
  const layer = wallSigns.layer_structure || signText(report, 'layer_structure');
  const serosa = wallSigns.serosa_change || signText(report, 'serosa_change');
  const perigastric = signText(report, 'perigastric_tissue');
  const call = String(input.aiValue || '').trim();
  const isNature = input.studyMode === 'benign_malignancy';

  if (isNature) {
    const consider = call === 'benign'
      ? (zh ? '良性病变' : 'a benign gastric-wall lesion')
      : call === 'malignant'
        ? (zh ? '恶性病变' : 'a malignant gastric-wall lesion')
        : pending(zh);
    if (zh) {
      return [
        '【超声描述】',
        `病灶位于［${site || '____'}］；胃壁增厚（${sizeLine || '最大径____cm，最厚径____cm'}）；胃壁层次结构（${layer || pending(true)}）；病灶表面（${morphology || pending(true)}）。`,
        '',
        '【超声提示】',
        `${site && site !== '胃' ? `${site}胃壁` : '胃壁'} ${layer || '________'}`,
        `综合超声影像征象及辅助分析，考虑：${consider}。`,
        '几何与规则辅助，非病理金标准；最终判断权在医生。',
      ].join('\n');
    }
    return [
      '[Ultrasound description]',
      `The lesion is at [${site || '____'}]; wall thickening (${sizeLine || 'diameter ____ cm, thickness ____ cm'}); wall layers (${layer || pending(false)}); surface (${morphology || pending(false)}).`,
      '',
      '[Ultrasound impression]',
      `Based on the ultrasound signs and assist analysis, consider: ${consider}.`,
      'Geometry and rules are not a pathology gold standard. The physician has the final call.',
    ].join('\n');
  }

  const stage = /^T[1-4]/.test(call) ? call.replace('T4+', 'T4') : '';
  if (zh) {
    const finding = [
      `${site ? `${site}见` : '胃壁见'}低回声占位性病变`,
      sizeLine || '大小以当前框选为准',
      `病灶呈${growth || morphology || pending(true)}生长方式，边界${boundary || pending(true)}`,
      `胃壁层次表现为${layer || pending(true)}，浆膜表现${serosa || pending(true)}，胃周组织${perigastric || pending(true)}`,
    ].join('，') + '。';
    const lockLine = input.adjacentLock?.lockedChoice
      ? (input.adjacentLock.outsideLock
        ? `医生锁定 ${input.adjacentLock.pairZh || '相邻期'}。四分类曾给出 ${input.adjacentLock.frozenTop1}，已收回到锁定范围内的 ${input.adjacentLock.lockedChoice}。冻结权重未改。`
        : `医生锁定 ${input.adjacentLock.pairZh || '相邻期'}，倾向 ${input.adjacentLock.lockedChoice}。冻结四分类数字仍保留对照。`)
      : '';
    const fusion = fuseWallDraftIntoStaging(
      input.wallDraft,
      input.adjacentLock?.pair,
      input.adjacentLock?.lockedChoice as AdjacentStage | undefined,
    );
    const fusionLine = fusion.noteZh;
    const impression = stage
      ? `综合超声影像征象、胃壁层次聚类及辅助分析，考虑：胃癌可能，超声评估 c${stage} 期。`
      : '综合超声影像征象及胃壁层次聚类，浸润深度尚不确定，供医生复核。';
    return [
      '【超声所见】',
      finding,
      ...(lockLine ? ['', lockLine] : []),
      ...(fusionLine ? [fusionLine] : []),
      '',
      '【超声提示】',
      impression,
      '几何与规则辅助，非病理金标准；最终判断权在医生。',
    ].join('\n');
  }

  const findingEn = [
    `A hypoechoic mass is seen in ${site || 'the gastric wall'}`,
    sizeLine || 'size from the current box',
    `growth ${growth || morphology || pending(false)}, margin ${boundary || pending(false)}`,
    `wall layers ${layer || pending(false)}, serosa ${serosa || pending(false)}, perigastric tissue ${perigastric || pending(false)}`,
  ].join('; ') + '.';
  const lockLineEn = input.adjacentLock?.lockedChoice
    ? (input.adjacentLock.outsideLock
      ? `Doctor locked ${input.adjacentLock.pairEn || 'an adjacent pair'}. Four-class had given ${input.adjacentLock.frozenTop1}; the in-pair tendency is ${input.adjacentLock.lockedChoice}. Frozen weights unchanged.`
      : `Doctor locked ${input.adjacentLock.pairEn || 'an adjacent pair'}; tendency ${input.adjacentLock.lockedChoice}. Four-class numbers stay for contrast.`)
    : '';
  const fusionEn = fuseWallDraftIntoStaging(
    input.wallDraft,
    input.adjacentLock?.pair,
    input.adjacentLock?.lockedChoice as AdjacentStage | undefined,
  ).noteEn;
  const impressionEn = stage
    ? `Based on the ultrasound signs, wall-layer clustering, and assist analysis, consider: gastric cancer is possible; ultrasound-assessed c${stage}.`
    : 'Based on the ultrasound signs and wall-layer clustering, invasion depth remains uncertain and needs physician review.';
  return [
    '[Ultrasound findings]',
    findingEn,
    ...(lockLineEn ? ['', lockLineEn] : []),
    ...(fusionEn ? [fusionEn] : []),
    '',
    '[Ultrasound impression]',
    impressionEn,
    'Geometry and rules are not a pathology gold standard. The physician has the final call.',
  ].join('\n');
}
