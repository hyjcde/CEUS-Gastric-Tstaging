'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, PlayCircle, ShieldCheck, Sparkles } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import type { Patient, ReaderStudyMode } from '@/types';
import type { SamReport } from '@/lib/reader/types';
import { useSettings } from '@/contexts/SettingsContext';

type DoctorAction = 'accept' | 'modify' | 'reject' | 'request_more_evidence';

type Props = {
  patient: Patient | null;
  patients?: Patient[];
  compact?: boolean;
  studyMode: ReaderStudyMode;
  onStudyModeChange: (mode: ReaderStudyMode) => void;
  onSelectPatient?: (patient: Patient) => void;
  systemReport?: SamReport | null;
};

const TASKS: Array<{ id: ReaderStudyMode; labelZh: string; labelEn: string; shortZh: string; shortEn: string }> = [
  { id: 'benign_malignancy', labelZh: '任务一 · 良恶性', labelEn: 'Task 1 · Benign vs malignant', shortZh: '良恶性 50 例', shortEn: '50 cases' },
  { id: 't_staging', labelZh: '任务二 · T 分期', labelEn: 'Task 2 · T staging', shortZh: 'T 分期 100 例', shortEn: '100 cases' },
];
const STAGES = ['', 'T1', 'T2', 'T3', 'T4+'];
const NATURES = ['', 'benign', 'malignant'];
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
  return zh ? '未评估' : 'Not assessed';
}

function stageLabel(stage: string | undefined, zh: boolean): string {
  if (!stage || stage === 'uncertain') return zh ? '不确定（需复核）' : 'Uncertain (review required)';
  return zh ? `倾向 ${stage}（非病理结论）` : `Suggests ${stage} (not a pathology conclusion)`;
}

