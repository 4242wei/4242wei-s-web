(function () {
  const REMOVE_TRANSITION_MS = 220;

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

  function showFlash(kind, message) {
    if (!message) {
      return;
    }

    const stack = ensureFlashStack();
    const item = document.createElement("div");
    item.className = `flash-message flash-${kind}`;
    item.setAttribute("data-flash-message", "");
    item.setAttribute("data-flash-kind", kind);
    item.innerHTML = `<div class="flash-body"></div><button class="flash-close" type="button" aria-label="关闭提示">X</button>`;

    const body = item.querySelector(".flash-body");
    const closeButton = item.querySelector(".flash-close");

    if (body instanceof HTMLElement) {
      body.textContent = message;
    }

    if (closeButton instanceof HTMLButtonElement) {
      closeButton.addEventListener("click", function () {
        item.remove();
      });
    }

    stack.prepend(item);
    window.setTimeout(function () {
      item.remove();
    }, 3600);
  }

  function updateCountNodes(selector, value) {
    document.querySelectorAll(selector).forEach(function (node) {
      node.textContent = String(value);
    });
  }

  function visibleCardCount() {
    return document.querySelectorAll("[data-trash-card]").length;
  }

  function syncEmptyState() {
    const emptyState = document.querySelector("[data-trash-empty-state]");
    const resultList = document.querySelector("[data-trash-result-list]");
    const hasCards = visibleCardCount() !== 0;

    if (!(emptyState instanceof HTMLElement)) {
      if (resultList instanceof HTMLElement) {
        resultList.hidden = !hasCards;
      }
      return;
    }

    emptyState.hidden = hasCards;
    if (resultList instanceof HTMLElement) {
      resultList.hidden = !hasCards;
    }
  }

  function syncTrashStats(stats) {
    if (stats) {
      updateCountNodes("[data-trash-total-count]", stats.total_count || 0);
      updateCountNodes("[data-trash-note-count]", stats.note_count || 0);
      updateCountNodes("[data-trash-file-count]", stats.file_count || 0);
      updateCountNodes("[data-trash-transcript-count]", stats.transcript_count || 0);
      updateCountNodes("[data-trash-group-count]", stats.group_count || 0);
      updateCountNodes("[data-trash-report-count]", stats.monitor_report_count || 0);
      updateCountNodes("[data-trash-signal-report-count]", stats.signal_report_count || 0);
    }

    updateCountNodes("[data-trash-filtered-count]", visibleCardCount());
    syncEmptyState();
  }

  function removeTrashCard(card, payload) {
    if (!(card instanceof HTMLElement)) {
      syncTrashStats(payload && payload.stats);
      showFlash("success", payload && payload.message ? payload.message : "操作已完成。");
      return;
    }

    card.classList.add("is-removing");
    card.setAttribute("aria-hidden", "true");

    window.setTimeout(function () {
      card.remove();
      syncTrashStats(payload && payload.stats);
      showFlash("success", payload && payload.message ? payload.message : "操作已完成。");
    }, REMOVE_TRANSITION_MS);
  }

  function bindActionForm(form, pendingLabel, fallbackError) {
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    form.addEventListener("submit", function (event) {
      if (event.defaultPrevented) {
        return;
      }

      event.preventDefault();
      if (form.dataset.processing === "true") {
        return;
      }

      form.dataset.processing = "true";
      const submitButton = form.querySelector("button[type='submit']");
      const originalLabel = submitButton instanceof HTMLButtonElement ? submitButton.textContent : "";

      if (submitButton instanceof HTMLButtonElement) {
        submitButton.disabled = true;
        submitButton.textContent = pendingLabel;
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
              throw new Error("页面没有收到可识别的结果。");
            })
            .then(function (payload) {
              if (!response.ok || !payload || payload.ok !== true) {
                throw new Error((payload && payload.message) || fallbackError);
              }

              return payload;
            });
        })
        .then(function (payload) {
          const trashId = form.getAttribute("data-trash-id") || payload.restored_id || payload.deleted_id || "";
          const card =
            form.closest("[data-trash-card]") ||
            (trashId ? document.querySelector(`[data-trash-card][data-trash-id='${trashId}']`) : null);

          removeTrashCard(card, payload);
        })
        .catch(function (error) {
          form.dataset.processing = "";
          if (submitButton instanceof HTMLButtonElement) {
            submitButton.disabled = false;
            submitButton.textContent = originalLabel || "提交";
          }
          showFlash("error", error instanceof Error ? error.message : fallbackError);
        });
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    syncTrashStats();
    document.querySelectorAll("form[data-trash-restore-form]").forEach(function (form) {
      bindActionForm(form, "恢复中", "恢复失败，请稍后重试。");
    });
    document.querySelectorAll("form[data-trash-delete-form]").forEach(function (form) {
      bindActionForm(form, "删除中", "永久删除失败，请稍后重试。");
    });
  });
})();
