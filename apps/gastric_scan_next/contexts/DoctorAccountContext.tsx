"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  doctorAuthHeaders,
  getDoctorSessionToken,
  setDoctorSessionToken,
} from '@/lib/reader/client-doctor-session';

export type DoctorAccount = {
  account_id: string;
  display_name: string;
  created_at?: string;
  last_seen_at?: string;
};

type DoctorAccountContextValue = {
  ready: boolean;
  account: DoctorAccount | null;
  accounts: DoctorAccount[];
  readerId: string | null;
  refresh: () => Promise<void>;
  login: (accountId: string, pin: string) => Promise<{ ok: boolean; error?: string }>;
  createAccount: (
    accountId: string,
    pin: string,
    displayName?: string,
  ) => Promise<{ ok: boolean; error?: string }>;
  logout: () => Promise<void>;
  authHeaders: (extra?: HeadersInit) => HeadersInit;
};

const DoctorAccountContext = createContext<DoctorAccountContextValue | null>(null);

export function DoctorAccountProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [account, setAccount] = useState<DoctorAccount | null>(null);
  const [accounts, setAccounts] = useState<DoctorAccount[]>([]);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/reader/account', {
        cache: 'no-store',
        headers: doctorAuthHeaders(),
      });
      const data = await response.json() as {
        ok?: boolean;
        authenticated?: boolean;
        account?: DoctorAccount | null;
        accounts?: DoctorAccount[];
      };
      setAccount(data.authenticated && data.account ? data.account : null);
      setAccounts(Array.isArray(data.accounts) ? data.accounts : []);
    } catch {
      setAccount(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (accountId: string, pin: string) => {
    try {
      const response = await fetch('/api/reader/account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'login', account_id: accountId, pin }),
      });
      const data = await response.json() as {
        ok?: boolean;
        error?: string;
        token?: string;
        account?: DoctorAccount;
      };
      if (!response.ok || !data.ok || !data.token) {
        return { ok: false, error: data.error || 'Login failed' };
      }
      setDoctorSessionToken(data.token);
      setAccount(data.account || null);
      await refresh();
      return { ok: true };
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error.message : 'Login failed',
      };
    }
  }, [refresh]);

  const createAccount = useCallback(async (
    accountId: string,
    pin: string,
    displayName?: string,
  ) => {
    try {
      const response = await fetch('/api/reader/account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'create',
          account_id: accountId,
          pin,
          display_name: displayName,
        }),
      });
      const data = await response.json() as {
        ok?: boolean;
        error?: string;
        token?: string;
        account?: DoctorAccount;
      };
      if (!response.ok || !data.ok || !data.token) {
        return { ok: false, error: data.error || 'Create failed' };
      }
      setDoctorSessionToken(data.token);
      setAccount(data.account || null);
      await refresh();
      return { ok: true };
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error.message : 'Create failed',
      };
    }
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await fetch('/api/reader/account', {
        method: 'POST',
        headers: doctorAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ action: 'logout', token: getDoctorSessionToken() }),
      });
    } catch {
      // Local logout still proceeds.
    }
    setDoctorSessionToken(null);
    setAccount(null);
    await refresh();
  }, [refresh]);

  const authHeaders = useCallback((extra: HeadersInit = {}) => doctorAuthHeaders(extra), []);

  const value = useMemo<DoctorAccountContextValue>(() => ({
    ready,
    account,
    accounts,
    readerId: account?.account_id || null,
    refresh,
    login,
    createAccount,
    logout,
    authHeaders,
  }), [account, accounts, authHeaders, createAccount, login, logout, ready, refresh]);

  return (
    <DoctorAccountContext.Provider value={value}>
      {children}
    </DoctorAccountContext.Provider>
  );
}

export function useDoctorAccount() {
  const value = useContext(DoctorAccountContext);
  if (!value) {
    throw new Error('useDoctorAccount must be used within DoctorAccountProvider');
  }
  return value;
}
