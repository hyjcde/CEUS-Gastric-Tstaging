"use client";

import React, { useCallback, useEffect, useState } from 'react';
import { History, Trash2, X, RefreshCw, ChevronRight } from 'lucide-react';
import { useDoctorAccount } from '@/contexts/DoctorAccountContext';
import { useSettings } from '@/contexts/SettingsContext';
import { DoctorAccountModal } from '@/components/DoctorAccountModal';

type HistoryEntry = {
  history_id: string;
  owner_account_id: string;
  session_id: string;
  case_id: string;
  patient_id?: string;
  title: string;
  summary: string;
  event_count: number;
  last_event_type: string;
  last_action?: string;
  updated_at: string;
  created_at: string;
};

type TraceItem = {
  event_id?: string;
  event_type?: string;
  recorded_at?: string;
  action?: string;
  status?: string | null;
  error?: string | null;
};

export function DoctorHistoryPanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const { account, authHeaders } = useDoctorAccount();
  const [loginOpen, setLoginOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [traces, setTraces] = useState<TraceItem[]>([]);
  const [detailBusy, setDetailBusy] = useState(false);

  const loadList = useCallback(async () => {
    if (!account) {
      setEntries([]);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch('/api/reader/history?limit=200', {
        cache: 'no-store',
        headers: authHeaders(),
      });
      const data = await response.json() as {
        ok?: boolean;
        error?: string;
        entries?: HistoryEntry[];
      };
      if (!response.ok || !data.ok) {
        throw new Error(data.error || 'Failed to load history');
      }
      setEntries(Array.isArray(data.entries) ? data.entries : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load history');
      setEntries([]);
    } finally {
      setBusy(false);
    }
  }, [account, authHeaders]);

  const loadDetail = useCallback(async (historyId: string) => {
    setSelectedId(historyId);
    setDetailBusy(true);
    setTraces([]);
    try {
      const response = await fetch(`/api/reader/history/${encodeURIComponent(historyId)}?limit=300`, {
        cache: 'no-store',
        headers: authHeaders(),
      });
      const data = await response.json() as {
        ok?: boolean;
        error?: string;
        traces?: TraceItem[];
      };
      if (!response.ok || !data.ok) {
        throw new Error(data.error || 'Failed to load traces');
      }
      setTraces(Array.isArray(data.traces) ? data.traces : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load traces');
    } finally {
      setDetailBusy(false);
    }
  }, [authHeaders]);

  const deleteEntry = useCallback(async (historyId: string) => {
    if (!window.confirm(zh ? '删除这条历史？仅对本账号隐藏，底层审计仍保留。' : 'Delete this history entry? It will be hidden for your account; raw audit logs remain.')) {
      return;
    }
    const response = await fetch(`/api/reader/history/${encodeURIComponent(historyId)}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });
    const data = await response.json() as { ok?: boolean; error?: string };
    if (!response.ok || !data.ok) {
      setError(data.error || 'Delete failed');
      return;
    }
    if (selectedId === historyId) {
      setSelectedId(null);
      setTraces([]);
    }
    await loadList();
  }, [authHeaders, loadList, selectedId, zh]);

  const deleteAll = useCallback(async () => {
    if (!window.confirm(zh ? '清空本账号全部历史列表？' : 'Clear all history for this account?')) {
      return;
    }
    const response = await fetch('/api/reader/history?all=1', {
      method: 'DELETE',
      headers: authHeaders(),
    });
    const data = await response.json() as { ok?: boolean; error?: string };
    if (!response.ok || !data.ok) {
      setError(data.error || 'Delete failed');
      return;
    }
    setSelectedId(null);
    setTraces([]);
    await loadList();
  }, [authHeaders, loadList, zh]);

  useEffect(() => {
    if (!open) return;
    void loadList();
  }, [loadList, open]);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-[205000] flex items-stretch justify-end bg-black/55">
        <button type="button" className="flex-1" aria-label="Close" onClick={onClose} />
        <div className="flex h-full w-full max-w-xl flex-col border-l border-white/10 bg-[#0d0e10] shadow-2xl">
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div className="flex items-center gap-2">
              <History size={16} className="text-blue-300" />
              <div>
                <div className="text-sm font-semibold text-white">
                  {zh ? '我的操作历史' : 'My operation history'}
                </div>
                <div className="text-[11px] text-gray-500">
                  {account
                    ? `${account.display_name} (${account.account_id})`
                    : (zh ? '未登录' : 'Not signed in')}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => void loadList()}
                className="rounded-lg p-1.5 text-gray-400 hover:bg-white/5 hover:text-white"
                title={zh ? '刷新' : 'Refresh'}
              >
                <RefreshCw size={14} />
              </button>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg p-1.5 text-gray-400 hover:bg-white/5 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {!account ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
              <p className="text-sm text-gray-300">
                {zh
                  ? '请先登录医生账号，才能查看与删除本人历史和操作 trace。'
                  : 'Sign in with a doctor account to view and delete your history and traces.'}
              </p>
              <button
                type="button"
                onClick={() => setLoginOpen(true)}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500"
              >
                {zh ? '登录 / 注册' : 'Sign in / Create'}
              </button>
            </div>
          ) : (
            <div className="grid min-h-0 flex-1 grid-rows-[auto_1fr] gap-0">
              <div className="flex items-center justify-between border-b border-white/5 px-4 py-2 text-[11px] text-gray-500">
                <span>{zh ? `${entries.length} 条会话` : `${entries.length} sessions`}</span>
                <button
                  type="button"
                  disabled={!entries.length}
                  onClick={() => void deleteAll()}
                  className="inline-flex items-center gap-1 text-red-400 hover:text-red-300 disabled:opacity-40"
                >
                  <Trash2 size={12} />
                  {zh ? '清空全部' : 'Clear all'}
                </button>
              </div>

              {error ? (
                <div className="border-b border-red-500/20 bg-red-500/10 px-4 py-2 text-[11px] text-red-300">
                  {error}
                </div>
              ) : null}

              <div className="grid min-h-0 grid-cols-1 md:grid-cols-2">
                <div className="min-h-0 overflow-y-auto border-r border-white/5 p-2">
                  {busy ? (
                    <div className="p-3 text-[11px] text-gray-500">{zh ? '加载中…' : 'Loading…'}</div>
                  ) : entries.length === 0 ? (
                    <div className="p-3 text-[11px] text-gray-500">
                      {zh ? '暂无本账号历史。开始阅片后会自动记录。' : 'No history yet. Records appear after reading.'}
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {entries.map((entry) => {
                        const active = selectedId === entry.history_id;
                        return (
                          <div
                            key={entry.history_id}
                            className={`rounded-lg border px-2.5 py-2 ${
                              active ? 'border-blue-500/40 bg-blue-500/10' : 'border-white/10 bg-black/20'
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => void loadDetail(entry.history_id)}
                              className="w-full text-left"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <div className="truncate text-[12px] font-medium text-white">{entry.title}</div>
                                  <div className="mt-0.5 truncate text-[10px] text-gray-400">{entry.summary}</div>
                                  <div className="mt-1 text-[10px] text-gray-500">
                                    {new Date(entry.updated_at).toLocaleString()} · {entry.event_count} events
                                  </div>
                                </div>
                                <ChevronRight size={14} className="mt-0.5 shrink-0 text-gray-500" />
                              </div>
                            </button>
                            <div className="mt-2 flex justify-end">
                              <button
                                type="button"
                                onClick={() => void deleteEntry(entry.history_id)}
                                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-red-400 hover:bg-red-500/10"
                              >
                                <Trash2 size={11} />
                                {zh ? '删除' : 'Delete'}
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className="min-h-0 overflow-y-auto p-3">
                  {!selectedId ? (
                    <div className="text-[11px] text-gray-500">
                      {zh ? '选择左侧会话查看操作 trace。' : 'Select a session to inspect operation traces.'}
                    </div>
                  ) : detailBusy ? (
                    <div className="text-[11px] text-gray-500">{zh ? '加载 trace…' : 'Loading traces…'}</div>
                  ) : traces.length === 0 ? (
                    <div className="text-[11px] text-gray-500">
                      {zh ? '该会话暂无可展示的操作 trace。' : 'No displayable traces for this session.'}
                    </div>
                  ) : (
                    <ol className="space-y-2">
                      {traces.map((trace, index) => (
                        <li
                          key={String(trace.event_id || index)}
                          className="rounded-lg border border-white/10 bg-black/20 px-2.5 py-2"
                        >
                          <div className="text-[11px] font-medium text-gray-200">
                            {String(trace.action || trace.event_type || 'step')}
                          </div>
                          <div className="mt-0.5 text-[10px] text-gray-500">
                            {trace.recorded_at ? new Date(String(trace.recorded_at)).toLocaleString() : '-'}
                            {trace.status ? ` · ${trace.status}` : ''}
                          </div>
                          {trace.error ? (
                            <div className="mt-1 text-[10px] text-red-400">{String(trace.error)}</div>
                          ) : null}
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      <DoctorAccountModal open={loginOpen} onClose={() => setLoginOpen(false)} />
    </>
  );
}
