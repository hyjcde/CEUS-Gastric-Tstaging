"use client";

import React, { useState, useRef, useEffect } from 'react';
import { useSettings } from '@/contexts/SettingsContext';
import { GASTRIC_COHORT_YEARS, GastricCohortYear, getCohortDisplayLabel } from '@/lib/cohort';
import { Activity, ChevronRight, Building2, Globe, User, Settings, LogOut, FileText, BarChart2, PenTool } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { getDirectionAnnotatorPath } from '@/lib/annotator-url';

interface HeaderProps {
  onShowStatistics?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onShowStatistics }) => {
  const { language, setLanguage, dataset, setDataset, cohortYear, setCohortYear, treatmentType, setTreatmentType, t } = useSettings();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNavigate = (path: string) => {
      router.push(path);
      setShowUserMenu(false);
  };

  const openAnnotator = () => {
    router.push(getDirectionAnnotatorPath());
    setShowUserMenu(false);
  };

  return (
    <header className="h-full w-full flex items-center justify-between px-5 bg-[#08090a] border-b border-white/10 shadow-md z-50 relative">
      <div className="flex items-center gap-6">
        {/* Logo Block */}
        <div 
            className="flex items-center gap-3.5 group cursor-pointer select-none"
            onClick={() => router.push('/')}
        >
          <div className="relative w-12 h-12 rounded-xl overflow-hidden border border-white/10 shadow-lg group-hover:border-white/20 transition-all duration-500">
            <img 
              src="/image.png" 
              alt="Union Hospital Logo" 
              className="w-full h-full object-contain bg-white/5 p-1.5"
            />
          </div>
          <div className="flex flex-col justify-center gap-0.5">
            <h1 className="font-bold text-base tracking-tight text-gray-100 leading-none">
              {t.title}
            </h1>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-blue-400 uppercase tracking-widest flex items-center gap-1.5">
                {t.hospital}
              </span>
              <span className="w-0.5 h-0.5 bg-gray-600 rounded-full"></span>
              <span className="text-[10px] font-medium text-gray-500 tracking-wide">{t.subtitle}</span>
            </div>
          </div>
        </div>

        <div className="h-8 w-px bg-white/5 hidden md:block"></div>

        {/* Controls: Language, Cohort & Dataset */}
        <div className="hidden lg:flex items-center gap-4">
            {/* Language Switcher */}
            <button 
                onClick={() => setLanguage(language === 'en' ? 'zh' : 'en')}
                className="flex items-center gap-2 text-[10px] font-mono text-gray-400 hover:text-gray-200 transition-colors bg-[#111] px-2 py-1 rounded border border-white/5"
            >
                <Globe size={10} />
                {language === 'en' ? 'EN' : '中文'}
            </button>

            {/* Cohort Year Switcher */}
            <div className="flex items-center gap-1 bg-[#111] p-1 rounded border border-white/5 max-w-[min(52vw,520px)] overflow-x-auto custom-scrollbar">
                {GASTRIC_COHORT_YEARS.map((year) => {
                  const isActive = cohortYear === year;
                  const activeClass = year === '2025'
                    ? 'bg-emerald-600 text-white'
                    : year === '2024'
                      ? 'bg-cyan-600 text-white'
                      : year === '2020_2023'
                        ? 'bg-orange-600 text-white'
                        : year === '2019'
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-600 text-white';
                  return (
                    <button
                      key={year}
                      type="button"
                      onClick={() => setCohortYear(year as GastricCohortYear)}
                      className={`shrink-0 px-2 py-0.5 text-[10px] font-bold rounded transition-colors ${isActive ? activeClass : 'text-gray-500 hover:text-gray-300'}`}
                    >
                      {getCohortDisplayLabel(year)}
                    </button>
                  );
                })}
            </div>

            {/* Dataset Switcher — CROP UI 为默认主视图 */}
            <div className="flex items-center gap-1 bg-[#111] p-1 rounded border border-white/5">
                <button 
                    onClick={() => setDataset('cropped')}
                    className={`px-2 py-0.5 text-[10px] font-bold rounded transition-colors ${dataset === 'cropped' ? 'bg-amber-600 text-white' : 'text-gray-500 hover:text-gray-300'}`}
                >
                    CROP UI
                </button>
                <button 
                    onClick={() => setDataset('original')}
                    className={`px-2 py-0.5 text-[10px] font-bold rounded transition-colors ${dataset === 'original' ? 'bg-blue-600 text-white' : 'text-gray-500 hover:text-gray-300'}`}
                >
                    ORIGINAL
                </button>
            </div>
        </div>
      </div>

      {/* Right Status & User Menu */}
      <div className="flex items-center gap-6 text-[10px] font-mono text-gray-500">
        {/* Statistics Button */}
        {onShowStatistics && (
          <button
            onClick={onShowStatistics}
            className="flex items-center gap-2 bg-[#111] px-3 py-1.5 rounded border border-white/5 hover:border-purple-500/50 hover:bg-purple-500/10 transition-colors text-purple-400 hover:text-purple-300"
            title={language === 'zh' ? '查看统计' : 'View Statistics'}
          >
            <BarChart2 size={12} />
            <span className="text-[10px] font-semibold">{language === 'zh' ? '统计' : 'Stats'}</span>
          </button>
        )}

        <button
          onClick={openAnnotator}
          className="flex items-center gap-2 bg-[#111] px-3 py-1.5 rounded border border-white/5 hover:border-amber-500/50 hover:bg-amber-500/10 transition-colors text-amber-400 hover:text-amber-300"
          title={t.nav.annotatorTitle}
        >
          <PenTool size={12} />
          <span className="text-[10px] font-semibold">{t.nav.annotator}</span>
        </button>
        
        <div className="hidden md:flex items-center gap-2 bg-[#111] px-3 py-1.5 rounded border border-white/5 shadow-inner">
            <div className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500"></span>
            </div>
            <span className="text-blue-400 font-semibold tracking-wider">{t.status.online}</span>
        </div>
        
        {/* User Avatar Menu */}
        <div className="relative" ref={menuRef}>
            <button 
                onClick={() => setShowUserMenu(!showUserMenu)}
                className="w-8 h-8 rounded-full bg-gradient-to-tr from-gray-800 to-gray-700 border border-white/10 flex items-center justify-center text-xs font-bold text-gray-300 shadow-lg hover:border-blue-500/50 transition-colors"
            >
              DR
            </button>

            {/* Dropdown Menu */}
            {showUserMenu && (
                <div className="absolute right-0 top-10 w-48 bg-[#111] border border-white/10 rounded-lg shadow-2xl py-1 flex flex-col z-50 backdrop-blur-xl">
                    <div className="px-4 py-3 border-b border-white/5">
                        <div className="text-xs font-bold text-white">{t.userMenu.name}</div>
                        <div className="text-[10px] text-gray-500">{t.userMenu.role}</div>
                    </div>
                    
                    <button 
                        onClick={() => handleNavigate('/profile')}
                        className="flex items-center gap-3 px-4 py-2 text-[11px] text-gray-400 hover:text-white hover:bg-white/5 transition-colors text-left"
                    >
                        <User size={12} /> {t.userMenu.profile}
                    </button>
                    <button 
                        onClick={() => handleNavigate('/reports')}
                        className="flex items-center gap-3 px-4 py-2 text-[11px] text-gray-400 hover:text-white hover:bg-white/5 transition-colors text-left"
                    >
                        <FileText size={12} /> {t.userMenu.reports}
                    </button>
                    <button 
                        onClick={openAnnotator}
                        className="flex items-center gap-3 px-4 py-2 text-[11px] text-gray-400 hover:text-white hover:bg-white/5 transition-colors text-left"
                    >
                        <PenTool size={12} /> {t.nav.annotator}
                    </button>
                    
                    <div className="h-px bg-white/5 my-1"></div>
                    
                    <button className="flex items-center gap-3 px-4 py-2 text-[11px] text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors text-left">
                        <LogOut size={12} /> {t.userMenu.signout}
                    </button>
                </div>
            )}
        </div>
      </div>
    </header>
  );
};
