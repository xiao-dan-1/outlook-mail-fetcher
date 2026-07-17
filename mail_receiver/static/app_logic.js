(function (globalScope) {
  'use strict';

  function createOperationGate() {
    var activeToken = null;

    function tryStart() {
      if (activeToken !== null) {
        return null;
      }
      activeToken = {};
      return activeToken;
    }

    function finish(token) {
      if (activeToken === null || token !== activeToken) {
        return false;
      }
      activeToken = null;
      return true;
    }

    function reset() {
      activeToken = null;
    }

    return {
      finish: finish,
      reset: reset,
      tryStart: tryStart,
    };
  }

  function createSessionCoordinator(controllerFactory) {
    var revision = 0;
    var controllers = new Set();
    var makeController = controllerFactory || function () {
      return new globalScope.AbortController();
    };

    function currentRevision() {
      return revision;
    }

    function isCurrent(candidateRevision) {
      return candidateRevision === revision;
    }

    function startRequest() {
      var controller = makeController();
      controllers.add(controller);
      return { controller: controller, revision: revision };
    }

    function finishRequest(controller) {
      controllers.delete(controller);
    }

    function reset() {
      revision += 1;
      var staleControllers = Array.from(controllers);
      controllers.clear();
      staleControllers.forEach(function (controller) {
        try {
          controller.abort();
        } catch (error) {
          // Cancellation is best-effort; revision checks still isolate stale work.
        }
      });
      return revision;
    }

    return {
      currentRevision: currentRevision,
      finishRequest: finishRequest,
      isCurrent: isCurrent,
      reset: reset,
      startRequest: startRequest,
    };
  }

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
    createOperationGate: createOperationGate,
    createSessionCoordinator: createSessionCoordinator,
    messageKey: messageKey,
    findMessageByKey: findMessageByKey,
  };

  globalScope.MailReceiverLogic = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
