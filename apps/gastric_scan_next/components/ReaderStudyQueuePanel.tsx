'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FileText, HelpCircle, Loader2, PlayCircle, ShieldCheck, Sparkles, X } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import type { AgentAnalysisResponse, Patient, ReaderStudyMode } from '@/types';
import type { SamReport } from '@/lib/reader/types';
import {
  compactReaderSigns,
  readerEnvironmentFromSearchParams,
  readerEvidenceIds,
  READER_ROUND2_VERSION_FIELDS,
} from '@/lib/reader/study-contract';
import { useSettings } from '@/contexts/SettingsContext';
import { useDoctorAccount } from '@/contexts/DoctorAccountContext';
import { useOpsRecorder } from '@/contexts/OperationRecorderContext';
import { patientDisplayLabel } from '@/lib/patient-display';
import { isPublicDemoStill } from '@/lib/public-demo-stills';
import { decisionEventType, writeDecisionTrace } from '@/lib/reader/decision-trace';
import { SIGN_OPTIONS, type AssistSignKey } from '@/lib/reader/assist-sign-defaults';
import {
  collectFeatureSnapshot,
  featureEdits,
  overlayAssistOnReport,
  readAssistDecision,
  visibleAssistFeatureFields,
} from '@/lib/reader/assist-report-overlay';
import { readAssistStage } from '@/components/reader/ReaderDoctorFirstBar';
import { BmEvidencePanel } from '@/components/BmEvidencePanel';
import {
  SimilarCaseReferencePanel,
  type SimilarCaseCard,
  type SimilarCaseLoadState,
  type SimilarCasePanelHandle,
} from '@/components/reader/SimilarCaseReferencePanel';
import { GuidelineTracePanel } from '@/components/reader/GuidelineTracePanel';
import { EvidenceFusionReport } from '@/components/reader/EvidenceFusionReport';
import { AssistLoopStrip } from '@/components/reader/AssistLoopStrip';
import { buildAssistJudgmentProse, mergeJudgmentDoctorSigns } from '@/lib/reader/assist-judgment-prose';
import type { BmUsReportState } from '@/lib/bm-us-report-template';
import type { AssistJudgmentState, EvidenceFusionState, SimilarCaseFeedbackEntry } from '@/lib/reader/doctor-case-state-store';
import { isEvaluationBrowserSession } from '@/lib/reader/evaluation-session';
import { buildEvidenceFusionTemplate, normalizeEvidenceCritic } from '@/lib/reader/evidence-fusion';
import { buildSimilarCaseEvidenceCards } from '@/lib/reader/similar-case-evidence-card';
import { readTentCompare } from '@/lib/reader/tent-compare';
import {
  ADJACENT_LOCK_EVENT,
  WALL_ASSIST_DRAFT_EVENT,
  WALL_INTERRUPT_OVERRIDE_EVENT,
  WALL_PROMPT_META_EVENT,
  DEPTH_SCREEN_EVENT,
  buildWallDraftProse,
  compareKeyframeContinuity,
  fuseWallDraftIntoStaging,
  lockAdjacentStage,
  pairMeta,
  parseAdjacentPair,
  type AdjacentLockEventDetail,
  type AdjacentPair,
  type DepthScreenEventDetail,
  type WallAssistDraftDetail,
} from '@/lib/reader/adjacent-stage-lock';
import { extractAssistProbabilities } from '@/components/reader/DoctorAiComparePanel';
import {
  DOCTOR_DEPTH_SCREEN_OPTIONS,
  DOCTOR_PROMPT_CONFIDENCE_OPTIONS,
  SEROSA_ANCHOR_OPTIONS,
  WALL_VISIBILITY_OPTIONS,
  anatomyTargetMeta,
  depthScreenConflictsAi,
  parseDoctorDepthScreen,
  parseDoctorPromptConfidence,
  verdictLabel,
  type DoctorDepthScreen,
  type DoctorPromptConfidence,
} from '@/lib/reader/wall-prompt';

const T_STAGING_TRIAL_STEPS_ZH = [
  '先看整段，再盯浸润最深。进度条粗定位，滚轮或左右键逐帧。空格只暂停；再按一次空格才标关键帧。选大约 2–3 帧。',
  '框选病灶；不准再小修。要重画用「框选病灶」。多个灶在「更多工具」点「再框一灶」。',
  '不要先把 T1–T4 输给模型。先框灶、确认最深浸润区，再点辅助分析。T 分期只作独立记录。',
  '框选后 AI 会自动找两侧正常胃壁。自动失败时再左右各画一段可见胃壁，不必穿过病灶。',
  '看不清标看不清，不要当成中断。',
  '先选一处最深浸润区：可点 AI 建议，或点病灶最靠近或最突出于外侧胃壁的位置。选完才开始分析。这不是突破点。用上一帧 / 下一帧 / ±5 帧核对，再点辅助分析。',
  '若单帧像断了，打开其他关键帧看相近位置是否还在。只有 1 帧中断时更可能是伪像。',
];

const T_STAGING_TRIAL_STEPS_EN = [
  'Watch the clip. Drag to seek; wheel or arrows step one frame. Space only pauses; press Space again to mark. Keep about 2–3 keyframes at deepest invasion.',
  'Box the lesion; do not nibble the mask. Retap Box lesion to replace. Add lesion is under More tools.',
  'Do not type T1–T4 into the model. Box the lesion, confirm the deepest-invasion region, then tap Assist. The T call is an independent record only.',
  'After the box, AI looks for intact wall on both flanks. If that fails, paint a short visible span on each side. Do not cross the mass.',
  'Mark Not seen if unclear. Not seen is not interruption.',
  'Select one deepest-invasion region first: tap the AI suggestion, or mark where the lesion is closest to or most proud of the outer wall. Analysis starts after you choose. This is not a breach. Check with prev / next / ±5 frames, then tap Assist.',
  'If one frame looks interrupted, check other keyframes at a similar location. A single-frame break is more likely artifact.',
];

type DoctorAction = 'accept' | 'modify' | 'reject' | 'request_more_evidence';

type Props = {
  patient: Patient | null;
  patients?: Patient[];
  compact?: boolean;
  studyMode: ReaderStudyMode;
  onStudyModeChange: (mode: ReaderStudyMode) => void;
  onSelectPatient?: (patient: Patient) => void;
  systemReport?: SamReport | null;
  onSystemReportChange?: (report: SamReport) => void;
  onInitialJudgmentChange?: (
    recorded: boolean,
    meta?: { source?: 'user' | 'restore' | 'reset' },
  ) => void;
  hideTaskChrome?: boolean;
  publicReaderOnly?: boolean;
  assistBusy?: boolean;
  assistResult?: AgentAnalysisResponse | null;
  assistError?: string | null;
  lesionReady?: boolean;
  onAssist?: () => void;
  onOpenReport?: () => void;
  onBmReportChange?: (state: BmUsReportState) => void;
  onGoViewer?: () => void;
  queryPreviewUrl?: string;
  queryMaskPolygon?: number[][] | null;
  queryImageWidth?: number;
  queryImageHeight?: number;
};

const TASKS: Array<{ id: ReaderStudyMode; labelZh: string; labelEn: string; shortZh: string; shortEn: string }> = [
  { id: 'benign_malignancy', labelZh: '良恶性判断', labelEn: 'Benignity review', shortZh: '良恶性', shortEn: 'Benign vs malignant' },
  { id: 't_staging', labelZh: 'T 分期判断', labelEn: 'T-staging review', shortZh: 'T 分期', shortEn: 'T staging' },
];
const SIGN_FIELDS = [
  ['size.length', '肿瘤长径', 'Tumor length'],
  ['size.thickness', '肿瘤厚度', 'Tumor thickness'],
  ['layer_structure', '胃壁层次', 'Wall layers'],
  ['morphology', '肿瘤形态', 'Tumor morphology'],
  ['boundary', '肿瘤边界', 'Tumor boundary'],
  ['growth_pattern', '生长方式', 'Growth pattern'],
  ['serosa_change', '浆膜改变', 'Serosal change'],
  ['perigastric_tissue', '胃周组织', 'Perigastric tissue'],
] as const;

function cleanSystemCopy(value: unknown, zh: boolean): string {
  return String(value ?? '')
    .replace(/\bSAM(?:2)?\b/gi, zh ? '系统分析' : 'system analysis')
    .replace(/\bSegment Anything(?: Model)?\b/gi, zh ? '系统分析' : 'system analysis');
}

function getSign(report: SamReport | null | undefined, path: string) {
  return path.split('.').reduce<SamReport['signs'] | Record<string, unknown> | undefined>(
    (current, key) => (current && typeof current === 'object' ? current[key] as Record<string, unknown> : undefined),
    report?.signs,
  ) as { value?: unknown; status?: string; source?: string } | undefined;
}

function signStatus(status?: string, zh = true): string {
  if (status === 'suggested') return zh ? '建议' : 'Suggested';
  if (status === 'confirmed') return zh ? '已确认' : 'Confirmed';
  if (status === 'doctor_edited') return zh ? '医生修正' : 'Doctor edited';
  if (status === 'conflict') return zh ? '冲突' : 'Conflict';
  if (status === 'pending') return zh ? '待补充' : 'Pending';
  if (status === 'uncertain') return zh ? '不确定，需复核' : 'Uncertain, review required';
  return zh ? '未评估' : 'Not assessed';
}

function stageLabel(stage: string | undefined, zh: boolean): string {
  if (!stage || stage === 'uncertain') return zh ? '不确定（需复核）' : 'Uncertain (review required)';
  return zh ? `倾向 ${stage}（非病理结论）` : `Suggests ${stage} (not a pathology conclusion)`;
}

/** Map AI stages like T4a onto the doctor button set T1–T4+. */
function toDoctorOption(value: string, isNature: boolean): string {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (isNature) {
    if (/^benign|良性$/i.test(raw)) return 'benign';
    if (/^malignant|恶性$/i.test(raw)) return 'malignant';
    return raw.toLowerCase();
  }
  if (/t4/i.test(raw)) return 'T4+';
  const match = raw.toUpperCase().match(/\bT([1-3])\b/);
  if (match) return `T${match[1]}`;
  return raw;
}

