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
      '1. 左侧队列选择病例（可按 T 分期 / 良恶性队列切换）。',
      '2. 播放视频，拖动时间轴自行选择关键帧（算法建议仅供参考）。',
      '3. 在关键帧上框选病灶，再用正点、负点、涂鸦或套索精修病灶轮廓。',
      '4. 确认胃腔轮廓，胃腔需覆盖胃壁与肿块区域，病灶应位于胃腔语义内。',
      '5. 需要时用「视频跟踪」生成整段视频的轮廓传播。',
      '6. 点击「辅助意见」运行 AI 分析，等待进度条完成。',
      '7. 在右侧报告面板与底部证据面板复核分析过程、T2/T3 依据与结构化报告。',
      '8. 在「医生最终判断」中采纳、修改、拒绝或标记证据不足，系统按账号记录。',
    ],
  },
  {
    title: '面板说明',
    items: [
      'Agent 报告：临床展示分期、置信度与文字报告；证据不足或冲突时显示 cTx。',
      '临床辅助资料：部位、长径、厚度、CEA、CA19-9，仅供医生参考，不参与自动分期。',
      '壁层分析：胃壁五层层次与突破相关特征，是 T2/T3 判读的主看点。',
      'GC-US 证据：结构化征象与模板报告状态。',
      '相似病例：运行辅助分析后显示实时检索结果；部分病例提供基于临床资料的预计算相似病例，仅供快速参考。',
      '频谱和形态特征：Fourier 频带能量与边界粗糙度等辅助指标，不能单独决定 T 分期。',
    ],
  },
  {
    title: '注意事项',
    items: [
      'AI 输出仅为辅助证据，最终分期判断由医生完成。',
      'cTx 表示当前证据不足以给出确定分期，请结合其他检查。',
      '相似病例来自院内训练集回顾性病例，其病理分期仅供参考。',
      '操作历史按医生账号隔离，可在顶部「历史」中查看与删除。',
    ],
  },
];

const SECTIONS_EN: HelpSection[] = [
  {
    title: 'Reading workflow',
    items: [
      '1. Select a case in the left queue (switch between T-staging and benign/malignant cohorts).',
      '2. Play the video and pick key frames yourself via the timeline; algorithmic suggestions are advisory only.',
      '3. Box the lesion on a key frame, then refine the contour with positive/negative points, scribble, or lasso.',
      '4. Confirm the lumen contour; it should cover the gastric wall and the mass, with the lesion inside the lumen semantics.',
      '5. Optionally run video tracking to propagate contours across the whole clip.',
      '6. Click the AI assist button to run the analysis and watch the progress indicator.',
      '7. Review the reasoning steps, T2/T3 evidence, and structured report in the right report panel and the bottom evidence panel.',
      '8. Record your final judgment (accept, modify, reject, or insufficient evidence); actions are logged per account.',
    ],
  },
  {
    title: 'Panels',
    items: [
      'Agent report: clinical display stage, confidence, and narrative report; shows cTx when evidence is insufficient or conflicting.',
      'Clinical auxiliaries: site, max length, thickness, CEA, CA19-9; reference only, not used for automatic staging.',
      'Wall-layer analysis: five-layer wall pattern and breakthrough-related features, the key reference for T2 vs T3.',
      'GC-US evidence: structured signs and the template report state.',
      'Similar cases: live retrieval appears after running the analysis; for some cases a precomputed list based on clinical profile is shown for quick reference.',
      'Spectral and morphology features: Fourier band energy and boundary roughness; assistive only and cannot decide T stage alone.',
    ],
  },
  {
    title: 'Notes',
    items: [
      'AI output is assistive evidence only; the final staging judgment rests with the physician.',
      'cTx means current evidence is insufficient for a definite stage; correlate with other examinations.',
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
