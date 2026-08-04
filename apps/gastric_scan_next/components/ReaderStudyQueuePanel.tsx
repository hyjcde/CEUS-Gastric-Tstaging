'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, PlayCircle, ShieldCheck, Sparkles } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import type { Patient, ReaderStudyMode } from '@/types';
import type { SamReport } from '@/lib/reader/types';

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

const TASKS: Array<{ id: ReaderStudyMode; label: string; short: string }> = [
  { id: 'benign_malignancy', label: '任务一 · 良恶性', short: '良恶性 50 例' },
  { id: 't_staging', label: '任务二 · T 分期', short: 'T 分期 100 例' },
];
const STAGES = ['', 'T1', 'T2', 'T3', 'T4+'];
const NATURES = ['', 'benign', 'malignant'];
const SIGN_FIELDS = [
  ['size.length', '肿瘤长径'],
  ['size.thickness', '肿瘤厚度'],
  ['layer_structure', '胃壁层次'],
  ['morphology', '肿瘤形态'],
  ['boundary', '肿瘤边界'],
  ['growth_pattern', '生长方式'],
  ['serosa_change', '浆膜改变'],
  ['perigastric_tissue', '胃周组织'],
] as const;

function cleanSystemCopy(value: unknown): string {
  return String(value ?? '')
    .replace(/\bSAM(?:2)?\b/gi, '系统分析')
    .replace(/\bSegment Anything(?: Model)?\b/gi, '系统分析');
}

function getSign(report: SamReport | null | undefined, path: string) {
  return path.split('.').reduce<SamReport['signs'] | Record<string, unknown> | undefined>(
    (current, key) => (current && typeof current === 'object' ? current[key] as Record<string, unknown> : undefined),
    report?.signs,
  ) as { value?: unknown; status?: string; source?: string } | undefined;
}

function signStatus(status?: string): string {
  if (status === 'suggested') return '建议';
  if (status === 'confirmed') return '已确认';
  if (status === 'doctor_edited') return '医生修正';
  if (status === 'conflict') return '冲突';
  if (status === 'pending') return '待补充';
  return '未评估';
}

