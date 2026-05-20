"use client";

import React, { useMemo, useState, useEffect } from 'react';
import { useSettings } from '@/contexts/SettingsContext';
import { ConceptState, Patient } from '@/types';
import { calculateDiagnosis } from '@/lib/diagnosis';
import { dedupePatientsForStatistics } from '@/lib/cohort-stats';
import { getConceptStateFromPatient } from '@/lib/patient-utils';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { BarChart2, TrendingUp, Users, Activity, Loader2 } from 'lucide-react';

interface StatisticsPanelProps {
  patients: Patient[];
  conceptStates: Map<string, ConceptState>; // patientId -> conceptState
}

interface StatisticsData {
  totalPatients: number;
  totalFrames: number;
  withClinicalCount: number;
  tStageDistribution: Record<string, number>;
  nStageDistribution: Record<string, number>;
  avgConfidence: number;
  avgTScore: number;
  avgNScore: number;
  highRiskCount: number;
  hasMetastasisCount: number;
  t4Count: number;
}

const COLORS = {
  t4: '#ef4444',
  t3: '#f59e0b',
  t2: '#10b981',
  n3: '#ef4444',
  n2: '#f97316',
  n1: '#eab308',
  n0: '#10b981',
};

// 使用 Web Worker 或优化计算（分批处理）
function calculateStatisticsBatch(
  patients: Patient[],
  conceptStates: Map<string, ConceptState>,
  batchSize: number = 100
): StatisticsData {
  const uniquePatients = dedupePatientsForStatistics(patients);
  const tStageCounts: Record<string, number> = {};
  const nStageCounts: Record<string, number> = {};
  let totalConfidence = 0;
  let totalTScore = 0;
  let totalNScore = 0;
  let highRiskCount = 0;
  let hasMetastasisCount = 0;
  let t4Count = 0;
  let withClinicalCount = 0;
  let processedCount = 0;

  for (let i = 0; i < uniquePatients.length; i += batchSize) {
    const batch = uniquePatients.slice(i, i + batchSize);

    batch.forEach((patient) => {
      let conceptState = conceptStates.get(patient.id);
      if (!conceptState) {
        conceptState = getConceptStateFromPatient(patient);
      }

      if (patient.clinical) {
        withClinicalCount += 1;
      }

      const diagnosis = calculateDiagnosis(conceptState, patient);
      processedCount++;

      tStageCounts[diagnosis.tStage] = (tStageCounts[diagnosis.tStage] || 0) + 1;
      nStageCounts[diagnosis.nStage] = (nStageCounts[diagnosis.nStage] || 0) + 1;

      totalConfidence += diagnosis.confidence.overall;
      totalTScore += diagnosis.scores.t;
      totalNScore += diagnosis.scores.n;

      if (diagnosis.flags.highRisk) highRiskCount++;
      if (diagnosis.flags.hasMetastasis) hasMetastasisCount++;
      if (diagnosis.flags.isT4) t4Count++;
    });
  }

  const validCount = processedCount || 1;

  return {
    totalPatients: uniquePatients.length,
    totalFrames: patients.length,
    withClinicalCount,
    tStageDistribution: tStageCounts,
    nStageDistribution: nStageCounts,
    avgConfidence: totalConfidence / validCount,
    avgTScore: totalTScore / validCount,
    avgNScore: totalNScore / validCount,
    highRiskCount,
    hasMetastasisCount,
    t4Count,
  };
}

