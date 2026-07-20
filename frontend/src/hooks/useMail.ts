import { useCallback, useRef } from 'react';
import { useAppStore } from '../stores/appStore';
import { fetchMail as fetchMailApi, inspectAccounts } from '../api/client';
import type { FetchOptions, FetchResultRow } from '../types';

function generateId(): string {
  return Math.random().toString(36).substring(2, 9);
}

export function useAccounts() {
  const { accounts, accountText, parsedText, busy } = useAppStore();
  const setAccounts = useAppStore((s) => s.setAccounts);
  const setAccountText = useAppStore((s) => s.setAccountText);
  const setBusy = useAppStore((s) => s.setBusy);
  const addLog = useAppStore((s) => s.addLog);

  const parseAccounts = useCallback(async (text: string) => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const data = await inspectAccounts(text);
      setAccounts(data.accounts, text);
      addLog({
        id: generateId(),
        timestamp: new Date(),
        level: 'ok',
        context: '账号解析',
        detail: `解析完成：${data.count} 个账号`,
      });
      return data;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      addLog({
        id: generateId(),
        timestamp: new Date(),
        level: 'fail',
        context: '账号解析',
        detail: message,
      });
      throw error;
    } finally {
      setBusy(false);
    }
  }, [setAccounts, setBusy, addLog]);

  return {
    accounts,
    accountText,
    parsedText,
    busy,
    setAccountText,
    parseAccounts,
  };
}

export function useMailFetch() {
  const {
    accounts,
    fetchScope,
    selectedAccountEmail,
    busy,
  } = useAppStore();

  const setBusy = useAppStore((s) => s.setBusy);
  const addMessages = useAppStore((s) => s.addMessages);
  const setAccountStatus = useAppStore((s) => s.setAccountStatus);
  const setFailedRows = useAppStore((s) => s.setFailedRows);
  const addLog = useAppStore((s) => s.addLog);
  const failedRows = useAppStore((s) => s.failedRows);

  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchAll = useCallback(async (options: FetchOptions) => {
    const accountsToFetch = fetchScope === 'all'
      ? accounts
      : accounts.filter((a) => a.email === selectedAccountEmail);

    if (accountsToFetch.length === 0) return;

    setBusy(true);
    abortControllerRef.current = new AbortController();

    const newFailedRows: FetchResultRow[] = [...failedRows];

    try {
      // Parallel fetch with Promise.all
      const promises = accountsToFetch.map(async (account) => {
        setAccountStatus(account.email, { kind: 'busy' });

        try {
          const payload: FetchOptions = {
            ...options,
            account_text: options.account_text,
            account: account.email,
          };

          const data = await fetchMailApi(payload);

          // Process results
          data.rows.forEach((row) => {
            if (row.ok) {
              setAccountStatus(row.email, {
                kind: 'fetch',
                fetched: row.fetched,
                elapsed_ms: row.elapsed_ms,
                raw_bytes: row.raw_bytes,
                timings: row.timings,
              });
              addLog({
                id: generateId(),
                timestamp: new Date(),
                level: 'ok',
                context: row.email,
                detail: `已拉取 ${row.fetched} 封邮件，耗时 ${row.elapsed_ms}ms`,
              });
            } else {
              setAccountStatus(row.email, {
                kind: 'fail',
                stage: row.stage,
                error: row.error || 'Unknown error',
                elapsed_ms: row.elapsed_ms,
              });
              newFailedRows.push(row);
              addLog({
                id: generateId(),
                timestamp: new Date(),
                level: 'fail',
                context: row.email,
                detail: row.error || '拉取失败',
              });
            }
          });

          // Add messages
          data.messages.forEach((msg) => {
            addMessages(msg.account_email, [msg]);
          });

          return data;
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          setAccountStatus(account.email, {
            kind: 'fail',
            stage: 'request',
            error: message,
          });
          const failedRow: FetchResultRow = {
            email: account.email,
            ok: false,
            error: message,
            stage: 'request',
          };
          newFailedRows.push(failedRow);
          addLog({
            id: generateId(),
            timestamp: new Date(),
            level: 'fail',
            context: account.email,
            detail: message,
          });
          throw error;
        }
      });

      await Promise.all(promises);
      setFailedRows(newFailedRows);
    } finally {
      setBusy(false);
      abortControllerRef.current = null;
    }
  }, [accounts, fetchScope, selectedAccountEmail, failedRows, setBusy, addMessages, setAccountStatus, setFailedRows, addLog]);

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort();
  }, []);

  return {
    fetchAll,
    cancel,
    busy,
  };
}

export function useTheme() {
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const setTheme = useAppStore((s) => s.setTheme);

  return { theme, toggleTheme, setTheme };
}

export function useLogs() {
  const logs = useAppStore((s) => s.logs);
  const addLog = useAppStore((s) => s.addLog);
  const clearLogs = useAppStore((s) => s.clearLogs);
  const logDrawerOpen = useAppStore((s) => s.logDrawerOpen);
  const setLogDrawerOpen = useAppStore((s) => s.setLogDrawerOpen);

  return { logs, addLog, clearLogs, logDrawerOpen, setLogDrawerOpen };
}
