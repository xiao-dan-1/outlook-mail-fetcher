import React from 'react';
import { useAppStore } from '../stores/appStore';

export const LogPanel: React.FC = () => {
  const logs = useAppStore((s) => s.logs);
  const logDrawerOpen = useAppStore((s) => s.logDrawerOpen);
  const setLogDrawerOpen = useAppStore((s) => s.setLogDrawerOpen);
  const clearLogs = useAppStore((s) => s.clearLogs);

  const levelLabels: Record<string, string> = {
    info: '信息',
    ok: '成功',
    fail: '错误',
    warning: '警告',
  };

  const levelClasses: Record<string, string> = {
    info: 'info',
    ok: 'ok',
    fail: 'fail',
    warning: 'warning',
  };

  return (
    <section className={`panel run-log-panel log-drawer ${logDrawerOpen ? 'is-open' : 'is-collapsed'}`}>
      <div className="section-title">
        <div>
          <h2>运行日志</h2>
        </div>
        <div className="log-drawer-actions">
          <button
            type="button"
            className="button ghost"
            onClick={clearLogs}
            disabled={logs.length === 0}
          >
            清空记录
          </button>
          <button
            type="button"
            className="button ghost"
            onClick={() => setLogDrawerOpen(!logDrawerOpen)}
          >
            {logDrawerOpen ? '收起' : '展开'}
          </button>
        </div>
      </div>
      <div className="activity-frame">
        <div className="activity-toolbar">
          <span className="activity-pulse" aria-hidden="true"></span>
          <strong>会话事件</strong>
          <small className="activity-hint">最新优先</small>
        </div>
        <div className="run-log activity-log" role="log" aria-live="polite">
          {logs.length === 0 ? (
            <div className="activity-event empty">暂无运行记录</div>
          ) : (
            logs.map((log) => (
              <div
                key={log.id}
                className={`activity-event ${levelClasses[log.level] || 'info'}`}
                role="listitem"
              >
                <div className="activity-event-body">
                  <div className="activity-event-meta">
                    <span className="activity-event-kind">{levelLabels[log.level] || log.level}</span>
                    <strong className="activity-event-account">{log.context}</strong>
                    <time className="activity-event-time">
                      {log.timestamp.toLocaleTimeString()}
                    </time>
                  </div>
                  <span className="activity-event-message">{log.detail}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
};