export function ReaderStudyQueuePanel({
  patient,
  patients = [],
  compact = false,
  studyMode,
  onStudyModeChange,
  onSelectPatient,
  systemReport = null,
}: Props) {
  const searchParams = useSearchParams();
  const { language } = useSettings();
  const zh = language === 'zh';
  const [finalStage, setFinalStage] = useState('');
  const [finalNature, setFinalNature] = useState('');
  const [reason, setReason] = useState('');
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [completedIds, setCompletedIds] = useState<string[]>([]);
  const sessionRef = useRef<string | null>(null);

  const taskPatients = useMemo(
    () => patients.filter((item) => item.study_mode === studyMode),
    [patients, studyMode],
  );
  const completedKey = `reader_v150_ai_completed_${studyMode}`;

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(completedKey);
      setCompletedIds(raw ? JSON.parse(raw) : []);
    } catch {
      setCompletedIds([]);
    }
  }, [completedKey]);

  useEffect(() => {
    setFinalStage('');
    setFinalNature('');
    setReason('');
    setActionStatus(null);
  }, [patient?.id, studyMode]);

  if (!patient) return null;

  const isNatureTask = studyMode === 'benign_malignancy';
  const currentIndex = taskPatients.findIndex((item) => item.id === patient.id);
  const completedCount = taskPatients.filter((item) => completedIds.includes(item.id)).length;
  const nextPatient = currentIndex >= 0 ? taskPatients[currentIndex + 1] : taskPatients[0];
  const frameCount = patient.frame_count || patient.video_urls?.length || 0;
  const selectedValue = isNatureTask ? finalNature : finalStage;
  const taskLabel = isNatureTask
    ? (zh ? '良恶性判断' : 'benign-versus-malignant classification')
    : (zh ? 'T 分期判断' : 'T-staging classification');
  const conflicts = systemReport?.conflicts || [];
  const highConflict = conflicts.some((item) => item.severity === 'high');
  const recommendationBlocked = !isNatureTask && (
    !systemReport || highConflict || systemReport.recommended_stage === 'uncertain'
  );

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

  const writeDoctorAction = async (actionType: DoctorAction) => {
    if (!patient) return;
    if (actionType === 'accept' && recommendationBlocked) {
      setActionStatus(zh
        ? '存在高风险证据冲突，不能直接采纳；请修改、拒绝或标记证据不足。'
        : 'A high-risk evidence conflict blocks direct acceptance. Modify, reject, or mark the evidence as insufficient.');
      return;
    }
    if (!selectedValue && actionType !== 'request_more_evidence') {
      setActionStatus(zh ? `请先完成${taskLabel}` : `Complete ${taskLabel} first`);
      return;
    }
    if (!sessionRef.current) sessionRef.current = `queue-${patient.id}-${Date.now()}`;
    setActionStatus(zh ? '正在记录…' : 'Recording…');
    try {
      const response = await fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: 'doctor_action',
          session_id: sessionRef.current,
          case_id: patient.id,
          reader_id: searchParams.get('reader_id') || 'public_reader',
          round: searchParams.get('round') || 'round2',
          patient_id: patient.patient_id,
          payload: {
            action_id: `action-${Date.now()}`,
            action_type: actionType,
            before_value: systemReport?.recommended_stage || null,
            after_value: selectedValue || null,
            reason: reason || (actionType === 'request_more_evidence' ? (zh ? '证据不足' : 'insufficient evidence') : null),
            queue: 'reader_v150',
            study_mode: studyMode,
            ai_assisted: true,
            system_report_available: Boolean(systemReport),
            recommendation_status: systemReport?.recommendation_status || null,
            conflicts,
            environment: searchParams.get('round') === 'qa' ? 'qa' : 'research',
          },
          client_recorded_at: new Date().toISOString(),
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setCompleted(patient.id);
      if (onSelectPatient && nextPatient) {
        onSelectPatient(nextPatient);
        setActionStatus(zh ? '已记录，已进入下一例' : 'Recorded. Moving to the next case.');
      } else {
        setActionStatus(zh ? '已记录，本任务已完成或没有下一例' : 'Recorded. This task is complete or has no next case.');
      }
    } catch (error) {
      setActionStatus(error instanceof Error
        ? `${zh ? '记录失败' : 'Recording failed'}: ${error.message}`
        : (zh ? '记录失败' : 'Recording failed'));
    }
  };

  return (
    <section className={`rounded-xl border border-white/10 bg-white/[0.03] text-gray-200 ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-amber-300">
            <PlayCircle size={15} /> {zh ? 'AI 辅助阅片任务' : 'AI-assisted reading task'}
          </div>
          <div className="mt-1 font-mono text-[11px] text-gray-400">
            {patient.id_short || patient.id} · {frameCount} {zh ? '个视频/帧' : 'videos/frames'}
          </div>
          {patient.video_urls?.length ? (
            <div className="mt-1 truncate text-[10px] text-amber-300/80" title={patient.video_urls.map((video) => video.filename).join(', ')}>
              {zh ? '视频：' : 'Videos: '}{patient.video_urls.map((video) => video.filename).join(zh ? '、' : ', ')}
            </div>
          ) : null}
        </div>
        <ShieldCheck size={16} className="text-emerald-300" />
      </div>

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
      <div className="mt-2 flex items-center justify-between text-[10px] text-gray-500">
        <span>
          {zh ? '当前任务进度：' : 'Task progress: '}
          {completedCount}/{taskPatients.length || (isNatureTask ? 50 : 100)}
        </span>
        <span>{zh ? 'AI 辅助 · 医生最终确认' : 'AI-assisted · physician final confirmation'}</span>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-gray-400">
        {zh
          ? '先播放视频并在画面上点选或框选当前帧，系统返回结构化征象；医生仍需结合连续视频完成本任务判断。'
          : 'Play the video, then click or box the current frame. The system returns structured signs; the physician should review the full sequence before deciding.'}
      </p>

      <div className={`mt-3 rounded-lg border p-2.5 ${highConflict ? 'border-rose-500/40 bg-rose-500/[0.07]' : 'border-amber-500/25 bg-amber-500/[0.05]'}`}>
        <div className={`flex items-center gap-2 text-[10px] font-semibold ${highConflict ? 'text-rose-300' : 'text-amber-300'}`}>
          <Sparkles size={12} /> {zh ? '结构化辅助证据' : 'Structured assistive evidence'}
        </div>
        {systemReport ? (
          <>
            <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-300">
              <span>{zh ? '建议' : 'Recommendation'}: {stageLabel(systemReport.recommended_stage, zh)}</span>
              {systemReport.calibrated_confidence != null
                ? <span>{zh ? '置信度' : 'Confidence'}: {Math.round(systemReport.calibrated_confidence * 100)}%</span>
                : null}
              <span>{zh ? '证据项' : 'Evidence items'}: {systemReport.evidence?.length || 0}</span>
              {systemReport.recommendation_status === 'conflict'
                ? <span className="font-semibold text-rose-300">{zh ? '高风险冲突' : 'High-risk conflict'}</span>
                : null}
            </div>
            {conflicts.length ? (
              <div className="mt-2 space-y-1 rounded border border-rose-500/25 bg-rose-500/[0.06] p-2 text-[10px] leading-relaxed text-rose-200">
                {conflicts.map((item, index) => (
                  <div key={`${item.code || 'conflict'}-${index}`}>
                    • {item.message || (zh ? '证据与阶段建议不一致' : 'Evidence conflicts with the stage recommendation')}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {SIGN_FIELDS.map(([path, labelZh, labelEn]) => {
                const field = getSign(systemReport, path);
                const value = field?.value == null || String(field.value).trim() === ''
                  ? (zh ? '未评估' : 'Not assessed')
                  : String(field.value);
                return (
                  <div key={path} className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
                    <div className="text-[9px] text-gray-500">{zh ? labelZh : labelEn}</div>
                    <div className="mt-0.5 truncate text-[10px] text-gray-200" title={value}>{value}</div>
                    <div className={`mt-0.5 text-[8px] ${field?.status === 'conflict' ? 'text-rose-300' : 'text-gray-500'}`}>
                      {signStatus(field?.status, zh)} · {field?.source || 'not_available'}
                    </div>
                  </div>
                );
              })}
            </div>
            {systemReport.summary ? <div className="mt-2 text-[10px] leading-relaxed text-slate-300">{cleanSystemCopy(systemReport.summary, zh)}</div> : null}
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

      <div className="mt-4 border-t border-white/10 pt-3">
        <div className="flex items-center gap-2 text-[10px] font-semibold text-emerald-300">
          <CheckCircle2 size={12} /> {zh ? '医生最终判断：' : 'Physician final decision: '}{taskLabel}
        </div>
        {isNatureTask ? (
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            {NATURES.slice(1).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setFinalNature(value)}
                className={`rounded border px-2 py-2 text-[11px] ${finalNature === value ? 'border-emerald-300 bg-emerald-400/20 text-emerald-100' : 'border-white/10 text-gray-400 hover:bg-white/5'}`}
              >
                {value === 'benign' ? (zh ? '良性' : 'Benign') : (zh ? '恶性' : 'Malignant')}
              </button>
            ))}
          </div>
        ) : (
          <select
            value={finalStage}
            onChange={(event) => setFinalStage(event.target.value)}
            className="mt-2 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[11px] text-gray-200"
          >
            {STAGES.map((stage) => <option key={stage} value={stage}>{stage || (zh ? '暂不确定' : 'Uncertain')}</option>)}
          </select>
        )}
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder={zh ? '记录证据、修改或证据不足原因' : 'Record evidence, changes, or why evidence is insufficient'}
          className="mt-2 min-h-12 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[11px] text-gray-200 placeholder:text-gray-600"
        />
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <button type="button" disabled={recommendationBlocked} onClick={() => void writeDoctorAction('accept')} className="reader-btn justify-center border-emerald-500/30 text-emerald-300 disabled:cursor-not-allowed disabled:opacity-40">{zh ? '采纳系统建议' : 'Accept recommendation'}</button>
          <button type="button" onClick={() => void writeDoctorAction('modify')} className="reader-btn justify-center border-amber-500/30 text-amber-300">{zh ? '修改后确认' : 'Modify and confirm'}</button>
          <button type="button" onClick={() => void writeDoctorAction('reject')} className="reader-btn justify-center border-rose-500/30 text-rose-300">{zh ? '拒绝系统建议' : 'Reject recommendation'}</button>
          <button type="button" onClick={() => void writeDoctorAction('request_more_evidence')} className="reader-btn justify-center border-slate-500/30 text-slate-300">{zh ? '证据不足' : 'Insufficient evidence'}</button>
        </div>
        {recommendationBlocked && systemReport
          ? <div className="mt-2 text-[10px] text-rose-300">
            {zh
              ? '存在冲突或未确定建议，不能直接采纳；请由医生修改、拒绝或标记证据不足。'
              : 'The recommendation is conflicting or uncertain and cannot be accepted directly. Modify, reject, or mark the evidence as insufficient.'}
          </div>
          : null}
        {actionStatus ? <div className="mt-2 text-[10px] text-amber-200">{actionStatus}</div> : null}
      </div>
    </section>
  );
}
