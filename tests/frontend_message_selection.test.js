const test = require('node:test');
const assert = require('node:assert/strict');

const {
  createSessionCoordinator,
  messageKey,
  findMessageByKey,
} = require('../mail_receiver/static/app_logic.js');

test('selects messages with the same API id by their stable UID identity', () => {
  const first = {
    id: 1,
    account_email: 'first@outlook.com',
    mailbox: 'INBOX',
    uidvalidity: 100,
    uid: 1,
  };
  const second = {
    id: 1,
    account_email: 'second@outlook.com',
    mailbox: 'INBOX',
    uidvalidity: 200,
    uid: 1,
  };

  assert.notEqual(messageKey(first), messageKey(second));
  assert.strictEqual(
    findMessageByKey([first, second], messageKey(second)),
    second,
  );
});

test('distinguishes UID and UIDVALIDITY changes within one mailbox', () => {
  const first = {
    id: 1,
    account_email: 'same@outlook.com',
    mailbox: 'INBOX',
    uidvalidity: 100,
    uid: 1,
  };
  const differentUid = {
    id: 1,
    account_email: 'same@outlook.com',
    mailbox: 'INBOX',
    uidvalidity: 100,
    uid: 2,
  };
  const differentUidvalidity = {
    id: 1,
    account_email: 'same@outlook.com',
    mailbox: 'INBOX',
    uidvalidity: 200,
    uid: 1,
  };
  const messages = [first, differentUid, differentUidvalidity];

  assert.notEqual(messageKey(first), messageKey(differentUid));
  assert.notEqual(messageKey(first), messageKey(differentUidvalidity));
  assert.strictEqual(
    findMessageByKey(messages, messageKey(differentUid)),
    differentUid,
  );
  assert.strictEqual(
    findMessageByKey(messages, messageKey(differentUidvalidity)),
    differentUidvalidity,
  );
});

test('falls back to account-scoped API ids when UID is missing', () => {
  const first = {
    id: 1,
    account_email: 'first@outlook.com',
    mailbox: 'INBOX',
  };
  const second = {
    id: 1,
    account_email: 'second@outlook.com',
    mailbox: 'INBOX',
  };

  assert.notEqual(messageKey(first), messageKey(second));
  assert.strictEqual(
    findMessageByKey([first, second], messageKey(second)),
    second,
  );
  assert.strictEqual(findMessageByKey([first, second], ''), null);
});

test('falls back to API ids when UID is an empty string', () => {
  const first = {
    id: 1,
    account_email: 'same@outlook.com',
    mailbox: 'INBOX',
    uidvalidity: 100,
    uid: '',
  };
  const second = {
    id: 2,
    account_email: 'same@outlook.com',
    mailbox: 'INBOX',
    uidvalidity: 100,
    uid: '',
  };

  assert.equal(
    messageKey(first),
    JSON.stringify(['same@outlook.com', 'INBOX', 'id', '1']),
  );
  assert.notEqual(messageKey(first), messageKey(second));
  assert.strictEqual(
    findMessageByKey([first, second], messageKey(second)),
    second,
  );
});

test('returns null when the message collection is absent', () => {
  const message = {
    id: 1,
    account_email: 'same@outlook.com',
    mailbox: 'INBOX',
  };
  const key = messageKey(message);

  assert.strictEqual(findMessageByKey(null, key), null);
  assert.strictEqual(findMessageByKey(undefined, key), null);
});

test('reset aborts active requests and advances the session revision', () => {
  const controllers = [];
  const coordinator = createSessionCoordinator(() => {
    const controller = {
      aborted: false,
      signal: {},
      abort() {
        this.aborted = true;
      },
    };
    controllers.push(controller);
    return controller;
  });

  const first = coordinator.startRequest();
  const second = coordinator.startRequest();

  assert.equal(first.revision, 0);
  assert.equal(second.revision, 0);
  assert.equal(coordinator.currentRevision(), 0);
  assert.equal(coordinator.isCurrent(first.revision), true);

  assert.equal(coordinator.reset(), 1);
  assert.equal(controllers[0].aborted, true);
  assert.equal(controllers[1].aborted, true);
  assert.equal(coordinator.isCurrent(first.revision), false);
  assert.equal(coordinator.currentRevision(), 1);
  assert.equal(coordinator.reset(), 2);
  assert.equal(coordinator.currentRevision(), 2);
});

test('finished requests are not aborted by a later reset', () => {
  const controllers = [];
  const coordinator = createSessionCoordinator(() => {
    const controller = {
      aborted: false,
      signal: {},
      abort() {
        this.aborted = true;
      },
    };
    controllers.push(controller);
    return controller;
  });

  const finished = coordinator.startRequest();
  coordinator.finishRequest(finished.controller);
  coordinator.reset();

  assert.equal(controllers[0].aborted, false);
  const current = coordinator.startRequest();
  assert.equal(current.revision, 1);
  assert.equal(coordinator.isCurrent(current.revision), true);
});
