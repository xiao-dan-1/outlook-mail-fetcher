import React, { useCallback } from 'react';
import { useAppStore } from '../stores/appStore';
import { useMailFetch } from '../hooks/useMail';

export const OperationPanel: React.FC = () => {
  const busy = useAppStore((s) => s.busy);
  const fetchScope = useAppStore((s) => s.fetchScope);
  const setFetchScope = useAppStore((s) => s.setFetchScope);
  const accounts = useAppStore((s) => s.accounts);
  const accountText = useAppStore((s) => s.accountText);
  const { fetchAll } = useMailFetch();

  const handleFetch = useCallback(async () => {
    if (!accountText.trim()) return;
    try {
      await fetchAll({
        account_text: accountText,
        mailbox: 'INBOX',
        limit: 1,
      });
    } catch {
      // Error handled in hook
    }
  }, [accountText, fetchAll]);

  return (
    <section className="panel operation-panel">
      <div className="section-title operation-panel-title">
        <div>
          <h2>控制台</h2>
        </div>
      </div>

      <div className="operation-command-row">
        <div className="operation-command-actions">
          <div className="action-stack">
            <button
              type="button"
              className={`button primary ${busy ? 'is-busy' : ''}`}
              onClick={handleFetch}
              disabled={busy || accounts.length === 0}
              aria-busy={busy}
            >
              {busy ? (
                <>
                  <span className="button-spinner" aria-hidden="true"></span>
                  <span>拉取中...</span>
                </>
              ) : (
                <>
                  <svg className="icon" aria-hidden="true" viewBox="0 0 24 24">
                    <path d="M8.25 5.75v12.5l10-6.25z" />
                  </svg>
                  <span>开始拉取邮件</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="scope-toggle-group" role="group" aria-label="拉取范围">
        <button
          type="button"
          className={`scope-toggle ${fetchScope === 'selected' ? 'is-active' : ''}`}
          aria-pressed={fetchScope === 'selected'}
          onClick={() => setFetchScope('selected')}
          disabled={busy}
        >
          选中账号
        </button>
        <button
          type="button"
          className={`scope-toggle ${fetchScope === 'all' ? 'is-active' : ''}`}
          aria-pressed={fetchScope === 'all'}
          onClick={() => setFetchScope('all')}
          disabled={busy}
        >
          全部账号
        </button>
      </div>
    </section>
  );
};