export function ReaderStudyQueuePanel({
  patient,
  patients = [],
  compact = false,
  studyMode,
  onStudyModeChange,
  onSelectPatient,
  systemReport = null,
  onSystemReportChange,
  onInitialJudgmentChange,
  hideTaskChrome = false,
  publicReaderOnly = false,
  assistBusy = false,
  assistResult = null,
  assistError = null,
  lesionReady = false,
  onAssist,
  onOpenReport,
  onBmReportChange,
  onGoViewer,
  queryPreviewUrl,
  queryMaskPolygon,
  queryImageWidth,
  queryImageHeight,
}: Props) {
  const searchParams = useSearchParams();
  const { language } = useSettings();
  const zh = language !== 'en';
  const { account, readerId: accountReaderId, authHeaders } = useDoctorAccount();
  const { recordOp } = useOpsRecorder();
  const [aiBaselineSigns, setAiBaselineSigns] = useState<Record<string, string>>({});
  const lastAssistSeedRef = useRef<string>('');
  const onInitialJudgmentChangeRef = useRef(onInitialJudgmentChange);
  onInitialJudgmentChangeRef.current = onInitialJudgmentChange;
  const [finalStage, setFinalStage] = useState('');
  const [finalNature, setFinalNature] = useState('');
  const [initialStage, setInitialStage] = useState('');
  const [initialNature, setInitialNature] = useState('');
  const [initialRecorded, setInitialRecorded] = useState(false);
  const [finalEditedAfterAi, setFinalEditedAfterAi] = useState(false);
  const [reason, setReason] = useState('');
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<string[]>([]);
  const [progressByCase, setProgressByCase] = useState<Record<string, 'in_progress' | 'completed'>>({});
  const [editableReport, setEditableReport] = useState<SamReport | null>(systemReport);
  const [similarUseful, setSimilarUseful] = useState<Record<string, boolean | null>>({});
  const [similarRevealed, setSimilarRevealed] = useState<Record<string, boolean>>({});
  const [similarCases, setSimilarCases] = useState<SimilarCaseCard[]>([]);
  const [evidenceFusion, setEvidenceFusion] = useState<EvidenceFusionState | null>(null);
  const [fusionBusy, setFusionBusy] = useState(false);
  const [assistJudgment, setAssistJudgment] = useState<AssistJudgmentState | null>(null);
  const [judgmentBusy, setJudgmentBusy] = useState(false);
  const lastJudgmentSeedRef = useRef('');
  const similarPanelRef = useRef<SimilarCasePanelHandle>(null);
  const [similarLoadState, setSimilarLoadState] = useState<SimilarCaseLoadState>({
    loading: false,
    loaded: false,
    refineRound: 0,
  });
  const [loopRepairBusy, setLoopRepairBusy] = useState(false);
  const [experienceReceipt, setExperienceReceipt] = useState<{ id: string; status: string } | null>(null);
  const [adjacentPair, setAdjacentPair] = useState<AdjacentPair | null>(null);
  const [depthScreen, setDepthScreen] = useState<DoctorDepthScreen | null>(null);
  const [promptConfidence, setPromptConfidence] = useState<DoctorPromptConfidence | null>(null);
  const [wallDraft, setWallDraft] = useState<WallAssistDraftDetail | null>(null);
  const [trialMemoOpen, setTrialMemoOpen] = useState(false);
  const fusionSeedRef = useRef('');
  const repairSeedRef = useRef('');
  const skipAutoLoopRef = useRef(false);
  const runEvidenceFusionRef = useRef<(force?: boolean) => Promise<void>>(async () => undefined);
  const sessionRef = useRef<string | null>(null);
  const caseStartedAtRef = useRef<number>(typeof performance === 'undefined' ? Date.now() : performance.now());
  const firstInteractionAtRef = useRef<number | null>(null);
  const reportFirstShownAtRef = useRef<number | null>(null);

  const studyEnvironment = readerEnvironmentFromSearchParams(searchParams);
  const evaluationSession = studyEnvironment === 'research' || isEvaluationBrowserSession();
  const researchAiLocked = false;

  useEffect(() => {
    if (researchAiLocked) {
      setEditableReport(null);
      return;
    }
    setEditableReport(systemReport);
    if (systemReport && reportFirstShownAtRef.current == null) {
      reportFirstShownAtRef.current = typeof performance === 'undefined' ? Date.now() : performance.now();
    }
  }, [systemReport, researchAiLocked]);

  const taskPatients = useMemo(
    () => patients.filter((item) => item.study_mode === studyMode && !isPublicDemoStill(item)),
    [patients, studyMode],
  );
  const progressReaderKey = studyEnvironment === 'research'
    ? 'authenticated_reader'
    : (searchParams.get('reader_id') || 'staging_reader');
  const completedKey = `reader_v150_${studyEnvironment}_${progressReaderKey}_completed_${studyMode}`;

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(completedKey);
      setCompletedIds(raw ? JSON.parse(raw) : []);
    } catch {
      setCompletedIds([]);
    }
  }, [completedKey]);

  useEffect(() => {
    setAdjacentPair(null);
    setDepthScreen(null);
    setPromptConfidence(null);
    setWallDraft(null);
  }, [patient?.id]);

  useEffect(() => {
    const onLock = (event: Event) => {
      const detail = (event as CustomEvent<AdjacentLockEventDetail>).detail;
      if (!detail) return;
      setAdjacentPair(detail.pair);
    };
    const onWall = (event: Event) => {
      const detail = (event as CustomEvent<WallAssistDraftDetail>).detail;
      if (!detail) return;
      setWallDraft(detail);
    };
    window.addEventListener(ADJACENT_LOCK_EVENT, onLock);
    window.addEventListener(WALL_ASSIST_DRAFT_EVENT, onWall);
    return () => {
      window.removeEventListener(ADJACENT_LOCK_EVENT, onLock);
      window.removeEventListener(WALL_ASSIST_DRAFT_EVENT, onWall);
    };
  }, []);

  const auditReaderId = account?.account_id || accountReaderId || undefined;
  const jsonHeaders = authHeaders({ 'Content-Type': 'application/json' });

  const persistCaseState = useCallback((patch: Record<string, unknown>, caseOverride?: Patient | null) => {
    const target = caseOverride || patient;
    if (!target || !auditReaderId) return;
    void fetch('/api/reader/case-state', {
      method: 'PUT',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        account_id: auditReaderId,
        case_id: target.id,
        patient_id: target.patient_id,
        study_mode: studyMode,
        ...patch,
      }),
    }).catch(() => {
      // Persist must not interrupt reading.
    });
  }, [auditReaderId, authHeaders, patient, studyMode]);

  const [similarReasons, setSimilarReasons] = useState<Record<string, string[]>>({});

  const buildSimilarFeedbackPayload = useCallback((
    usefulMap: Record<string, boolean | null>,
    revealedMap: Record<string, boolean>,
    cases: SimilarCaseCard[],
    reasonMap: Record<string, string[]> = similarReasons,
  ): SimilarCaseFeedbackEntry[] => {
    const byId = new Map(cases.map((c) => [String(c.image_id || ''), c]));
    const ids = new Set([
      ...Object.keys(usefulMap),
      ...Object.keys(revealedMap),
      ...cases.map((c) => String(c.image_id || '')),
    ]);
    const out: SimilarCaseFeedbackEntry[] = [];
    for (const imageId of ids) {
      if (!imageId) continue;
      const useful = usefulMap[imageId];
      const revealed = Boolean(revealedMap[imageId]);
      if (useful == null && !revealed) continue;
      const card = byId.get(imageId);
      out.push({
        image_id: imageId,
        display_id: card?.display_id || imageId,
        useful: useful === true,
        revealed_pathology: revealed,
        rank: typeof card?.rank === 'number' ? card.rank : null,
        evidence_role: evaluationSession ? null : (card?.evidence_role || null),
        reasons: reasonMap[imageId] || [],
        updated_at: new Date().toISOString(),
      });
    }
    return out;
  }, [evaluationSession, similarReasons]);

  const activityAppend = useCallback((type: string, labelZh: string, labelEn: string, detail?: Record<string, unknown>) => ({
    id: `act_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
    at: new Date().toISOString(),
    type,
    label_zh: labelZh,
    label_en: labelEn,
    detail,
  }), []);

  const handleSimilarUsefulChange = useCallback((item: SimilarCaseCard, useful: boolean) => {
    const imageId = String(item.image_id || '').trim();
    if (!imageId) return;
    setSimilarUseful((prev) => {
      const next = { ...prev, [imageId]: useful };
      const cases = similarCases.some((c) => String(c.image_id) === imageId)
        ? similarCases
        : [...similarCases, item];
      if (!similarCases.some((c) => String(c.image_id) === imageId)) {
        setSimilarCases(cases);
      }
      const feedback = buildSimilarFeedbackPayload(next, similarRevealed, cases);
      persistCaseState({ similar_case_feedback: feedback });
      return next;
    });
  }, [buildSimilarFeedbackPayload, persistCaseState, similarCases, similarRevealed]);

  const handleSimilarRevealChange = useCallback((imageId: string, revealed: boolean) => {
    setSimilarRevealed((prev) => {
      const next = { ...prev, [imageId]: revealed };
      const feedback = buildSimilarFeedbackPayload(similarUseful, next, similarCases);
      persistCaseState({ similar_case_feedback: feedback });
      return next;
    });
  }, [buildSimilarFeedbackPayload, persistCaseState, similarCases, similarUseful]);

  const handleSimilarReasonChange = useCallback((item: SimilarCaseCard, reasons: string[]) => {
    const imageId = String(item.image_id || '').trim();
    if (!imageId) return;
    setSimilarReasons((prev) => {
      const next = { ...prev, [imageId]: reasons };
      persistCaseState({
        similar_case_feedback: buildSimilarFeedbackPayload(
          similarUseful,
          similarRevealed,
          similarCases,
          next,
        ),
      });
      return next;
    });
  }, [buildSimilarFeedbackPayload, persistCaseState, similarCases, similarRevealed, similarUseful]);

  useEffect(() => {
    if (!auditReaderId) return;
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch(
          `/api/reader/case-state?study_mode=${encodeURIComponent(studyMode)}`,
          { cache: 'no-store', headers: authHeaders() },
        );
        if (!response.ok || cancelled) return;
        const data = await response.json() as {
          ok?: boolean;
          states?: Array<{ case_id?: string; progress?: string; completed?: boolean }>;
        };
        if (!Array.isArray(data.states)) return;
        const map: Record<string, 'in_progress' | 'completed'> = {};
        const done: string[] = [];
        for (const row of data.states) {
          const id = String(row.case_id || '').trim();
          if (!id) continue;
          if (row.completed || row.progress === 'completed') {
            map[id] = 'completed';
            done.push(id);
          } else {
            map[id] = 'in_progress';
          }
        }
        if (cancelled) return;
        setProgressByCase(map);
        if (done.length) {
          setCompletedIds((prev) => Array.from(new Set([...prev, ...done])));
        }
      } catch {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [auditReaderId, authHeaders, studyMode]);

  useEffect(() => {
    caseStartedAtRef.current = typeof performance === 'undefined' ? Date.now() : performance.now();
    firstInteractionAtRef.current = null;
    reportFirstShownAtRef.current = null;
    sessionRef.current = null;
    setFinalStage('');
    setFinalNature('');
    setInitialStage('');
    setInitialNature('');
    setInitialRecorded(false);
    setFinalEditedAfterAi(false);
    onInitialJudgmentChangeRef.current?.(false, { source: 'reset' });
    setReason('');
    setActionStatus(null);
    setAiBaselineSigns({});
    lastAssistSeedRef.current = '';
    setSimilarUseful({});
    setSimilarRevealed({});
    setSimilarCases([]);
    setSimilarReasons({});
    setEvidenceFusion(null);
    setExperienceReceipt(null);
    setFusionBusy(false);
    setAssistJudgment(null);
    setJudgmentBusy(false);
    lastJudgmentSeedRef.current = '';
    setSimilarLoadState({ loading: false, loaded: false, refineRound: 0 });
    setLoopRepairBusy(false);
    fusionSeedRef.current = '';
    repairSeedRef.current = '';
    skipAutoLoopRef.current = false;

    if (!patient?.id || !auditReaderId) return;
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch(
          `/api/reader/case-state?case_id=${encodeURIComponent(patient.id)}`,
          { cache: 'no-store', headers: authHeaders() },
        );
        if (!response.ok || cancelled) return;
        const data = await response.json() as {
          ok?: boolean;
          state?: {
            initial_nature?: string | null;
            initial_stage?: string | null;
            final_nature?: string | null;
            final_stage?: string | null;
            initial_recorded?: boolean;
            final_edited_after_ai?: boolean;
            completed?: boolean;
            similar_case_feedback?: SimilarCaseFeedbackEntry[];
            evidence_fusion?: EvidenceFusionState | null;
            assist_judgment?: AssistJudgmentState | null;
            adjacent_lock?: AdjacentPair | null;
            depth_screen?: 'shallow_clear' | 'outer_clear' | 'boundary_unclear' | null;
            doctor_prompt_confidence?: 'high' | 'mid' | 'low' | null;
          } | null;
        };
        const state = data.state;
        if (!state || cancelled) return;
        if (state.initial_nature) setInitialNature(String(state.initial_nature));
        if (state.initial_stage) setInitialStage(String(state.initial_stage));
        if (state.final_nature) setFinalNature(String(state.final_nature));
        if (state.final_stage) setFinalStage(String(state.final_stage));
        if (state.initial_recorded) {
          setInitialRecorded(true);
          // Restore must not force-close mobile panes (parent used to fight bottom-nav reopen).
          onInitialJudgmentChangeRef.current?.(true, { source: 'restore' });
        }
        // Prefer showing the doctor's last choice on resume (final if present).
        if (state.final_edited_after_ai || state.final_stage || state.final_nature) {
          setFinalEditedAfterAi(true);
        }
        if (Array.isArray(state.similar_case_feedback) && state.similar_case_feedback.length) {
          const usefulMap: Record<string, boolean | null> = {};
          const revealedMap: Record<string, boolean> = {};
          const reasonMap: Record<string, string[]> = {};
          for (const row of state.similar_case_feedback) {
            const id = String(row.image_id || '').trim();
            if (!id) continue;
            usefulMap[id] = Boolean(row.useful);
            if (row.revealed_pathology) revealedMap[id] = true;
            if (Array.isArray(row.reasons) && row.reasons.length) {
              reasonMap[id] = row.reasons.map(String);
            }
          }
          setSimilarUseful(usefulMap);
          setSimilarRevealed(revealedMap);
          setSimilarReasons(reasonMap);
        }
        if (state.evidence_fusion?.prose) {
          setEvidenceFusion(state.evidence_fusion);
          skipAutoLoopRef.current = true;
        }
        if (state.assist_judgment?.explanation?.length || state.assist_judgment?.prose) {
          setAssistJudgment(state.assist_judgment);
        }
        const restoredScreen = parseDoctorDepthScreen(state.depth_screen);
        if (restoredScreen) setDepthScreen(restoredScreen);
        const restoredConfidence = parseDoctorPromptConfidence(state.doctor_prompt_confidence);
        if (restoredConfidence) setPromptConfidence(restoredConfidence);
        const restoredLock = parseAdjacentPair(state.adjacent_lock);
        if (restoredLock) {
          setAdjacentPair(restoredLock);
          window.dispatchEvent(new CustomEvent(ADJACENT_LOCK_EVENT, {
            detail: { pair: restoredLock, source: 'restore' } satisfies AdjacentLockEventDetail,
          }));
        }
        if (state.completed) {
          setActionStatus(zh ? '本例此前已保存；可继续核对或改判后再次保存' : 'This case was saved earlier; you can review or change and save again');
        } else if (state.initial_recorded) {
          setActionStatus(zh ? '已恢复上次判断，可继续辅助分析或改判' : 'Restored your last judgment; continue assist or edit');
        }
      } catch {
        // ignore
      }
    })();
    return () => { cancelled = true; };
    // Intentionally omit onInitialJudgmentChange: use ref so parent re-renders do not re-reset/restore.
  }, [auditReaderId, authHeaders, patient?.id, studyMode, zh]);

  useEffect(() => {
    if (!assistResult || researchAiLocked) return;
    const seedKey = [
      patient?.id,
      studyMode,
      readAssistDecision(assistResult, studyMode).value,
      readAssistDecision(assistResult, studyMode).confidence,
    ].join('|');
    if (lastAssistSeedRef.current === seedKey) return;
    lastAssistSeedRef.current = seedKey;
    const seeded = overlayAssistOnReport(systemReport, assistResult, studyMode);
    if (!seeded) return;
    setEditableReport(seeded);
    onSystemReportChange?.(seeded);
    const decision = readAssistDecision(assistResult, studyMode);
    setAiBaselineSigns(collectFeatureSnapshot(
      seeded,
      visibleAssistFeatureFields({
        studyMode,
        nature: decision.value,
        stage: decision.value,
      }),
    ));
    if (reportFirstShownAtRef.current == null) {
      reportFirstShownAtRef.current = typeof performance === 'undefined' ? Date.now() : performance.now();
    }
  }, [assistResult, onSystemReportChange, patient?.id, researchAiLocked, studyMode, systemReport]);

  if (!patient) return null;

  const isNatureTask = studyMode === 'benign_malignancy';
  const aiDecision = readAssistDecision(assistResult, studyMode);
  const currentIndex = taskPatients.findIndex((item) => item.id === patient.id);
  const completedCount = taskPatients.filter((item) => completedIds.includes(item.id)).length;
  const nextPatient = currentIndex >= 0 ? taskPatients[currentIndex + 1] : taskPatients[0];
  const selectedValue = isNatureTask ? finalNature : finalStage;
  const taskLabel = isNatureTask
    ? (zh ? '良恶性判断' : 'benign-versus-malignant classification')
    : (zh ? 'T 分期判断' : 'T-staging classification');
  const activeReport = researchAiLocked ? null : (editableReport || systemReport);
  const conflicts = activeReport?.conflicts || [];
  const highConflict = conflicts.some((item) => item.severity === 'high');
  const recommendationBlocked = researchAiLocked || !aiDecision.value;
  const finalActionsLocked = studyEnvironment === 'research' && !initialRecorded;

  const updateReportSign = (fieldPath: string, value: string) => {
    if (!activeReport) return;
    if (firstInteractionAtRef.current == null) {
      firstInteractionAtRef.current = typeof performance === 'undefined' ? Date.now() : performance.now();
    }
    const currentSigns = (activeReport.signs || {}) as Record<string, Record<string, unknown>>;
    const [group, key] = fieldPath.split('.');
    const nextSigns: Record<string, Record<string, unknown>> = { ...currentSigns };
    if (key) {
      nextSigns[group] = {
        ...(currentSigns[group] || {}),
        [key]: {
          ...((currentSigns[group]?.[key] as Record<string, unknown> | undefined) || {}),
          value,
          status: 'doctor_edited',
          source: 'doctor',
        },
      };
    } else {
      nextSigns[group] = {
        ...(currentSigns[group] || {}),
        value,
        status: 'doctor_edited',
        source: 'doctor',
      };
    }
    const next = { ...activeReport, signs: nextSigns };
    setEditableReport(next);
    onSystemReportChange?.(next);
    recordOp('sign_edit', {
      op: 'sign_edit',
      value,
      label: fieldPath,
      tool: fieldPath,
    }, {
      caseId: patient?.id,
      patientId: patient?.patient_id,
      page: 'workbench',
    });
    persistCaseState({
      progress: 'in_progress',
      activity_append: activityAppend(
        'sign_edit',
        `改特征 ${fieldPath}=${value}`,
        `Edited sign ${fieldPath}=${value}`,
        { field: fieldPath, value },
      ),
    });
  };

  const chooseTask = (nextMode: ReaderStudyMode) => {
    if (nextMode === studyMode) return;
    onStudyModeChange(nextMode);
  };

  const setCompleted = (id: string) => {
    setCompletedIds((current) => {
      const next = current.includes(id) ? current : [...current, id];
      try {
        window.localStorage.setItem(completedKey, JSON.stringify(next));
      } catch {
        /* Local progress is a convenience; server audit remains authoritative. */
      }
      return next;
    });
  };

  const recordInitialJudgment = async (pickedValue?: string) => {
    if (!patient || initialRecorded) return;
    const initialValue = pickedValue
      || (isNatureTask ? initialNature : initialStage);
    if (!initialValue) {
      setActionStatus(zh ? `请先完成${taskLabel}` : `Complete ${taskLabel} first`);
      return;
    }
    if (isNatureTask) setInitialNature(initialValue);
    else setInitialStage(initialValue);
    if (!sessionRef.current) sessionRef.current = `queue-${patient.id}-${Date.now()}`;
    const environment = studyEnvironment;
    const readerId = environment === 'research' ? undefined : auditReaderId;
    const recordedAt = new Date().toISOString();
    setActionStatus(zh ? '正在记录初始判断…' : 'Recording initial judgment…');
    try {
      const response = await fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({
          ...READER_ROUND2_VERSION_FIELDS,
          event_type: 'initial_judgment',
          session_id: sessionRef.current,
          case_id: patient.id,
          ...(readerId ? { reader_id: readerId } : {}),
          condition: 'ai_assisted',
          study_mode: studyMode,
          round: searchParams.get('round') || 'round2',
          environment,
          patient_id: patient.patient_id,
          payload: {
            doctor_initial_nature: isNatureTask ? initialValue : null,
            doctor_initial_t_stage: isNatureTask ? null : initialValue,
            initial_recorded_at: recordedAt,
            ai_visible_before_initial: false,
            structured_signs_visible: false,
            research_ai_locked_until_initial: studyEnvironment === 'research',
          },
          client_recorded_at: recordedAt,
        }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({})) as { error?: string };
        throw new Error(detail.error || `HTTP ${response.status}`);
      }
      setInitialRecorded(true);
      onInitialJudgmentChange?.(true, { source: 'user' });
      recordOp('initial_judgment', {
        op: 'initial_judgment',
        action_type: 'initial_judgment',
        value: initialValue,
        doctor_initial_nature: isNatureTask ? initialValue : null,
        doctor_initial_t_stage: isNatureTask ? null : initialValue,
        after_value: initialValue,
        initial_recorded_at: recordedAt,
      }, {
        caseId: patient.id,
        patientId: patient.patient_id,
        page: 'reader',
      });
      persistCaseState({
        progress: 'in_progress',
        initial_recorded: true,
        initial_nature: isNatureTask ? initialValue : null,
        initial_stage: isNatureTask ? null : initialValue,
        activity_append: activityAppend(
          'initial_judgment',
          `初判 ${optionLabel(initialValue)}`,
          `Initial judgment ${optionLabel(initialValue)}`,
          { value: initialValue },
        ),
      });
      if (systemReport) {
        setEditableReport(systemReport);
        reportFirstShownAtRef.current = typeof performance === 'undefined' ? Date.now() : performance.now();
      }
      setActionStatus(zh ? '初始判断已记录，请继续核对 AI 证据并提交最终判断。' : 'Initial judgment recorded. Review the AI evidence and submit the final judgment.');
    } catch (error) {
      setActionStatus(error instanceof Error
        ? `${zh ? '初始判断记录失败' : 'Initial judgment failed'}: ${error.message}`
        : (zh ? '初始判断记录失败' : 'Initial judgment failed'));
    }
  };

  const writeDoctorAction = async (actionType: DoctorAction, afterValue?: string) => {
    if (!patient) return;
    const selected = afterValue || selectedValue;
    if (finalActionsLocked) {
      setActionStatus(zh ? '请先给出你的判断' : 'Record your judgment first');
      return;
    }
    if (actionType === 'accept' && recommendationBlocked) {
      setActionStatus(zh
        ? '存在高风险证据冲突，不能直接接受；请不接受或标记证据不足。'
        : 'A high-risk evidence conflict blocks direct acceptance. Reject, or mark evidence as insufficient.');
      return;
    }
    if (!selected && actionType !== 'request_more_evidence') {
      setActionStatus(zh ? `请先完成${taskLabel}` : `Complete ${taskLabel} first`);
      return;
    }
    if (actionType === 'request_more_evidence' && similarLoadState.refineRound < 1) {
      setLoopRepairBusy(true);
      setActionStatus(zh ? '证据偏薄，正在再检索一轮…' : 'Evidence is thin; retrieving one more round…');
      try {
        await similarPanelRef.current?.refineOnce();
      } finally {
        setLoopRepairBusy(false);
      }
    }
    if (!sessionRef.current) sessionRef.current = `queue-${patient.id}-${Date.now()}`;
    const environment = readerEnvironmentFromSearchParams(searchParams);
    const now = typeof performance === 'undefined' ? Date.now() : performance.now();
    const totalCaseTimeSec = Math.max(0, (now - caseStartedAtRef.current) / 1000);
    const aiWaitSec = Number.isFinite(Number(activeReport?.elapsed_ms))
      ? Math.max(0, Number(activeReport?.elapsed_ms) / 1000)
      : 0;
    const reportCompletionSec = reportFirstShownAtRef.current == null
      ? null
      : Math.max(0, (now - reportFirstShownAtRef.current) / 1000);
    const doctorActiveReadingSec = Math.max(0, totalCaseTimeSec - aiWaitSec);
    const firstInteractionSec = firstInteractionAtRef.current == null
      ? null
      : Math.max(0, (firstInteractionAtRef.current - caseStartedAtRef.current) / 1000);
    const structuredSigns = compactReaderSigns(activeReport);
    const evidenceIds = readerEvidenceIds(activeReport);
    const readerId = environment === 'research' ? undefined : auditReaderId;
    const visibleFields = visibleAssistFeatureFields({
      studyMode,
      nature: isNatureTask ? aiDecision.value : null,
      stage: aiDecision.value,
    });
    const currentFeatures = collectFeatureSnapshot(activeReport, visibleFields);
    const edits = featureEdits(aiBaselineSigns, currentFeatures, visibleFields);
    setActionStatus(zh ? '正在记录…' : 'Recording…');
    try {
      const response = await fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({
          ...READER_ROUND2_VERSION_FIELDS,
          event_type: 'doctor_action',
          session_id: sessionRef.current,
          case_id: patient.id,
          ...(readerId ? { reader_id: readerId } : {}),
          condition: 'ai_assisted',
          study_mode: studyMode,
          round: searchParams.get('round') || 'round2',
          environment,
          patient_id: patient.patient_id,
          payload: {
            action_id: `action-${Date.now()}`,
            action_type: actionType,
            doctor_initial_nature: isNatureTask ? initialNature || null : null,
            doctor_initial_t_stage: isNatureTask ? null : initialStage || null,
            initial_judgment_recorded: initialRecorded,
            before_value: aiDecision.value || activeReport?.recommended_stage || null,
            after_value: selected || null,
            features_modified: edits.length > 0,
            feature_edits: edits,
            ai_features: aiBaselineSigns,
            doctor_features: currentFeatures,
            account_id: auditReaderId || null,
            reason: reason || (actionType === 'request_more_evidence' ? (zh ? '证据不足' : 'insufficient evidence') : null),
            queue: 'reader_v150',
            study_mode: studyMode,
            ai_assisted: true,
            system_report_available: Boolean(activeReport),
            recommendation_status: activeReport?.recommendation_status || null,
            conflicts,
            judgment_prose: buildAssistJudgmentProse({
              studyMode,
              report: activeReport,
              patient,
              aiValue: assistHeadline || aiDecision.value || selected || '',
              zh,
              wallDraft,
              adjacentLock: adjacentLock
                ? {
                  pair: adjacentPair,
                  pairZh: adjacentLock.left + ' / ' + adjacentLock.right,
                  pairEn: adjacentLock.left + ' / ' + adjacentLock.right,
                  lockedChoice: adjacentLock.lockedChoice,
                  outsideLock: adjacentLock.outsideLock,
                  frozenTop1: adjacentLock.frozenTop1,
                }
                : null,
            }),
            similar_case_feedback: buildSimilarFeedbackPayload(similarUseful, similarRevealed, similarCases),
            evidence_fusion: evidenceFusion,
            assist_judgment: assistJudgment,
            structured_signs: structuredSigns,
            lesion_extent: {
              length: (structuredSigns['size.length'] as Record<string, unknown> | undefined)?.value
                || (structuredSigns.size as Record<string, unknown> | undefined)?.length
                || null,
              thickness: (structuredSigns['size.thickness'] as Record<string, unknown> | undefined)?.value
                || (structuredSigns.size as Record<string, unknown> | undefined)?.thickness
                || null,
              mask_evidence: evidenceIds.some((id) => /mask|lesion|roi/i.test(id)),
            },
            wall_invasion_depth: structuredSigns.layer_structure || null,
            serosal_breakthrough: structuredSigns.serosa_change || null,
            growth_pattern: structuredSigns.growth_pattern || null,
            evidence_ids: evidenceIds,
            time_decomposition: {
              total_case_time_sec: totalCaseTimeSec,
              doctor_active_reading_sec: doctorActiveReadingSec,
              ai_wait_sec: aiWaitSec,
              report_completion_sec: reportCompletionSec,
              first_interaction_sec: firstInteractionSec,
            },
            environment,
          },
          client_recorded_at: new Date().toISOString(),
        }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({})) as { error?: string };
        throw new Error(detail.error || `HTTP ${response.status}`);
      }
      await writeDecisionTrace({
        eventType: decisionEventType(actionType),
        sessionId: sessionRef.current,
        caseId: patient.id,
        patientId: patient.patient_id,
        readerId,
        studyMode,
        environment,
        page: 'reader',
        headers: jsonHeaders,
        payload: {
          action_type: actionType,
          accepted: actionType === 'accept',
          doctor_initial_nature: isNatureTask ? initialNature || null : null,
          doctor_initial_t_stage: isNatureTask ? null : initialStage || null,
          ai_t_stage: aiDecision.value || activeReport?.recommended_stage || null,
          ai_confidence: aiDecision.confidence,
          before_value: aiDecision.value || activeReport?.recommended_stage || null,
          after_value: selected || null,
          features_modified: edits.length > 0,
          feature_edits: edits,
          account_id: auditReaderId || null,
          reason: reason || null,
        },
      });
      recordOp(decisionEventType(actionType), {
        op: actionType,
        value: selected || null,
        before_value: aiDecision.value || activeReport?.recommended_stage || null,
        after_value: selected || null,
        status: 'ok',
        reason: reason || null,
      }, {
        caseId: patient.id,
        patientId: patient.patient_id,
        page: 'workbench',
      });
      if (actionType !== 'request_more_evidence') {
        await fetch('/api/reader-audit/events', {
          method: 'POST',
          headers: jsonHeaders,
          body: JSON.stringify({
            ...READER_ROUND2_VERSION_FIELDS,
            event_type: 'case_completed',
            session_id: sessionRef.current,
            case_id: patient.id,
            ...(readerId ? { reader_id: readerId } : {}),
            condition: 'ai_assisted',
            study_mode: studyMode,
            round: searchParams.get('round') || 'round2',
            environment,
            patient_id: patient.patient_id,
            payload: {
              doctor_action: actionType,
              after_value: selected || null,
              doctor_final_nature: isNatureTask ? selected || null : null,
              doctor_final_t_stage: isNatureTask ? null : selected || null,
              completed: true,
            },
            client_recorded_at: new Date().toISOString(),
          }),
        });
      }
      try {
        await fetch('/api/agent/feedback', {
          method: 'POST',
          headers: jsonHeaders,
          body: JSON.stringify({
            patient_id: patient.patient_id,
            session_id: sessionRef.current,
            action: actionType === 'accept' ? 'accept' : actionType === 'reject' ? 'reject' : 'defer',
            predicted_t_stage: activeReport?.recommended_stage || undefined,
            recommended_t_stage: activeReport?.recommended_stage || undefined,
            final_t_stage: selected || undefined,
            feedback_type: 'doctor_correction',
            correction_text: reason || (actionType === 'request_more_evidence' ? (zh ? '证据不足' : 'insufficient evidence') : undefined),
            confidence: activeReport?.calibrated_confidence != null
              ? String(activeReport.calibrated_confidence)
              : undefined,
            reviewer: readerId || 'authenticated_reader',
          }),
        });
      } catch {
        // Audit remains authoritative; feedback promotion is best effort and governed separately.
      }
      if (actionType === 'accept' || actionType === 'modify') {
        try {
          const expRes = await fetch('/api/reader/experience', {
            method: 'POST',
            headers: jsonHeaders,
            body: JSON.stringify({
              case_id: patient.id,
              patient_id: patient.patient_id,
              study_mode: studyMode,
              action: actionType,
              task_type: studyMode === 'benign_malignancy' ? 'BM' : 'T_staging',
              uncertainty: evidenceFusion?.critic?.adequacy || '',
              critic_adequacy: evidenceFusion?.critic?.adequacy || '',
              refine_round: similarLoadState.refineRound,
              predicted: aiDecision.value || activeReport?.recommended_stage || null,
              doctor_final: selected || null,
              workflow: [
                'source_prediction',
                'episodic_tent',
                'guideline_retrieval',
                'case_retrieval',
                'evidence_adjudication',
                ...(similarLoadState.refineRound > 0 ? ['optional_repair'] : []),
              ],
            }),
          });
          const expJson = await expRes.json() as { ok?: boolean; experience_id?: string; release_status?: string };
          if (expJson.ok && expJson.experience_id) {
            setExperienceReceipt({
              id: expJson.experience_id,
              status: expJson.release_status || 'candidate',
            });
          }
        } catch {
          // Candidate log is offline collection only.
        }
      }
      setCompleted(patient.id);
      setProgressByCase((prev) => ({ ...prev, [patient.id]: 'completed' }));
      persistCaseState({
        progress: 'completed',
        completed: true,
        initial_recorded: true,
        final_edited_after_ai: finalEditedAfterAi,
        initial_nature: isNatureTask ? initialNature || null : null,
        initial_stage: isNatureTask ? null : initialStage || null,
        final_nature: isNatureTask ? (selected || null) : null,
        final_stage: isNatureTask ? null : (selected || null),
        similar_case_feedback: buildSimilarFeedbackPayload(similarUseful, similarRevealed, similarCases),
        evidence_fusion: evidenceFusion,
        assist_judgment: assistJudgment,
        activity_append: activityAppend(
          actionType === 'accept' ? 'ai_decision_accept' : actionType === 'modify' ? 'ai_decision_modify' : 'ai_decision_more_evidence',
          actionType === 'accept'
            ? `同意 AI 并保存 (${selected || '-'})`
            : actionType === 'modify'
              ? `按我的判断保存 (${selected || '-'})`
              : '证据不足并保存',
          actionType === 'accept'
            ? `Accept AI and save (${selected || '-'})`
            : actionType === 'modify'
              ? `Save my call (${selected || '-'})`
              : 'Need more evidence and save',
          { action: actionType, value: selected || null },
        ),
      });
      if (onSelectPatient && nextPatient) {
        onSelectPatient(nextPatient);
        setActionStatus(zh ? '已保存，进入下一例' : 'Saved. Moving to the next case.');
      } else {
        setActionStatus(zh ? '已保存，本任务已完成或没有下一例' : 'Saved. This task is complete or has no next case.');
      }
    } catch (error) {
      setActionStatus(error instanceof Error
        ? `${zh ? '记录失败' : 'Recording failed'}: ${error.message}`
        : (zh ? '记录失败' : 'Recording failed'));
    }
  };

  const doctorValue = isNatureTask ? initialNature : initialStage;
  const finalValue = isNatureTask ? finalNature : finalStage;
  const aiValueRaw = aiDecision.value
    || (isNatureTask
      ? (/^benign|良性$/i.test(String(activeReport?.recommended_stage || '')) ? 'benign' : (activeReport?.recommended_stage ? 'malignant' : ''))
      : String(activeReport?.recommended_stage || '').trim());
  const aiValue = toDoctorOption(aiValueRaw, isNatureTask);
  const aiLabel = aiDecision.label
    || (isNatureTask
      ? (aiValue === 'benign' ? (zh ? '良性' : 'Benign') : aiValue === 'malignant' ? (zh ? '恶性' : 'Malignant') : '')
      : (aiValueRaw || aiValue));
  const aiPct = aiDecision.confidence != null
    ? Math.round(aiDecision.confidence * 100)
    : (activeReport?.calibrated_confidence != null ? Math.round(activeReport.calibrated_confidence * 100) : null);
  const natureOptions = ['benign', 'malignant'] as const;
  const stageOptions = ['T1', 'T2', 'T3', 'T4+'] as const;
  const optionLabel = (value: string) => (
    value === 'benign' ? (zh ? '良性' : 'Benign')
      : value === 'malignant' ? (zh ? '恶性' : 'Malignant')
        : value
  );
  const displayDoctorValue = finalEditedAfterAi && finalValue ? finalValue : doctorValue;
  const myCallValue = displayDoctorValue || doctorValue || finalValue;
  const canModifySave = Boolean(initialRecorded && myCallValue);
  const canAcceptAi = Boolean(aiValue) && !recommendationBlocked;
  const tAssist = readAssistStage(assistResult);
  const tLooksReal = /^T[1-4]/i.test(String(tAssist.label || ''));
  const tPct = tAssist.confidence != null ? Math.round(tAssist.confidence * 100) : null;
  const featureFields = visibleAssistFeatureFields({
    studyMode,
    nature: isNatureTask ? (aiValue || displayDoctorValue) : null,
    stage: isNatureTask ? (aiValue || displayDoctorValue) : (tAssist.label || aiValue || displayDoctorValue),
  });
  const showBenignFill = isNatureTask && aiValue === 'benign';
  const assistCanRun = Boolean(lesionReady && onAssist && !assistBusy);
  const tentCompare = readTentCompare(assistResult);
  const assistProbs = extractAssistProbabilities(assistResult);
  const adjacentLock = !isNatureTask && adjacentPair
    ? lockAdjacentStage(assistProbs.t, adjacentPair)
    : null;
  const assistHeadline = aiValue;
  const assistHeadlinePct = aiPct;
  const wallProse = buildWallDraftProse(wallDraft, zh);
  const wallFusion = fuseWallDraftIntoStaging(wallDraft, adjacentPair, adjacentLock?.lockedChoice);
  const wallContinuity = compareKeyframeContinuity(wallDraft?.keyframes || []);
  const pickAdjacentLock = (pair: AdjacentPair) => {
    const next = adjacentPair === pair ? null : pair;
    setAdjacentPair(next);
    recordOp('adjacent_lock', {
      op: 'adjacent_lock',
      value: next || '',
      after_value: next || '',
      before_value: adjacentPair || '',
      layer: next ? String(pairMeta(next).layers) : null,
    }, {
      caseId: patient?.id,
      patientId: patient?.patient_id,
      page: 'workbench',
    });
    window.dispatchEvent(new CustomEvent(ADJACENT_LOCK_EVENT, {
      detail: { pair: next, source: 'evidence' } satisfies AdjacentLockEventDetail,
    }));
    persistCaseState({ adjacent_lock: next });
  };
  const pickDepthScreen = (screen: DoctorDepthScreen) => {
    const next = depthScreen === screen ? null : screen;
    setDepthScreen(next);
    recordOp('depth_screen', {
      op: 'depth_screen',
      value: next || '',
      after_value: next || '',
      before_value: depthScreen || '',
    }, {
      caseId: patient?.id,
      patientId: patient?.patient_id,
      page: 'workbench',
    });
    window.dispatchEvent(new CustomEvent(DEPTH_SCREEN_EVENT, {
      detail: { screen: next, confidence: promptConfidence } satisfies DepthScreenEventDetail,
    }));
    persistCaseState({ depth_screen: next });
  };
  const pickPromptConfidence = (value: DoctorPromptConfidence) => {
    const next = promptConfidence === value ? null : value;
    setPromptConfidence(next);
    window.dispatchEvent(new CustomEvent(DEPTH_SCREEN_EVENT, {
      detail: { screen: depthScreen, confidence: next } satisfies DepthScreenEventDetail,
    }));
    persistCaseState({ doctor_prompt_confidence: next });
  };
  const loopSteps = [
    {
      id: 'visual',
      zh: '分类',
      en: 'Visual',
      status: assistBusy ? 'run' as const : (aiValue ? 'done' as const : 'idle' as const),
    },
    {
      id: 'guideline',
      zh: '指南',
      en: 'Guideline',
      status: judgmentBusy ? 'run' as const : (assistJudgment ? 'done' as const : (aiValue ? 'idle' as const : 'idle' as const)),
    },
    {
      id: 'cases',
      zh: '相似例',
      en: 'Cases',
      status: similarLoadState.loading
        ? 'run' as const
        : (similarLoadState.loaded ? 'done' as const : (aiValue ? 'idle' as const : 'idle' as const)),
    },
    {
      id: 'critic',
      zh: '对照',
      en: 'Critic',
      status: fusionBusy ? 'run' as const : (evidenceFusion ? 'done' as const : (similarLoadState.loaded ? 'idle' as const : 'idle' as const)),
    },
    {
      id: 'repair',
      zh: '再检索',
      en: 'Repair',
      status: loopRepairBusy
        ? 'run' as const
        : (similarLoadState.refineRound >= 1
          ? 'done' as const
          : (evidenceFusion && !evidenceFusion.critic?.repair_recommended ? 'skip' as const : 'idle' as const)),
    },
  ];
  const notAssessedLabel = zh ? '未评估' : 'Not assessed';
  const judgmentProse = assistHeadline
    ? [buildAssistJudgmentProse({
      studyMode,
      report: activeReport,
      patient,
      aiValue: assistHeadline,
      zh,
      wallDraft,
      adjacentLock: adjacentLock
        ? {
          pair: adjacentPair,
          pairZh: adjacentLock.left + ' / ' + adjacentLock.right,
          pairEn: adjacentLock.left + ' / ' + adjacentLock.right,
          lockedChoice: adjacentLock.lockedChoice,
          outsideLock: adjacentLock.outsideLock,
          frozenTop1: adjacentLock.frozenTop1,
        }
        : null,
    }), wallProse].filter(Boolean).join('\n')
    : '';

  const doctorFeatureValues = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [path] of featureFields) {
      const field = getSign(activeReport, path);
      const value = String(field?.value || aiBaselineSigns[path] || '').trim();
      if (value) out[path] = value;
    }
    return out;
  }, [activeReport, aiBaselineSigns, featureFields]);

  const frozenTop1 = String(
    isNatureTask
      ? (aiValue || aiDecision.value || '')
      : (tAssist.label || aiValue || activeReport?.recommended_stage || ''),
  ).trim();
  const displayTop1 = String(frozenTop1 || aiValue || '').trim();
  const depthConflict = !isNatureTask && depthScreenConflictsAi(depthScreen, displayTop1);
  const judgmentSigns = useMemo(
    () => mergeJudgmentDoctorSigns({
      signs: doctorFeatureValues,
      wallDraft,
      headline: displayTop1,
      frozenTop1,
      zh,
    }),
    [displayTop1, doctorFeatureValues, frozenTop1, wallDraft, zh],
  );
  const wallJudgmentSeed = [
    wallDraft?.targetLayers || '',
    (wallDraft?.interrupts || []).map((item) => `${item.layer}:${item.interrupted ? 1 : 0}`).join(','),
    (wallDraft?.ticks || []).map((item) => `${item.nameZh}:${item.status || ''}`).join(','),
    (wallDraft?.fates || []).map((item) => `${item.id}:${item.verdict || ''}`).join(','),
    wallDraft?.cluster?.pattern || '',
    wallDraft?.remainPx ?? '',
    wallDraft?.echoPatternZh || '',
    wallDraft?.echoDoctorPatternZh || '',
    wallDraft?.echoAiPatternZh || '',
    wallDraft?.echoNoteZh || '',
    wallFusion.lean || '',
  ].join('/');

  const runAssistJudgment = useCallback(async (force = false) => {
    if (!patient || !aiValue || !judgmentProse) return;
    const seed = [patient.id, studyMode, displayTop1, adjacentPair || '', wallJudgmentSeed].join('|');
    if (!force && lastJudgmentSeedRef.current === seed && assistJudgment) return;
    lastJudgmentSeedRef.current = seed;
    setJudgmentBusy(true);
    try {
      const originalTop1 = displayTop1 || frozenTop1 || aiValue;
      const response = await fetch('/api/reader/assist-judgment', {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({
          study_mode: studyMode,
          zh,
          original_top1: originalTop1,
          frozen_top1: frozenTop1 && frozenTop1 !== originalTop1 ? frozenTop1 : null,
          doctor_signs: judgmentSigns,
          template_prose: judgmentProse,
          use_llm: true,
        }),
      });
      const data = await response.json() as AssistJudgmentState & {
        ok?: boolean;
        error?: string;
        runtime?: { source?: string; llm_called?: boolean };
      };
      if (!response.ok || !data.ok) {
        throw new Error(data.error || (zh ? '指南解释失败' : 'Guideline explanation failed'));
      }
      const next: AssistJudgmentState = {
        original_top1: data.original_top1 || originalTop1,
        template_prose: data.template_prose || judgmentProse,
        explanation: Array.isArray(data.explanation) ? data.explanation : [],
        citations: Array.isArray(data.citations) ? data.citations : [],
        guideline_cards: Array.isArray(data.guideline_cards) ? data.guideline_cards : [],
        prose: data.prose,
        source: data.source || data.runtime?.source || 'template',
        generated_at: new Date().toISOString(),
        llm_called: Boolean(data.runtime?.llm_called) || data.source === 'llm',
      };
      setAssistJudgment(next);
      persistCaseState({ assist_judgment: next });
    } catch {
      lastJudgmentSeedRef.current = '';
    } finally {
      setJudgmentBusy(false);
    }
  }, [
    activeReport?.recommended_stage,
    adjacentPair,
    aiValue,
    assistJudgment,
    displayTop1,
    frozenTop1,
    jsonHeaders,
    judgmentProse,
    judgmentSigns,
    patient,
    persistCaseState,
    studyMode,
    wallJudgmentSeed,
    zh,
  ]);

  useEffect(() => {
    if (!aiValue || !judgmentProse || !patient) return;
    void runAssistJudgment(false);
    // Auto-run once per case / Assist call / lock / wall draft. Sign edits use「重写指南解释」.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aiValue, patient?.id, studyMode, adjacentPair, assistHeadline, wallJudgmentSeed]);

  const runEvidenceFusion = async () => {
    if (!patient || fusionBusy) return;
    if (!aiValue && !assistResult && !activeReport?.recommended_stage) {
      setActionStatus(zh ? '请先完成 Assist 再做证据对照' : 'Run Assist before evidence fusion');
      return;
    }
    setFusionBusy(true);
    setActionStatus(zh ? '先出本地六段稿，再请 LLM 写对照报告…' : 'Local six-section draft first, then the LLM report…');
    try {
      const originalTop1 = displayTop1 || frozenTop1;
      const bmProbs = (assistResult as { bm?: { probs?: Record<string, number> } } | null)?.bm?.probs;
      const cls = (assistResult?.tool_evidence?.classification || {}) as Record<string, unknown>;
      const classProbsRaw = (cls.class_probs || cls.probabilities || {}) as Record<string, number>;
      const classProbs: Record<string, number> = {};
      for (const [key, value] of Object.entries(classProbsRaw || {})) {
        const n = Number(value);
        if (key && Number.isFinite(n)) classProbs[key] = n;
      }
      const originalProbs = isNatureTask
        ? {
            benign: Number(bmProbs?.benign
              ?? (aiValue === 'benign' ? (aiDecision.confidence ?? 0) : (1 - (aiDecision.confidence ?? 0)))),
            malignant: Number(bmProbs?.malignant
              ?? (aiValue === 'malignant' ? (aiDecision.confidence ?? 0) : (1 - (aiDecision.confidence ?? 0)))),
          }
        : {
            ...classProbs,
            ...(Object.keys(classProbs).length
              ? {}
              : (aiDecision.confidence != null && (frozenTop1 || originalTop1)
                ? { [frozenTop1 || originalTop1]: aiDecision.confidence }
                : {})),
          };
      const lockedTop1 = originalTop1 || (isNatureTask ? 'malignant' : 'T3');
      const localCards = buildSimilarCaseEvidenceCards(similarCases, {
        usefulByImageId: similarUseful,
        revealedByImageId: similarRevealed,
        evaluation: evaluationSession,
      });
      const localDraft = buildEvidenceFusionTemplate({
        zh,
        evaluation: evaluationSession,
        study_mode: studyMode,
        original_top1: lockedTop1,
        frozen_top1: frozenTop1 && frozenTop1 !== lockedTop1 ? frozenTop1 : undefined,
        original_probs: originalProbs,
        doctor_signs: judgmentSigns,
        cards: localCards,
      });
      const localState: EvidenceFusionState = {
        prose: localDraft.prose,
        sections: localDraft.sections,
        source: 'template',
        selected_image_ids: localDraft.selected_image_ids,
        unlike_image_ids: localDraft.unlike_image_ids,
        generated_at: new Date().toISOString(),
        llm_called: false,
        critic: localDraft.critic,
      };
      setEvidenceFusion(localState);
      const response = await fetch('/api/reader/evidence-fusion', {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({
          study_mode: studyMode,
          evaluation: evaluationSession,
          zh,
          original_top1: lockedTop1,
          frozen_top1: frozenTop1 && frozenTop1 !== lockedTop1 ? frozenTop1 : undefined,
          original_probs: originalProbs,
          doctor_signs: judgmentSigns,
          similar_cases: similarCases,
          useful_by_image_id: similarUseful,
          revealed_by_image_id: similarRevealed,
          use_llm: true,
        }),
      });
      const data = await response.json() as {
        ok?: boolean;
        prose?: string;
        sections?: EvidenceFusionState['sections'];
        source?: string;
        selected_image_ids?: string[];
        unlike_image_ids?: string[];
        critic?: EvidenceFusionState['critic'];
        error?: string;
        runtime?: { source?: string; llm_called?: boolean; llm_error?: string };
      };
      if (!response.ok || !data.ok || !data.prose) {
        throw new Error(data.error || (zh ? '证据对照失败' : 'Evidence fusion failed'));
      }
      const fusionSource = data.source || data.runtime?.source || 'template';
      const fusionState: EvidenceFusionState = {
        prose: data.prose,
        sections: data.sections || localDraft.sections,
        source: fusionSource,
        selected_image_ids: data.selected_image_ids || localDraft.selected_image_ids,
        unlike_image_ids: data.unlike_image_ids || localDraft.unlike_image_ids,
        generated_at: new Date().toISOString(),
        llm_called: Boolean(data.runtime?.llm_called) || fusionSource === 'llm',
        llm_error: data.runtime?.llm_error,
        critic: normalizeEvidenceCritic(data.critic || localDraft.critic),
      };
      setEvidenceFusion(fusionState);
      const feedback = buildSimilarFeedbackPayload(similarUseful, similarRevealed, similarCases);
      persistCaseState({
        evidence_fusion: fusionState,
        similar_case_feedback: feedback,
        activity_append: activityAppend(
          'evidence_fusion',
          '生成证据对照（不改原始概率）',
          'Evidence fusion (original probabilities unchanged)',
          { source: fusionState.source, case_count: similarCases.length },
        ),
      });
      setActionStatus(
        fusionState.source === 'llm'
          ? (zh ? 'LLM 对照报告已生成（上方分期概率未改）' : 'LLM contrast ready (stage probs unchanged)')
          : (zh ? '已显示对照稿（上方分期概率未改）' : 'Contrast draft ready (stage probs unchanged)'),
      );
    } catch (error) {
      setActionStatus(error instanceof Error
        ? `${zh ? '证据对照失败' : 'Evidence fusion failed'}: ${error.message}`
        : (zh ? '证据对照失败' : 'Evidence fusion failed'));
    } finally {
      setFusionBusy(false);
    }
  };
  runEvidenceFusionRef.current = runEvidenceFusion;

  useEffect(() => {
    if (!assistResult?.session_id) return;
    skipAutoLoopRef.current = false;
    fusionSeedRef.current = '';
    repairSeedRef.current = '';
  }, [assistResult?.session_id]);

  useEffect(() => {
    if (skipAutoLoopRef.current || !aiValue || !patient || fusionBusy || loopRepairBusy) return;
    if (!similarLoadState.loaded || similarLoadState.loading) return;
    const ids = similarCases.map((item) => String(item.image_id || '')).join(',');
    const seed = [patient.id, studyMode, aiValue, ids, similarLoadState.refineRound].join('|');
    if (fusionSeedRef.current === seed) return;
    fusionSeedRef.current = seed;
    void runEvidenceFusionRef.current();
  }, [
    aiValue,
    fusionBusy,
    loopRepairBusy,
    patient,
    similarCases,
    similarLoadState.loaded,
    similarLoadState.loading,
    similarLoadState.refineRound,
    studyMode,
  ]);

  useEffect(() => {
    if (skipAutoLoopRef.current || !patient || fusionBusy || loopRepairBusy) return;
    if (!evidenceFusion?.critic?.repair_recommended) return;
    if (similarLoadState.refineRound >= 1) return;
    const seed = `${patient.id}|${evidenceFusion.generated_at || ''}|${evidenceFusion.critic.repair_reason || ''}`;
    if (repairSeedRef.current === seed) return;
    repairSeedRef.current = seed;
    setLoopRepairBusy(true);
    setActionStatus(zh ? '证据偏薄，正在再检索一轮…' : 'Evidence is thin; retrieving one more round…');
    void similarPanelRef.current?.refineOnce()
      .then((ok) => {
        if (!ok) {
          setActionStatus(zh ? '已达再检索上限' : 'Extra retrieve already used');
        }
      })
      .finally(() => setLoopRepairBusy(false));
  }, [
    evidenceFusion,
    fusionBusy,
    loopRepairBusy,
    patient,
    similarLoadState.refineRound,
    zh,
  ]);

  return (
    <section className={`flex min-h-0 flex-1 flex-col rounded-2xl border border-white/10 bg-black/30 text-zinc-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] backdrop-blur-md ${compact ? 'p-3' : 'p-4'}`}>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-amber-300">
            <PlayCircle size={15} /> {zh ? (hideTaskChrome ? '医生判断' : (publicReaderOnly ? '医生决策' : 'AI 辅助分析')) : (hideTaskChrome ? 'Physician call' : (publicReaderOnly ? 'Physician decision' : 'AI-assisted analysis'))}
          </div>
          <div className="mt-1 font-mono text-[11px] text-gray-400">
            {patientDisplayLabel(patient, language)}
          </div>
        </div>
        <ShieldCheck size={16} className="text-emerald-300" />
      </div>

      {!hideTaskChrome ? (
        <>
          <div className="mt-3 grid grid-cols-2 gap-1 rounded-lg border border-white/10 bg-black/20 p-1">
            {TASKS.map((task) => (
              <button
                key={task.id}
                type="button"
                onClick={() => chooseTask(task.id)}
                className={`rounded-md px-2 py-2 text-left text-[10px] transition ${studyMode === task.id ? 'bg-amber-500/20 text-amber-200' : 'text-gray-500 hover:bg-white/5 hover:text-gray-300'}`}
              >
                <span className="block font-semibold">{zh ? task.labelZh : task.labelEn}</span>
                <span className="mt-0.5 block text-[9px] opacity-70">{zh ? task.shortZh : task.shortEn}</span>
              </button>
            ))}
          </div>
          {!publicReaderOnly ? (
            <div className="mt-2 flex items-center justify-between text-[10px] text-gray-500">
              <span>
                {zh ? '当前任务进度：' : 'Task progress: '}
                {completedCount}/{taskPatients.length || (isNatureTask ? 50 : 100)}
              </span>
              <span>{zh ? 'AI 辅助, 医生最终确认' : 'AI-assisted, physician final confirmation'}</span>
            </div>
          ) : null}

          <p className="mt-3 text-[11px] leading-relaxed text-gray-400">
            {zh
              ? (publicReaderOnly
                ? '播放视频并检查当前帧；证据面板显示可追溯征象、冲突和需要医生确认的内容。'
                : '先播放视频并在画面上点选或框选当前帧，系统返回结构化征象；医生仍需结合连续视频完成本任务判断。')
              : (publicReaderOnly
                ? 'Review the current video frame; the evidence panel shows traceable signs, conflicts, and items requiring physician confirmation.'
                : 'Play the video, then click or box the current frame. The system returns structured signs; the physician should review the full sequence before deciding.')}
          </p>
        </>
      ) : null}

      {!hideTaskChrome ? (
      <div className={`mt-3 rounded-lg border p-2.5 ${highConflict ? 'border-rose-500/40 bg-rose-500/[0.07]' : 'border-amber-500/25 bg-amber-500/[0.05]'}`}>
        <div className={`flex items-center gap-2 text-[10px] font-semibold ${highConflict ? 'text-rose-300' : 'text-amber-300'}`}>
          <Sparkles size={12} /> {zh ? '结构化辅助证据' : 'Structured assistive evidence'}
        </div>
        {researchAiLocked ? (
          <div className="mt-2 rounded border border-sky-500/30 bg-sky-500/[0.08] p-2 text-[10px] leading-relaxed text-sky-100">
            {zh
              ? '研究模式下，AI 建议与结构化证据在记录医生初始判断后才会显示，避免先见 AI 再补初始答案。'
              : 'In research mode, AI recommendations and structured evidence stay hidden until the physician initial judgment is recorded.'}
          </div>
        ) : activeReport ? (
          <>
            <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-300">
              <span>{zh ? '建议' : 'Recommendation'}: {stageLabel(activeReport.recommended_stage, zh)}</span>
              {activeReport.calibrated_confidence != null
                ? <span>{zh ? '置信度' : 'Confidence'}: {Math.round(activeReport.calibrated_confidence * 100)}%</span>
                : null}
              <span>{zh ? '证据项' : 'Evidence items'}: {activeReport.evidence?.length || 0}</span>
              {activeReport.recommendation_status === 'conflict'
                ? <span className="font-semibold text-rose-300">{zh ? '高风险冲突' : 'High-risk conflict'}</span>
                : null}
            </div>
            {conflicts.length ? (
              <div className="mt-2 space-y-1 rounded border border-rose-500/25 bg-rose-500/[0.06] p-2 text-[10px] leading-relaxed text-rose-200">
                {conflicts.map((item, index) => (
                  <div key={`${item.code || 'conflict'}-${index}`}>
                    - {item.message || (zh ? '证据与阶段建议不一致' : 'Evidence conflicts with the stage recommendation')}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {SIGN_FIELDS.map(([path, labelZh, labelEn]) => {
                const field = getSign(activeReport, path);
                const value = field?.value == null || String(field.value).trim() === ''
                  ? (zh ? '未评估' : 'Not assessed')
                  : String(field.value);
                return (
                  <div key={path} className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
                    <div className="text-[9px] text-gray-500">{zh ? labelZh : labelEn}</div>
                    <input
                      value={value}
                      onChange={(event) => updateReportSign(path, event.target.value)}
                      className="mt-0.5 w-full rounded border border-white/10 bg-black/30 px-1 py-0.5 text-[10px] text-gray-200 outline-none focus:border-emerald-300/50"
                      aria-label={zh ? labelZh : labelEn}
                    />
                    <div className={`mt-0.5 text-[8px] ${field?.status === 'conflict' ? 'text-rose-300' : 'text-gray-500'}`}>
                      {signStatus(field?.status, zh)} / {field?.source || 'not_available'}
                    </div>
                  </div>
                );
              })}
            </div>
            {activeReport.summary ? <div className="mt-2 text-[10px] leading-relaxed text-slate-300">{cleanSystemCopy(activeReport.summary, zh)}</div> : null}
          </>
        ) : (
          <div className="mt-1 text-[10px] leading-relaxed text-gray-500">
            {zh ? '尚未生成当前帧证据；请在左侧视频画面操作。' : 'No current-frame evidence yet. Use the video view on the left.'}
          </div>
        )}
        <div className="mt-2 border-t border-white/10 pt-2 text-[9px] text-gray-500">
          {zh
            ? '几何与规则辅助，非病理金标准；最终判断权在医生。层次、浆膜和胃周组织未评估时，不生成确定性侵润结论。'
            : 'Geometry and rules provide assistive evidence, not a pathology gold standard. The physician makes the final decision; no definitive invasion claim is produced when layers, serosa, or perigastric tissue are unassessed.'}
        </div>
      </div>
      ) : null}

      <div className="mt-3 space-y-3">
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-semibold text-amber-100">
            <span className="flex items-center gap-1.5">
              <span>{zh ? '独立记录 T（不进模型）' : 'Independent T record (not a model input)'}</span>
              {!isNatureTask ? (
                <button
                  type="button"
                  onClick={() => setTrialMemoOpen(true)}
                  className="inline-flex items-center gap-0.5 rounded border border-white/15 bg-black/30 px-1.5 py-0.5 text-[10px] font-normal text-slate-300 hover:bg-white/10"
                  title={zh ? '画线备忘' : 'Paint memo'}
                >
                  <HelpCircle size={11} />
                  {zh ? '备忘' : 'Memo'}
                </button>
              ) : null}
            </span>
            <span className="text-[10px] font-normal text-slate-500">
              {!initialRecorded
                ? (zh ? '点一下即记录' : 'Tap to record')
                : finalEditedAfterAi
                  ? (zh ? `最终 ${optionLabel(displayDoctorValue)}` : `Final ${optionLabel(displayDoctorValue)}`)
                  : (zh ? `初判 ${optionLabel(displayDoctorValue)}，可再点修改` : `Initial ${optionLabel(displayDoctorValue)}, retap to change`)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {(isNatureTask ? natureOptions : stageOptions).map((value) => {
              const selected = displayDoctorValue === value;
              return (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    if (firstInteractionAtRef.current == null) {
                      firstInteractionAtRef.current = typeof performance === 'undefined' ? Date.now() : performance.now();
                    }
                    if (!initialRecorded) {
                      void recordInitialJudgment(value);
                      return;
                    }
                    if (displayDoctorValue === value && !aiValue) return;
                    if (isNatureTask) {
                      setInitialNature(value);
                      if (aiValue) setFinalNature(value);
                    } else {
                      setInitialStage(value);
                      if (aiValue) setFinalStage(value);
                    }
                    if (aiValue) {
                      setFinalEditedAfterAi(true);
                      recordOp('stage_override', {
                        op: 'stage_override',
                        value,
                        after_value: value,
                        before_value: displayDoctorValue || null,
                      }, {
                        caseId: patient.id,
                        patientId: patient.patient_id,
                        page: 'workbench',
                      });
                      persistCaseState({
                        progress: 'in_progress',
                        initial_recorded: true,
                        final_edited_after_ai: true,
                        final_nature: isNatureTask ? value : null,
                        final_stage: isNatureTask ? null : value,
                        activity_append: activityAppend(
                          'final_judgment',
                          `改判为 ${optionLabel(value)}`,
                          `Changed judgment to ${optionLabel(value)}`,
                          { value },
                        ),
                      });
                      setActionStatus(zh
                        ? `已改为 ${optionLabel(value)}，点下方「按我的判断保存并下一例」`
                        : `Changed to ${optionLabel(value)}. Tap Save my call and next below`);
                      return;
                    }
                    recordOp('initial_judgment', {
                      op: 'initial_judgment_edit',
                      value,
                      after_value: value,
                      before_value: displayDoctorValue || null,
                    }, {
                      caseId: patient.id,
                      patientId: patient.patient_id,
                      page: 'workbench',
                    });
                    persistCaseState({
                      progress: 'in_progress',
                      initial_recorded: true,
                      initial_nature: isNatureTask ? value : null,
                      initial_stage: isNatureTask ? null : value,
                      activity_append: activityAppend(
                        'initial_judgment',
                        `改初判为 ${optionLabel(value)}`,
                        `Changed initial judgment to ${optionLabel(value)}`,
                        { value },
                      ),
                    });
                    setActionStatus(zh
                      ? `初判已改为 ${optionLabel(value)}`
                      : `Initial call changed to ${optionLabel(value)}`);
                  }}
                  className={`rounded-xl border px-3 py-5 text-2xl font-black tracking-wide transition max-md:py-3.5 max-md:text-xl ${
                    selected
                      ? 'border-amber-200 bg-amber-400 text-black shadow-[0_0_0_3px_rgba(251,191,36,0.55)] ring-2 ring-amber-200/90 scale-[1.02]'
                      : 'border-white/15 bg-black/35 text-slate-100 hover:bg-white/10'
                  }`}
                >
                  {selected ? `✓ ${optionLabel(value)}` : optionLabel(value)}
                </button>
              );
            })}
          </div>
          {!isNatureTask ? (
            <div className="mt-2 rounded-lg border border-sky-400/20 bg-sky-500/10 px-2.5 py-2">
              <div className="mb-1.5 text-[11px] font-semibold text-sky-100">
                {zh ? '粗筛（解剖倾向，不是 T 分期）' : 'Coarse screen (anatomy, not a T call)'}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {DOCTOR_DEPTH_SCREEN_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => pickDepthScreen(option.id)}
                    className={`rounded-lg border px-2.5 py-1.5 text-[12px] font-semibold ${
                      depthScreen === option.id
                        ? 'border-sky-200 bg-sky-300 text-slate-900'
                        : 'border-white/15 bg-black/30 text-sky-50 hover:bg-white/10'
                    }`}
                    title={zh ? option.hintZh : option.hintEn}
                  >
                    {zh ? option.zh : option.en}
                  </button>
                ))}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {DOCTOR_PROMPT_CONFIDENCE_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => pickPromptConfidence(option.id)}
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      promptConfidence === option.id
                        ? 'bg-sky-200 text-slate-900'
                        : 'bg-black/30 text-sky-50 hover:bg-white/10'
                    }`}
                  >
                    {zh ? option.zh : option.en}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-[10px] leading-relaxed text-slate-400">
                {zh
                  ? '这不是 T1–T4，也不输入核心模型。请框选病灶并确认最深浸润区。保存最终结果前再独立记下 T。'
                  : 'This is not a T1–T4 call and is not a core-model input. Box the lesion and confirm the deepest-invasion region. Record T independently before saving.'}
              </p>
            </div>
          ) : null}
          {wallProse && !isNatureTask ? (
            <div className="mt-2 rounded-lg border border-amber-200/20 bg-amber-500/10 px-2.5 py-2">
              <div className="text-[11px] font-semibold text-amber-100">
                {zh ? '胃壁草稿已并入分期推理（不定 cT）' : 'Wall draft is in staging reasoning (not a definite cT)'}
              </div>
              {wallFusion.noteZh || wallFusion.noteEn ? (
                <p className="mt-1.5 text-[12px] leading-relaxed text-amber-50">
                  {zh ? wallFusion.noteZh : wallFusion.noteEn}
                </p>
              ) : null}
              {wallDraft?.interrupts?.length ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {wallDraft.interrupts.map((item) => {
                    const verdict = item.verdict
                      || (item.interrupted ? 'interrupted' : 'continuous');
                    return (
                    <button
                      key={`interrupt-${item.layer}`}
                      type="button"
                      onClick={() => {
                        window.dispatchEvent(new CustomEvent(WALL_INTERRUPT_OVERRIDE_EVENT, {
                          detail: { layer: item.layer },
                        }));
                      }}
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        verdict === 'interrupted'
                          ? 'bg-rose-400/25 text-rose-100'
                          : verdict === 'suspected'
                            ? 'bg-amber-400/20 text-amber-100'
                            : verdict === 'cannot_judge'
                              ? 'bg-white/10 text-slate-200'
                              : 'bg-emerald-400/20 text-emerald-100'
                      }`}
                      title={zh ? '点一下在连续 / 疑似中断 / 中断 / 无法判断之间切换' : 'Tap to cycle continuous / suspected / interrupted / cannot judge'}
                    >
                      {zh ? item.nameZh : (item.nameEn || item.nameZh)}
                      {' '}
                      {verdictLabel(verdict as 'continuous' | 'suspected' | 'interrupted' | 'cannot_judge', zh)}
                      {item.doctorOverride ? (zh ? '（已改）' : ' (edited)') : ''}
                    </button>
                    );
                  })}
                </div>
              ) : null}
              <div className="mt-1.5 flex flex-wrap gap-1">
                {WALL_VISIBILITY_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent(WALL_PROMPT_META_EVENT, {
                        detail: { visibility: option.id, anchorMode: wallDraft?.anchorMode || undefined },
                      }));
                    }}
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      wallDraft?.visibility === option.id
                        ? 'bg-amber-300 text-slate-900'
                        : 'bg-black/30 text-amber-50 hover:bg-white/10'
                    }`}
                  >
                    {zh ? option.zh : option.en}
                  </button>
                ))}
                {SEROSA_ANCHOR_OPTIONS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent(WALL_PROMPT_META_EVENT, {
                        detail: { visibility: wallDraft?.visibility || undefined, anchorMode: option.id },
                      }));
                    }}
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      wallDraft?.anchorMode === option.id
                        ? 'bg-sky-300 text-slate-900'
                        : 'bg-black/30 text-sky-50 hover:bg-white/10'
                    }`}
                  >
                    {zh ? option.zh : option.en}
                  </button>
                ))}
              </div>
              {wallDraft?.interrupts?.length ? (
                <p className="mt-1 text-[10px] leading-relaxed text-slate-400">
                  {zh ? '点芯片可改结论。看不清不等于中断。不定 cT。' : 'Tap a chip to edit the verdict. Not seen is not interruption. Not a definite cT.'}
                </p>
              ) : null}
              {wallDraft?.ticks?.length ? (
                <div className="mt-1 flex flex-wrap gap-1">
                  {wallDraft.ticks.map((tick) => (
                    <span
                      key={`tick-${tick.layer}`}
                      className={`rounded px-1.5 py-0.5 text-[10px] ${
                        tick.status === 'absent' || tick.status === 'imaginary' || tick.status === 'interrupted'
                          ? 'bg-rose-400/20 text-rose-100'
                          : tick.status === 'thinned'
                            ? 'bg-amber-400/20 text-amber-100'
                            : 'bg-emerald-400/15 text-emerald-100'
                      }`}
                    >
                      {zh ? `${tick.nameZh} ${tick.labelZh}` : `${tick.nameEn || tick.nameZh} ${tick.labelZh}`}
                    </span>
                  ))}
                </div>
              ) : null}
              <p className="mt-1 text-[12px] leading-relaxed text-slate-200">{wallProse}</p>
              {wallContinuity.mixed ? (
                <p className="mt-1 text-[11px] leading-relaxed text-amber-100/90">
                  {zh ? wallContinuity.noteZh : wallContinuity.noteEn}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>

        {assistBusy || assistResult ? (
          <AssistLoopStrip
            steps={loopSteps}
            zh={zh}
          />
        ) : null}
        <SimilarCaseReferencePanel
          ref={similarPanelRef}
          caseId={patient.id}
          patientId={patient.patient_id || patient.id}
          studyMode={studyMode}
          enabled={Boolean(assistBusy || assistResult)}
          zh={zh}
          compact
          allowOpenWorkbench={!publicReaderOnly && studyEnvironment !== 'research'}
          onLoadStateChange={setSimilarLoadState}
          queryPreviewUrl={queryPreviewUrl}
          queryMaskPolygon={queryMaskPolygon}
          queryImageWidth={queryImageWidth}
          queryImageHeight={queryImageHeight}
          usefulMarks={similarUseful}
          onUsefulChange={handleSimilarUsefulChange}
          reasonMarks={similarReasons}
          onReasonChange={handleSimilarReasonChange}
          revealedMarks={similarRevealed}
          onRevealChange={handleSimilarRevealChange}
          onCasesChange={setSimilarCases}
          queryWallDraft={
            studyMode === 't_staging' && wallDraft
              ? {
                targetLayers: wallDraft.targetLayers,
                patternZh: wallDraft.echoPatternZh || wallDraft.noteZh,
                interrupted: Boolean(wallDraft.interrupts?.some((item) => item.interrupted)),
              }
              : null
          }
        />

        <div>
          <div className="mb-2 space-y-1 rounded-lg border border-white/10 bg-black/25 px-2.5 py-2 text-[12px] text-slate-300">
            <div className={lesionReady ? 'text-emerald-200' : 'text-slate-400'}>
              {lesionReady ? '1. ✓ ' : '1. '}
              {zh ? '框选病灶' : 'Box the lesion'}
            </div>
            <div className={(wallDraft?.focusCount || 0) >= 1 ? 'text-emerald-200' : 'text-slate-400'}>
              {(wallDraft?.focusCount || 0) >= 1 ? '2. ✓ ' : '2. '}
              {zh ? '先选一处最深浸润区，选完才分析（可点 AI 建议，不是突破点）' : 'Select one deepest region first; analysis starts after (AI suggestion OK; not a breach)'}
            </div>
            <div className={(wallDraft?.spanCount || 0) >= 2 ? 'text-emerald-200' : 'text-slate-400'}>
              {(wallDraft?.spanCount || 0) >= 2 ? '3. ✓ ' : '3. '}
              {zh
                ? ((wallDraft?.spanCount || 0) === 1 ? '已留 1 段，请再画对侧' : '两侧短线：自动留下，失败时再手画')
                : ((wallDraft?.spanCount || 0) === 1 ? '1 span kept; paint the other flank' : 'Flanks: auto-kept; paint only if auto-anchors fail')}
            </div>
            <div className={initialRecorded ? 'text-emerald-200' : 'text-slate-400'}>
              {initialRecorded ? '4. ✓ ' : '4. '}
              {zh ? 'T 分期只作独立记录，不进模型' : 'T stage is an independent record, not a model input'}
            </div>
            <div className={aiValue ? 'text-emerald-200' : assistCanRun ? 'text-sky-100' : 'text-slate-500'}>
              {aiValue ? '5. ✓ ' : '5. '}
              {zh ? '框选后即可辅助分析。建议先确认最深区' : 'Assist lights after a lesion box. Confirm the deepest region first'}
            </div>
          </div>
          <button
            type="button"
            disabled={!assistCanRun}
            onClick={() => onAssist?.()}
            className={`flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-4 text-lg font-bold ${
              assistCanRun
                ? 'border-sky-400/40 bg-sky-500/20 text-sky-50'
                : 'cursor-not-allowed border-white/10 bg-white/[0.04] text-slate-500'
            }`}
          >
            {assistBusy ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />}
            {assistBusy
              ? (zh ? '分析中' : 'Running')
              : assistError
                ? (zh ? '重新分析' : 'Retry analysis')
                : (zh ? '辅助分析' : 'Assist')}
          </button>
          <div className="mt-1.5 text-center text-[12px] text-slate-400">
            {!lesionReady
              ? (zh ? '现在还不能点：先框选病灶' : 'Grayed out until you box the lesion')
                : assistBusy
                  ? (zh ? '正在分析当前框选' : 'Analyzing the current box')
                  : assistError
                    ? (zh ? '上次没有完成。病灶还在，可直接再分析一次' : 'The last run did not finish. The lesion is still here; tap to analyze again')
                  : (aiValue
                    ? (zh ? '可核对下方结果；不同意就再点上面的分期' : 'Review below; retap a stage if you disagree')
                    : (zh
                      ? ((wallDraft || depthScreen)
                        ? '可以点了：对当前框选和最深浸润区给出辅助意见，不使用您的 T 分期'
                        : '可以点了。建议先确认最深浸润区。T 分期不输入模型')
                      : ((wallDraft || depthScreen)
                        ? 'Ready: assist uses the box and deepest-invasion region, not your T call'
                        : 'Ready. Confirm the deepest-invasion region when you can. The T call is not a model input')))}
          </div>
          {onGoViewer && !lesionReady && !assistBusy ? (
            <button
              type="button"
              onClick={onGoViewer}
              className="mt-2 w-full rounded-lg border border-white/15 px-3 py-2.5 text-[13px] font-semibold text-slate-100 md:hidden"
            >
              {zh ? '去超声勾画病灶' : 'Go to ultrasound'}
            </button>
          ) : null}
        </div>

        {aiValue ? (
          <div className="rounded-2xl border border-white/10 bg-black/40 px-3.5 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md">
            <div className="text-[11px] font-semibold tracking-[0.12em] text-zinc-200">
              {zh ? 'AI 判断' : 'AI call'}
            </div>
            <div className="mt-1 text-4xl font-black tracking-wide text-slate-50 max-md:text-3xl">
              {optionLabel(assistHeadline)}
              {assistHeadline !== aiValue ? (
                <span className="ml-2 text-lg font-semibold text-slate-400">
                  {zh ? `四分类 ${optionLabel(aiValue)}` : `four-class ${optionLabel(aiValue)}`}
                </span>
              ) : aiLabel && aiLabel !== aiValue ? (
                <span className="ml-2 text-lg font-semibold text-slate-400">({aiLabel})</span>
              ) : null}
            </div>
            <div className="mt-1 text-lg font-semibold tabular-nums text-slate-200">
              {assistHeadlinePct != null
                ? (zh ? `置信度 ${assistHeadlinePct}%` : `Confidence ${assistHeadlinePct}%`)
                : (zh ? '置信度未返回' : 'Confidence not returned')}
            </div>
            {isNatureTask && tentCompare ? (
              <p className="mt-2 text-[11px] leading-relaxed text-amber-100/85">
                {zh
                  ? `适应前 ${tentCompare.frozen_top1}，适应后 ${tentCompare.adapted_top1}。仅展示，数字仍以当前 Assist 为准。`
                  : `Before adaptation ${tentCompare.frozen_top1}; after ${tentCompare.adapted_top1}. Display only; the current Assist number stays authoritative.`}
              </p>
            ) : null}
            {depthConflict ? (
              <div className="mt-3 rounded-xl border border-rose-300/40 bg-rose-500/10 px-2.5 py-2">
                <div className="text-[11px] font-semibold text-rose-100">
                  {zh ? '医机不一致' : 'Doctor / AI mismatch'}
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-rose-50/90">
                  {zh
                    ? '您的粗筛与 AI 四分类不一致。不自动覆盖任何一方。请复核浸润最深区和相邻帧。'
                    : 'Your coarse screen disagrees with the frozen four-class. Neither side is overwritten. Recheck the deepest zone and nearby frames.'}
                </p>
              </div>
            ) : null}
            {isNatureTask && aiValue === 'malignant' && tLooksReal ? (
              <div className="mt-3 border-t border-white/8 pt-2">
                <div className="text-[11px] font-semibold tracking-[0.12em] text-zinc-300">{zh ? 'T 分期分析' : 'T-stage analysis'}</div>
                <div className="mt-1 text-3xl font-black tracking-wide text-slate-50">
                  {tAssist.label}
                </div>
                <div className="mt-0.5 text-base font-semibold tabular-nums text-slate-200">
                  {tPct != null
                    ? (zh ? `置信度 ${tPct}%` : `Confidence ${tPct}%`)
                    : (zh ? '置信度未返回' : 'Confidence not returned')}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {aiValue ? (
          <GuidelineTracePanel
            caseId={patient.id}
            patientId={patient.patient_id || patient.id}
            studyMode={studyMode}
            originalTop1={displayTop1 || aiValue}
            doctorSigns={judgmentSigns}
            cards={assistJudgment?.guideline_cards}
            citations={assistJudgment?.citations}
            zh={zh}
            compact
          />
        ) : null}

        {judgmentProse ? (
          <div className="rounded-2xl border border-white/10 bg-black/35 px-3.5 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] backdrop-blur-md">
            <div className="flex items-start justify-between gap-2">
              <div className="text-[11px] font-semibold tracking-[0.12em] text-zinc-100">
                {zh ? '辅助判断（按报告模板，供你决定是否接受）' : 'Assist judgment (template draft; you decide whether to accept)'}
              </div>
              <span className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${
                judgmentBusy
                  ? 'border-amber-200/25 bg-amber-100/10 text-amber-100'
                  : assistJudgment?.source === 'llm'
                    ? 'border-emerald-200/25 bg-emerald-100/10 text-emerald-100'
                    : 'border-white/12 bg-white/[0.04] text-zinc-300'
              }`}>
                {judgmentBusy ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                {judgmentBusy
                  ? (zh ? 'LLM 正在写指南解释' : 'LLM writing guideline note')
                  : assistJudgment?.source === 'llm'
                    ? (zh ? 'LLM 指南解释' : 'LLM guideline note')
                    : (zh ? '本地模板' : 'Local template')}
              </span>
            </div>
            <pre className="mt-2 whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-zinc-200">
              {judgmentProse}
            </pre>
            <div className="mt-3 border-t border-white/8 pt-2.5">
              <div className="text-[11px] font-semibold tracking-[0.12em] text-zinc-100">
                {zh ? '指南解释（AJCC / NCCN，不改上方概率）' : 'Guideline explanation (AJCC / NCCN, probs locked)'}
              </div>
              {judgmentBusy && !assistJudgment?.explanation?.length ? (
                <p className="mt-2 text-[11px] text-zinc-500">
                  {zh ? '正在检索指南并请 LLM 写解释…' : 'Retrieving guidelines and asking the LLM to explain…'}
                </p>
              ) : (
                <ul className="mt-2 space-y-1.5">
                  {(assistJudgment?.explanation || []).map((item, index) => (
                    <li key={`${item.source}-${index}`} className="text-[12px] leading-relaxed text-zinc-200">
                      <span>{item.text}</span>
                      {item.source ? (
                        <button
                          type="button"
                          onClick={() => {
                            const cardId = item.source.replace(/^\[|\]$/g, '');
                            const node = document.getElementById(`rag-guideline-${cardId}`);
                            node?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                          }}
                          className="ml-1.5 inline-flex rounded-full border border-amber-200/25 bg-amber-400/10 px-1.5 py-px text-[9px] text-amber-100 hover:bg-amber-400/20"
                        >
                          {item.source.replace(/^\[|\]$/g, '')}
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="mt-3 flex items-center justify-between gap-2">
              <p className="text-[10px] leading-relaxed text-zinc-500">
                {zh
                  ? '模板段只用当前框选和征象。指南解释只引用 AJCC / NCCN 卡片，不编文献，也不改上面的分期概率。'
                  : 'The template uses the current box and signs only. The guideline note cites AJCC / NCCN cards only and does not change stage probabilities.'}
              </p>
              <button
                type="button"
                disabled={judgmentBusy}
                onClick={() => void runAssistJudgment(true)}
                className="shrink-0 rounded-full border border-white/12 bg-white/[0.04] px-2 py-0.5 text-[10px] text-zinc-300 disabled:opacity-40"
              >
                {zh ? '重写指南解释' : 'Rewrite note'}
              </button>
            </div>
          </div>
        ) : null}

        {showBenignFill ? (
          <BmEvidencePanel
            caseId={patient.id}
            clinical={(patient.clinical || {}) as Record<string, unknown>}
            compact
            coreOnly
            assistNature="benign"
            onStateChange={onBmReportChange}
          />
        ) : null}

        {featureFields.length ? (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold text-slate-200">
              {aiValue
                ? (zh ? '特征预测（可改）' : 'Predicted signs (editable)')
                : (zh ? '特征（尚未评估）' : 'Signs (not yet assessed)')}
            </div>
            <div className="grid grid-cols-1 gap-1.5">
              {featureFields.map(([path, labelZh, labelEn]) => {
                const field = getSign(activeReport, path);
                const value = String(field?.value || aiBaselineSigns[path] || '').trim();
                const options = SIGN_OPTIONS[path as AssistSignKey] || [];
                const listed = options.includes(value) ? value : '';
                const assessed = Boolean(listed);
                return (
                  <label key={path} className="rounded-lg border border-white/10 bg-black/25 px-2 py-1.5">
                    <div className="flex items-center justify-between gap-2 text-[10px] text-slate-500">
                      <span>{zh ? labelZh : labelEn}</span>
                      <span className={assessed ? 'text-emerald-300/80' : 'text-amber-200/80'}>
                        {assessed ? (zh ? '已评估' : 'Assessed') : notAssessedLabel}
                      </span>
                    </div>
                    <select
                      value={listed}
                      disabled={!aiValue}
                      onChange={(event) => updateReportSign(path, event.target.value)}
                      className="mt-0.5 w-full rounded border border-white/10 bg-black/40 px-1.5 py-1 text-[12px] text-slate-100 outline-none disabled:text-slate-500 max-md:min-h-11 max-md:px-2"
                    >
                      <option value="">{notAssessedLabel}</option>
                      {value && !options.includes(value) ? (
                        <option value={value}>{value}</option>
                      ) : null}
                      {options.map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </select>
                  </label>
                );
              })}
            </div>
          </div>
        ) : null}

        {aiValue ? (
          <div className="space-y-2">
            <button
              type="button"
              disabled={fusionBusy || (!similarCases.length && !Object.keys(similarUseful).length)}
              onClick={() => void runEvidenceFusion()}
              className="flex w-full items-center justify-center gap-2 rounded-2xl border border-white/15 bg-white/[0.06] px-3 py-3.5 text-[15px] font-semibold tracking-wide text-zinc-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.12)] backdrop-blur-md disabled:cursor-not-allowed disabled:opacity-40"
            >
              {fusionBusy ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
              {fusionBusy
                ? (zh ? 'LLM 正在写对照报告…' : 'LLM writing contrast…')
                : (zh ? '基于已选病例做证据对照' : 'Evidence contrast from selected cases')}
            </button>
            <p className="text-[10px] leading-relaxed text-zinc-500">
              {zh
                ? '未点「有对照价值」时用当前列出的全部卡片；点选后只送有价值病例。「不太像」仅作负例摘要。先出本地六段稿，再换成 LLM 报告。不改上方分期概率。'
                : 'Uses all listed cards if none marked useful; otherwise only useful ones. Unlike marks are negative summaries only. A local six-section draft appears first, then the LLM report. Stage probabilities stay unchanged.'}
            </p>
            <EvidenceFusionReport fusion={evidenceFusion} busy={fusionBusy} zh={zh} />
          </div>
        ) : null}

        <div>
          <div className="mb-1.5 text-[11px] font-semibold text-emerald-100">
            {zh ? '保存并继续' : 'Save and continue'}
          </div>
          <div className="grid grid-cols-1 gap-2">
            <button
              type="button"
              disabled={finalActionsLocked || !canAcceptAi}
              onClick={() => {
                if (isNatureTask) setFinalNature(aiValue);
                else setFinalStage(assistHeadline);
                void writeDoctorAction('accept', assistHeadline || aiValue);
              }}
              className="rounded-xl border border-emerald-400/35 bg-emerald-500/15 px-3 py-4 text-lg font-bold text-emerald-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {zh ? '接受这段判断并下一例' : 'Accept this judgment and next'}
            </button>
            <button
              type="button"
              disabled={finalActionsLocked || !canModifySave}
              onClick={() => {
                if (isNatureTask) {
                  if (!finalNature) setFinalNature(myCallValue);
                } else if (!finalStage) {
                  setFinalStage(myCallValue);
                }
                void writeDoctorAction('modify', myCallValue);
              }}
              className="rounded-xl border border-amber-300/40 bg-amber-400/15 px-3 py-4 text-lg font-bold text-amber-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {zh ? '不接受，按我的判断保存' : 'Decline; save my call'}
            </button>
          </div>
          {canModifySave ? (
            <div className="mt-1.5 text-center text-[12px] text-slate-400">
              {zh
                ? `将保存你的判断：${optionLabel(myCallValue)}`
                : `Will save your call: ${optionLabel(myCallValue)}`}
            </div>
          ) : (
            <div className="mt-1.5 text-center text-[12px] text-slate-500">
              {zh ? '先点上面的判断，再保存' : 'Choose your call above first, then save'}
            </div>
          )}
          <button
            type="button"
            disabled={finalActionsLocked}
            onClick={() => void writeDoctorAction('request_more_evidence')}
            className="mt-2 w-full rounded-lg border border-white/10 px-3 py-2 text-[12px] text-slate-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {zh ? '证据不足' : 'Insufficient evidence'}
          </button>
        </div>
        {experienceReceipt ? (
          <div className="rounded-xl border border-emerald-300/25 bg-emerald-500/[0.08] px-2.5 py-2 text-[11px] leading-relaxed text-emerald-50">
            <div className="font-semibold">{zh ? '已记下经验候选' : 'Experience candidate logged'}</div>
            <div className="mt-0.5 font-mono text-[10px] text-emerald-100/80">{experienceReceipt.id}</div>
            <div className="mt-0.5 text-[10px] text-emerald-100/70">
              {zh
                ? `${experienceReceipt.status}，不进生产邻居表`
                : `${experienceReceipt.status}; not added to the neighbor table`}
            </div>
          </div>
        ) : null}
        {actionStatus ? <div className="text-[11px] text-amber-200">{actionStatus}</div> : null}
      </div>
      </div>
      {trialMemoOpen && !isNatureTask ? (
        <div
          className="fixed inset-0 z-[90] flex items-start justify-end bg-black/40 p-3"
          onClick={() => setTrialMemoOpen(false)}
        >
          <div
            role="dialog"
            aria-label={zh ? '画线备忘' : 'Paint memo'}
            className="mt-14 w-[min(18.5rem,calc(100vw-1.5rem))] rounded-xl border border-white/15 bg-slate-950/95 p-2.5 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px] font-semibold text-amber-100">{zh ? '画线备忘' : 'Paint memo'}</span>
              <button
                type="button"
                onClick={() => setTrialMemoOpen(false)}
                className="rounded p-0.5 text-slate-400 hover:bg-white/10 hover:text-slate-100"
                aria-label={zh ? '关闭' : 'Close'}
              >
                <X size={14} />
              </button>
            </div>
            <ol className="space-y-1 text-[10px] leading-relaxed text-slate-200">
              {(zh ? T_STAGING_TRIAL_STEPS_ZH : T_STAGING_TRIAL_STEPS_EN).map((item, index) => (
                <li key={item} className="flex gap-1.5">
                  <span className="mt-px w-3 shrink-0 font-semibold text-amber-200">{index + 1}.</span>
                  <span>{item}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      ) : null}
      {onOpenReport ? (
        <button
          type="button"
          onClick={onOpenReport}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-amber-300/50 bg-amber-400/20 px-4 py-5 text-xl font-black text-amber-50"
        >
          <FileText size={20} />
          {zh ? '查看并确认报告' : 'Review and confirm report'}
        </button>
      ) : null}
    </section>
  );
}
