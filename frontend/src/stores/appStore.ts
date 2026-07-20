import { create } from 'zustand';
import type { Account, Message, AccountStatus, LogEntry, FetchScope, Theme, FetchResultRow } from '../types';

interface AppState {
  // Config
  config: {
    version: string;
    account_file: string | null;
    defaults: {
      mailbox: string;
      limit: number;
      imap_host: string;
      imap_port: number;
      imap_timeout: number;
      token_endpoint: string;
      token_timeout: number;
      scope: string;
    };
  } | null;

  // Accounts
  accounts: Account[];
  accountText: string;
  parsedText: string;
  accountPrivacy: boolean;

  // Messages
  messagesByAccount: Map<string, Message[]>;
  selectedMessageKey: string | null;
  activeAccountEmail: string;
  selectedAccountEmail: string;

  // Status
  accountStatus: Map<string, AccountStatus>;
  failedRows: FetchResultRow[];
  busy: boolean;

  // UI
  fetchScope: FetchScope;
  theme: Theme;
  logs: LogEntry[];
  logDrawerOpen: boolean;

  // Actions
  setConfig: (config: AppState['config']) => void;
  setAccounts: (accounts: Account[], parsedText: string) => void;
  setAccountText: (text: string) => void;
  setAccountPrivacy: (privacy: boolean) => void;
  addMessages: (accountEmail: string, messages: Message[]) => void;
  setMessagesByAccount: (messagesByAccount: Map<string, Message[]>) => void;
  selectMessage: (key: string | null) => void;
  setActiveAccount: (email: string) => void;
  setSelectedAccount: (email: string) => void;
  setAccountStatus: (email: string, status: AccountStatus) => void;
  setFailedRows: (rows: FetchResultRow[]) => void;
  addFailedRow: (row: FetchResultRow) => void;
  removeFailedRow: (email: string) => void;
  setBusy: (busy: boolean) => void;
  setFetchScope: (scope: FetchScope) => void;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
  addLog: (entry: LogEntry) => void;
  clearLogs: () => void;
  setLogDrawerOpen: (open: boolean) => void;
  resetSession: () => void;
  resetAll: () => void;
}

const generateId = () => Math.random().toString(36).substring(2, 9);

export const useAppStore = create<AppState>((set) => ({
  // Initial state
  config: null,
  accounts: [],
  accountText: '',
  parsedText: '',
  accountPrivacy: true,
  messagesByAccount: new Map(),
  selectedMessageKey: null,
  activeAccountEmail: '',
  selectedAccountEmail: '',
  accountStatus: new Map(),
  failedRows: [],
  busy: false,
  fetchScope: 'selected',
  theme: (localStorage.getItem('mailReceiverTheme') as Theme) || 'light',
  logs: [],
  logDrawerOpen: false,

  // Actions
  setConfig: (config) => set({ config }),

  setAccounts: (accounts, parsedText) => set({
    accounts,
    parsedText,
    accountStatus: new Map(),
    failedRows: [],
  }),

  setAccountText: (text) => set({ accountText: text }),

  setAccountPrivacy: (privacy) => set({ accountPrivacy: privacy }),

  addMessages: (accountEmail, messages) => set((state) => {
    const newMap = new Map(state.messagesByAccount);
    const existing = newMap.get(accountEmail) || [];
    newMap.set(accountEmail, [...existing, ...messages]);
    return { messagesByAccount: newMap };
  }),

  setMessagesByAccount: (messagesByAccount) => set({ messagesByAccount }),

  selectMessage: (key) => set({ selectedMessageKey: key }),

  setActiveAccount: (email) => set({ activeAccountEmail: email }),

  setSelectedAccount: (email) => set({ selectedAccountEmail: email }),

  setAccountStatus: (email, status) => set((state) => {
    const newMap = new Map(state.accountStatus);
    newMap.set(email, status);
    return { accountStatus: newMap };
  }),

  setFailedRows: (rows) => set({ failedRows: rows }),

  addFailedRow: (row) => set((state) => ({
    failedRows: [...state.failedRows, row],
  })),

  removeFailedRow: (email) => set((state) => ({
    failedRows: state.failedRows.filter((r) => r.email !== email),
  })),

  setBusy: (busy) => set({ busy }),

  setFetchScope: (scope) => set({ fetchScope: scope }),

  toggleTheme: () => set((state) => {
    const next = state.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('mailReceiverTheme', next);
    return { theme: next };
  }),

  setTheme: (theme) => {
    localStorage.setItem('mailReceiverTheme', theme);
    set({ theme });
  },

  addLog: (entry) => set((state) => ({
    logs: [entry, ...state.logs],
  })),

  clearLogs: () => set({ logs: [] }),

  setLogDrawerOpen: (open) => set({ logDrawerOpen: open }),

  resetSession: () => set({
    messagesByAccount: new Map(),
    selectedMessageKey: null,
    activeAccountEmail: '',
    accountStatus: new Map(),
    failedRows: [],
  }),

  resetAll: () => set({
    accounts: [],
    accountText: '',
    parsedText: '',
    messagesByAccount: new Map(),
    selectedMessageKey: null,
    activeAccountEmail: '',
    selectedAccountEmail: '',
    accountStatus: new Map(),
    failedRows: [],
    busy: false,
    fetchScope: 'selected',
    logs: [],
  }),
}));
