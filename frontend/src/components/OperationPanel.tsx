import React, { useCallback, useState } from 'react';
import { useAppStore } from '../stores/appStore';
import { useWebSocketFetch } from '../hooks/useWebSocket';

export const OperationPanel: React.FC = () => {
  const busy = useAppStore((s) => s.busy);
  const fetchScope = useAppStore((s) => s.fetchScope);
  const setFetchScope = useAppStore((s) => s.setFetchScope);
  const accounts = useAppStore((s) => s.accounts);
  const accountText = useAppStore((s) => s.accountText);
  const setBusy = useAppStore((s) => s.setBusy);
  const addLog = useAppStore((s) => s.addLog);
  const addMessages = useAppStore((s) => s.addMessages);
  const setAccountStatus = useAppStore((s) => s.setAccountStatus);

  const [progress, setProgress] = useState({ total: 0, completed: 0, failed: 0 });

  const handleProgress = useCallback((data: any) => {
    setProgress({
      total: data.total || 0,
      completed: data.completed || 0,
      failed: data.failed || 0,
    });

    if (data.status === 'progress' && data.account) {
      setAccountStatus(data.account, {
        kind: 'fetch',
        fetched: data.messages || 0,
      });
    } else if (data.status === 'account_failed' && data.account) {
      setAccountStatus(data.account, {
        kind: 'fail',
        error: data.error || 'Unknown error',
      });
    }
  }, [setAccountStatus]);

  const handleComplete = useCallback((data: any) => {
    setBusy(false);
    addLog({
      id: Math.random().toString(36).substring(2, 9),
      timestamp: new Date(),
      level: 'ok',
      context: '拉取完成',
      detail: `完成 ${data.completed}/${data.total} 个账号，失败 ${data.failed} 个`,
    });
  }, [setBusy, addLog]);

  const handleError = useCallback((error: string) => {
    setBusy(false);
    addLog({
      id: Math.random().toString(36).substring(2, 9),
      timestamp: new Date(),
      level: 'fail',
      context: '拉取失败',
      detail: error,
    });
  }, [setBusy, addLog]);

  const { isConnected, isFetching, startFetch } = useWebSocketFetch({
    onProgress: handleProgress,
    onComplete: handleComplete,
    onError: handleError,
  });

  const handleFetch = useCallback(() => {
    if (!accountText.trim()) return;
    
    setBusy(true);
    setProgress({ total: accounts.length, completed: 0, failed: 0 });
    
    startFetch({
      account_text: accountText,
      mailbox: 'INBOX',
      limit: 1,
      scope: fetchScope,
    });
  }, [accountText, accounts.length, fetchScope, setBusy, startFetch]);

  return (
    <section className="panel operation-panel">
      <div className="section-title operation-panel-title">
        <div>
          <h2>控制台</h2>
        </div>
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : ''}`} />
          {isConnected ? 'WebSocket 已连接' : 'WebSocket 未连接'}
        </div>
      </div>

      {isFetching && (
        <div className="progress-bar">
          <div 
            className="progress-fill"
            style={{ 
              width: `${progress.total > 0 ? (progress.completed / progress.total) * 100 : 0}%` 
            }}
          />
          <span className="progress-text">
            {progress.completed}/{progress.total} ({progress.failed} 失败)
          </span>
        </div>
      )}

      <div className="operation-command-row">
        <div className="operation-command-actions">
          <div className="action-stack">
            <button
              type="button"
              className={`button primary ${busy ? 'is-busy' : ''}`}
              onClick={handleFetch}
              disabled={busy || accounts.length === 0 || !isConnected}
              aria-busy={busy}
            >
              {busy ? (
                <>
                  <span className="button-spinner" aria-hidden="true"></span>
                  <span>拉取中... {progress.completed}/{progress.total}</span>
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
