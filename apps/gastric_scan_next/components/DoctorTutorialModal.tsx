'use client';

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';

type TutorialStep = {
  titleZh: string;
  titleEn: string;
  whereZh: string;
  whereEn: string;
  doZh: string[];
  doEn: string[];
  tipZh?: string;
  tipEn?: string;
};

const STEPS: TutorialStep[] = [
  {
    titleZh: '登录账号',
    titleEn: 'Sign in',
    whereZh: '顶栏右侧圆形头像',
    whereEn: 'Circle button on the right of the top bar',
    doZh: [
      '点头像，再点「登录」或「切换账号」。',
      '用发给你的账号和密码进入。判断、勾画、历史都记在这个账号下。',
      '手机登录后直接进入超声画面，不用先点判断。',
    ],
    doEn: [
      'Tap the avatar, then Sign in or Switch account.',
      'Use the account you were given. Judgments, drawings, and history stay on this account.',
      'On a phone, sign-in opens the ultrasound viewer first.',
    ],
  },
  {
    titleZh: '选病例',
    titleEn: 'Pick a case',
    whereZh: '电脑看左侧列表；手机点底部「病例」',
    whereEn: 'Desktop: left list. Phone: bottom Cases tab',
    doZh: [
      '在列表里点一例，中间会打开这段超声视频。',
      '没评过的会标「未评」，做过的会标「半途」或「已完成」。',
      '手机选完病例后回到超声；可用底部「超声 / 判断」来回切。',
    ],
    doEn: [
      'Tap a case; the ultrasound video opens in the center.',
      'Open cases show Open; started cases show Partial or Done.',
      'On a phone, switch with the bottom Ultrasound / Call tabs.',
    ],
  },
  {
    titleZh: '先给出你的判断',
    titleEn: 'Record your call first',
    whereZh: '电脑看右侧；手机点底部「判断」',
    whereEn: 'Desktop: right panel. Phone: bottom Call tab',
    doZh: [
      '良恶性队列：点「良性」或「恶性」。',
      'T 分期队列：点 T1、T2、T3 或 T4+。',
      '点过后仍可再点别的选项改初判，不必等 AI。',
    ],
    doEn: [
      'Benign/malignant queue: tap Benign or Malignant.',
      'T-staging queue: tap T1, T2, T3, or T4+.',
      'You can retap another option to change your first call before AI runs.',
    ],
  },
  {
    titleZh: '看视频并框选病灶',
    titleEn: 'Watch and box the lesion',
    whereZh: '中间超声画面',
    whereEn: 'Center viewer',
    doZh: [
      '先播放，找到病灶最清楚的一帧，暂停。',
      '点亮「框选病灶」，在画面上拖一个框。',
      '松手后当前帧就是关键帧，系统会自动分割。要重画，再点「框选病灶」拖新框。多个灶点「再框一灶」。',
    ],
    doEn: [
      'Play first, pause on the clearest lesion frame.',
      'Arm Box lesion, then drag a box on the image.',
      'On release, this frame becomes a keyframe and auto-segments. Arm Box lesion again to replace. Tap Add lesion for a second mass.',
    ],
  },
  {
    titleZh: '关键帧和浸润最深',
    titleEn: 'Keyframes and deepest invasion',
    whereZh: '阅片画面上方的关键帧条',
    whereEn: 'Keyframe strip above the viewer',
    doZh: [
      'T 分期最好留 2–3 帧，盯浸润最深的那一帧为主；不必选满 10 枚。',
      '进度条先粗定位；滚轮或左右键逐帧，停在想看的毫秒和帧。',
      '空格先暂停；已暂停时再按空格才标关键帧。多个灶用「再框一灶」，不要把「框选」当成再加一灶。',
    ],
    doEn: [
      'For T-staging, keep about 2–3 frames and mark deepest invasion; do not fill all 10 slots.',
      'Drag the seek bar to get close; wheel or arrow keys step one frame.',
      'Space pauses first; press again while paused to mark. Use Add lesion for a second mass; Box lesion replaces.',
    ],
  },
  {
    titleZh: '只给解剖提示，不要先定义 T',
    titleEn: 'Give anatomy, not a T call',
    whereZh: '右侧粗筛；阅片工具条浆膜预期线',
    whereEn: 'Call-panel coarse screen; viewer expected serosal line',
    doZh: [
      '不要把 T1–T4 输入模型。T 分期只作独立记录，用于以后对照。',
      '粗筛只选：明确浅层征象 / 明确外层突破征象 / 深度边界不清。这不是分期。',
      '第一版请画浆膜预期走行线。浆膜 / 固有肌 / 浅层是分析哪条界面，不是判断已经到了哪一层。',
    ],
    doEn: [
      'Do not type T1–T4 into the model. The T call is an independent record for later comparison.',
      'The coarse screen is only: clear shallow signs / clear outer-breach signs / depth unclear. That is not a stage.',
      'First version: draw the expected serosal trajectory. Serosa / MP / Shallow pick the interface to analyze, not the depth reached.',
    ],
    tipZh: '分层是草稿，不是病理五层，也不解锁确定 cT。',
    tipEn: 'Wall layers are a draft, not pathology five-layer truth, and do not unlock a definite cT.',
  },
  {
    titleZh: '画一条浆膜预期走行线',
    titleEn: 'Draw one expected serosal trajectory',
    whereZh: '中间阅片：画预期线，可选分析焦点；再看右侧草稿',
    whereEn: 'Center viewer: expected line and optional focus; then the draft on the right',
    doZh: [
      '画浆膜预期线，一笔穿过可疑区到对侧。',
      '看不清标看不清，不要当成中断。',
      '可点最多 3 个分析焦点，表示重点分析位置，不是突破点。单帧中断要对照其他关键帧。',
    ],
    doEn: [
      'Draw one expected serosal line through the suspicious zone to the opposite side.',
      'Mark Not seen if unclear. Not seen is not interruption.',
      'Optionally tap up to 3 analysis-focus points. These are where to look, not breach marks. Check other keyframes if one frame looks broken.',
    ],
  },
  {
    titleZh: '辅助分析',
    titleEn: 'Assist analysis',
    whereZh: '右侧判断面板里的「辅助分析」按钮',
    whereEn: 'Assist button in the Call panel',
    doZh: [
      '没点判断、没框选病灶时，按钮是灰色的，上面有 1-2-3 提示。',
      '先锁相邻期、画邻近胃壁，再点「辅助分析」。指南解释跟大字走，不把四分类 T4 写成主判断。',
      '手机上如果还在判断页，可先点「去勾画病灶」或底部「超声」回到视频。',
    ],
    doEn: [
      'The button stays gray until you record a call and box the lesion. A 1-2-3 checklist shows what is missing.',
      'Lock the adjacent pair and paint the remaining wall first, then tap Assist. Guideline text follows the headline, not frozen T4.',
      'On a phone, tap Go draw the lesion if you are still on the Call tab.',
    ],
  },
  {
    titleZh: '核对 AI，可改自己的判断',
    titleEn: 'Review AI, then edit your call',
    whereZh: '右侧「AI 判断」和上方你的判断按钮',
    whereEn: 'AI call card and your stage buttons',
    doZh: [
      '勾了相邻期后，大字「AI 判断」只在这两期里给倾向，不会把 T4 写成主判断。',
      '四分类原数字仍写在大字旁边对照；冻结权重未改。胃壁草稿不定 cT。',
      '不同意就再点上面你的分期。层次草稿不定 cT。',
    ],
    doEn: [
      'After an adjacent lock, the large AI call ranks only inside that pair and will not headline T4.',
      'Frozen four-class stays beside the headline for contrast. Weights are unchanged. Wall draft is not a definite cT.',
      'Disagree by retapping your stage. Wall draft does not make a definite cT.',
    ],
  },
  {
    titleZh: '保存并下一例',
    titleEn: 'Save and go to the next case',
    whereZh: '判断面板下方两个大按钮',
    whereEn: 'Two large buttons under the Call panel',
    doZh: [
      '同意 AI：点「同意 AI 并下一例」。',
      '坚持自己的判断：直接点「按我的判断保存并下一例」；若要改，先再点上面的分期。',
      '看不清就点「证据不足」。关掉网页再打开，会回到上次判断和勾画。',
    ],
    doEn: [
      'Agree with AI: tap Agree with AI and next.',
      'Keep your own call: tap Save my call and next. Retap a stage first only if you want to change it.',
      'If the clip is unclear, tap Insufficient evidence. Reopening the site restores your last call and drawings.',
    ],
  },
  {
    titleZh: '查看并确认报告',
    titleEn: 'Review and confirm the report',
    whereZh: '判断面板最底部的大按钮',
    whereEn: 'Large button at the bottom of the Call panel',
    doZh: [
      '阅片结束后点「查看并确认报告」。',
      '核对文字和附图，确认后再关闭。',
      '报告是阅片后的整理，不是开始阅片的第一步。',
    ],
    doEn: [
      'After reading, tap Review and confirm report.',
      'Check the text and images, then close.',
      'The report comes after reading; it is not the first step.',
    ],
  },
  {
    titleZh: '历史和手机操作',
    titleEn: 'History and phone layout',
    whereZh: '顶栏「历史」；手机底部三栏',
    whereEn: 'History in the top bar; three phone tabs',
    doZh: [
      '顶栏「历史」可回看本账号评过的病例、判断和关键帧。',
      '手机：底部「病例」选例，「超声」看视频和勾画，「判断 / 结果」给判断和看 AI。',
      '任何一步不清楚，再点顶栏「教程」从这一步继续看。',
    ],
    doEn: [
      'History in the top bar lists this account’s cases, calls, and keyframes.',
      'Phone: Cases to pick, Ultrasound to watch and draw, Call / Result to judge and review AI.',
      'If any step is unclear, tap Tutorial in the top bar and continue from there.',
    ],
  },
  {
    titleZh: '桌面应用（可选）',
    titleEn: 'Desktop app (optional)',
    whereZh: '顶栏头像菜单：桌面应用（Mac / Windows / 鸿蒙）',
    whereEn: 'Avatar menu: Desktop app (Mac / Windows / Harmony)',
    doZh: [
      '窗口壳只打开公网站，不锁前端版本。Electron 不会比浏览器更快。',
      '日常用 Chrome / Edge，点顶栏「全屏」。要图标时下个人资料页的轻量启动器，打开即全屏。Electron 约 100 MB，可不用。',
      '公网站更新后硬刷新。鸿蒙仍是同一只公网 WebView 壳。',
    ],
    doEn: [
      'The window only opens the public site. It does not freeze the frontend. Electron is not faster than the browser.',
      'Day to day, use Chrome / Edge and tap Fullscreen. The profile light launcher opens fullscreen. The 100 MB Electron pack is optional.',
      'Hard-reload after a site update. Harmony is the same live WebView shell.',
    ],
  },
];

