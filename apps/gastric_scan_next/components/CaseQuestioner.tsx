'use client';

import React, { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { MessageSquareText, Send } from 'lucide-react';
import type { AgentAnalysisResponse, Patient } from '@/types';

type Props = {
  patient: Patient;
  analysis: AgentAnalysisResponse | null;
  reportText: string;
  zh?: boolean;
};

function asNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function answerFromEvidence(
  question: string,
  patient: Patient,
  analysis: AgentAnalysisResponse | null,
  reportText: string,
  zh: boolean,
): string {
  const query = question.toLowerCase();
  const report = analysis?.report;
  const clinical = patient.clinical;
  const morphology = analysis?.tool_evidence?.morphology || {};
  const stage = report?.recommended_t_stage || '未输出';
  const confidence = report?.confidence || '未生成';
  const pathology = normalizeText(patient.report?.pathology_report);
  const length = clinical?.tumorSize?.length;
  const thickness = clinical?.tumorSize?.thickness;
  const cea = clinical?.biomarkers?.cea;
  const ca199 = clinical?.biomarkers?.ca199;

  if (/病理|pathology|pT|后验/.test(query)) {
    return pathology
      ? `${zh ? '病理资料已挂接，但仅作为后验复核资料，不参与术前自动分期：' : 'Pathology is attached as retrospective review data and does not drive preoperative staging:'}\n${pathology}`
      : (zh
        ? '当前病例没有挂接病理报告。病理结果如后续获得，应在医生复核区登记，不回写为术前确定结论。'
        : 'No pathology report is attached. If obtained later, record it in physician review rather than rewriting the preoperative conclusion.');
  }

  if (/长径|厚度|大小|尺寸|size|length|thickness/.test(query)) {
    const sizeText = length != null || thickness != null
      ? `${length ?? '未评估'} cm x ${thickness ?? '未评估'} cm`
      : '未评估';
    return `${zh ? '病例表格中的病灶尺寸：' : 'Tumor size from the case table: '}${sizeText}。`;
  }

  if (/cea|ca19|化验|biomarker|marker/.test(query)) {
    return `${zh ? '实验室辅助资料：' : 'Laboratory auxiliary data: '}CEA ${cea ?? '未提供'}，CA19-9 ${ca199 ?? '未提供'}。${zh ? '这些数据仅供医生参考。' : 'These values are for physician reference only.'}`;
  }

  if (/为什么|依据|证据|分期|stage|evidence|why/.test(query)) {
    const reasons = [
      ...(report?.supporting_evidence || []),
      ...(report?.conflicting_evidence || []),
      ...(report?.uncertainty_flags || []),
    ].filter(Boolean).slice(0, 5);
    const reasonText = reasons.length ? reasons.join('；') : (report?.reasoning || reportText || '当前没有可展开的结构化依据。');
    return `${zh ? `当前报告建议 ${stage}，置信度 ${confidence}。依据与限制：` : `The report suggests ${stage} with ${confidence} confidence. Evidence and limitations: `}${reasonText}`;
  }

  if (/频谱|傅里叶|fourier|粗糙|边界|spectral/.test(query)) {
    const roughness = asNumber(morphology.boundary_roughness);
    return roughness != null
      ? `${zh ? '当前提供的是边界高频细节代理，频谱粗糙度为 ' : 'The current output provides a boundary high-frequency proxy. Spectral roughness is '}${roughness.toFixed(2)}。${zh ? '仓库未发现独立 Fourier 模型或频域服务，因此不能把它解释成独立 Fourier 结论。' : 'No independent Fourier model or frequency-domain service was found, so this is not an independent Fourier conclusion.'}`
      : (zh
        ? '当前病例没有返回频谱粗糙度。不能从缺失的频域输入推断病理结论。'
        : 'No spectral roughness was returned for this case. A pathology conclusion cannot be inferred from missing frequency-domain input.');
  }

  return reportText
    ? `${zh ? '当前病例的自然语言报告摘要：' : 'Natural-language report summary for this case:'}\n${reportText.slice(0, 900)}`
    : (zh
      ? '当前还没有自然语言报告。可以提问：分期依据、病理资料、病灶尺寸、CEA/CA19-9 或频谱特征。'
      : 'No natural-language report is available yet. Ask about stage evidence, pathology, lesion size, CEA/CA19-9, or spectral features.');
}

export function CaseQuestioner({ patient, analysis, reportText, zh = true }: Props) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const quickQuestions = useMemo(
    () => (zh
      ? ['当前分期依据是什么？', '病理资料是否参与自动分期？', '长径、厚度和化验结果是多少？', '频谱特征能说明什么？']
      : ['What supports the current stage?', 'Does pathology drive automatic staging?', 'What are the size and biomarker values?', 'What does the spectral feature mean?']),
    [zh],
  );

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const nextQuestion = question.trim();
    if (!nextQuestion) return;
    setAnswer(answerFromEvidence(nextQuestion, patient, analysis, reportText, zh));
  };

  return (
    <section className="rounded-2xl border border-fuchsia-300/20 bg-[linear-gradient(135deg,rgba(67,24,86,0.24),rgba(6,10,15,0.92))] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-bold text-fuchsia-100">
            <MessageSquareText size={15} />
            {zh ? '病例提问器' : 'Case questioner'}
          </div>
          <div className="mt-1 text-[10px] leading-relaxed text-slate-500">
            {zh ? '只基于当前病例已加载的影像、临床和报告证据，不引入病理后验。' : 'Grounded only in the loaded image, clinical, and report evidence; pathology hindsight is excluded.'}
          </div>
        </div>
        <span className="rounded border border-fuchsia-300/25 bg-fuchsia-300/10 px-2 py-1 text-[9px] text-fuchsia-100">
          {zh ? '本地证据问答' : 'Local evidence QA'}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {quickQuestions.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => {
              setQuestion(item);
              setAnswer(answerFromEvidence(item, patient, analysis, reportText, zh));
            }}
            className="rounded-full border border-white/10 bg-black/20 px-2.5 py-1 text-[10px] text-slate-300 transition hover:border-fuchsia-300/40 hover:text-fuchsia-100"
          >
            {item}
          </button>
        ))}
      </div>
      <form onSubmit={submit} className="mt-3 flex gap-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={zh ? '输入关于当前病例的问题' : 'Ask about this case'}
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/35 px-3 py-2 text-[11px] text-white outline-none placeholder:text-slate-600 focus:border-fuchsia-300/50"
        />
        <button
          type="submit"
          disabled={!question.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-fuchsia-300/30 bg-fuchsia-300/10 px-3 py-2 text-[11px] font-semibold text-fuchsia-100 transition hover:bg-fuchsia-300/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send size={13} />
          {zh ? '回答' : 'Ask'}
        </button>
      </form>
      {answer ? (
        <div className="mt-3 whitespace-pre-wrap rounded-xl border border-fuchsia-300/15 bg-black/25 px-3 py-3 text-[11px] leading-relaxed text-slate-200">
          {answer}
        </div>
      ) : null}
    </section>
  );
}
