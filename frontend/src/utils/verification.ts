import type { VerificationCode, VerificationProvider, Message } from '../types';

const VERIFICATION_KEYWORD_PATTERN = /验证码|验证代码|校验码|动态码|verification|verify|code|otp|passcode|security code/i;

const VERIFICATION_PROVIDERS: VerificationProvider[] = [
  {
    id: 'xai',
    label: 'xAI',
    priority: 100,
    source: 'xAI 确认码',
    identityPatterns: [/x\.ai/i, /xai/i, /grok/i],
    keywords: [/confirmation code/i, /verification code/i, /security code/i],
    codePatterns: [
      {
        pattern: /(?<![A-Z0-9])([A-Z0-9]{3}[-\s][A-Z0-9]{3})(?![A-Z0-9])/i,
        preserveSeparator: true,
        validator: /^[A-Z0-9]{6}$/i,
      },
      {
        pattern: /(?:confirmation code|verification code|security code|验证码)[^A-Z0-9]{0,48}([A-Z0-9][A-Z0-9\s-]{2,10}[A-Z0-9])/i,
        preserveSeparator: true,
        validator: /^[A-Z0-9]{4,8}$/i,
      },
    ],
  },
  {
    id: 'generic',
    label: '通用',
    priority: 0,
    source: '关键词附近',
    keywords: [VERIFICATION_KEYWORD_PATTERN],
    codePatterns: [
      {
        pattern: /(?!\d)(\d[\d\s-]{2,10}\d)(?!\d)/,
        validator: /^\d{4,8}$/,
      },
    ],
    fallbackCodePatterns: [
      {
        pattern: /(?!\d)(\d{4,8})(?!\d)/,
        source: '正文数字',
        confidence: 'medium',
        validator: /^\d{4,8}$/,
      },
    ],
  },
];

function normalizeVerificationCode(value: string, options: { preserveSeparator?: boolean } = {}): string {
  const raw = value.trim();
  if (options.preserveSeparator) {
    return raw.replace(/\s+/g, '-').replace(/-+/g, '-').toUpperCase();
  }
  return raw.replace(/[\s-]+/g, '').toUpperCase();
}

function compactComparableCode(value: string): string {
  return value.replace(/[\s-]+/g, '').toUpperCase();
}

function providerMatchesText(provider: VerificationProvider, text: string): boolean {
  if (!provider.identityPatterns?.length) return true;
  return provider.identityPatterns.some((pattern) => pattern.test(text));
}

function providerKeywordWindows(text: string, provider: VerificationProvider) {
  const windows: Array<{ text: string; source: string; confidence: string }> = [];
  for (const keyword of provider.keywords || []) {
    const match = text.match(keyword);
    if (!match) continue;
    const windowStart = Math.max(0, match.index! - 64);
    const windowEnd = Math.min(text.length, match.index! + 180);
    windows.push({
      text: text.slice(windowStart, windowEnd),
      source: provider.source || '关键词附近',
      confidence: 'high',
    });
  }
  return windows;
}

function codeCandidateFromRule(
  provider: VerificationProvider,
  rule: { pattern: RegExp; preserveSeparator?: boolean; validator?: RegExp; source?: string; confidence?: string },
  windowInfo: { text: string; source: string; confidence: string }
): VerificationCode | null {
  const match = windowInfo.text.match(rule.pattern);
  if (!match) return null;
  const rawCode = match[1] || match[0];
  const code = normalizeVerificationCode(rawCode, rule);
  const comparableCode = compactComparableCode(code);
  if (rule.validator && !rule.validator.test(comparableCode)) return null;
  return {
    code,
    source: rule.source || windowInfo.source,
    confidence: (rule.confidence as 'high' | 'medium' | 'none') || windowInfo.confidence as 'high' | 'medium' | 'none',
    provider: provider.id,
    providerLabel: provider.label,
  };
}

function providerVerificationCandidate(provider: VerificationProvider, text: string, identityText: string = text): VerificationCode | null {
  if (provider.identityPatterns?.length && !providerMatchesText(provider, identityText)) {
    return null;
  }

  for (const windowInfo of providerKeywordWindows(text, provider)) {
    for (const rule of provider.codePatterns || []) {
      const candidate = codeCandidateFromRule(provider, rule, windowInfo);
      if (candidate) return candidate;
    }
  }

  for (const rule of provider.fallbackCodePatterns || []) {
    const candidate = codeCandidateFromRule(provider, rule, {
      text,
      source: rule.source || '正文数字',
      confidence: (rule.confidence as 'high' | 'medium' | 'none') || 'medium',
    });
    if (candidate) return candidate;
  }

  return null;
}

export function extractVerificationCode(mail: Message): VerificationCode {
  const text = [
    mail.subject,
    mail.body_preview,
    mail.sender,
    mail.recipients,
  ]
    .filter(Boolean)
    .join('\n');

  if (!text) {
    return { code: '', source: '未找到可读内容', confidence: 'none' };
  }

  const identityText = [mail.sender, mail.recipients].filter(Boolean).join('\n');

  for (const provider of [...VERIFICATION_PROVIDERS].sort((a, b) => b.priority - a.priority)) {
    const candidate = providerVerificationCandidate(provider, text, identityText);
    if (candidate) return candidate;
  }

  return { code: '', source: '未识别验证码', confidence: 'none' };
}

export function confidenceLabel(confidence: 'high' | 'medium' | 'none'): string {
  switch (confidence) {
    case 'high': return '高置信';
    case 'medium': return '中置信';
    default: return '未识别';
  }
}