export const StatisticsPanel: React.FC<StatisticsPanelProps> = ({ patients, conceptStates }) => {
  const { language } = useSettings();
  const [isCalculating, setIsCalculating] = useState(true);
  const [statistics, setStatistics] = useState<StatisticsData>({
    totalPatients: 0,
    totalFrames: 0,
    withClinicalCount: 0,
    tStageDistribution: {},
    nStageDistribution: {},
    avgConfidence: 0,
    avgTScore: 0,
    avgNScore: 0,
    highRiskCount: 0,
    hasMetastasisCount: 0,
    t4Count: 0,
  });

  // 使用 useEffect 异步计算，避免阻塞 UI
  useEffect(() => {
    if (patients.length === 0) {
      setStatistics({
        totalPatients: 0,
        totalFrames: 0,
        withClinicalCount: 0,
        tStageDistribution: {},
        nStageDistribution: {},
        avgConfidence: 0,
        avgTScore: 0,
        avgNScore: 0,
        highRiskCount: 0,
        hasMetastasisCount: 0,
        t4Count: 0,
      });
      setIsCalculating(false);
      return;
    }

    setIsCalculating(true);
    
    // 使用 requestIdleCallback 或 setTimeout 分批计算
    const calculateAsync = () => {
      const result = calculateStatisticsBatch(patients, conceptStates, 50);
      setStatistics(result);
      setIsCalculating(false);
    };

    // 如果数据量大，使用 setTimeout 分批处理
    if (patients.length > 500) {
      setTimeout(calculateAsync, 0);
    } else {
      calculateAsync();
    }
  }, [patients, conceptStates]);

  // 准备图表数据
  const tStageChartData = useMemo(() => {
    return Object.entries(statistics.tStageDistribution)
      .map(([stage, count]) => ({
        stage,
        count,
        percentage: statistics.totalPatients > 0 ? ((count / statistics.totalPatients) * 100).toFixed(1) : '0.0',
      }))
      .sort((a, b) => {
        // 排序：T1/T2, T3, T4a, T4b
        const order: Record<string, number> = { 'T1/T2': 1, 'T3': 2, 'T4a': 3, 'T4b': 4 };
        return (order[a.stage] || 99) - (order[b.stage] || 99);
      });
  }, [statistics]);

  const nStageChartData = useMemo(() => {
    return Object.entries(statistics.nStageDistribution)
      .map(([stage, count]) => ({
        stage,
        count,
        percentage: statistics.totalPatients > 0 ? ((count / statistics.totalPatients) * 100).toFixed(1) : '0.0',
      }))
      .sort((a, b) => {
        // 排序：N0, N1, N2, N3
        const order: Record<string, number> = { 'N0': 1, 'N1': 2, 'N2': 3, 'N3': 4 };
        return (order[a.stage] || 99) - (order[b.stage] || 99);
      });
  }, [statistics]);

  const pieData = useMemo(() => {
    const lowRiskCount = statistics.totalPatients - statistics.highRiskCount;
    const highRiskPercentage = statistics.totalPatients > 0 
      ? ((statistics.highRiskCount / statistics.totalPatients) * 100).toFixed(1)
      : '0.0';
    const lowRiskPercentage = statistics.totalPatients > 0
      ? ((lowRiskCount / statistics.totalPatients) * 100).toFixed(1)
      : '0.0';
    
    return [
      { 
        name: language === 'zh' ? '高危' : 'High Risk', 
        value: statistics.highRiskCount, 
        percentage: highRiskPercentage,
        color: '#ef4444' 
      },
      { 
        name: language === 'zh' ? '低危' : 'Low Risk', 
        value: lowRiskCount, 
        percentage: lowRiskPercentage,
        color: '#10b981' 
      },
    ];
  }, [statistics, language]);

  if (isCalculating) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500 p-8">
        <Loader2 className="w-8 h-8 animate-spin text-purple-400 mb-4" />
        <span className="text-sm">{language === 'zh' ? '正在计算统计数据...' : 'Calculating statistics...'}</span>
        <span className="text-xs text-gray-600 mt-2">
          {language === 'zh' ? `处理 ${patients.length} 帧 / 去重后病例` : `Processing ${patients.length} frames / deduped cases`}
        </span>
      </div>
    );
  }

  if (statistics.totalPatients === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500 p-8">
        <BarChart2 size={48} className="opacity-40 mb-4" />
        <span className="text-sm">{language === 'zh' ? '暂无统计数据' : 'No statistics available'}</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full bg-[#0b0b0d] overflow-y-auto custom-scrollbar">
      {/* Header */}
      <div className="h-10 shrink-0 border-b border-white/5 flex items-center justify-between px-3 bg-[#0b0b0d]">
        <span className="flex items-center gap-2 text-[11px] font-bold text-gray-300 uppercase tracking-widest">
          <BarChart2 size={12} className="text-purple-500" />
          {language === 'zh' ? '队列统计' : 'Cohort Statistics'}
        </span>
        <span className="text-[9px] font-mono text-gray-500">
          N={statistics.totalPatients}
          {statistics.totalFrames > statistics.totalPatients && (
            <span className="text-gray-600"> · {statistics.totalFrames} {language === 'zh' ? '帧' : 'frames'}</span>
          )}
        </span>
      </div>

      <div className="flex-1 p-4 space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#18181b] p-3 rounded-lg border border-white/5">
            <div className="flex items-center gap-2 mb-2">
              <Activity size={14} className="text-blue-400" />
              <span className="text-[10px] text-gray-500 uppercase">{language === 'zh' ? '平均置信度' : 'Avg Confidence'}</span>
            </div>
            <div className="text-2xl font-bold text-gray-200">{statistics.avgConfidence.toFixed(1)}%</div>
          </div>
          
          <div className="bg-[#18181b] p-3 rounded-lg border border-white/5">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp size={14} className="text-emerald-400" />
              <span className="text-[10px] text-gray-500 uppercase">{language === 'zh' ? '高危病例' : 'High Risk'}</span>
            </div>
            <div className="text-2xl font-bold text-red-400">{statistics.highRiskCount}</div>
            <div className="text-[9px] text-gray-500">
              {((statistics.highRiskCount / statistics.totalPatients) * 100).toFixed(1)}%
            </div>
          </div>

          <div className="bg-[#18181b] p-3 rounded-lg border border-white/5">
            <div className="flex items-center gap-2 mb-2">
              <Users size={14} className="text-red-400" />
              <span className="text-[10px] text-gray-500 uppercase">{language === 'zh' ? 'T4 分期' : 'T4 Stage'}</span>
            </div>
            <div className="text-2xl font-bold text-red-400">{statistics.t4Count}</div>
            <div className="text-[9px] text-gray-500">
              {((statistics.t4Count / statistics.totalPatients) * 100).toFixed(1)}%
            </div>
          </div>

          <div className="bg-[#18181b] p-3 rounded-lg border border-white/5">
            <div className="flex items-center gap-2 mb-2">
              <Activity size={14} className="text-amber-400" />
              <span className="text-[10px] text-gray-500 uppercase">{language === 'zh' ? '淋巴结转移' : 'Metastasis'}</span>
            </div>
            <div className="text-2xl font-bold text-amber-400">{statistics.hasMetastasisCount}</div>
            <div className="text-[9px] text-gray-500">
              {((statistics.hasMetastasisCount / statistics.totalPatients) * 100).toFixed(1)}%
            </div>
          </div>
        </div>

        {/* T-Stage Distribution Chart */}
        <div className="bg-[#18181b] p-4 rounded-lg border border-white/5">
          <div className="text-[11px] font-bold text-gray-300 uppercase tracking-wider mb-4">
            {language === 'zh' ? 'T 分期分布' : 'T-Stage Distribution'}
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={tStageChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis 
                dataKey="stage" 
                stroke="#888"
                tick={{ fill: '#888', fontSize: 10 }}
              />
              <YAxis 
                stroke="#888"
                tick={{ fill: '#888', fontSize: 10 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0b0b0d',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '4px',
                }}
                labelStyle={{ color: '#e4e4e7' }}
                formatter={(value: any, name: string, props: any) => [
                  `${value} (${props.payload.percentage}%)`,
                  language === 'zh' ? '病例数' : 'Cases'
                ]}
              />
              <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]}>
                {tStageChartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[entry.stage as keyof typeof COLORS] || '#3b82f6'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* N-Stage Distribution Chart */}
        <div className="bg-[#18181b] p-4 rounded-lg border border-white/5">
          <div className="text-[11px] font-bold text-gray-300 uppercase tracking-wider mb-4">
            {language === 'zh' ? 'N 分期分布' : 'N-Stage Distribution'}
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={nStageChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis 
                dataKey="stage" 
                stroke="#888"
                tick={{ fill: '#888', fontSize: 10 }}
              />
              <YAxis 
                stroke="#888"
                tick={{ fill: '#888', fontSize: 10 }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0b0b0d',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '4px',
                }}
                labelStyle={{ color: '#e4e4e7' }}
                formatter={(value: any, name: string, props: any) => [
                  `${value} (${props.payload.percentage}%)`,
                  language === 'zh' ? '病例数' : 'Cases'
                ]}
              />
              <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]}>
                {nStageChartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[entry.stage as keyof typeof COLORS] || '#3b82f6'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Risk Distribution Pie Chart */}
        <div className="bg-[#18181b] p-4 rounded-lg border border-white/5">
          <div className="text-[11px] font-bold text-gray-300 uppercase tracking-wider mb-4">
            {language === 'zh' ? '风险分布' : 'Risk Distribution'}
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={(entry: any) => {
                  const percentage = entry.percentage || ((entry.value / statistics.totalPatients) * 100).toFixed(1);
                  return `${entry.name}: ${percentage}%`;
                }}
                outerRadius={70}
                fill="#8884d8"
                dataKey="value"
              >
                {pieData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: '#0b0b0d',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '4px',
                }}
                labelStyle={{ color: '#e4e4e7' }}
                formatter={(value: any, name: string, props: any) => [
                  `${value} (${props.payload.percentage}%)`,
                  language === 'zh' ? '病例数' : 'Cases'
                ]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Detailed Statistics Table */}
        <div className="bg-[#18181b] p-4 rounded-lg border border-white/5">
          <div className="text-[11px] font-bold text-gray-300 uppercase tracking-wider mb-4">
            {language === 'zh' ? '详细统计' : 'Detailed Statistics'}
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between text-gray-400">
              <span>{language === 'zh' ? '平均 T 评分' : 'Avg T-Score'} (0-100):</span>
              <span className="text-gray-200 font-mono">{statistics.avgTScore.toFixed(1)}</span>
            </div>
            <div className="flex justify-between text-gray-400">
              <span>{language === 'zh' ? '平均 N 评分' : 'Avg N-Score'} (0-100):</span>
              <span className="text-gray-200 font-mono">{statistics.avgNScore.toFixed(1)}</span>
            </div>
            <div className="flex justify-between text-gray-400">
              <span>{language === 'zh' ? '总病例数（去重）' : 'Unique cases'}:</span>
              <span className="text-gray-200 font-mono">{statistics.totalPatients}</span>
            </div>
            <div className="flex justify-between text-gray-400">
              <span>{language === 'zh' ? '总图像帧数' : 'Total frames'}:</span>
              <span className="text-gray-200 font-mono">{statistics.totalFrames}</span>
            </div>
            <div className="flex justify-between text-gray-400">
              <span>{language === 'zh' ? '有临床资料' : 'With clinical data'}:</span>
              <span className="text-gray-200 font-mono">
                {statistics.withClinicalCount}
                {statistics.totalPatients > 0 && (
                  <span className="text-gray-500"> ({((statistics.withClinicalCount / statistics.totalPatients) * 100).toFixed(1)}%)</span>
                )}
              </span>
            </div>
            <div className="mt-4 pt-2 border-t border-white/5 text-[10px] text-gray-500">
               *{language === 'zh' ? '注：统计按 patient_id + 治疗组 去重，每例只计一次；T/N 评分为 CBM 连续风险值。' : 'Note: Stats dedupe by patient_id + treatment group (one case counted once). T/N scores are CBM risk values.'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
