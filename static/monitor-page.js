(function () {
  const REMOVE_TRANSITION_MS = 180;

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
    const node = document.createElement("div");
    node.className = `flash-message flash-${kind}`;
    node.setAttribute("data-flash-message", "");
    node.innerHTML = `<div class="flash-body"></div><button class="flash-close" type="button" aria-label="关闭提示">X</button>`;

    const body = node.querySelector(".flash-body");
    const close = node.querySelector(".flash-close");
    if (body instanceof HTMLElement) {
      body.textContent = message;
    }
    if (close instanceof HTMLButtonElement) {
      close.addEventListener("click", function () {
        node.remove();
      });
    }

    stack.prepend(node);
    window.setTimeout(function () {
      node.remove();
    }, kind === "error" ? 6400 : 3600);
  }

  function parseSymbolList(rawValue) {
    return String(rawValue || "")
      .split(/[\s,;；,]+/)
      .map(function (value) {
        return value.trim().toUpperCase().replace(/^\$/, "").replace(/[^A-Z0-9.\-]/g, "");
      })
      .filter(function (value, index, list) {
        return value && list.indexOf(value) === index;
      });
  }

  function updateCountNodes(selector, value) {
    document.querySelectorAll(selector).forEach(function (node) {
      if (!(node instanceof HTMLElement)) {
        return;
      }
      node.textContent = String(value);
    });
  }

  function setReportCount(value) {
    document.querySelectorAll("[data-monitor-report-count]").forEach(function (node) {
      if (!(node instanceof HTMLElement)) {
        return;
      }
      node.textContent = node.classList.contains("summary-count") ? String(value) : `${value} 份`;
    });
  }

  function setTodayCount(value) {
    updateCountNodes("[data-monitor-today-count]", `${value} 份`);
  }

  function syncEmptyState() {
    const list = document.querySelector("[data-monitor-report-list]");
    const emptyState = document.querySelector("[data-monitor-report-empty-state]");
    const count = document.querySelectorAll("[data-monitor-report-card]").length;
    if (list instanceof HTMLElement) {
      list.hidden = count === 0;
    }
    if (emptyState instanceof HTMLElement) {
      emptyState.hidden = count !== 0;
    }
  }

  function removeReportCard(card, payload) {
    if (!(card instanceof HTMLElement)) {
      syncEmptyState();
      return;
    }

    card.classList.add("is-removing");
    window.setTimeout(function () {
      card.remove();
      if (payload) {
        setReportCount(payload.report_count || 0);
        setTodayCount(payload.today_report_count || 0);
      }
      syncEmptyState();
      showFlash("success", (payload && payload.message) || "Monitor 报告已移入回收站。");
    }, REMOVE_TRANSITION_MS);
  }

  function bindReportDeleteForms() {
    document.querySelectorAll("form[data-monitor-report-delete-form]").forEach(function (form) {
      if (!(form instanceof HTMLFormElement)) {
        return;
      }

      form.addEventListener("submit", function (event) {
        if (event.defaultPrevented) {
          return;
        }

        event.preventDefault();
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
                throw new Error("页面没有收到可识别的删除结果。");
              })
              .then(function (payload) {
                if (!response.ok || !payload || payload.ok !== true) {
                  throw new Error((payload && payload.message) || "删除失败，请稍后重试。");
                }
                return payload;
              });
          })
          .then(function (payload) {
            const card = form.closest("[data-monitor-report-card]");
            removeReportCard(card, payload);
          })
          .catch(function (error) {
            if (submitButton instanceof HTMLButtonElement) {
              submitButton.disabled = false;
              submitButton.textContent = originalLabel || "删除";
            }
            showFlash("error", error instanceof Error ? error.message : "删除失败，请稍后重试。");
          });
      });
    });
  }

  function setupStockBuilder() {
    const form = document.querySelector("[data-monitor-stock-form]");
    const terminateForm = document.querySelector("[data-monitor-terminate-form]");
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    const hiddenInput = form.querySelector("[data-monitor-stock-hidden]");
    const confirmInput = form.querySelector("[data-monitor-confirm-existing]");
    const chipList = form.querySelector("[data-monitor-chip-list]");
    const chipInput = form.querySelector("[data-monitor-chip-input]");
    const addButton = form.querySelector("[data-monitor-chip-add]");
    const suggestionButtons = form.querySelectorAll("[data-monitor-suggestion]");
    let symbols = hiddenInput instanceof HTMLInputElement ? parseSymbolList(hiddenInput.value) : [];

    function syncHidden() {
      if (hiddenInput instanceof HTMLInputElement) {
        hiddenInput.value = symbols.join(";");
      }
      updateCountNodes("[data-monitor-chip-count]", symbols.length);
    }

    function renderChips() {
      if (!(chipList instanceof HTMLElement)) {
        syncHidden();
        return;
      }

      chipList.innerHTML = "";
      symbols.forEach(function (symbol) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "monitor-chip";
        chip.setAttribute("data-monitor-remove", symbol);
        chip.innerHTML = `<span>${symbol}</span><span class="monitor-chip-remove">×</span>`;
        chipList.appendChild(chip);
      });

      if (!symbols.length) {
        const empty = document.createElement("div");
        empty.className = "monitor-chip-empty";
        empty.textContent = "还没有股票，先从下方建议里点几只，或手动添加。";
        chipList.appendChild(empty);
      }

      syncHidden();
    }

    function addSymbols(rawValue) {
      const candidates = parseSymbolList(rawValue);
      let added = 0;
      candidates.forEach(function (candidate) {
        if (symbols.indexOf(candidate) !== -1) {
          return;
        }
        symbols.push(candidate);
        added += 1;
      });
      if (!added) {
        return 0;
      }
      renderChips();
      return added;
    }

    function resetConfirmFlag() {
      if (confirmInput instanceof HTMLInputElement) {
        confirmInput.value = "0";
      }
    }

    renderChips();

    if (addButton instanceof HTMLButtonElement) {
      addButton.addEventListener("click", function () {
        if (!(chipInput instanceof HTMLInputElement)) {
          return;
        }
        if (addSymbols(chipInput.value)) {
          chipInput.value = "";
          chipInput.focus();
          resetConfirmFlag();
          return;
        }
        if (chipInput.value.trim()) {
          showFlash("error", "请输入有效且未重复的股票代码。");
        }
      });
    }

    if (chipInput instanceof HTMLInputElement) {
      chipInput.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") {
          return;
        }
        event.preventDefault();
        if (addSymbols(chipInput.value)) {
          chipInput.value = "";
          resetConfirmFlag();
          return;
        }
        if (chipInput.value.trim()) {
          showFlash("error", "请输入有效且未重复的股票代码。");
        }
      });
    }

    if (chipList instanceof HTMLElement) {
      chipList.addEventListener("click", function (event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        const chip = target.closest("[data-monitor-remove]");
        if (!(chip instanceof HTMLElement)) {
          return;
        }
        const symbol = chip.getAttribute("data-monitor-remove") || "";
        symbols = symbols.filter(function (item) {
          return item !== symbol;
        });
        renderChips();
        resetConfirmFlag();
      });
    }

    suggestionButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        const symbol = button.getAttribute("data-monitor-suggestion") || "";
        addSymbols(symbol);
        resetConfirmFlag();
      });
    });

    form.addEventListener("submit", function (event) {
      const submitter = event.submitter;
      syncHidden();

      if (!symbols.length) {
        event.preventDefault();
        showFlash("error", "请先添加至少一只股票。");
        if (chipInput instanceof HTMLInputElement) {
          chipInput.focus();
        }
        return;
      }

      const isRunAction =
        submitter instanceof HTMLButtonElement && submitter.hasAttribute("data-monitor-run-button");
      if (!isRunAction) {
        resetConfirmFlag();
        return;
      }

      if (form.dataset.runBypass === "true") {
        form.dataset.runBypass = "";
        return;
      }

      if (form.dataset.running === "true") {
        event.preventDefault();
        if (window.confirm("程序已在运行，是否终止？") && terminateForm instanceof HTMLFormElement) {
          terminateForm.requestSubmit();
        }
        return;
      }

      if (form.dataset.todayExists === "true" && !(confirmInput instanceof HTMLInputElement && confirmInput.value === "1")) {
        event.preventDefault();
        if (!window.confirm("当天已经存在一份监测结果，是否继续运行？")) {
          return;
        }
        if (confirmInput instanceof HTMLInputElement) {
          confirmInput.value = "1";
        }
        form.dataset.runBypass = "true";
        window.requestAnimationFrame(function () {
          form.requestSubmit(submitter);
        });
      }
    });
  }

  function applyRuntimeState(payload) {
    if (!payload || !payload.runtime) {
      return;
    }

    const runtime = payload.runtime;
    const panel = document.querySelector("[data-monitor-status-panel]");
    updateCountNodes("[data-monitor-status-label]", runtime.status_label || "待运行");
    updateCountNodes("[data-monitor-runtime-label]", runtime.status_label || "待运行");
    updateCountNodes("[data-monitor-started-at]", runtime.started_at_label || "刚刚");
    updateCountNodes("[data-monitor-finished-at]", runtime.finished_at_label || "刚刚");
    updateCountNodes("[data-monitor-runtime-stocks]", (runtime.stock_pool || []).join("；") || "尚未运行");
    setTodayCount(payload.today_report_count || 0);
    setReportCount(payload.report_count || 0);

    const form = document.querySelector("[data-monitor-stock-form]");
    const runButton = document.querySelector("[data-monitor-run-button]");
    if (form instanceof HTMLElement) {
      form.dataset.running = runtime.is_running ? "true" : "false";
      form.dataset.todayExists = payload.today_report_count ? "true" : "false";
    }
    if (runButton instanceof HTMLButtonElement) {
      runButton.textContent = runtime.is_running ? "监测运行中" : "运行监测";
    }
    if (panel instanceof HTMLElement) {
      panel.setAttribute("data-monitor-running", runtime.is_running ? "true" : "false");
      panel.setAttribute("data-monitor-status", runtime.status || "idle");
    }

    const messageNode = document.querySelector("[data-monitor-message]");
    if (messageNode instanceof HTMLElement) {
      const message = runtime.message || "";
      messageNode.textContent = message;
      messageNode.hidden = !message;
    }

    const errorNode = document.querySelector("[data-monitor-error]");
    if (errorNode instanceof HTMLElement) {
      const error = runtime.error || "";
      errorNode.textContent = error;
      errorNode.hidden = !error;
    }
  }

  function setupStatusPolling() {
    const panel = document.querySelector("[data-monitor-status-panel]");
    if (!(panel instanceof HTMLElement)) {
      return;
    }

    const statusUrl = panel.getAttribute("data-status-url") || "";
    const pollSeconds = Number.parseInt(panel.getAttribute("data-monitor-poll-seconds") || "4", 10);
    let previousStatus = panel.getAttribute("data-monitor-status") || "idle";
    let timerId = 0;

    if (!statusUrl) {
      return;
    }

    function startPolling() {
      if (timerId) {
        return;
      }
      timerId = window.setInterval(poll, Math.max(2, pollSeconds) * 1000);
    }

    function stopPolling() {
      if (!timerId) {
        return;
      }
      window.clearInterval(timerId);
      timerId = 0;
    }

    function poll() {
      fetch(statusUrl, {
        headers: {
          Accept: "application/json",
        },
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (payload) {
          if (!payload || payload.ok !== true) {
            return;
          }
          applyRuntimeState(payload);
          const nextStatus = payload.runtime && payload.runtime.status ? payload.runtime.status : "idle";
          if (previousStatus === "running" && nextStatus !== "running") {
            window.location.reload();
            return;
          }
          previousStatus = nextStatus;
          if (nextStatus === "running") {
            startPolling();
            return;
          }
          stopPolling();
        })
        .catch(function () {
          return;
        });
    }

    poll();

    if (panel.getAttribute("data-monitor-running") === "true") {
      startPolling();
    }

    window.addEventListener("pageshow", function () {
      poll();
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    setupStockBuilder();
    bindReportDeleteForms();
    setupStatusPolling();
    syncEmptyState();
  });
})();
