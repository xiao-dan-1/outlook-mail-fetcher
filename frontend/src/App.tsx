import React, { useEffect } from 'react';
import { useAppStore } from './stores/appStore';
import { getConfig } from './api/client';
import { AccountInput } from './components/AccountInput';
import { OperationPanel } from './components/OperationPanel';
import { MailList } from './components/MailList';
import { MailReader } from './components/MailReader';
import { LogPanel } from './components/LogPanel';
import { ThemeToggle } from './components/ThemeToggle';
import './App.css';

function App() {
  const theme = useAppStore((s) => s.theme);
  const setConfig = useAppStore((s) => s.setConfig);
  const config = useAppStore((s) => s.config);

  useEffect(() => {
    getConfig().then((data) => {
      setConfig(data);
    }).catch((err) => {
      console.error('Failed to load config:', err);
    });
  }, [setConfig]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  return (
    <div className="app-shell" data-theme={theme}>
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark">
            <svg className="icon" aria-hidden="true" viewBox="0 0 24 24">
              <path d="M4.5 6.75A2.25 2.25 0 0 1 6.75 4.5h10.5a2.25 2.25 0 0 1 2.25 2.25v10.5a2.25 2.25 0 0 1-2.25 2.25H6.75a2.25 2.25 0 0 1-2.25-2.25z" />
              <path d="m5.25 8.25 6.75 4.5 6.75-4.5" />
            </svg>
          </div>
          <div>
            <h1>Outlook 邮件</h1>
            <p className="brand-subtitle">
              <span>账号校验、IMAP 拉取与本次结果审阅</span>
              {config?.version && (
                <span className="version-badge">v{config.version}</span>
              )}
            </p>
          </div>
        </div>
        <div className="header-actions">
          <ThemeToggle />
          <div className="status-module is-ready" data-status="ready">
            <span className="status-orb"></span>
            <div>
              <span>系统状态</span>
              <strong>准备就绪</strong>
            </div>
          </div>
        </div>
      </header>

      <main className="workspace dashboard-grid">
        <div className="control-column command-center">
          <AccountInput />
          <OperationPanel />
        </div>

        <div className="review-column mail-review-stage">
          <section className="panel result-panel">
            <div className="section-title">
              <div>
                <h2>邮件结果</h2>
              </div>
            </div>
            <div className="mail-workbench">
              <MailList />
              <div className="mail-reader-shell">
                <MailReader />
              </div>
            </div>
          </section>
        </div>
      </main>

      <LogPanel />
    </div>
  );
}

export default App;
