"use client";

import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useSettings } from '@/contexts/SettingsContext';
import { languageLabel, nextLanguage } from '@/lib/i18n';
import { Globe, User, LogOut, FileText, BarChart2, PenTool, Clapperboard, ScanSearch, Compass } from 'lucide-react';
import { getDirectionAnnotatorPath } from '@/lib/annotator-url';
import { getVideoAnnotatorUrl } from '@/lib/video-annotator-url';
import { buildReaderAppUrl, buildHumanAssistUrl } from '@/lib/reading-agent-url';
import { navigateTo } from '@/lib/navigation';
import type { Patient } from '@/types';

interface HeaderProps {
  onShowStatistics?: () => void;
  selectedPatient?: Patient | null;
}

export const Header: React.FC<HeaderProps> = ({ onShowStatistics, selectedPatient }) => {
  const { language, setLanguage, t } = useSettings();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showLangMenu, setShowLangMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const langRef = useRef<HTMLDivElement>(null);
  const userButtonRef = useRef<HTMLButtonElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const languageButtonRef = useRef<HTMLButtonElement>(null);
  const languageMenuRef = useRef<HTMLDivElement>(null);
  const [userMenuPosition, setUserMenuPosition] = useState<{ top: number; right: number } | null>(null);
  const [languageMenuPosition, setLanguageMenuPosition] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        menuRef.current
        && !menuRef.current.contains(target)
        && !userMenuRef.current?.contains(target)
      ) {
        setShowUserMenu(false);
      }
      if (
        langRef.current
        && !langRef.current.contains(target)
        && !languageMenuRef.current?.contains(target)
      ) {
        setShowLangMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!showUserMenu) return;
    const updatePosition = () => {
      const rect = userButtonRef.current?.getBoundingClientRect();
      if (!rect) return;
      setUserMenuPosition({
        top: rect.bottom + 8,
        right: Math.max(8, window.innerWidth - rect.right),
      });
    };
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [showUserMenu]);

  useEffect(() => {
    if (!showLangMenu) return;
    const updatePosition = () => {
      const rect = languageButtonRef.current?.getBoundingClientRect();
      if (!rect) return;
      setLanguageMenuPosition({
        top: rect.bottom + 4,
        left: rect.left,
      });
    };
    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [showLangMenu]);

  const handleNavigate = (path: string) => {
    navigateTo(path);
    setShowUserMenu(false);
  };

  const openAnnotator = () => {
    navigateTo(getDirectionAnnotatorPath());
    setShowUserMenu(false);
  };

  const openVideoAnnotator = () => {
    window.open(getVideoAnnotatorUrl(), '_blank', 'noopener,noreferrer');
    setShowUserMenu(false);
  };

  const openReadingAgent = () => {
    navigateTo(buildReaderAppUrl(selectedPatient || null));
    setShowUserMenu(false);
  };

  const openHumanAssist = () => {
    const url = buildHumanAssistUrl(selectedPatient || null);
    window.open(url, '_blank', 'noopener,noreferrer');
    setShowUserMenu(false);
  };

  return (
    <header className="relative z-50 flex h-full w-full min-w-0 items-center justify-between gap-3 overflow-visible border-b border-white/10 bg-[#08090a] px-3 shadow-md sm:px-4">
      <div className="flex min-w-0 flex-1 items-center gap-3 lg:gap-5">
        <div
          className="group flex min-w-0 max-w-[min(70vw,28rem)] cursor-pointer select-none items-center gap-2.5 sm:gap-3.5"
          onClick={() => navigateTo('/')}
        >
          <div className="relative h-8 w-8 shrink-0 overflow-hidden rounded-xl border border-white/10 shadow-lg transition-all duration-500 group-hover:border-white/20 sm:h-12 sm:w-12">
            <img
              src="/image.png"
              alt="Union Hospital Logo"
              className="h-full w-full bg-white/5 object-contain p-1.5"
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
              <span className="hidden h-3 w-px bg-gray-600/60 sm:block" />
              <span className="text-[9px] font-medium leading-tight tracking-wide text-gray-500 sm:text-[10px]">{t.subtitle}</span>
            </div>
          </div>
        </div>

        <div className="hidden h-8 w-px shrink-0 bg-white/5 md:block" />

        <div className="relative hidden shrink-0 lg:block" ref={langRef}>
          <button
            type="button"
            ref={languageButtonRef}
            onClick={() => setShowLangMenu((value) => !value)}
            className="flex shrink-0 items-center gap-2 rounded border border-white/5 bg-[#111] px-2 py-1 text-[10px] font-mono text-gray-400 transition-colors hover:text-gray-200"
            title="简体 / 香港繁體 / EN"
          >
            <Globe size={10} />
            {languageLabel(language)}
          </button>
          {showLangMenu && languageMenuPosition ? createPortal(
            <div
              ref={languageMenuRef}
              className="fixed z-[200000] flex min-w-[8.5rem] flex-col overflow-hidden rounded-lg border border-white/10 bg-[#111] py-1 shadow-2xl"
              style={languageMenuPosition}
            >
              {([
                { id: 'zh' as const, label: '简体中文' },
                { id: 'zh-HK' as const, label: '繁體中文（香港）' },
                { id: 'en' as const, label: 'English' },
              ]).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setLanguage(item.id);
                    setShowLangMenu(false);
                  }}
                  className={`px-3 py-1.5 text-left text-[11px] transition-colors ${
                    language === item.id
                      ? 'bg-white/10 text-white'
                      : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>,
            document.body,
          ) : null}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1.5 text-[10px] font-mono text-gray-500 sm:gap-2">
        <button
          type="button"
          onClick={() => setLanguage(nextLanguage(language))}
          className="flex items-center gap-1.5 rounded border border-white/5 bg-[#111] px-2 py-1.5 text-gray-400 transition-colors hover:text-gray-200 lg:hidden"
          title="简体 / 香港繁體 / EN"
        >
          <Globe size={12} />
          <span className="text-[10px] font-semibold">{languageLabel(language)}</span>
        </button>

        {onShowStatistics ? (
          <button
            onClick={onShowStatistics}
            className="flex items-center gap-2 rounded border border-white/5 bg-[#111] px-2 py-1.5 text-purple-400 transition-colors hover:border-purple-500/50 hover:bg-purple-500/10 hover:text-purple-300 sm:px-2.5"
            title={language === 'en' ? 'View Statistics' : (language === 'zh-HK' ? '查看統計' : '查看统计')}
          >
            <BarChart2 size={12} />
            <span className="hidden text-[10px] font-semibold sm:inline">
              {language === 'en' ? 'Stats' : (language === 'zh-HK' ? '統計' : '统计')}
            </span>
          </button>
        ) : null}

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

        <div className="relative" ref={menuRef}>
          <button
            ref={userButtonRef}
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-gradient-to-tr from-gray-800 to-gray-700 text-xs font-bold text-gray-300 shadow-lg transition-colors hover:border-blue-500/50"
          >
            DR
          </button>

          {showUserMenu && userMenuPosition ? createPortal(
            <div
              ref={userMenuRef}
              className="fixed z-[200000] flex w-48 flex-col rounded-lg border border-white/10 bg-[#111] py-1 shadow-2xl backdrop-blur-xl"
              style={userMenuPosition}
            >
              <div className="border-b border-white/5 px-4 py-3">
                <div className="text-xs font-bold text-white">{t.userMenu.name}</div>
                <div className="text-[10px] text-gray-500">{t.userMenu.role}</div>
              </div>

              <button
                onClick={() => handleNavigate('/profile')}
                className="flex items-center gap-3 px-4 py-2 text-left text-[11px] text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
              >
                <User size={12} /> {t.userMenu.profile}
              </button>
              <button
                onClick={() => handleNavigate('/reports')}
                className="flex items-center gap-3 px-4 py-2 text-left text-[11px] text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
              >
                <FileText size={12} /> {t.userMenu.reports}
              </button>
              <button
                onClick={openAnnotator}
                className="flex items-center gap-3 px-4 py-2 text-left text-[11px] text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
              >
                <PenTool size={12} /> {t.nav.annotator}
              </button>
              <button
                onClick={openVideoAnnotator}
                className="flex items-center gap-3 px-4 py-2 text-left text-[11px] text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
              >
                <Clapperboard size={12} /> {t.nav.videoAnnotator}
              </button>
              <button
                onClick={openReadingAgent}
                className="flex items-center gap-3 px-4 py-2 text-left text-[11px] text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
              >
                <ScanSearch size={12} /> {t.nav.readingAgent}
              </button>
              <button
                onClick={openHumanAssist}
                className="flex items-center gap-3 px-4 py-2 text-left text-[11px] text-gray-400 transition-colors hover:bg-white/5 hover:text-white"
              >
                <Compass size={12} /> {t.nav.humanAssist}
              </button>

              <div className="my-1 h-px bg-white/5" />

              <button className="flex items-center gap-3 px-4 py-2 text-left text-[11px] text-red-400 transition-colors hover:bg-red-500/10 hover:text-red-300">
                <LogOut size={12} /> {t.userMenu.signout}
              </button>
            </div>,
            document.body,
          ) : null}
        </div>
      </div>
    </header>
  );
};
