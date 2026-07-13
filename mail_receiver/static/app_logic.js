(function (globalScope) {
  'use strict';

  function messageKey(message) {
    var safeMessage = message || {};
    var accountEmail = String(safeMessage.account_email ?? '').toLowerCase();
    var uid = String(safeMessage.uid ?? '');
    var uidvalidity = String(safeMessage.uidvalidity ?? '');
    var mailbox = String(safeMessage.mailbox ?? '');
    var identity = uid
      ? ['uid', uidvalidity, uid]
      : ['id', String(safeMessage.id ?? '')];

    return JSON.stringify([accountEmail, mailbox].concat(identity));
  }

  function findMessageByKey(messages, key) {
    if (!key) {
      return null;
    }

    return (messages || []).find(function (message) {
      return messageKey(message) === key;
    }) || null;
  }

  var api = {
    messageKey: messageKey,
    findMessageByKey: findMessageByKey,
  };

  globalScope.MailReceiverLogic = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
