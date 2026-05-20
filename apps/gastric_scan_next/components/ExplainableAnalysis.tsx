"use client";

import React, { useState, useCallback, useRef } from 'react';
import { Patient } from '@/types';
import { useSettings } from '@/contexts/SettingsContext';
import { 
  Activity, 
  AlertTriangle, 
  CheckCircle, 
  Loader2, 
  X,
  TrendingUp,
  Shield,
  Target,
  Download,
  Camera,
  FileText,
  Maximize2,
  BarChart3,
  Layers,
  Circle
} from 'lucide-react';
import html2canvas from 'html2canvas';

interface ExplainableAnalysisProps {
  patient: Patient | null;
  isOpen: boolean;
  onClose: () => void;
}

interface MorphologyData {
  diameter_mm?: number;
  area_mm2?: number;
  circularity?: number;
  irregularity?: number;
}

interface AnalysisResult {
  success: boolean;
  patient_id: string;
  predicted_stage?: string;
  confidence?: string;
  sii?: number;
  bci?: number;
  cri?: number;
  composite_score?: number;
  morphology?: MorphologyData;
  explanation?: string;
  total_danger_regions?: number;
  visualization_base64?: string;
  error?: string;
}

// API 配置 — 走 Next.js 同源代理，内部调用 V4 边界分析脚本
const API_BASE_URL = '/api/explainable/analyze';

