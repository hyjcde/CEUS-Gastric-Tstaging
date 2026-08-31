'use client';

import React, { useState } from 'react';
import { BookOpen, X } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';

type Props = {
  open: boolean;
  onClose: () => void;
};

type HelpSection = {
  title: string;
  items: string[];
};

const SECTIONS_ZH: HelpSection[] = [
  {
    title: '阅片流程',
    items: [
      '1. 左侧队列选择病例（可按 T 分期 / 良恶性队列切换）。手机用底部「病例 / 阅片 / 判断(结果)」切换，电脑仍是左中右三栏。',
      '2. 不要先把 T1–T4 输给模型。T 分期只作独立记录。',
      '3. 播放视频，点亮「框选病灶」后拖框；当前帧会作为关键帧并自动分割。',
      '4. 框选后 AI 会留下两侧短线建议。请先选一处最深浸润区：可点 AI 建议，或自己点病灶最靠近或最突出于外侧胃壁的位置。选完才开始分析。这不是突破点。',
      '5. 自动锚点失败时再「补画短线」，左右各画一段看得见的胃壁，不必穿过病灶。可先测厚设定笔刷。要删最近一段用「撤销一段」；清全部用「清除胃壁」。连接草稿可接受、修改或拒绝。用 ±1 / ±5 核对，邻帧会留下残影。',
      '6. 看不清点「看不清」，不要当成中断。本段只剩浆膜就标一层。停接或越线时超声上会有白红叉和层名，不定 cT。',
      '7. 「辅助分析」在框选后可点。建议先确认最深区。特征没评到会标「未评估」。',
      '8. 阅片结束后，点底部「查看并确认报告」打开报告。',
      '9. 胃腔在「更多工具」里点亮「框选胃腔」，松手后自动分割。',
    ],
  },
  {
    title: '面板说明',
    items: [
      'Agent 报告：临床展示分期、置信度与文字报告；证据不足或冲突时分期标记为 provisional。',
      '临床辅助资料：部位、长径、厚度、CEA、CA19-9，仅供医生参考，不参与自动分期。',
      '壁层分析：壁层与突破相关特征，是 T2/T3 判读的主看点；完整分层图在完整模板中展开。',
      'GC-US 证据：结构化征象与模板报告状态。',
      '相似病例：运行辅助分析后显示实时检索结果；部分病例提供基于临床资料的预计算相似病例，仅供快速参考。',
      '频谱和形态特征：Fourier 频带能量与边界粗糙度等辅助指标，不能单独决定 T 分期。',
    ],
  },
  {
    title: '注意事项',
    items: [
      'AI 输出仅为辅助证据，最终分期判断由医生完成。',
      'provisional 表示当前分期为辅助初步判断，待医生确认壁层/浆膜证据后签出。',
      '相似病例来自院内训练集回顾性病例，其病理分期仅供参考。',
      '操作历史按医生账号隔离，可在顶部「历史」中查看与删除。',
    ],
  },
];

const SECTIONS_EN: HelpSection[] = [
  {
    title: 'Reading workflow',
    items: [
      '1. Select a case in the left queue (switch between T-staging and benign/malignant cohorts). On a phone, use the bottom Cases / Viewer / Call (Result) tabs; the desktop layout stays three columns.',
      '2. Do not type T1–T4 into the model. The T call is an independent record.',
      '3. Play the video, arm Box lesion, then drag; this frame becomes the keyframe and auto-segments.',
      '4. After the box, AI keeps short flank suggestions. Select one deepest-invasion region first: tap the AI suggestion, or mark where the lesion is closest to or most proud of the outer wall. Analysis starts after you choose. This is not a breach.',
      '5. If auto-anchors fail, paint a short visible span on each flank. Do not cross the mass. Optionally tap inner and outer wall edges to set the brush. Use Undo span for the last stroke, or Clear wall for all. Accept, modify, or reject the join draft. Step ±1 / ±5; neighbor frames keep a ghost overlay.',
      '6. Tap Not seen if the plane is unclear. Not seen is not interruption. If only serosa remains, mark 1 layer. A stop or overshoot shows a labeled cross on the cine; it is not a definite cT.',
      '7. Assist lights after a lesion box. Confirm the deepest region first. Unrated signs are labeled Not assessed.',
      '8. After reading, tap Review and confirm report at the bottom.',
      '9. Open More tools, arm Box lumen, then drag; release auto-segments the lumen.',
    ],
  },
  {
    title: 'Panels',
    items: [
      'Agent report: clinical display stage, confidence, and narrative report; the stage is marked provisional when evidence is insufficient or conflicting.',
      'Clinical auxiliaries: site, max length, thickness, CEA, CA19-9; reference only, not used for automatic staging.',
      'Wall-layer analysis: wall and breakthrough-related features, the key reference for T2 vs T3; full layer maps open in the complete template.',
      'GC-US evidence: structured signs and the template report state.',
      'Similar cases: live retrieval appears after running the analysis; for some cases a precomputed list based on clinical profile is shown for quick reference.',
      'Spectral and morphology features: Fourier band energy and boundary roughness; assistive only and cannot decide T stage alone.',
    ],
  },
  {
    title: 'Notes',
    items: [
      'AI output is assistive evidence only; the final staging judgment rests with the physician.',
      'A provisional stage is an assistive preliminary judgment; confirm wall-layer/serosa evidence before sign-off.',
      'Similar cases come from retrospective in-house training cases; their pathology stages are for reference only.',
      'Operation history is isolated per doctor account and can be reviewed or deleted under History in the top bar.',
    ],
  },
];

export function ReaderHelpModal({ open, onClose }: Props) {
  const { language } = useSettings();
  const [override, setOverride] = useState<'zh' | 'en' | null>(null);
  if (!open) return null;
  const showZh = override ? override === 'zh' : language !== 'en';
  const sections = showZh ? SECTIONS_ZH : SECTIONS_EN;

  return (
    <div
      className="fixed inset-0 z-[300100] flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#0c0d0f] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-100">
            <BookOpen size={15} className="text-emerald-300" />
            {showZh ? '使用说明' : 'User Guide'}
          </div>
          <div className="flex items-center gap-2">
            <div className="inline-flex overflow-hidden rounded-md border border-white/10">
              {([
                { id: 'zh' as const, label: '中文' },
                { id: 'en' as const, label: 'EN' },
              ]).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setOverride(item.id)}
                  className={`border-0 px-2.5 py-1 text-[10px] transition ${
                    showZh === (item.id === 'zh')
                      ? 'bg-emerald-400 text-slate-950'
                      : 'bg-transparent text-slate-400 hover:bg-white/10 hover:text-white'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <button type="button" onClick={onClose} className="reader-btn" title={showZh ? '关闭' : 'Close'}>
              <X size={14} />
            </button>
          </div>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3">
          {sections.map((section) => (
            <section key={section.title}>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-200/80">
                {section.title}
              </div>
              <ul className="space-y-1 text-[11px] leading-relaxed text-gray-300">
                {section.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
