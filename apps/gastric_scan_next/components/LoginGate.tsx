"use client";

import React, { useEffect, useState } from 'react';
import { useDoctorAccount, type DoctorAccount, type ReaderIdentity } from '@/contexts/DoctorAccountContext';
import { useSettings } from '@/contexts/SettingsContext';
import { formatDoctorLoginError } from '@/lib/reader/login-error';
import { isLocalBrowserHost } from '@/lib/reader/local-access';

export function LocalIdentityButtons({
  readers,
  accounts,
  busy,
  currentId,
  onSelect,
  zh,
}: {
  readers: ReaderIdentity[];
  accounts: DoctorAccount[];
  busy: boolean;
  currentId?: string | null;
  onSelect: (accountId: string) => void;
  zh: boolean;
}) {
  const seen = new Set<string>();
  const choices: Array<{ id: string; label: string; sub?: string }> = [];
  for (const reader of readers) {
    const id = reader.username;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    choices.push({
      id,
      label: reader.display_name || reader.reader_label || id,
      sub: reader.reader_label && reader.reader_label !== reader.display_name ? reader.reader_label : id,
    });
  }
  for (const account of accounts) {
    const id = account.account_id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    choices.push({
      id,
      label: account.display_name || id,
      sub: id,
    });
  }
  if (!choices.length) {
    return (
      <div className="text-[11px] text-gray-500">
        {zh ? '本机还没有可读身份。请检查阅片账号表。' : 'No local reader identities are available.'}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-2">
      {choices.map((choice) => (
        <button
          key={choice.id}
          type="button"
          disabled={busy}
          onClick={() => onSelect(choice.id)}
          className={`min-h-11 rounded-lg border px-3 py-2.5 text-left hover:bg-white/5 disabled:opacity-50 ${
            currentId === choice.id
              ? 'border-blue-400/50 bg-blue-500/10'
              : 'border-white/10 bg-black/30'
          }`}
        >
          <div className="text-sm font-medium text-white">{choice.label}</div>
          {choice.sub && choice.sub !== choice.label ? (
            <div className="text-[11px] text-gray-500">{choice.sub}</div>
          ) : null}
        </button>
      ))}
    </div>
  );
}

export function LoginGate({ children }: { children: React.ReactNode }) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const {
    ready,
    account,
    readers,
    accounts,
    loginWithPassword,
    selectLocalIdentity,
    signedOut,
  } = useDoctorAccount();
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hadSession, setHadSession] = useState(false);
  const localHost = isLocalBrowserHost();

  useEffect(() => {
    if (signedOut) {
      setHadSession(false);
      return;
    }
    if (account) setHadSession(true);
  }, [account, signedOut]);

  const submitPassword = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (!password.trim() || busy) return;
    setBusy(true);
    setError(null);
    const result = await loginWithPassword(password);
    setBusy(false);
    if (!result.ok) {
      setError(formatDoctorLoginError(result.error, zh));
      return;
    }
    setPassword('');
  };

  const submitLocalIdentity = async (accountId: string) => {
    if (!accountId || busy) return;
    setBusy(true);
    setError(null);
    const result = await selectLocalIdentity(accountId);
    setBusy(false);
    if (!result.ok) {
      setError(formatDoctorLoginError(result.error, zh));
    }
  };

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#050506] px-4 text-sm text-gray-500">
        {zh ? '正在打开…' : 'Opening…'}
      </div>
    );
  }

  if (account) return <>{children}</>;

  const resumeHint = hadSession
    ? (zh ? '请重新登录' : 'Sign in again')
    : null;

  const localForm = (
    <div className={hadSession
      ? 'flex w-full items-center justify-center'
      : 'flex min-h-screen items-center justify-center bg-[#050506] p-6 max-md:min-h-svh max-md:px-4 max-md:pt-[max(1.5rem,env(safe-area-inset-top))] max-md:pb-[max(1.5rem,env(safe-area-inset-bottom))]'}>
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#111] p-6 shadow-2xl">
        <div className="mb-6 flex items-center gap-3">
          <img
            src="/image.png"
            alt="Union Hospital"
            className="h-12 w-12 shrink-0 rounded-xl border border-white/10 bg-white/5 object-contain p-1.5"
          />
          <div className="min-w-0">
            <div className="text-base font-semibold text-white">
              {zh ? '胃癌充盈超声智能诊断' : 'Gastric US workstation'}
            </div>
            <div className="text-[11px] leading-relaxed text-gray-500">
              {zh
                ? '本机 / 局域网点选身份即可进入，不用密码。操作会记到该账号。'
                : 'On this machine or LAN, tap an identity. No password. Actions are attributed to that account.'}
            </div>
          </div>
        </div>
        <LocalIdentityButtons
          readers={readers}
          accounts={accounts}
          busy={busy}
          onSelect={(accountId) => void submitLocalIdentity(accountId)}
          zh={zh}
        />
        {error ? <div className="mt-3 text-[11px] text-red-400">{error}</div> : null}
      </div>
    </div>
  );

  const passwordForm = (
    <div className={hadSession
      ? 'flex w-full items-center justify-center'
      : 'flex min-h-screen items-center justify-center bg-[#050506] p-6 max-md:min-h-svh max-md:px-4 max-md:pt-[max(1.5rem,env(safe-area-inset-top))] max-md:pb-[max(1.5rem,env(safe-area-inset-bottom))]'}>
      <form
        onSubmit={(event) => void submitPassword(event)}
        className="w-full max-w-md rounded-2xl border border-white/10 bg-[#111] p-6 shadow-2xl"
      >
        <div className="mb-6 flex items-center gap-3">
          <img
            src="/image.png"
            alt="Union Hospital"
            className="h-12 w-12 shrink-0 rounded-xl border border-white/10 bg-white/5 object-contain p-1.5"
          />
          <div className="min-w-0">
            <div className="text-base font-semibold text-white">
              {zh ? '胃癌充盈超声智能诊断' : 'Gastric US workstation'}
            </div>
            {resumeHint ? (
              <div className="text-[11px] leading-relaxed text-gray-500">{resumeHint}</div>
            ) : (
              <div className="text-[11px] leading-relaxed text-gray-500">
                {zh ? '请输入密码登录。登录后先进入超声阅片。所有操作会记到该账号。' : 'Enter the password. After sign-in you land on the ultrasound viewer. All actions are attributed to that account.'}
              </div>
            )}
          </div>
        </div>

        <label className="block space-y-1">
          <span className="text-[11px] text-gray-400">
            {zh ? '密码' : 'Password'}
          </span>
          <input
            type="password"
            autoFocus
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={zh ? '请输入密码' : 'Enter password'}
            className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-3 text-base text-white outline-none focus:border-blue-500/50 sm:py-2 sm:text-sm"
          />
        </label>

        {error ? <div className="mt-3 text-[11px] text-red-400">{error}</div> : null}

        <button
          type="submit"
          disabled={busy || !password.trim()}
          className="mt-4 min-h-11 w-full rounded-lg bg-blue-600 px-3 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {busy ? (zh ? '登录中…' : 'Signing in…') : (zh ? '登录' : 'Sign in')}
        </button>
      </form>
    </div>
  );

  const form = localHost ? localForm : passwordForm;

  if (!hadSession) return form;
  return (
    <>
      <div className="pointer-events-none select-none" aria-hidden>
        {children}
      </div>
      <div className="fixed inset-0 z-[400000] flex items-center justify-center bg-black/70 p-4 backdrop-blur-[2px]">
        {form}
      </div>
    </>
  );
}
