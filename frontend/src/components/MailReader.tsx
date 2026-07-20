import React from 'react';
import { useAppStore } from '../stores/appStore';
import { formatMailDate, senderDisplayName, senderAddress, senderInitial } from '../utils/format';
import { extractVerificationCode, confidenceLabel } from '../utils/verification';

export const MailReader: React.FC = () => {
  const messagesByAccount = useAppStore((s) => s.messagesByAccount);
  const activeAccountEmail = useAppStore((s) => s.activeAccountEmail);
  const selectedMessageKey = useAppStore((s) => s.selectedMessageKey);

  const messages = React.useMemo(() => {
    if (activeAccountEmail) {
      return messagesByAccount.get(activeAccountEmail) || [];
    }
    return Array.from(messagesByAccount.values()).flat();
  }, [messagesByAccount, activeAccountEmail]);

  const mail = React.useMemo(() => {
    if (!selectedMessageKey) return null;
    return messages.find((m) => `${m.account_email}-${m.uid}` === selectedMessageKey) || null;
  }, [messages, selectedMessageKey]);

  if (!mail) {
    return (
      <article className="mail-detail">
        <div className="mail-detail-placeholder">
          <strong>邮件详情</strong>
          <span>选中邮件后显示正文和验证码摘要。</span>
        </div>
      </article>
    );
  }

  const verification = extractVerificationCode(mail);
  const senderName = senderDisplayName(mail.sender);
  const senderAddr = senderAddress(mail.sender);
  const initial = senderInitial(mail.sender);
  const displayDate = formatMailDate(mail.sent_at);

  return (
    <article className="mail-detail">
      <div className="detail-header">
        <div>
          <h2>{mail.subject || '(无主题)'}</h2>
          <div className="meta detail-meta-line">
            <span>{senderName}</span>
            <span>{displayDate}</span>
          </div>
        </div>
        <div className="detail-actions">
          <span className="pill">{mail.mailbox}</span>
        </div>
      </div>

      <section className="verification-card" aria-label="验证码摘要">
        <div className="verification-card-copy">
          <span className="verification-eyebrow">验证码摘要</span>
          <strong className="verification-code-value">
            {verification.code || '未识别验证码'}
          </strong>
          <span className="verification-source">
            {verification.providerLabel ? `${verification.providerLabel} · ` : ''}
            {verification.source} · {confidenceLabel(verification.confidence)}
          </span>
        </div>
        {verification.code && (
          <button type="button" className="button secondary">
            复制验证码
          </button>
        )}
      </section>

      <div className="detail-summary-bar" aria-label="邮件摘要">
        <div className="detail-summary-item">
          <span>账号</span>
          <strong>{mail.account_email || '-'}</strong>
        </div>
        <div className="detail-summary-item">
          <span>目录</span>
          <strong>{mail.mailbox || '-'}</strong>
        </div>
        <div className="detail-summary-item">
          <span>时间</span>
          <strong>{displayDate}</strong>
        </div>
      </div>

      <div className="detail-meta-card sender-identity-card" aria-label="发件人身份信息">
        <div className="sender-avatar" aria-hidden="true">{initial}</div>
        <div className="sender-copy">
          <div className="sender-copy-head">
            <strong>{senderName}</strong>
            <span>{displayDate}</span>
          </div>
          <div className="sender-address">{senderAddr}</div>
        </div>
      </div>

      <section className="body-card">
        <div className="body-card-title">正文预览</div>
        <pre className="body-preview">{mail.body_preview || '没有可读正文预览。'}</pre>
      </section>
    </article>
  );
};
