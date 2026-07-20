import React from 'react';
import { FixedSizeList as List } from 'react-window';
import { useAppStore } from '../stores/appStore';
import { formatMailDate, senderDisplayName, senderInitial } from '../utils/format';
import type { Message } from '../types';

interface MailRowData {
  messages: Message[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
}

const MailRow = React.memo(function MailRow({
  index,
  style,
  data,
}: {
  index: number;
  style: React.CSSProperties;
  data: MailRowData;
}) {
  const mail = data.messages[index];
  const key = `${mail.account_email}-${mail.uid}`;
  const isSelected = key === data.selectedKey;
  const senderName = senderDisplayName(mail.sender);
  const initial = senderInitial(mail.sender);
  const displayDate = formatMailDate(mail.sent_at);

  return (
    <button
      type="button"
      className={`mail-row ${isSelected ? 'active' : ''}`}
      style={style}
      onClick={() => data.onSelect(key)}
      role="option"
      aria-selected={isSelected}
    >
      <div className="mail-row-main">
        <span className="mail-row-avatar" aria-hidden="true">{initial}</span>
        <span className="mail-row-title-group">
          <span className="mail-row-title-line">
            <span className="mail-row-status-dot" aria-hidden="true"></span>
            <strong className="subject">{mail.subject || '(无主题)'}</strong>
          </span>
          <span className="mail-row-meta-line">
            <span className="mail-row-sender">{senderName}</span>
            <span className="mail-row-account">{mail.account_email}</span>
          </span>
          <span className="mail-row-preview">{mail.body_preview?.slice(0, 100)}</span>
        </span>
        <span className="mail-time">{displayDate}</span>
      </div>
    </button>
  );
});

export const MailList: React.FC = () => {
  const messagesByAccount = useAppStore((s) => s.messagesByAccount);
  const activeAccountEmail = useAppStore((s) => s.activeAccountEmail);
  const selectedMessageKey = useAppStore((s) => s.selectedMessageKey);
  const selectMessage = useAppStore((s) => s.selectMessage);

  const messages = React.useMemo(() => {
    if (activeAccountEmail) {
      return messagesByAccount.get(activeAccountEmail) || [];
    }
    return Array.from(messagesByAccount.values()).flat();
  }, [messagesByAccount, activeAccountEmail]);

  const handleSelect = React.useCallback((key: string) => {
    selectMessage(key);
  }, [selectMessage]);

  if (messages.length === 0) {
    return (
      <div className="mail-list empty">
        <div className="mail-empty-panel">
          <div className="mail-empty-copy">
            <strong>等待邮件</strong>
            <span>拉取后显示邮件与验证码。</span>
          </div>
        </div>
      </div>
    );
  }

  const itemData: MailRowData = {
    messages,
    selectedKey: selectedMessageKey,
    onSelect: handleSelect,
  };

  return (
    <div className="mail-list-shell">
      <List
        height={600}
        itemCount={messages.length}
        itemSize={72}
        width="100%"
        itemData={itemData}
      >
        {MailRow as any}
      </List>
    </div>
  );
};
