import React, { useState, useCallback, useEffect } from 'react';
import { useAppStore } from '../stores/appStore';
import { useAccounts } from '../hooks/useMail';

export const AccountInput: React.FC = () => {
  const [input, setInput] = useState('');
  const { parseAccounts, busy } = useAccounts();
  const accountPrivacy = useAppStore((s) => s.accountPrivacy);
  const setAccountPrivacy = useAppStore((s) => s.setAccountPrivacy);
  const accounts = useAppStore((s) => s.accounts);

  const handleParse = useCallback(async () => {
    if (!input.trim()) return;
    try {
      await parseAccounts(input);
    } catch {
      // Error handled in hook
    }
  }, [input, parseAccounts]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleParse();
    }
  }, [handleParse]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (input.trim()) {
        handleParse();
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [input, handleParse]);

  const inspectResult = React.useMemo(() => {
    const lines = input.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    let valid = 0;
    let invalid = 0;
    for (const line of lines) {
      const parts = line.split('----').map((p) => p.trim());
      const looksValid = parts.length === 4 && parts[0].includes('@') && parts.slice(1).every(Boolean);
      if (looksValid) valid++;
      else invalid++;
    }
    return { total: lines.length, valid, invalid, quality: lines.length === 0 ? 0 : Math.round((valid / lines.length) * 100) };
  }, [input]);

  return (
    <section className="panel account-input-panel">
      <div className="section-title">
        <div>
          <h2>账号管理</h2>
        </div>
        <div className="section-actions">
          <button
            type="button"
            className="button ghost privacy-toggle"
            aria-pressed={accountPrivacy}
            onClick={() => setAccountPrivacy(!accountPrivacy)}
          >
            {accountPrivacy ? '显示原文' : '隐藏敏感字段'}
          </button>
          <span className="count-chip">{accounts.length} 个账号</span>
        </div>
      </div>

      <label className="field-label">
        <span>粘贴账号</span>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="none"
          autoCorrect="off"
          wrap="off"
          placeholder="邮箱----密码----客户端 ID----刷新令牌"
          disabled={busy}
        />
      </label>

      {inspectResult.total > 0 && (
        <div className="input-quality">
          <div className="quality-meter" aria-hidden="true">
            <span style={{ width: `${inspectResult.quality}%` }}></span>
          </div>
          <div className="quality-copy">
            <span className={`quality-chip is-${inspectResult.invalid > 0 ? 'warn' : 'good'}`}>
              {inspectResult.valid} / {inspectResult.total} 行有效
            </span>
            <span>{inspectResult.invalid > 0 ? `${inspectResult.invalid} 行格式需要检查` : '格式完整'}</span>
          </div>
        </div>
      )}
    </section>
  );
};
