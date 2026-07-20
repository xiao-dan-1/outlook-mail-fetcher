export function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export function normalizeReadableText(value: string): string {
  return value
    .replace(/\u00a0/g, ' ')
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n[ \t]+/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function formatMailDate(value: string): string {
  const raw = value.trim();
  if (!raw) return '-';
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return raw;
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

export function formatElapsedTime(elapsedMs: number): string {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return '耗时未知';
  if (elapsedMs < 1000) return `${Math.round(elapsedMs)}ms`;
  return `${(elapsedMs / 1000).toFixed(elapsedMs < 10000 ? 1 : 0)}s`;
}

export function formatBytes(byteCount: number): string {
  if (!Number.isFinite(byteCount) || byteCount < 0) return '大小未知';
  if (byteCount < 1024) return `${Math.round(byteCount)}B`;
  const units = ['KB', 'MB', 'GB'];
  let scaled = byteCount / 1024;
  let unitIndex = 0;
  while (scaled >= 1024 && unitIndex < units.length - 1) {
    scaled /= 1024;
    unitIndex += 1;
  }
  return `${scaled.toFixed(scaled < 10 ? 1 : 0)}${units[unitIndex]}`;
}

export function senderDisplayName(value: string): string {
  const raw = value.trim();
  if (!raw) return '未知发件人';
  const match = raw.match(/^(.+?)\s*<[^>]+>$/);
  return (match?.[1] || raw).replace(/^["']|["']$/g, '').trim() || raw;
}

export function senderAddress(value: string): string {
  const raw = value.trim();
  if (!raw) return '-';
  const match = raw.match(/<([^>]+)>/);
  return (match?.[1] || raw).replace(/^mailto:/i, '').trim() || raw;
}

export function senderInitial(value: string): string {
  const displayName = senderDisplayName(value).replace(/^[^A-Za-z0-9\u4e00-\u9fff]+/, '').trim();
  return (Array.from(displayName)[0] || '邮').toUpperCase();
}

export function firstReadableValue(...values: unknown[]): string {
  for (const value of values) {
    const text = String(value ?? '').trim();
    if (text) return text;
  }
  return '';
}
