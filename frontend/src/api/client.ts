import type { AppConfig, FetchOptions, FetchResponse, Account } from '../types';

const API_BASE = '';

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data as T;
}

export async function getConfig(): Promise<AppConfig> {
  return api<AppConfig>('/api/config');
}

export async function inspectAccounts(accountText: string): Promise<{ count: number; accounts: Account[] }> {
  return api('/api/accounts', {
    method: 'POST',
    body: JSON.stringify({ account_text: accountText }),
  });
}

export async function fetchMail(options: FetchOptions): Promise<FetchResponse> {
  return api('/api/fetch', {
    method: 'POST',
    body: JSON.stringify(options),
  });
}
