"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { ChevronLeft, Download, GitBranch } from "lucide-react";
import { useSettings } from "@/contexts/SettingsContext";
import {
  reportData,
  getStatusLabel,
  stageBadgeClass,
  statusDotClass
} from "@/app/reports/report-data";
import { downloadReportPdf, downloadSavedTemplateReportPdf } from "@/lib/report-download";
import { TemplateReportPreview } from "@/components/TemplateReportEditor";
import type { GcUsReportState } from "@/lib/gc-us-report-template";
import type { Report } from "@/app/reports/report-data";
import type { Patient } from "@/types";

type TemplateReportRecord = {
  requestKey: string;
  summary: Report;
  report: GcUsReportState;
  revisions: Array<{
    report_id: string;
    revision: number;
    status: 'draft' | 'reviewed' | 'finalized';
    updated_at: string;
    finalized_at: string | null;
    signed_by?: string | null;
    changed_fields?: string[];
  }>;
};

function patientFromTemplateReport(summary: Report, report: GcUsReportState): Patient {
  const patientId = summary.patient || report.case_id || summary.id;
  return {
    id: patientId,
    id_short: patientId,
    patient_id: patientId,
    group: '',
    phase: '',
    source_label: summary.source === 'template' ? '模板报告' : '',
    frame_count: 0,
    image_url: '',
    overlay_url: '',
    json_url: '',
    segmentation: {
      source: 'none',
      has_annotation: false,
      has_overlay: false,
      has_roi: false,
      annotation_count: 0,
      frame_count: 0,
    },
    agent_report: {
      schema_version: 'report-detail-v1',
      case_token: patientId,
      data_source: 'template_report',
      frame_count: 0,
      report_status: 'draft',
      image_quality: { status: 'pending', summary: '' },
      segmentation: { status: 'missing', summary: '' },
      classification: { status: 'placeholder', summary: summary.stage },
      similar_case_support: { status: 'pending', summary: '' },
      manual_review_recommended: false,
    },
    clinical: {
      age: null,
      sex: '',
      tumorSize: { length: null, thickness: null },
      location: typeof report.template_fields.lesion_site.value === 'string'
        ? report.template_fields.lesion_site.value
        : '',
      biomarkers: {
        cea: null,
        ca199: null,
        cea_positive: false,
        ca199_positive: false,
      },
    },
  };
}

