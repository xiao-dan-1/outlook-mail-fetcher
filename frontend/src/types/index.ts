// Types for the Outlook Mail Fetcher application

export interface Account {
  line: number;
  email: string;
  password: string;
  client_id: string;
  refresh_token: string;
}

export interface AppConfig {
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
}

export interface FetchOptions {
  account_text: string;
  mailbox?: string;
  limit?: number;
  account?: string;
  include_raw?: boolean;
  imap_host?: string;
  imap_port?: number;
  imap_timeout?: number;
  token_endpoint?: string;
  token_timeout?: number;
  scope?: string;
}

export interface Message {
  id: number;
  account_email: string;
  mailbox: string;
  uid: string;
  uidvalidity: string;
  message_id: string;
  subject: string;
  sender: string;
  recipients: string;
  sent_at: string;
  body_preview: string;
  raw_message_complete: boolean;
  raw_message?: string;
  raw_message_base64?: string;
}

export interface FetchResultRow {
  email: string;
  ok: boolean;
  fetched?: number;
  elapsed_ms?: number;
  error?: string | null;
  stage?: string;
  timings?: Record<string, number>;
  raw_bytes?: number;
  downloaded_bytes?: number;
  message_count?: number;
}

export interface FetchResponse {
  account_file: string | null;
  accounts: number;
  fetched: number;
  failed: number;
  rows: FetchResultRow[];
  messages: Message[];
}

export interface AccountStatus {
  kind: 'busy' | 'fetch' | 'fail' | 'ready';
  fetched?: number;
  elapsed_ms?: number;
  stage?: string;
  error?: string;
  raw_bytes?: number;
  downloaded_bytes?: number;
  message_count?: number;
  timings?: Record<string, number>;
}

export interface VerificationCode {
  code: string;
  source: string;
  confidence: 'high' | 'medium' | 'none';
  provider?: string;
  providerLabel?: string;
}

export interface VerificationProvider {
  id: string;
  label: string;
  priority: number;
  source: string;
  identityPatterns?: RegExp[];
  keywords: RegExp[];
  codePatterns: CodePattern[];
  fallbackCodePatterns?: CodePattern[];
}

export interface CodePattern {
  pattern: RegExp;
  preserveSeparator?: boolean;
  validator?: RegExp;
  source?: string;
  confidence?: string;
}

export interface LogEntry {
  id: string;
  timestamp: Date;
  level: 'info' | 'ok' | 'fail' | 'warning';
  context: string;
  detail: string;
}

export type FetchScope = 'selected' | 'all';
export type Theme = 'light' | 'dark';
