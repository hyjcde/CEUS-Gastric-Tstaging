"use client";

import React, { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Header } from '@/components/Header';
import { FileText, Download, Search, Filter } from 'lucide-react';
import { useSettings } from '@/contexts/SettingsContext';
import {
  reportData,
  statusFilters,
  statusCounts,
  stageBadgeClass,
  statusDotClass,
  getStatusLabel,
  StatusFilter
} from '@/app/reports/report-data';

export default function ReportsPage() {
  const { t, language } = useSettings();
  const router = useRouter();
  const [searchTerm, setSearchTerm] = useState('');
  const [activeStatusFilter, setActiveStatusFilter] = useState<StatusFilter>('All');

  const summaryCards = useMemo(() => ([
    { key: 'total', label: language === 'zh' ? '总报告数' : 'Total Reports', value: statusCounts.All, gradient: 'from-blue-900/30 to-blue-800/10' },
    { key: 'Finalized', label: language === 'zh' ? '已完成' : 'Finalized', value: statusCounts.Finalized, gradient: 'from-emerald-900/30 to-emerald-800/10' },
    { key: 'Reviewed', label: language === 'zh' ? '待审核' : 'Reviewed', value: statusCounts.Reviewed, gradient: 'from-amber-900/30 to-amber-800/10' },
    { key: 'Draft', label: language === 'zh' ? '草稿' : 'Draft', value: statusCounts.Draft, gradient: 'from-gray-900/30 to-gray-800/10' }
  ]), [language]);

  const filteredReports = useMemo(() => {
    const normalized = searchTerm.trim().toLowerCase();
    return reportData.filter(report => {
      const matchesStatus = activeStatusFilter === 'All' || report.status === activeStatusFilter;
      if (!matchesStatus) return false;
      if (!normalized) return true;
      return report.id.toLowerCase().includes(normalized) ||
        report.patient.toLowerCase().includes(normalized);
    });
  }, [searchTerm, activeStatusFilter]);

  const handleRowNavigation = (reportId: string) => {
    router.push(`/reports/${reportId}`);
  };

  return (
    <main className="flex h-screen w-screen flex-col bg-[#000000] text-gray-200 overflow-hidden">
      <div className="h-16 shrink-0 border-b border-white/10 z-50">
        <Header />
      </div>

      <div className="flex-1 overflow-hidden flex flex-col p-8">
        <div className="max-w-6xl mx-auto w-full h-full flex flex-col">

          {/* Header Section */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-4">
              <h1 className="text-3xl font-bold text-white flex items-center gap-3">
                <div className="p-2 bg-blue-500/20 rounded-lg border border-blue-500/30">
                  <FileText className="text-blue-400" size={24} />
                </div>
                {t.userMenu.reports}
              </h1>
              <div className="flex gap-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
                  <input
                    type="text"
                    placeholder={language === 'zh' ? '搜索报告...' : 'Search reports...'}
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                    className="bg-neutral-900/50 border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:border-blue-500/50 focus:bg-neutral-900 transition-all w-64"
                  />
                </div>
                <button className="flex items-center gap-2 px-4 py-2.5 bg-neutral-900/50 border border-white/10 rounded-lg hover:bg-white/5 text-sm transition-colors">
                  <Filter size={16} /> {language === 'zh' ? '筛选' : 'Filter'}
                </button>
              </div>
            </div>

            {/* Stats Summary */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {summaryCards.map(card => (
                <div
                  key={card.key}
                  className={`bg-gradient-to-br ${card.gradient} border border-white/10 p-4 rounded-xl shadow-lg`}
                >
                  <div className="text-xs text-gray-400 mb-1 uppercase tracking-wider">{card.label}</div>
                  <div className="text-3xl font-bold text-white">{card.value}</div>
                </div>
              ))}
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-gray-500">{language === 'zh' ? '筛选' : 'Filter'}</span>
              {statusFilters.map(filter => (
                <button
                  key={filter}
                  onClick={() => setActiveStatusFilter(filter)}
                  className={`flex items-center gap-2 px-3 py-1 rounded-full text-[11px] font-bold transition-all border ${
                    activeStatusFilter === filter
                      ? 'bg-white/10 border-white/30 text-white'
                      : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${statusDotClass(filter)}`}></span>
                  {getStatusLabel(filter, language)}
                  <span className="text-[10px] text-gray-400">({statusCounts[filter] ?? 0})</span>
                </button>
              ))}
            </div>
          </div>

          {/* Reports Table */}
          <div className="bg-gradient-to-br from-neutral-900/80 to-neutral-800/40 border border-white/10 rounded-xl overflow-hidden flex-1 shadow-xl flex flex-col">
            <div className="px-6 py-3 border-b border-white/10 flex flex-wrap items-center justify-between gap-3 text-[11px] text-gray-400">
              <div className="flex flex-wrap items-center gap-2">
                <span>
                  {language === 'zh'
                    ? `显示 ${filteredReports.length}/${reportData.length} 条报告`
                    : `Showing ${filteredReports.length}/${reportData.length} reports`
                  }
                </span>
                <span className="text-gray-500">•</span>
                <span>
                  {language === 'zh' ? '当前筛选' : 'Active filter'}: {getStatusLabel(activeStatusFilter, language)}
                </span>
                {searchTerm && (
                  <span className="text-gray-500">
                    {language === 'zh' ? '搜索关键词' : 'Search'}: "{searchTerm}"
                  </span>
                )}
              </div>
              <button
                onClick={() => {
                  setSearchTerm('');
                  setActiveStatusFilter('All');
                }}
                className="px-3 py-1 rounded-full border border-white/20 text-[10px] uppercase tracking-widest hover:border-white/50 transition-colors"
              >
                {language === 'zh' ? '重置筛选' : 'Reset filters'}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 z-10 bg-gradient-to-r from-neutral-900 to-neutral-800 border-b border-white/10 text-gray-400 uppercase text-xs tracking-wider">
                  <tr>
                    <th className="px-6 py-4 font-medium">{language === 'zh' ? '报告ID' : 'Report ID'}</th>
                    <th className="px-6 py-4 font-medium">{language === 'zh' ? '病人ID' : 'Patient ID'}</th>
                    <th className="px-6 py-4 font-medium">{language === 'zh' ? '日期' : 'Date'}</th>
                    <th className="px-6 py-4 font-medium">{language === 'zh' ? '分期预测' : 'Stage Prediction'}</th>
                    <th className="px-6 py-4 font-medium">{language === 'zh' ? '状态' : 'Status'}</th>
                    <th className="px-6 py-4 font-medium text-right">{language === 'zh' ? '操作' : 'Action'}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {filteredReports.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-6 py-10 text-center text-gray-500">
                        {language === 'zh'
                          ? '没有匹配当前筛选条件的报告。'
                          : 'No reports match the current filters.'}
                      </td>
                    </tr>
                  ) : (
                    filteredReports.map(report => (
                      <tr
                        key={report.id}
                        className="hover:bg-white/5 transition-colors group cursor-pointer"
                        role="button"
                        tabIndex={0}
                        onClick={() => handleRowNavigation(report.id)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') {
                            handleRowNavigation(report.id);
                          }
                        }}
                      >
                        <td className="px-6 py-4 font-mono text-gray-300 group-hover:text-white transition-colors">{report.id}</td>
                        <td className="px-6 py-4 font-mono text-blue-400 group-hover:text-blue-300 transition-colors">{report.patient}</td>
                        <td className="px-6 py-4 text-gray-400">{report.date}</td>
                        <td className="px-6 py-4">
                          <span className={`px-3 py-1.5 rounded-lg text-xs font-bold border ${stageBadgeClass(report.stage)}`}>
                            {report.stage}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className="flex items-center gap-2 text-gray-300">
                            <span className={`w-2 h-2 rounded-full ${statusDotClass(report.status)}`}></span>
                            {getStatusLabel(report.status, language)}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button
                            className="p-2 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-all group-hover:bg-white/5"
                            onClick={event => {
                              event.stopPropagation();
                            }}
                          >
                            <Download size={18} />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </div>
    </main>
  );
}
