'use client';

import { ClipboardList, ScanSearch, Users, X } from 'lucide-react';

export type WorkbenchMobilePane = 'cases' | 'viewer' | 'evidence';

type NavItem = {
  id: WorkbenchMobilePane;
  label: string;
  Icon: typeof Users;
};

export function MobilePaneNav({
  pane,
  onChange,
  language,
  evidenceLabel,
  caseLabel,
}: {
  pane: WorkbenchMobilePane;
  onChange: (pane: WorkbenchMobilePane) => void;
  language: string;
  evidenceLabel?: string;
  caseLabel?: string | null;
}) {
  const zh = language !== 'en';
  const items: NavItem[] = [
    { id: 'cases', Icon: Users, label: zh ? '病例' : 'Cases' },
    { id: 'viewer', Icon: ScanSearch, label: zh ? '超声' : 'Ultrasound' },
    {
      id: 'evidence',
      Icon: ClipboardList,
      label: evidenceLabel || (zh ? '判断' : 'Call'),
    },
  ];

  return (
    <nav
      className="workbench-mobile-nav relative z-[250] md:hidden shrink-0 border-t border-white/10 bg-[#0b0b0d]"
      aria-label={zh ? '工作台分区' : 'Workbench sections'}
    >
      <div className="grid grid-cols-3">
        {items.map(({ id, Icon, label }) => {
          const active = pane === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              title={id === 'viewer' && caseLabel ? caseLabel : label}
              className={`flex min-h-12 flex-col items-center justify-center gap-0.5 px-2 py-1.5 text-[11px] font-semibold transition-colors ${
                active ? 'text-sky-100' : 'text-slate-500 hover:text-slate-200'
              }`}
              aria-current={active ? 'page' : undefined}
            >
              <Icon size={16} className={active ? 'text-sky-300' : 'text-slate-500'} />
              <span className="max-w-full truncate">{label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}

export function MobileSheetHeader({
  title,
  onClose,
  language,
}: {
  title: string;
  onClose: () => void;
  language: string;
}) {
  const zh = language !== 'en';
  return (
    <div className="workbench-sheet-bar shrink-0 items-center justify-between border-b border-white/10 bg-[#0b0b0d] px-3 py-2">
      <span className="text-[13px] font-semibold text-gray-100">{title}</span>
      <button
        type="button"
        onClick={onClose}
        className="inline-flex min-h-9 items-center gap-1 rounded-lg border border-white/15 px-3 text-[12px] text-gray-200"
      >
        <X size={14} />
        {zh ? '完成' : 'Done'}
      </button>
    </div>
  );
}