type Props = {
  open: boolean;
  onClose: () => void;
};

export function DoctorTutorialModal({ open, onClose }: Props) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (open) setStep(0);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'ArrowRight') setStep((value) => Math.min(STEPS.length - 1, value + 1));
      if (event.key === 'ArrowLeft') setStep((value) => Math.max(0, value - 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open || typeof document === 'undefined') return null;

  const current = STEPS[step];
  const last = step === STEPS.length - 1;
  const items = zh ? current.doZh : current.doEn;

  return createPortal(
    <div
      className="fixed inset-0 z-[300200] flex items-end justify-center bg-black/70 p-3 sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        className="flex max-h-[92svh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#0c0d10] shadow-2xl"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="doctor-tutorial-title"
      >
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-gray-100">
            <BookOpen size={16} className="shrink-0 text-sky-300" />
            <span id="doctor-tutorial-title">{zh ? '使用教程' : 'Tutorial'}</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <span>{step + 1}/{STEPS.length}</span>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex min-h-9 min-w-9 items-center justify-center rounded-lg border border-white/15 text-slate-200"
              aria-label={zh ? '关闭教程' : 'Close tutorial'}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-sky-200/80">
            {zh ? `第 ${step + 1} 步` : `Step ${step + 1}`}
          </div>
          <h2 className="mt-1 text-2xl font-black tracking-wide text-slate-50">
            {zh ? current.titleZh : current.titleEn}
          </h2>
          <div className="mt-2 rounded-lg border border-sky-400/20 bg-sky-500/10 px-3 py-2 text-[13px] text-sky-50">
            <span className="font-semibold">{zh ? '在哪看：' : 'Where: '}</span>
            {zh ? current.whereZh : current.whereEn}
          </div>
          <ol className="mt-4 space-y-2.5 text-[15px] leading-relaxed text-slate-200">
            {items.map((item, index) => (
              <li key={item} className="flex gap-2">
                <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-white/10 text-[11px] font-bold text-slate-100">
                  {index + 1}
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ol>
          {(zh ? current.tipZh : current.tipEn) ? (
            <p className="mt-4 rounded-lg border border-amber-200/20 bg-amber-500/10 px-3 py-2 text-[13px] leading-relaxed text-amber-50">
              {zh ? current.tipZh : current.tipEn}
            </p>
          ) : null}
        </div>

        <div className="border-t border-white/10 px-4 py-3">
          <div className="mb-3 flex justify-center gap-1.5">
            {STEPS.map((item, index) => (
              <button
                key={item.titleZh}
                type="button"
                onClick={() => setStep(index)}
                className={`h-2 rounded-full transition-all ${
                  index === step ? 'w-6 bg-sky-300' : 'w-2 bg-white/20 hover:bg-white/40'
                }`}
                aria-label={zh ? `打开第 ${index + 1} 步` : `Open step ${index + 1}`}
              />
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={step === 0}
              onClick={() => setStep((value) => Math.max(0, value - 1))}
              className="inline-flex min-h-11 items-center justify-center gap-1 rounded-xl border border-white/15 text-[14px] font-semibold text-slate-100 disabled:opacity-35"
            >
              <ChevronLeft size={16} />
              {zh ? '上一步' : 'Back'}
            </button>
            <button
              type="button"
              onClick={() => {
                if (last) {
                  onClose();
                  return;
                }
                setStep((value) => Math.min(STEPS.length - 1, value + 1));
              }}
              className="inline-flex min-h-11 items-center justify-center gap-1 rounded-xl border border-sky-300/40 bg-sky-500/20 text-[14px] font-semibold text-sky-50"
            >
              {last ? (zh ? '完成' : 'Done') : (zh ? '下一步' : 'Next')}
              {last ? null : <ChevronRight size={16} />}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
