"use client";

import React, { useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { useDoctorAccount } from '@/contexts/DoctorAccountContext';
import { useSettings } from '@/contexts/SettingsContext';

type Mode = 'login' | 'create';

export function DoctorAccountModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const { accounts, login, createAccount } = useDoctorAccount();
  const [mode, setMode] = useState<Mode>('login');
  const [accountId, setAccountId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sortedAccounts = useMemo(
    () => [...accounts].sort((a, b) => a.display_name.localeCompare(b.display_name)),
    [accounts],
  );

  if (!open) return null;

  const submit = async () => {
    setBusy(true);
    setError(null);
    const result = mode === 'create'
      ? await createAccount(accountId.trim(), pin.trim(), displayName.trim() || undefined)
      : await login(accountId.trim(), pin.trim());
    setBusy(false);
    if (!result.ok) {
      setError(result.error || (zh ? '操作失败' : 'Failed'));
      return;
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[210000] flex items-center justify-center bg-black/70 p-4">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#111] shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-white">
              {zh ? '医生账号' : 'Doctor account'}
            </div>
            <div className="text-[11px] text-gray-500">
              {zh
                ? '历史与操作 trace 按账号隔离保存'
                : 'History and operation traces are saved per account'}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-white/5 hover:text-white"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-3 px-4 py-4">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setMode('login')}
              className={`flex-1 rounded-lg px-3 py-2 text-xs ${
                mode === 'login' ? 'bg-blue-500/20 text-blue-200' : 'bg-white/5 text-gray-400'
              }`}
            >
              {zh ? '登录' : 'Sign in'}
            </button>
            <button
              type="button"
              onClick={() => setMode('create')}
              className={`flex-1 rounded-lg px-3 py-2 text-xs ${
                mode === 'create' ? 'bg-blue-500/20 text-blue-200' : 'bg-white/5 text-gray-400'
              }`}
            >
              {zh ? '注册账号' : 'Create account'}
            </button>
          </div>

          {mode === 'login' && sortedAccounts.length > 0 ? (
            <div className="max-h-28 space-y-1 overflow-y-auto rounded-lg border border-white/10 p-2">
              {sortedAccounts.map((item) => (
                <button
                  key={item.account_id}
                  type="button"
                  onClick={() => setAccountId(item.account_id)}
                  className={`block w-full rounded px-2 py-1.5 text-left text-[11px] ${
                    accountId === item.account_id
                      ? 'bg-white/10 text-white'
                      : 'text-gray-400 hover:bg-white/5'
                  }`}
                >
                  <span className="font-medium text-gray-200">{item.display_name}</span>
                  <span className="ml-2 text-gray-500">{item.account_id}</span>
                </button>
              ))}
            </div>
          ) : null}

          <label className="block space-y-1">
            <span className="text-[11px] text-gray-400">{zh ? '账号 ID' : 'Account ID'}</span>
            <input
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
              placeholder="dr_lin"
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
            />
          </label>

          {mode === 'create' ? (
            <label className="block space-y-1">
              <span className="text-[11px] text-gray-400">{zh ? '显示名称' : 'Display name'}</span>
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder={zh ? '林医生' : 'Dr Lin'}
                className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
              />
            </label>
          ) : null}

          <label className="block space-y-1">
            <span className="text-[11px] text-gray-400">{zh ? 'PIN（4-8 位数字）' : 'PIN (4-8 digits)'}</span>
            <input
              type="password"
              inputMode="numeric"
              value={pin}
              onChange={(event) => setPin(event.target.value)}
              placeholder="••••"
              className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm text-white outline-none focus:border-blue-500/50"
            />
          </label>

          {error ? <div className="text-[11px] text-red-400">{error}</div> : null}

          <button
            type="button"
            disabled={busy || !accountId.trim() || !pin.trim()}
            onClick={() => void submit()}
            className="w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {busy
              ? (zh ? '处理中…' : 'Working…')
              : mode === 'create'
                ? (zh ? '创建并登录' : 'Create and sign in')
                : (zh ? '登录' : 'Sign in')}
          </button>
        </div>
      </div>
    </div>
  );
}