function stageLabel(stage?: string): string {
  if (!stage || stage === 'uncertain') return '不确定（需复核）';
  return `倾向 ${stage}（非病理结论）`;
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
  const taskLabel = isNatureTask ? '良恶性判断' : 'T 分期判断';
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
      setActionStatus('存在高风险证据冲突，不能直接采纳；请修改、拒绝或标记证据不足。');
      return;
    }
    if (!selectedValue && actionType !== 'request_more_evidence') {
      setActionStatus(`请先完成${taskLabel}`);
      return;
    }
    if (!sessionRef.current) sessionRef.current = `queue-${patient.id}-${Date.now()}`;
    setActionStatus('正在记录…');
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
            reason: reason || (actionType === 'request_more_evidence' ? '证据不足' : null),
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
        setActionStatus('已记录，已进入下一例');
      } else {
        setActionStatus('已记录，本任务已完成或没有下一例');
      }
    } catch (error) {
      setActionStatus(error instanceof Error ? `记录失败：${error.message}` : '记录失败');
    }
  };

  return (
    <section className={`rounded-xl border border-white/10 bg-white/[0.03] text-gray-200 ${compact ? 'p-3' : 'p-4'}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-amber-300">
            <PlayCircle size={15} /> AI 辅助阅片任务
          </div>
          <div className="mt-1 font-mono text-[11px] text-gray-400">
            {patient.id_short || patient.id} · {frameCount} 个视频/帧
          </div>
          {patient.video_urls?.length ? (
            <div className="mt-1 truncate text-[10px] text-amber-300/80" title={patient.video_urls.map((video) => video.filename).join(', ')}>
              视频：{patient.video_urls.map((video) => video.filename).join('、')}
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
            <span className="block font-semibold">{task.label}</span>
            <span className="mt-0.5 block text-[9px] opacity-70">{task.short}</span>
          </button>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between text-[10px] text-gray-500">
        <span>当前任务进度：{completedCount}/{taskPatients.length || (isNatureTask ? 50 : 100)}</span>
        <span>AI 辅助 · 医生最终确认</span>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-gray-400">
        先播放视频并在画面上点选或框选当前帧，系统返回结构化征象；医生仍需结合连续视频完成本任务判断。
      </p>

      <div className={`mt-3 rounded-lg border p-2.5 ${highConflict ? 'border-rose-500/40 bg-rose-500/[0.07]' : 'border-amber-500/25 bg-amber-500/[0.05]'}`}>
        <div className={`flex items-center gap-2 text-[10px] font-semibold ${highConflict ? 'text-rose-300' : 'text-amber-300'}`}>
          <Sparkles size={12} /> 结构化辅助证据
        </div>
        {systemReport ? (
          <>
            <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-300">
              <span>建议：{stageLabel(systemReport.recommended_stage)}</span>
              {systemReport.calibrated_confidence != null ? <span>置信度：{Math.round(systemReport.calibrated_confidence * 100)}%</span> : null}
              <span>证据项：{systemReport.evidence?.length || 0}</span>
              {systemReport.recommendation_status === 'conflict' ? <span className="font-semibold text-rose-300">高风险冲突</span> : null}
            </div>
            {conflicts.length ? (
              <div className="mt-2 space-y-1 rounded border border-rose-500/25 bg-rose-500/[0.06] p-2 text-[10px] leading-relaxed text-rose-200">
                {conflicts.map((item, index) => <div key={`${item.code || 'conflict'}-${index}`}>• {item.message || '证据与阶段建议不一致'}</div>)}
              </div>
            ) : null}
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {SIGN_FIELDS.map(([path, label]) => {
                const field = getSign(systemReport, path);
                const value = field?.value == null || String(field.value).trim() === '' ? '未评估' : String(field.value);
                return (
                  <div key={path} className="rounded border border-white/10 bg-black/20 px-2 py-1.5">
                    <div className="text-[9px] text-gray-500">{label}</div>
                    <div className="mt-0.5 truncate text-[10px] text-gray-200" title={value}>{value}</div>
                    <div className={`mt-0.5 text-[8px] ${field?.status === 'conflict' ? 'text-rose-300' : 'text-gray-500'}`}>
                      {signStatus(field?.status)} · {field?.source || 'not_available'}
                    </div>
                  </div>
                );
              })}
            </div>
            {systemReport.summary ? <div className="mt-2 text-[10px] leading-relaxed text-slate-300">{cleanSystemCopy(systemReport.summary)}</div> : null}
          </>
        ) : (
          <div className="mt-1 text-[10px] leading-relaxed text-gray-500">尚未生成当前帧证据；请在左侧视频画面操作。</div>
        )}
        <div className="mt-2 border-t border-white/10 pt-2 text-[9px] text-gray-500">
          几何与规则辅助，非病理金标准；最终判断权在医生。层次、浆膜和胃周组织未评估时，不生成确定性侵润结论。
        </div>
      </div>

      <div className="mt-4 border-t border-white/10 pt-3">
        <div className="flex items-center gap-2 text-[10px] font-semibold text-emerald-300">
          <CheckCircle2 size={12} /> 医生最终判断：{taskLabel}
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
                {value === 'benign' ? '良性' : '恶性'}
              </button>
            ))}
          </div>
        ) : (
          <select
            value={finalStage}
            onChange={(event) => setFinalStage(event.target.value)}
            className="mt-2 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[11px] text-gray-200"
          >
            {STAGES.map((stage) => <option key={stage} value={stage}>{stage || '暂不确定'}</option>)}
          </select>
        )}
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="记录证据、修改或证据不足原因"
          className="mt-2 min-h-12 w-full rounded border border-white/10 bg-black/30 px-2 py-1.5 text-[11px] text-gray-200 placeholder:text-gray-600"
        />
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <button type="button" disabled={recommendationBlocked} onClick={() => void writeDoctorAction('accept')} className="reader-btn justify-center border-emerald-500/30 text-emerald-300 disabled:cursor-not-allowed disabled:opacity-40">采纳系统建议</button>
          <button type="button" onClick={() => void writeDoctorAction('modify')} className="reader-btn justify-center border-amber-500/30 text-amber-300">修改后确认</button>
          <button type="button" onClick={() => void writeDoctorAction('reject')} className="reader-btn justify-center border-rose-500/30 text-rose-300">拒绝系统建议</button>
          <button type="button" onClick={() => void writeDoctorAction('request_more_evidence')} className="reader-btn justify-center border-slate-500/30 text-slate-300">证据不足</button>
        </div>
        {recommendationBlocked && systemReport ? <div className="mt-2 text-[10px] text-rose-300">存在冲突或未确定建议，不能直接采纳；请由医生修改、拒绝或标记证据不足。</div> : null}
        {actionStatus ? <div className="mt-2 text-[10px] text-amber-200">{actionStatus}</div> : null}
      </div>
    </section>
  );
}
