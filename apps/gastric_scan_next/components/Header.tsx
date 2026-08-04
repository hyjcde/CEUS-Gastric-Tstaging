"use client";

import React, { useState, useRef, useEffect } from 'react';
import { useSettings } from '@/contexts/SettingsContext';
import { Globe, User, LogOut, FileText, BarChart2, PenTool, Clapperboard, ScanSearch, Compass } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { getDirectionAnnotatorPath } from '@/lib/annotator-url';
import { getVideoAnnotatorUrl } from '@/lib/video-annotator-url';
import { buildReaderAppUrl, buildHumanAssistUrl } from '@/lib/reading-agent-url';
import type { Patient } from '@/types';

interface HeaderProps {
  onShowStatistics?: () => void;
  selectedPatient?: Patient | null;
}

export const Header: React.FC<HeaderProps> = ({ onShowStatistics, selectedPatient }) => {
  const { language, setLanguage, dataset, setDataset, t } = useSettings();
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

  const openVideoAnnotator = () => {
    window.open(getVideoAnnotatorUrl(), '_blank', 'noopener,noreferrer');
    setShowUserMenu(false);
  };

  const openReadingAgent = () => {
    router.push(buildReaderAppUrl(selectedPatient || null));
    setShowUserMenu(false);
  };

  const openHumanAssist = () => {
    const url = buildHumanAssistUrl(selectedPatient || null);
    window.open(url, '_blank', 'noopener,noreferrer');
    setShowUserMenu(false);
  };

  return (
    <header className="relative z-50 flex h-full w-full min-w-0 items-center justify-between gap-3 overflow-hidden border-b border-white/10 bg-[#08090a] px-3 shadow-md sm:px-4">
      <div className="flex min-w-0 flex-1 items-center gap-3 lg:gap-5">
        {/* Logo Block */}
        <div 
            className="group flex min-w-0 max-w-[min(70vw,28rem)] cursor-pointer select-none items-center gap-2.5 sm:gap-3.5"
            onClick={() => router.push('/')}
        >
          <div className="relative h-8 w-8 shrink-0 overflow-hidden rounded-xl border border-white/10 shadow-lg transition-all duration-500 group-hover:border-white/20 sm:h-12 sm:w-12">
            <img 
              src="/image.png" 
              alt="Union Hospital Logo" 
              className="w-full h-full object-contain bg-white/5 p-1.5"
            />
          </div>
          <div className="flex min-w-0 flex-col justify-center gap-1">
            <h1 className="text-balance text-[clamp(0.78rem,1.35vw,1rem)] font-bold leading-[1.05] tracking-tight text-gray-100">
              {t.title}
            </h1>
            <div className="hidden min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 sm:flex">
              <span className="text-[9px] font-bold uppercase leading-tight tracking-[0.16em] text-blue-400 sm:text-[10px]">
                {t.hospital}
              </span>
              <span className="hidden h-3 w-px bg-gray-600/60 sm:block"></span>
              <span className="text-[9px] font-medium leading-tight tracking-wide text-gray-500 sm:text-[10px]">{t.subtitle}</span>
            </div>
          </div>
        </div>

        <div className="hidden h-8 w-px shrink-0 bg-white/5 md:block"></div>

        {/* Controls: Language, Cohort & Dataset */}
        <div className="hidden shrink-0 items-center gap-2 xl:gap-3 lg:flex">
            {/* Language Switcher */}
            <button 
                onClick={() => setLanguage(language === 'en' ? 'zh' : 'en')}
                className="flex shrink-0 items-center gap-2 rounded border border-white/5 bg-[#111] px-2 py-1 text-[10px] font-mono text-gray-400 transition-colors hover:text-gray-200"
            >
                <Globe size={10} />
                {language === 'en' ? 'EN' : '中文'}
            </button>

            {/* Dataset Switcher — CROP UI 为默认主视图 */}
            <div className="flex shrink-0 items-center gap-1 rounded border border-white/5 bg-[#111] p-1">
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
      <div className="flex shrink-0 items-center gap-1.5 text-[10px] font-mono text-gray-500 sm:gap-2">
        {/* Statistics Button */}
        {onShowStatistics && (
          <button
            onClick={onShowStatistics}
            className="flex items-center gap-2 rounded border border-white/5 bg-[#111] px-2 py-1.5 text-purple-400 transition-colors hover:border-purple-500/50 hover:bg-purple-500/10 hover:text-purple-300 sm:px-2.5"
            title={language === 'zh' ? '查看统计' : 'View Statistics'}
          >
            <BarChart2 size={12} />
            <span className="hidden text-[10px] font-semibold sm:inline">{language === 'zh' ? '统计' : 'Stats'}</span>
          </button>
        )}

        <button
          onClick={openAnnotator}
          className="hidden items-center gap-2 rounded border border-white/5 bg-[#111] px-3 py-1.5 text-amber-400 transition-colors hover:border-amber-500/50 hover:bg-amber-500/10 hover:text-amber-300 xl:flex"
          title={t.nav.annotatorTitle}
        >
          <PenTool size={12} />
          <span className="text-[10px] font-semibold">{t.nav.annotator}</span>
        </button>

        <button
          onClick={openVideoAnnotator}
          className="hidden items-center gap-2 rounded border border-white/5 bg-[#111] px-3 py-1.5 text-cyan-400 transition-colors hover:border-cyan-500/50 hover:bg-cyan-500/10 hover:text-cyan-300 xl:flex"
          title={t.nav.videoAnnotatorTitle}
        >
          <Clapperboard size={12} />
          <span className="text-[10px] font-semibold">{t.nav.videoAnnotator}</span>
        </button>

        <button
          onClick={openReadingAgent}
          className="hidden items-center gap-2 rounded border border-white/5 bg-[#111] px-3 py-1.5 text-emerald-400 transition-colors hover:border-emerald-500/50 hover:bg-emerald-500/10 hover:text-emerald-300 xl:flex"
          title={t.nav.readingAgentTitle}
        >
          <ScanSearch size={12} />
          <span className="text-[10px] font-semibold">{t.nav.readingAgent}</span>
        </button>

        <button
          onClick={openHumanAssist}
          className="hidden items-center gap-2 rounded border border-white/5 bg-[#111] px-3 py-1.5 text-orange-400 transition-colors hover:border-orange-500/50 hover:bg-orange-500/10 hover:text-orange-300 xl:flex"
          title={t.nav.humanAssistTitle}
        >
          <Compass size={12} />
          <span className="text-[10px] font-semibold">{t.nav.humanAssist}</span>
        </button>
        
        <div className="hidden items-center gap-2 rounded border border-white/5 bg-[#111] px-3 py-1.5 shadow-inner 2xl:flex">
            <span className="text-blue-400 font-semibold tracking-wider">{t.status.online}</span>
        </div>
        
        {/* User Avatar Menu */}
        <div className="relative" ref={menuRef}>
            <button 
                onClick={() => setShowUserMenu(!showUserMenu)}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-gradient-to-tr from-gray-800 to-gray-700 text-xs font-bold text-gray-300 shadow-lg transition-colors hover:border-blue-500/50"
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
                    <button 
                        onClick={openVideoAnnotator}
                        className="flex items-center gap-3 px-4 py-2 text-[11px] text-gray-400 hover:text-white hover:bg-white/5 transition-colors text-left"
                    >
                        <Clapperboard size={12} /> {t.nav.videoAnnotator}
                    </button>
                    <button 
                        onClick={openReadingAgent}
                        className="flex items-center gap-3 px-4 py-2 text-[11px] text-gray-400 hover:text-white hover:bg-white/5 transition-colors text-left"
                    >
                        <ScanSearch size={12} /> {t.nav.readingAgent}
                    </button>
                    <button 
                        onClick={openHumanAssist}
                        className="flex items-center gap-3 px-4 py-2 text-[11px] text-gray-400 hover:text-white hover:bg-white/5 transition-colors text-left"
                    >
                        <Compass size={12} /> {t.nav.humanAssist}
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
