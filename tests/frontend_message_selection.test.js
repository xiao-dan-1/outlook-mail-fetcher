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

test('reset isolates reentrant requests and continues after abort failures', () => {
  const abortAttempts = [];
  let coordinator;
  let reentrantRequest;
  const firstController = {
    abort() {
      abortAttempts.push('first');
      reentrantRequest = coordinator.startRequest();
      throw new Error('abort failed');
    },
  };
  const secondController = {
    abort() {
      abortAttempts.push('second');
    },
  };
  const reentrantController = {
    aborted: false,
    abort() {
      abortAttempts.push('reentrant');
      this.aborted = true;
    },
  };
  const controllers = [
    firstController,
    secondController,
    reentrantController,
  ];
  let nextController = 0;
  coordinator = createSessionCoordinator(() => controllers[nextController++]);

  coordinator.startRequest();
  coordinator.startRequest();

  let revision;
  assert.doesNotThrow(() => {
    revision = coordinator.reset();
  });
  assert.equal(revision, 1);
  assert.deepEqual(abortAttempts, ['first', 'second']);
  assert.equal(reentrantRequest.revision, 1);
  assert.strictEqual(reentrantRequest.controller, reentrantController);
  assert.equal(reentrantController.aborted, false);
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

test('reset does not abort requests started by stale abort callbacks', () => {
  const controllers = [];
  let coordinator;
  let reentrantRequest;
  coordinator = createSessionCoordinator(() => {
    const controllerIndex = controllers.length;
    const controller = {
      aborted: false,
      signal: {},
      abort() {
        this.aborted = true;
        if (controllerIndex === 0) {
          reentrantRequest = coordinator.startRequest();
        }
      },
    };
    controllers.push(controller);
    return controller;
  });

  coordinator.startRequest();
  coordinator.startRequest();

  assert.equal(coordinator.reset(), 1);
  assert.equal(controllers[0].aborted, true);
  assert.equal(controllers[1].aborted, true);
  assert.equal(reentrantRequest.revision, 1);
  assert.equal(controllers[2].aborted, false);
  assert.equal(coordinator.isCurrent(reentrantRequest.revision), true);
});
