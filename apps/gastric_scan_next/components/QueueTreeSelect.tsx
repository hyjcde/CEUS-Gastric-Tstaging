"use client";

import React, { useEffect, useRef, useState } from 'react';
import {
  Building2,
  ChevronDown,
  ChevronRight,
  Database,
  FolderTree,
  Globe2,
  HeartPulse,
  Layers3,
} from 'lucide-react';
import {
  getQueueGroupDisplayLabel,
  getQueueDisplayLabel,
  getQueueOptionDisplayLabel,
  WorkbenchQueueGroup,
  WorkbenchQueueId,
  WORKBENCH_QUEUE_GROUPS,
} from '@/lib/cohort';
import { useSettings } from '@/contexts/SettingsContext';

interface QueueTreeSelectProps {
  value: WorkbenchQueueId;
  onChange: (value: WorkbenchQueueId) => void;
}

const GROUP_ICONS = {
  internal: Building2,
  external: Globe2,
  benign: HeartPulse,
  special: Layers3,
} as const;

export function QueueTreeSelect({ value, onChange }: QueueTreeSelectProps) {
  const { language } = useSettings();
  const [open, setOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<WorkbenchQueueGroup['id']>>(
    () => new Set(WORKBENCH_QUEUE_GROUPS.map((group) => group.id)),
  );
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  const toggleGroup = (groupId: WorkbenchQueueGroup['id']) => {
    setExpandedGroups((current) => {
      const next = new Set(current);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  const choose = (nextValue: WorkbenchQueueId) => {
    onChange(nextValue);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative min-w-[210px]">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center gap-2 rounded border border-cyan-500/25 bg-[#111] px-2 py-1 text-left text-[10px] text-gray-200 transition-colors hover:border-cyan-400/50"
        aria-haspopup="tree"
        aria-expanded={open}
        title={language === 'en' ? 'Select study queue' : '选择数据队列'}
      >
        <FolderTree size={12} className="shrink-0 text-cyan-300" />
        <span className="min-w-0 flex-1 truncate font-semibold">{getQueueDisplayLabel(value, language)}</span>
        <ChevronDown size={12} className={`shrink-0 text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open ? (
        <div
          role="tree"
          aria-label={language === 'en' ? 'Study queue tree' : '数据队列树'}
          className="absolute left-0 top-[calc(100%+0.4rem)] z-[80] w-[290px] overflow-hidden rounded-lg border border-cyan-500/25 bg-[#0d0f12] p-1.5 shadow-2xl shadow-black/60"
        >
          <QueueTreeItem
            label={getQueueOptionDisplayLabel('all', language)}
            value="all"
            selected={value === 'all'}
            depth={0}
            icon={<Database size={12} />}
            language={language}
            onChoose={choose}
          />
          {WORKBENCH_QUEUE_GROUPS.map((group) => {
            const Icon = GROUP_ICONS[group.id];
            const expanded = expandedGroups.has(group.id);
            return (
              <div key={group.id} role="group" className="mt-1">
                <button
                  type="button"
                  onClick={() => toggleGroup(group.id)}
                  className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-[10px] font-semibold text-gray-400 hover:bg-white/5 hover:text-gray-200"
                  aria-expanded={expanded}
                >
                  {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                  <Icon
                    size={12}
                    className={group.id === 'external' ? 'text-amber-300' : group.id === 'benign' ? 'text-emerald-300' : 'text-cyan-300'}
                  />
                  {getQueueGroupDisplayLabel(group.id, language)}
                </button>
                {expanded ? (
                  <div className="border-l border-white/10 pl-2">
                    {group.children.map((child) => (
                      <QueueTreeItem
                        key={child.id}
                        label={getQueueOptionDisplayLabel(child.id, language)}
                        value={child.id}
                        selected={value === child.id}
                        depth={1}
                        language={language}
                        onChoose={choose}
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function QueueTreeItem({
  label,
  value,
  selected,
  depth,
  icon,
  language,
  onChoose,
}: {
  label: string;
  value: WorkbenchQueueId;
  selected: boolean;
  depth: number;
  icon?: React.ReactNode;
  language: 'zh' | 'en';
  onChoose: (value: WorkbenchQueueId) => void;
}) {
  return (
    <button
      type="button"
      role="treeitem"
      aria-selected={selected}
      onClick={() => onChoose(value)}
      className={`flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-[10px] transition-colors ${
        selected
          ? 'bg-cyan-500/20 text-cyan-100'
          : 'text-gray-400 hover:bg-white/5 hover:text-gray-100'
      }`}
      style={{ paddingLeft: `${8 + depth * 12}px` }}
    >
      <span className={selected ? 'text-cyan-300' : 'text-gray-600'}>{icon || <ChevronRight size={11} />}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {selected ? <span className="text-[9px] text-cyan-300">{language === 'en' ? 'Current' : '当前'}</span> : null}
    </button>
  );
}
