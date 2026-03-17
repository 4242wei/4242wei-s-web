(function () {
  const MODAL_TRANSITION_MS = 220;
  const REMOVE_TRANSITION_MS = 180;

  function setGroupDisabled(group, disabled) {
    group.classList.toggle("is-disabled", disabled);
    const fields = group.querySelectorAll("input, select, textarea, button");
    fields.forEach(function (field) {
      if (
        field instanceof HTMLInputElement ||
        field instanceof HTMLSelectElement ||
        field instanceof HTMLTextAreaElement ||
        field instanceof HTMLButtonElement
      ) {
        field.disabled = disabled;
      }
    });
  }

  function bindToggle(form, controlName, groupName) {
    const control = form.querySelector(`[name='${controlName}']`);
    const group = form.querySelector(`[data-toggle-group='${groupName}']`);
    if (!(control instanceof HTMLInputElement) || !(group instanceof HTMLElement)) {
      return;
    }

    const sync = function () {
      setGroupDisabled(group, !control.checked);
    };

    control.addEventListener("change", sync);
    sync();
  }

  function bindStockLinkMode(form) {
    const linkToggle = form.querySelector("[name='link_to_stock']");
    const multiToggle = form.querySelector("[name='link_to_multiple_stocks']");
    const wrapper = form.querySelector("[data-toggle-group='stock-link-fields']");
    const singleGroup = form.querySelector("[data-toggle-group='single-stock-field']");
    const multiGroup = form.querySelector("[data-toggle-group='multi-stock-fields']");

    if (
      !(linkToggle instanceof HTMLInputElement) ||
      !(multiToggle instanceof HTMLInputElement) ||
      !(wrapper instanceof HTMLElement) ||
      !(singleGroup instanceof HTMLElement) ||
      !(multiGroup instanceof HTMLElement)
    ) {
      return;
    }

    const sync = function () {
      const linkEnabled = linkToggle.checked;
      const multiEnabled = linkEnabled && multiToggle.checked;

      wrapper.classList.toggle("is-disabled", !linkEnabled);
      setGroupDisabled(singleGroup, !linkEnabled || multiEnabled);
      setGroupDisabled(multiGroup, !multiEnabled);
    };

    linkToggle.addEventListener("change", sync);
    multiToggle.addEventListener("change", sync);
    sync();
  }

  function parseSymbolList(rawValue) {
    return String(rawValue || "")
      .split(/[\s,，;；/]+/)
      .map(function (value) {
        return value.trim().toUpperCase().replace(/^\$/, "").replace(/[^A-Z0-9.\-]/g, "");
      })
      .filter(function (value, index, list) {
        return value && list.indexOf(value) === index;
      });
  }

  function bindTranscriptValidation(form) {
    const knownSymbols = new Set(parseSymbolList(form.dataset.knownStockSymbols || ""));
    const linkToggle = form.querySelector("[name='link_to_stock']");
    const multiToggle = form.querySelector("[name='link_to_multiple_stocks']");
    const singleSelect = form.querySelector("[name='linked_symbol']");
    const multiInput = form.querySelector("[name='linked_symbols_text']");

    if (!(linkToggle instanceof HTMLInputElement) || !(multiToggle instanceof HTMLInputElement)) {
      return;
    }

    form.addEventListener("submit", function (event) {
      if (!linkToggle.checked) {
        return;
      }

      if (multiToggle.checked) {
        if (!(multiInput instanceof HTMLInputElement)) {
          return;
        }

        const symbols = parseSymbolList(multiInput.value);
        if (!symbols.length) {
          event.preventDefault();
          showFlash("error", "如果要关联到多个股票，请先填写股票代码。");
          multiInput.focus();
          return;
        }

        const missingSymbols = symbols.filter(function (symbol) {
          return !knownSymbols.has(symbol);
        });
        if (missingSymbols.length) {
          event.preventDefault();
          showFlash("error", `未找到对应股票：${missingSymbols.join("；")}`);
          multiInput.focus();
        }
        return;
      }

      if (!(singleSelect instanceof HTMLSelectElement)) {
        return;
      }

      const symbol = String(singleSelect.value || "").trim().toUpperCase();
      if (symbol && !knownSymbols.has(symbol)) {
        event.preventDefault();
        showFlash("error", `未找到对应股票：${symbol}`);
        singleSelect.focus();
      }
    });
  }

  function setupComposerModal() {
    const overlay = document.querySelector("[data-compose-overlay]");
    if (!(overlay instanceof HTMLElement)) {
      return;
    }

    const openButtons = document.querySelectorAll("[data-compose-open]");
    let closeTimer = 0;

    const finishClose = function () {
      overlay.hidden = true;
      overlay.classList.remove("is-open", "is-closing");
      document.body.style.overflow = "";
      closeTimer = 0;
    };

    const closeModal = function () {
      if (overlay.hidden) {
        return;
      }

      overlay.classList.remove("is-open");
      overlay.classList.add("is-closing");
      window.clearTimeout(closeTimer);
      closeTimer = window.setTimeout(finishClose, MODAL_TRANSITION_MS);
    };

    const openModal = function () {
      window.clearTimeout(closeTimer);
      overlay.hidden = false;
      overlay.classList.remove("is-closing");
      window.requestAnimationFrame(function () {
        overlay.classList.add("is-open");
      });
      document.body.style.overflow = "hidden";
      const firstInput = overlay.querySelector("input[type='text'], input[type='file'], textarea, select");
      if (firstInput instanceof HTMLElement) {
        window.requestAnimationFrame(function () {
          firstInput.focus();
        });
      }
    };

    openButtons.forEach(function (button) {
      button.addEventListener("click", openModal);
    });

    overlay.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (target.hasAttribute("data-compose-close") || target === overlay) {
        closeModal();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !overlay.hidden) {
        closeModal();
      }
    });
  }

  function dismissFlash(node) {
    if (!(node instanceof HTMLElement) || node.dataset.flashClosing === "true") {
      return;
    }

    node.dataset.flashClosing = "true";
    node.classList.add("is-leaving");
    window.setTimeout(function () {
      node.remove();
    }, 220);
  }

  function autoDismissDelay(kind, textLength) {
    if (kind === "error") {
      return textLength > 180 ? 10000 : 7000;
    }

    return 3800;
  }

  function ensureFlashStack() {
    let stack = document.querySelector(".flash-stack");
    if (stack instanceof HTMLElement) {
      return stack;
    }

    stack = document.createElement("div");
    stack.className = "flash-stack";
    stack.setAttribute("role", "status");
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
    return stack;
  }

  function wireFlashNode(node, kind) {
    const closeButton = node.querySelector("[data-flash-close]");
    const body = node.querySelector(".flash-body");
    const messageLength = body ? body.textContent.trim().length : 0;
    const delay = autoDismissDelay(kind, messageLength);
    let timerId = window.setTimeout(function () {
      dismissFlash(node);
    }, delay);

    function restartTimer(nextDelay) {
      window.clearTimeout(timerId);
      timerId = window.setTimeout(function () {
        dismissFlash(node);
      }, nextDelay);
    }

    if (closeButton instanceof HTMLButtonElement) {
      closeButton.addEventListener("click", function () {
        window.clearTimeout(timerId);
        dismissFlash(node);
      });
    }

    node.addEventListener("mouseenter", function () {
      window.clearTimeout(timerId);
    });

    node.addEventListener("mouseleave", function () {
      if (node.dataset.flashClosing === "true") {
        return;
      }
      restartTimer(2200);
    });
  }

  function showFlash(kind, message) {
    const stack = ensureFlashStack();
    const node = document.createElement("div");
    node.className = `flash-message flash-${kind}`;
    node.dataset.flashMessage = "true";
    node.dataset.flashKind = kind;
    node.innerHTML =
      `<div class="flash-body"></div>` +
      `<button class="flash-close" type="button" aria-label="关闭提示" data-flash-close>X</button>`;
    const body = node.querySelector(".flash-body");
    if (body instanceof HTMLElement) {
      body.textContent = message;
    }
    stack.prepend(node);
    wireFlashNode(node, kind);
  }

  function computeCountsFromDom() {
    const cards = Array.from(document.querySelectorAll("[data-transcript-card]"));
    const completed = cards.filter(function (card) {
      return card.getAttribute("data-transcript-group") === "completed";
    }).length;
    const queue = cards.filter(function (card) {
      return card.getAttribute("data-transcript-group") === "queue";
    }).length;
    const linked = cards.filter(function (card) {
      return card.getAttribute("data-transcript-linked") === "true";
    }).length;
    const active = cards.filter(function (card) {
      const statusNode = card.querySelector(".status-pill");
      const statusText = statusNode ? statusNode.textContent.trim() : "";
      return statusText === "排队中" || statusText === "转录中";
    }).length;

    return {
      total: cards.length,
      completed: completed,
      queue: queue,
      linked: linked,
      active: active,
    };
  }

  function updateCountNodes(selector, value) {
    document.querySelectorAll(selector).forEach(function (node) {
      if (node instanceof HTMLElement) {
        node.textContent = node.classList.contains("summary-count") ? `${value}` : `${value} 个`;
      }
    });
  }

  function syncQueueEmptyState() {
    const list = document.querySelector("[data-transcript-queue-list]");
    const empty = document.querySelector("[data-transcript-queue-empty]");
    const count = document.querySelectorAll("[data-transcript-card][data-transcript-group='queue']").length;

    if (list instanceof HTMLElement) {
      list.hidden = count === 0;
    }
    if (empty instanceof HTMLElement) {
      empty.hidden = count !== 0;
    }
  }

  function syncCompletedEmptyState() {
    const list = document.querySelector("[data-transcript-completed-list]");
    const empty = document.querySelector("[data-transcript-completed-empty]");
    const count = document.querySelectorAll("[data-transcript-card][data-transcript-group='completed']").length;

    if (list instanceof HTMLElement) {
      list.hidden = count === 0;
    }
    if (empty instanceof HTMLElement) {
      empty.hidden = count !== 0;
    }
  }

  function syncSyncButton(counts) {
    const syncForm = document.querySelector("[data-transcript-sync-form]");
    if (!(syncForm instanceof HTMLElement)) {
      return;
    }

    syncForm.hidden = !counts.active;
  }

  function syncTranscriptStats(nextCounts) {
    const counts = nextCounts || computeCountsFromDom();

    updateCountNodes("[data-transcript-completed-count]", counts.completed);
    updateCountNodes("[data-transcript-queue-count]", counts.queue);
    updateCountNodes("[data-transcript-linked-count]", counts.linked);

    const totalLabel = document.querySelector("[data-transcript-total-label]");
    if (totalLabel instanceof HTMLElement) {
      totalLabel.textContent = `当前已存 ${counts.total} 个转录任务`;
    }

    syncQueueEmptyState();
    syncCompletedEmptyState();
    syncSyncButton(counts);
  }

  function removeTranscriptCard(card, transcriptId, counts, message) {
    if (!(card instanceof HTMLElement)) {
      syncTranscriptStats(counts);
      if (message) {
        showFlash("success", message);
      }
      return;
    }

    card.classList.add("is-removing");
    card.setAttribute("aria-hidden", "true");

    const detachedTemplate = document.getElementById(`transcript-reader-${transcriptId}`);
    if (detachedTemplate instanceof HTMLElement && !card.contains(detachedTemplate)) {
      detachedTemplate.remove();
    }

    window.setTimeout(function () {
      card.remove();
      syncTranscriptStats(counts);
      if (message) {
        showFlash("success", message);
      }
    }, REMOVE_TRANSITION_MS);
  }

  function setupDeleteForms() {
    document.addEventListener("submit", function (event) {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || !form.matches("form[data-transcript-delete-form]")) {
        return;
      }

      if (event.defaultPrevented) {
        return;
      }

      event.preventDefault();
      if (form.dataset.deleting === "true") {
        return;
      }

      form.dataset.deleting = "true";
      const submitButton = form.querySelector("button[type='submit']");
      const originalLabel = submitButton instanceof HTMLButtonElement ? submitButton.textContent : "";
      if (submitButton instanceof HTMLButtonElement) {
        submitButton.disabled = true;
        submitButton.textContent = "删除中";
      }

      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              throw new Error("删除请求没有返回可识别的结果。");
            })
            .then(function (payload) {
              if (!response.ok || !payload || payload.ok !== true) {
                throw new Error((payload && payload.message) || "删除失败，请稍后重试。");
              }
              return payload;
            });
        })
        .then(function (payload) {
          const transcriptId = form.getAttribute("data-transcript-id") || payload.deleted_id || "";
          const card =
            form.closest("[data-transcript-card]") ||
            (transcriptId ? document.querySelector(`[data-transcript-card][data-transcript-id='${transcriptId}']`) : null);
          removeTranscriptCard(card, transcriptId, payload.counts, payload.message);
        })
        .catch(function (error) {
          form.dataset.deleting = "";
          if (submitButton instanceof HTMLButtonElement) {
            submitButton.disabled = false;
            submitButton.textContent = originalLabel || "删除";
          }
          showFlash("error", error instanceof Error ? error.message : "删除失败，请稍后重试。");
        });
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector("[data-transcript-form]");
    if (form instanceof HTMLFormElement) {
      bindStockLinkMode(form);
      bindTranscriptValidation(form);
      bindToggle(form, "diarization_enabled", "speaker-fields");
      bindToggle(form, "meeting_assistance_enabled", "meeting-assistance-fields");
      bindToggle(form, "summarization_enabled", "summarization-fields");
      bindToggle(form, "custom_prompt_enabled", "prompt-fields");
    }

    setupComposerModal();
    setupDeleteForms();
    syncTranscriptStats();
  });
})();