export const ExplainableAnalysis: React.FC<ExplainableAnalysisProps> = ({
  patient,
  isOpen,
  onClose
}) => {
  const { language, dataset, cohortYear, treatmentType } = useSettings();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  const runAnalysis = useCallback(async () => {
    if (!patient) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          patient,
          dataset,
          cohortYear,
          treatmentType,
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: AnalysisResult = await response.json();
      
      if (data.success) {
        setResult(data);
      } else {
        setError(data.error || 'Analysis failed');
      }
    } catch (err) {
      console.error('Analysis error:', err);
      setError(err instanceof Error ? err.message : 'Failed to connect to analysis server');
    } finally {
      setLoading(false);
    }
  }, [patient, dataset, cohortYear, treatmentType]);

  // 导出为图片（论文用）
  const exportAsImage = useCallback(async () => {
    if (!reportRef.current) return;
    
    try {
      const canvas = await html2canvas(reportRef.current, {
        backgroundColor: '#171717', // 导出时使用实色背景
        scale: 2, // 高分辨率
        useCORS: true,
      });
      
      const link = document.createElement('a');
      link.download = `explainable_analysis_${patient?.id || 'unknown'}_${Date.now()}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (err) {
      console.error('Export failed:', err);
    }
  }, [patient]);

  if (!isOpen) return null;

  const getStageColor = (stage?: string) => {
    if (!stage) return 'text-gray-400';
    if (stage.includes('T4')) return 'text-red-400';
    if (stage.includes('T3')) return 'text-amber-400';
    if (stage.includes('T2')) return 'text-yellow-400';
    return 'text-emerald-400';
  };

  const getStageBgColor = (stage?: string) => {
    if (!stage) return 'from-gray-900/50 to-gray-800/30';
    if (stage.includes('T4')) return 'from-red-900/40 to-red-800/20';
    if (stage.includes('T3')) return 'from-amber-900/40 to-amber-800/20';
    if (stage.includes('T2')) return 'from-yellow-900/40 to-yellow-800/20';
    return 'from-emerald-900/40 to-emerald-800/20';
  };

  const getMetricStatus = (value: number, thresholds: [number, number]): 'good' | 'warning' | 'danger' => {
    if (value >= thresholds[1]) return 'good';
    if (value >= thresholds[0]) return 'warning';
    return 'danger';
  };

  const renderMetricGauge = (value: number, label: string, sublabel: string, thresholds: [number, number], icon: React.ReactNode) => {
    const status = getMetricStatus(value, thresholds);
    const colors = {
      good: { ring: 'stroke-emerald-500', text: 'text-emerald-400', bg: 'bg-emerald-500/10' },
      warning: { ring: 'stroke-amber-500', text: 'text-amber-400', bg: 'bg-amber-500/10' },
      danger: { ring: 'stroke-red-500', text: 'text-red-400', bg: 'bg-red-500/10' }
    };
    const c = colors[status];
    const percentage = Math.min(value * 100, 100);
    const circumference = 2 * Math.PI * 36;
    const offset = circumference - (percentage / 100) * circumference;

    return (
      <div className="flex flex-col items-center p-4 bg-neutral-800/30 rounded-xl border border-white/10">
        <div className="relative w-24 h-24">
          <svg className="w-24 h-24 transform -rotate-90">
            <circle
              cx="48"
              cy="48"
              r="36"
              stroke="currentColor"
              strokeWidth="6"
              fill="none"
              className="text-white/5"
            />
            <circle
              cx="48"
              cy="48"
              r="36"
              strokeWidth="6"
              fill="none"
              strokeLinecap="round"
              className={`${c.ring} transition-all duration-1000`}
              style={{
                strokeDasharray: circumference,
                strokeDashoffset: offset
              }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-xl font-bold font-mono ${c.text}`}>
              {value.toFixed(2)}
            </span>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-1.5">
          <span className={c.text}>{icon}</span>
          <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">{label}</span>
        </div>
        <span className="text-[10px] text-gray-500 mt-0.5">{sublabel}</span>
      </div>
    );
  };

  const renderLegend = () => (
    <div className="flex items-center gap-4 text-[10px] text-gray-400">
      <div className="flex items-center gap-1.5">
        <Circle size={8} className="fill-emerald-500 text-emerald-500" />
        <span>{language === 'zh' ? '边界清晰' : 'Clear Boundary'}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Circle size={8} className="fill-amber-500 text-amber-500" />
        <span>{language === 'zh' ? '边界模糊' : 'Blurred Boundary'}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Circle size={8} className="fill-red-500 text-red-500" />
        <span>{language === 'zh' ? '可疑突破' : 'Suspected Breach'}</span>
      </div>
    </div>
  );

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm ${isFullscreen ? 'p-0' : 'p-4'}`}>
      <div className={`bg-neutral-900/70 backdrop-blur-xl border border-white/20 rounded-2xl overflow-hidden flex flex-col shadow-2xl shadow-black/50 transition-all duration-300 ${
        isFullscreen ? 'w-full h-full rounded-none' : 'w-[95vw] max-w-7xl max-h-[95vh]'
      }`}>
        {/* Header - 科研风格 */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-white/15 bg-neutral-800/50">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-600 flex items-center justify-center shadow-lg">
                <Layers className="w-5 h-5 text-white" />
              </div>
              <div>
                <h2 className="text-sm font-bold text-white tracking-wide">
                  {language === 'zh' ? '可解释性边界分析' : 'Explainable Boundary Analysis'}
                </h2>
                <p className="text-[10px] text-gray-500 font-mono">
                  Normal-Weighted Gradient + Bilinear Correlation + Curvature-Risk
                </p>
              </div>
            </div>
            {patient && (
              <div className="hidden md:flex items-center gap-2 px-3 py-1 bg-white/5 rounded-lg border border-white/5">
                <span className="text-[10px] text-gray-500">Patient ID:</span>
                <span className="text-xs font-mono text-blue-400">{patient.id_short || patient.id}</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {result && (
              <>
                <button
                  onClick={exportAsImage}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded-lg transition-colors text-xs font-medium border border-blue-500/30"
                  title={language === 'zh' ? '导出为图片 (论文用)' : 'Export as Image (for paper)'}
                >
                  <Camera size={14} />
                  <span className="hidden sm:inline">{language === 'zh' ? '导出图片' : 'Export'}</span>
                </button>
              </>
            )}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400"
            >
              <Maximize2 size={16} />
            </button>
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {!result && !loading && !error && (
            <div className="flex flex-col items-center justify-center h-full min-h-[500px] gap-8 p-8">
              <div className="relative">
                <div className="absolute inset-0 bg-blue-500/20 rounded-full blur-3xl"></div>
                <div className="relative p-8 bg-gradient-to-br from-blue-600/20 to-cyan-600/20 rounded-full border border-blue-500/30">
                  <BarChart3 className="w-16 h-16 text-blue-400" />
                </div>
              </div>
              <div className="text-center max-w-lg">
                <h3 className="text-2xl font-bold text-white mb-3">
                  {language === 'zh' ? '边界完整性分析' : 'Boundary Integrity Analysis'}
                </h3>
                <p className="text-gray-400 leading-relaxed">
                  {language === 'zh' 
                    ? '基于法向梯度的边界验证算法，通过分析肿瘤边界的梯度强度、内外相关性和曲率特征，评估浆膜层完整性，辅助T分期判断。'
                    : 'Normal-gradient based boundary verification algorithm analyzes gradient strength, inner-outer correlation, and curvature features to assess serosal integrity and assist T-staging.'}
                </p>
              </div>
              <button
                onClick={runAnalysis}
                disabled={!patient}
                className="group relative px-10 py-4 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white font-bold rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-3 shadow-lg shadow-blue-500/25"
              >
                <Activity className="w-5 h-5" />
                {language === 'zh' ? '开始分析' : 'Run Analysis'}
                <div className="absolute inset-0 rounded-xl bg-white/20 opacity-0 group-hover:opacity-100 transition-opacity"></div>
              </button>
            </div>
          )}

          {loading && (
            <div className="flex flex-col items-center justify-center h-full min-h-[500px] gap-6">
              <div className="relative">
                <div className="absolute inset-0 bg-blue-500/20 rounded-full blur-2xl animate-pulse"></div>
                <Loader2 className="relative w-16 h-16 text-blue-400 animate-spin" />
              </div>
              <div className="text-center">
                <p className="text-lg text-white font-medium mb-2">
                  {language === 'zh' ? '正在分析边界特征...' : 'Analyzing boundary features...'}
                </p>
                <p className="text-sm text-gray-500">
                  {language === 'zh' ? '计算法向梯度、相关性和曲率指标' : 'Computing gradient, correlation, and curvature metrics'}
                </p>
              </div>
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center justify-center h-full min-h-[500px] gap-6 p-8">
              <div className="p-6 bg-red-500/10 rounded-full border border-red-500/30">
                <AlertTriangle className="w-12 h-12 text-red-400" />
              </div>
              <div className="text-center">
                <h3 className="text-xl font-bold text-red-400 mb-2">
                  {language === 'zh' ? '分析失败' : 'Analysis Failed'}
                </h3>
                <p className="text-gray-400 max-w-md mb-6">{error}</p>
                <button
                  onClick={runAnalysis}
                  className="px-6 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-colors font-medium"
                >
                  {language === 'zh' ? '重试' : 'Retry'}
                </button>
              </div>
            </div>
          )}

          {result && result.success && (
            <div ref={reportRef} className="p-6 space-y-6">
              {/* 顶部摘要卡片 */}
              <div className={`bg-gradient-to-br ${getStageBgColor(result.predicted_stage)} rounded-2xl border border-white/10 p-6 relative overflow-hidden`}>
                <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"></div>
                <div className="relative flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-4">
                      <div className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                        result.confidence === 'High' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                        result.confidence === 'Medium' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                        'bg-gray-500/20 text-gray-400 border border-gray-500/30'
                      }`}>
                        {result.confidence} Confidence
                      </div>
                      {result.total_danger_regions && result.total_danger_regions > 0 && (
                        <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/20 text-red-400 border border-red-500/30 text-xs font-bold">
                          <AlertTriangle size={12} />
                          {result.total_danger_regions} {language === 'zh' ? '危险区域' : 'Danger Zones'}
                        </div>
                      )}
                    </div>
                    <div className="flex items-baseline gap-3 mb-4">
                      <span className={`text-6xl font-black tracking-tight ${getStageColor(result.predicted_stage)}`}>
                        {result.predicted_stage}
                      </span>
                      <span className="text-xl text-gray-400 font-medium">
                        {language === 'zh' ? '预测分期' : 'Predicted Stage'}
                      </span>
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed max-w-2xl">
                      {result.explanation}
                    </p>
                  </div>
                  
                  {/* 综合评分仪表盘 */}
                  <div className="hidden lg:flex flex-col items-center ml-8">
                    <div className="relative w-32 h-32">
                      <svg className="w-32 h-32 transform -rotate-90">
                        <circle cx="64" cy="64" r="54" stroke="currentColor" strokeWidth="8" fill="none" className="text-white/5" />
                        <circle
                          cx="64" cy="64" r="54"
                          strokeWidth="8" fill="none" strokeLinecap="round"
                          className={`${
                            (result.composite_score || 0) >= 0.5 ? 'stroke-emerald-500' :
                            (result.composite_score || 0) >= 0.3 ? 'stroke-amber-500' : 'stroke-red-500'
                          } transition-all duration-1000`}
                          style={{
                            strokeDasharray: 2 * Math.PI * 54,
                            strokeDashoffset: 2 * Math.PI * 54 * (1 - (result.composite_score || 0))
                          }}
                        />
                      </svg>
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className={`text-3xl font-black font-mono ${
                          (result.composite_score || 0) >= 0.5 ? 'text-emerald-400' :
                          (result.composite_score || 0) >= 0.3 ? 'text-amber-400' : 'text-red-400'
                        }`}>
                          {((result.composite_score || 0) * 100).toFixed(0)}
                        </span>
                        <span className="text-[10px] text-gray-500 uppercase tracking-wider">Score</span>
                      </div>
                    </div>
                    <span className="text-xs text-gray-400 mt-2">
                      {language === 'zh' ? '边界完整性评分' : 'Boundary Integrity'}
                    </span>
                  </div>
                </div>
              </div>

              {/* 主要内容区 */}
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                {/* 左侧：可视化图像 */}
                <div className="xl:col-span-2 bg-neutral-800/30 rounded-2xl border border-white/5 overflow-hidden">
                  <div className="px-5 py-3 border-b border-white/5 flex items-center justify-between bg-[#111]">
                    <div className="flex items-center gap-2">
                      <Target className="w-4 h-4 text-blue-400" />
                      <span className="text-sm font-bold text-gray-200">
                        {language === 'zh' ? '边界风险热力图' : 'Boundary Risk Heatmap'}
                      </span>
                    </div>
                    {renderLegend()}
                  </div>
                  <div className="p-4">
                    {result.visualization_base64 && (
                      <img 
                        src={`data:image/png;base64,${result.visualization_base64}`}
                        alt="Analysis Visualization"
                        className="w-full h-auto rounded-xl"
                      />
                    )}
                  </div>
                </div>

                {/* 右侧：指标面板 */}
                <div className="space-y-4">
                  {/* 三大指标 */}
                  <div className="bg-neutral-800/30 rounded-2xl border border-white/5 p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <BarChart3 className="w-4 h-4 text-blue-400" />
                      <span className="text-sm font-bold text-gray-200 uppercase tracking-wider">
                        {language === 'zh' ? '核心指标' : 'Core Metrics'}
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                      {renderMetricGauge(
                        result.sii || 0, 
                        'SII', 
                        language === 'zh' ? '浆膜完整性' : 'Serosal Integrity',
                        [0.25, 0.4],
                        <Shield size={12} />
                      )}
                      {renderMetricGauge(
                        result.bci || 0, 
                        'BCI', 
                        language === 'zh' ? '边界相关性' : 'Boundary Corr.',
                        [0.5, 0.7],
                        <Activity size={12} />
                      )}
                      {renderMetricGauge(
                        result.cri || 0, 
                        'CRI', 
                        language === 'zh' ? '曲率风险' : 'Curvature Risk',
                        [0.7, 0.85],
                        <TrendingUp size={12} />
                      )}
                    </div>
                  </div>

                  {/* 形态学特征 */}
                  {result.morphology && (
                    <div className="bg-neutral-800/30 rounded-2xl border border-white/5 p-5">
                      <div className="flex items-center gap-2 mb-4">
                        <Layers className="w-4 h-4 text-purple-400" />
                        <span className="text-sm font-bold text-gray-200 uppercase tracking-wider">
                          {language === 'zh' ? '形态学特征' : 'Morphology'}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="p-3 bg-white/5 rounded-xl">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
                            {language === 'zh' ? '等效直径' : 'Diameter'}
                          </div>
                          <div className="text-lg font-bold text-white font-mono">
                            {(result.morphology.diameter_mm || 0).toFixed(1)} <span className="text-xs text-gray-500">mm</span>
                          </div>
                        </div>
                        <div className="p-3 bg-white/5 rounded-xl">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
                            {language === 'zh' ? '面积' : 'Area'}
                          </div>
                          <div className="text-lg font-bold text-white font-mono">
                            {(result.morphology.area_mm2 || 0).toFixed(1)} <span className="text-xs text-gray-500">mm²</span>
                          </div>
                        </div>
                        <div className="p-3 bg-white/5 rounded-xl">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
                            {language === 'zh' ? '圆度' : 'Circularity'}
                          </div>
                          <div className="text-lg font-bold text-white font-mono">
                            {(result.morphology.circularity || 0).toFixed(2)}
                          </div>
                        </div>
                        <div className="p-3 bg-white/5 rounded-xl">
                          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
                            {language === 'zh' ? '不规则度' : 'Irregularity'}
                          </div>
                          <div className="text-lg font-bold text-white font-mono">
                            {(result.morphology.irregularity || 0).toFixed(2)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 方法说明 */}
                  <div className="bg-neutral-800/30 rounded-2xl border border-white/5 p-5">
                    <div className="flex items-center gap-2 mb-3">
                      <FileText className="w-4 h-4 text-gray-400" />
                      <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">
                        {language === 'zh' ? '方法说明' : 'Methods'}
                      </span>
                    </div>
                    <div className="space-y-2 text-[11px] text-gray-500 leading-relaxed">
                      <p>
                        <span className="text-blue-400 font-medium">SII</span>: {language === 'zh' 
                          ? '法向梯度采样，检测边界最弱环节的梯度强度' 
                          : 'Normal gradient sampling, detecting weakest boundary gradient'}
                      </p>
                      <p>
                        <span className="text-purple-400 font-medium">BCI</span>: {language === 'zh' 
                          ? '内外轨相关性分析，高相关性提示边界突破' 
                          : 'Inner-outer track correlation, high correlation suggests breach'}
                      </p>
                      <p>
                        <span className="text-orange-400 font-medium">CRI</span>: {language === 'zh' 
                          ? '曲率-梯度联合检测，识别尖锐突起点' 
                          : 'Curvature-gradient joint detection, identifying sharp protrusions'}
                      </p>
                    </div>
                  </div>

                  {/* 重新分析 */}
                  <button
                    onClick={runAnalysis}
                    className="w-full px-4 py-3 bg-white/5 hover:bg-white/10 text-gray-300 rounded-xl transition-colors flex items-center justify-center gap-2 border border-white/5"
                  >
                    <Activity className="w-4 h-4" />
                    {language === 'zh' ? '重新分析' : 'Re-analyze'}
                  </button>
                </div>
              </div>

              {/* 底部：论文引用格式 */}
              <div className="bg-neutral-800/30 rounded-xl border border-white/5 p-4">
                <div className="flex items-center gap-2 text-[10px] text-gray-500">
                  <FileText size={12} />
                  <span className="uppercase tracking-wider font-bold">{language === 'zh' ? '引用格式' : 'Citation'}</span>
                </div>
                <p className="text-[11px] text-gray-400 mt-2 font-mono leading-relaxed">
                  Explainable T-staging analysis using normal-weighted gradient (SII: {(result.sii || 0).toFixed(3)}), 
                  bilinear boundary correlation (BCI: {(result.bci || 0).toFixed(3)}), 
                  and curvature-risk index (CRI: {(result.cri || 0).toFixed(3)}). 
                  Composite score: {(result.composite_score || 0).toFixed(3)}. 
                  Predicted stage: {result.predicted_stage} ({result.confidence} confidence).
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