export default function ReportDetailPage() {
  const { language } = useSettings();
  const params = useParams<{ reportId: string }>();
  const searchParams = useSearchParams();
  const reportId = Array.isArray(params?.reportId) ? params.reportId[0] : params?.reportId;
  const revisionParam = searchParams.get('revision');
  const revision = revisionParam ? Number(revisionParam) : null;
  const staticReport = reportData.find(item => item.id === reportId);
  const [templateRecord, setTemplateRecord] = useState<TemplateReportRecord | null>(null);
  const [loadedRequestKey, setLoadedRequestKey] = useState<string | null>(null);
  const requestKey = Number.isFinite(revision) && revision != null ? `revision:${revision}` : "current";

  useEffect(() => {
    if (staticReport || !reportId) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ report_id: reportId });
    if (Number.isFinite(revision) && revision != null) query.set('revision', String(revision));
    void fetch(`/api/reports/template?${query.toString()}`, { signal: controller.signal })
      .then(async response => {
        if (!response.ok) return null;
        return await response.json() as {
          ok?: boolean;
          report?: GcUsReportState | null;
          metadata?: {
            report_id: string;
            patient_id: string;
            patient_label: string;
            status: 'draft' | 'reviewed' | 'finalized';
            revision: number;
            case_id: string;
            signed_by?: string | null;
            updated_at: string;
            template_stage?: string;
            changed_fields?: string[];
          } | null;
          revisions?: Array<{
            report_id: string;
            revision: number;
            status: 'draft' | 'reviewed' | 'finalized';
            updated_at: string;
            finalized_at: string | null;
            signed_by?: string | null;
            changed_fields?: string[];
          }>;
        };
      })
      .then(payload => {
        if (controller.signal.aborted || !payload?.ok || !payload.report || !payload.metadata) return;
        const metadata = payload.metadata;
        setTemplateRecord({
          requestKey,
          summary: {
            id: metadata.report_id,
            patient: metadata.patient_label || metadata.patient_id,
            date: metadata.updated_at.slice(0, 10),
            stage: metadata.template_stage || 'uTx',
            status: metadata.status === 'finalized'
              ? 'Finalized'
              : metadata.status === 'reviewed'
                ? 'Reviewed'
                : 'Draft',
            source: 'template',
            caseId: metadata.case_id,
            revision: metadata.revision,
            signedBy: metadata.signed_by,
            changedFields: metadata.changed_fields,
          },
          report: payload.report,
          revisions: payload.revisions || [],
        });
      })
      .catch(() => {
        // Fall through to the not-found state when the persisted report is unavailable.
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadedRequestKey(requestKey);
      });
    return () => {
      controller.abort();
    };
  }, [reportId, requestKey, revision, staticReport]);

  const activeTemplateRecord = templateRecord?.requestKey === requestKey ? templateRecord : null;
  const report = staticReport || activeTemplateRecord?.summary;
  if (!report && !staticReport && loadedRequestKey !== requestKey) {
    return (
      <main className="flex h-screen w-screen flex-col bg-[#000000] text-gray-200">
        <div className="h-16 shrink-0 border-b border-white/10">
          <Header />
        </div>
        <div className="flex flex-1 items-center justify-center p-8 text-sm text-gray-400">
          {language !== "en" ? "正在读取模板报告..." : "Loading template report..."}
        </div>
      </main>
    );
  }
  if (!report) {
    return (
      <main className="flex h-screen w-screen flex-col bg-[#000000] text-gray-200">
        <div className="h-16 shrink-0 border-b border-white/10">
          <Header />
        </div>
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="space-y-4 text-center">
            <h1 className="text-2xl font-bold text-white">
              {language !== "en" ? "未找到报告" : "Report not found"}
            </h1>
            <Link
              href="/reports"
              className="inline-flex items-center gap-2 text-sm text-blue-300 hover:text-white transition-colors"
            >
              <ChevronLeft size={16} />
              {language !== "en" ? "返回报告列表" : "Back to reports"}
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const stageConfidence = report.stage.includes("T4")
    ? 92
    : report.stage.startsWith("T3")
      ? 78
      : 64;

  const structuredSections = [
    {
      label: language !== "en" ? "影像发现" : "Imaging Findings",
      value: language !== "en"
        ? "胃体后壁肿块伴不规则内壁，可见低密度灶，淋巴结信号多发。"
        : "Irregular posterior body mass with hypoechoic core and multiple nodal signals."
    },
    {
      label: language !== "en" ? "淋巴结" : "Lymph nodes",
      value: language !== "en"
        ? "提示区域淋巴结肿大，伴环形增强，N2-N3风险。"
        : "Regional node enlargement with ring enhancement, raising N2-N3 suspicion."
    },
    {
      label: language !== "en" ? "建议方案" : "Recommended action",
      value: language !== "en"
        ? "推荐增强CT+腹腔镜探查，若确认为T4则需优先新辅助方案。"
        : "Recommend contrast CT and laparoscopy; consider neoadjuvant protocol if T4 confirmed."
    }
  ];

  const smartSummary = [
    language !== "en"
      ? "模型融合 Ki-67/CPS/PD-1 信号推断为 T4a，淋巴结转移风险高。"
      : "Model fusion of Ki-67/CPS/PD-1 suggests T4a with high nodal risk.",
    language !== "en"
      ? "病理提示分化中等腺癌，CEA/CA19-9 均轻度升高。"
      : "Pathology indicates moderately differentiated adenocarcinoma with mild CEA/CA19-9 elevation.",
    language !== "en"
      ? "建议 2-4 周内复查标志物并准备 MDT 讨论新辅助。"
      : "Schedule follow-up markers in 2-4 weeks and prep MDT discussion for neoadjuvant plan."
  ];

  return (
    <main className="flex h-screen w-screen flex-col bg-[#000000] text-gray-200 overflow-hidden">
      <div className="h-16 shrink-0 border-b border-white/10 z-50">
        <Header />
      </div>
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-5xl mx-auto space-y-6">
          <Link
            href="/reports"
            className="inline-flex items-center gap-2 text-sm text-blue-300 hover:text-white transition-colors"
          >
            <ChevronLeft size={16} />
            {language !== "en" ? "返回报告列表" : "Back to reports"}
          </Link>

          <div className="bg-linear-to-br from-neutral-900/90 to-neutral-800/50 border border-white/10 rounded-2xl p-6 shadow-2xl space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{language !== "en" ? "报告编号" : "Report ID"}</div>
                <div className="text-3xl font-bold font-mono">{report.id}</div>
                <div className="text-[11px] text-gray-500 mt-1">
                  {report.patient} / {report.date}
                  {report.revision ? ` / v${report.revision}` : ''}
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {activeTemplateRecord?.summary.caseId ? (
                  <Link
                    href={`/?case_id=${encodeURIComponent(activeTemplateRecord.summary.caseId)}`}
                    className="inline-flex items-center gap-2 rounded-full border border-cyan-300/25 px-3 py-1.5 text-[10px] text-cyan-100 hover:bg-cyan-300/10"
                  >
                    <GitBranch size={14} />
                    {language !== "en" ? "继续修订" : "Continue revision"}
                  </Link>
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    if (activeTemplateRecord) {
                      void downloadSavedTemplateReportPdf(
                        report.id,
                        language === 'en'
                          ? `gastric_us_report_${report.patient.replace(/[^a-zA-Z0-9_-]/g, '_')}_v${report.revision || 1}.pdf`
                          : `胃癌超声报告_${report.patient.replace(/[^a-zA-Z0-9_\u4e00-\u9fff-]/g, "_")}_v${report.revision || 1}.pdf`,
                        report.revision,
                        language === 'en' ? 'en' : 'zh',
                      );
                    } else {
                      downloadReportPdf(report);
                    }
                  }}
                  className="inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-[10px] uppercase tracking-widest text-gray-300 hover:bg-white/10 transition-colors"
                >
                  <Download size={16} />
                  {language !== "en" ? "下载PDF" : "Download PDF"}
                </button>
              </div>
            </div>

            {!activeTemplateRecord ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-black/30 border border-white/5 rounded-2xl p-4 space-y-1">
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{language !== "en" ? "分期预测" : "Stage Prediction"}</div>
                <div className="text-3xl font-black text-emerald-300">{report.stage}</div>
                <div className="flex items-center gap-2 text-gray-300">
                  <span className={`w-2 h-2 rounded-full ${statusDotClass(report.status)}`}></span>
                  {getStatusLabel(report.status, language)}
                </div>
              </div>
              <div className="bg-black/30 border border-white/5 rounded-2xl p-4 space-y-1">
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{language !== "en" ? "置信度" : "Confidence"}</div>
                <div className="text-3xl font-black text-blue-300">{stageConfidence}%</div>
                <div className="text-[11px] text-gray-500">{language !== "en" ? "根据模型推断" : "Model inference"}</div>
              </div>
              <div className="bg-black/30 border border-white/5 rounded-2xl p-4">
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{language !== "en" ? "淋巴结提示" : "Nodal risk"}</div>
                <span className={`px-3 py-1 rounded-full text-[11px] border ${stageBadgeClass(report.stage)}`}>{report.stage}</span>
              </div>
            </div>
            ) : null}

            {activeTemplateRecord ? (
              <div className="space-y-4">
                {activeTemplateRecord.revisions.length > 1 ? (
                  <section className="rounded-2xl border border-white/10 bg-black/20 p-4">
                    <div className="mb-3 text-[10px] uppercase tracking-wider text-gray-400">
                      {language !== "en" ? "版本时间线" : "Version history"}
                    </div>
                    <div className="space-y-2">
                      {[...activeTemplateRecord.revisions].reverse().map((item) => (
                        <Link
                          key={`${item.report_id}-${item.revision}`}
                          href={`/reports/${encodeURIComponent(item.report_id)}?revision=${item.revision}`}
                          className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-[10px] transition-colors ${
                            item.revision === report.revision
                              ? 'border-cyan-300/30 bg-cyan-300/10 text-cyan-100'
                              : 'border-white/10 text-gray-400 hover:bg-white/5 hover:text-white'
                          }`}
                        >
                          <span>
                            v{item.revision} / {item.status === 'finalized' ? '已签发' : item.status === 'reviewed' ? '已复核' : '草稿'}
                            {item.signed_by ? ` / ${item.signed_by}` : ''}
                          </span>
                          <span>{item.updated_at.slice(0, 19).replace('T', ' ')}</span>
                          <span className="w-full text-[9px] text-gray-500">
                            {item.changed_fields?.length
                              ? `修改: ${item.changed_fields.join(', ')}`
                              : '无结构化字段变化'}
                          </span>
                        </Link>
                      ))}
                    </div>
                  </section>
                ) : null}
                <div className="overflow-auto rounded-2xl border border-white/10 bg-[#101820] p-3">
                  <TemplateReportPreview
                    patient={patientFromTemplateReport(report, activeTemplateRecord.report)}
                    state={activeTemplateRecord.report}
                    previewId={`template-report-history-${report.id}-v${report.revision || 0}`}
                    zh={language !== 'en'}
                  />
                </div>
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  {structuredSections.map(section => (
                    <div key={section.label} className="space-y-2 rounded-xl border border-white/10 bg-white/5 p-4">
                      <div className="text-[10px] uppercase tracking-wider text-gray-400">{section.label}</div>
                      <p className="text-sm leading-relaxed text-gray-200">{section.value}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-2xl border border-blue-500/30 bg-gradient-to-br from-blue-900/20 to-blue-800/10 p-5">
                  <div className="text-[10px] uppercase tracking-wider text-blue-200">Smart summary</div>
                  <ul className="mt-3 list-inside list-disc space-y-2 text-sm text-white">
                    {smartSummary.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

