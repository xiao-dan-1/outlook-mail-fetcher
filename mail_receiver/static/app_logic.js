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

  function createRequestFailureState(email, error) {
    var errorMessage = error && error.message !== undefined
      ? String(error.message)
      : String(error ?? '');

    return {
      row: {
        email: email,
        ok: false,
        stage: 'request',
        fetched: 0,
        elapsed_ms: 0,
        error: errorMessage,
        timings: {},
        raw_bytes: 0,
        downloaded_bytes: 0,
        message_count: 0,
      },
      status: {
        kind: 'fail',
        stage: 'request',
        elapsed_ms: 0,
        error: errorMessage,
        timings: {},
        raw_bytes: 0,
        downloaded_bytes: 0,
        message_count: 0,
      },
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

  function createVerificationRuleRegistry(initialRules) {
    var entries = [];
    var ruleIds = new Set();
    var nextOrder = 0;

    function register(rule) {
      if (!rule || !rule.id || typeof rule.match !== 'function') {
        throw new TypeError('verification rule requires id and match');
      }
      if (ruleIds.has(rule.id)) {
        throw new Error('verification rule already registered: ' + rule.id);
      }
      ruleIds.add(rule.id);
      entries.push({ rule: rule, order: nextOrder });
      nextOrder += 1;
      entries.sort(function (left, right) {
        var priorityDifference = (Number(right.rule.priority) || 0)
          - (Number(left.rule.priority) || 0);
        return priorityDifference || left.order - right.order;
      });
      return rule;
    }

    function find(context) {
      for (var entry of entries) {
        try {
          var result = entry.rule.match(context);
          if (result) {
            return Object.assign({}, result, { rule_id: entry.rule.id });
          }
        } catch (error) {
          // A provider rule must not prevent lower-priority fallback rules.
        }
      }
      return null;
    }

    (initialRules || []).forEach(register);
    return {
      find: find,
      register: register,
    };
  }

  var api = {
    createOperationGate: createOperationGate,
    createRequestFailureState: createRequestFailureState,
    createSessionCoordinator: createSessionCoordinator,
    createVerificationRuleRegistry: createVerificationRuleRegistry,
    messageKey: messageKey,
    findMessageByKey: findMessageByKey,
  };

  globalScope.MailReceiverLogic = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
