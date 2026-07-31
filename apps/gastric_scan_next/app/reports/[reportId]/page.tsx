"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Header } from "@/components/Header";
import { ChevronLeft, Download } from "lucide-react";
import { useSettings } from "@/contexts/SettingsContext";
import {
  reportData,
  getStatusLabel,
  stageBadgeClass,
  statusDotClass
} from "@/app/reports/report-data";

interface ReportDetailPageProps {
  params: {
    reportId: string;
  };
}

export default function ReportDetailPage({ params }: ReportDetailPageProps) {
  const { t, language } = useSettings();
  const report = reportData.find(item => item.id === params.reportId);
  if (!report) {
    notFound();
  }

  const stageConfidence = report.stage.startsWith("T4")
    ? 92
    : report.stage.startsWith("T3")
      ? 78
      : 64;

  const structuredSections = [
    {
      label: language === "zh" ? "影像发现" : "Imaging Findings",
      value: language === "zh"
        ? "胃体后壁肿块伴不规则内壁，可见低密度灶，淋巴结信号多发。"
        : "Irregular posterior body mass with hypoechoic core and multiple nodal signals."
    },
    {
      label: language === "zh" ? "淋巴结" : "Lymph nodes",
      value: language === "zh"
        ? "提示区域淋巴结肿大，伴环形增强，N2-N3风险。"
        : "Regional node enlargement with ring enhancement, raising N2-N3 suspicion."
    },
    {
      label: language === "zh" ? "建议方案" : "Recommended action",
      value: language === "zh"
        ? "推荐增强CT+腹腔镜探查，若确认为T4则需优先新辅助方案。"
        : "Recommend contrast CT and laparoscopy; consider neoadjuvant protocol if T4 confirmed."
    }
  ];

  const smartSummary = [
    language === "zh"
      ? "模型融合 Ki-67/CPS/PD-1 信号推断为 T4a，淋巴结转移风险高。"
      : "Model fusion of Ki-67/CPS/PD-1 suggests T4a with high nodal risk.",
    language === "zh"
      ? "病理提示分化中等腺癌，CEA/CA19-9 均轻度升高。"
      : "Pathology indicates moderately differentiated adenocarcinoma with mild CEA/CA19-9 elevation.",
    language === "zh"
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
            {language === "zh" ? "返回报告列表" : "Back to reports"}
          </Link>

          <div className="bg-linear-to-br from-neutral-900/90 to-neutral-800/50 border border-white/10 rounded-2xl p-6 shadow-2xl space-y-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{language === "zh" ? "报告编号" : "Report ID"}</div>
                <div className="text-3xl font-bold font-mono">{report.id}</div>
                <div className="text-[11px] text-gray-500 mt-1">
                  {report.patient} • {report.date}
                </div>
              </div>
              <button className="px-3 py-1.5 rounded-full border border-white/10 text-[10px] uppercase tracking-widest text-gray-300 flex items-center gap-2 hover:bg-white/10 transition-colors">
                <Download size={16} />
                {language === "zh" ? "下载PDF" : "Download PDF"}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-black/30 border border-white/5 rounded-2xl p-4 space-y-1">
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{language === "zh" ? "分期预测" : "Stage Prediction"}</div>
                <div className="text-3xl font-black text-emerald-300">{report.stage}</div>
                <div className="flex items-center gap-2 text-gray-300">
                  <span className={`w-2 h-2 rounded-full ${statusDotClass(report.status)}`}></span>
                  {getStatusLabel(report.status, language)}
                </div>
              </div>
              <div className="bg-black/30 border border-white/5 rounded-2xl p-4 space-y-1">
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{language === "zh" ? "置信度" : "Confidence"}</div>
                <div className="text-3xl font-black text-blue-300">{stageConfidence}%</div>
                <div className="text-[11px] text-gray-500">{language === "zh" ? "根据模型推断" : "Model inference"}</div>
              </div>
              <div className="bg-black/30 border border-white/5 rounded-2xl p-4">
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">{language === "zh" ? "淋巴结提示" : "Nodal risk"}</div>
                <span className={`px-3 py-1 rounded-full text-[11px] border ${stageBadgeClass(report.stage)}`}>{report.stage}</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {structuredSections.map(section => (
                <div key={section.label} className="bg-white/5 rounded-xl border border-white/10 p-4 space-y-2">
                  <div className="text-[10px] uppercase tracking-wider text-gray-400">{section.label}</div>
                  <p className="text-sm text-gray-200 leading-relaxed">{section.value}</p>
                </div>
              ))}
            </div>

            <div className="bg-gradient-to-br from-blue-900/20 to-blue-800/10 border border-blue-500/30 rounded-2xl p-5">
              <div className="text-[10px] uppercase tracking-wider text-blue-200">Smart summary</div>
              <ul className="list-disc list-inside text-sm text-white space-y-2 mt-3">
                {smartSummary.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

