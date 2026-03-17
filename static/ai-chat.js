(function () {
  const root = document.querySelector("[data-ai-chat-root]");
  if (!root) {
    return;
  }

  const shell = root.closest("[data-ai-shell]") || root;
  const allContentKinds = ["report", "note", "file", "transcript"];
  const messageList = root.querySelector("[data-ai-message-list]");
  const composerForm = root.querySelector("[data-ai-composer-form]");
  const textarea = composerForm ? composerForm.querySelector("textarea[name='prompt']") : null;
  const modelSelect = root.querySelector("[data-ai-model-select]");
  const reasoningSelect = root.querySelector("[data-ai-reasoning-select]");
  const submitButton = composerForm ? composerForm.querySelector("button[type='submit']") : null;
  const pollUrl = root.dataset.aiPollUrl || "";
  const pollInterval = Number.parseInt(root.dataset.aiPollInterval || "5000", 10);
  const sidebarToggleButtons = Array.from(document.querySelectorAll("[data-ai-sidebar-toggle]"));
  const renameToggleButtons = Array.from(document.querySelectorAll("[data-ai-session-rename-toggle]"));
  const renameForms = Array.from(document.querySelectorAll(".ai-session-rename-form"));
  const collapsedStorageKey = "aiSidebarCollapsed";
  const scopePreviewUrl = root.dataset.aiScopePreviewUrl || "";
  const scopeSaveUrl = root.dataset.aiScopeSaveUrl || "";

  const summaryHeadline = root.querySelector("[data-ai-scope-headline]");
  const summaryDescription = root.querySelector("[data-ai-scope-description]");
  const summaryStockLabel = root.querySelector("[data-ai-scope-stock-label]");
  const summaryTimeLabel = root.querySelector("[data-ai-scope-time-label]");
  const summaryContentLabel = root.querySelector("[data-ai-scope-content-label]");
  const summaryMetrics = Array.from(root.querySelectorAll("[data-ai-scope-metric]"));
  const summaryResetButton = root.querySelector("[data-ai-scope-summary-card] [data-ai-scope-reset]");

  const hiddenScopeFields = {
    useStockScope: composerForm ? composerForm.querySelector("[data-ai-scope-hidden='use_stock_scope']") : null,
    symbols: composerForm ? composerForm.querySelector("[data-ai-scope-hidden='scope_symbols']") : null,
    contentKinds: composerForm ? composerForm.querySelector("[data-ai-scope-hidden='scope_content_kinds']") : null,
    useDateScope: composerForm ? composerForm.querySelector("[data-ai-scope-hidden='use_date_scope']") : null,
    startDate: composerForm ? composerForm.querySelector("[data-ai-scope-hidden='scope_start_date']") : null,
    endDate: composerForm ? composerForm.querySelector("[data-ai-scope-hidden='scope_end_date']") : null,
    previewMonth: composerForm ? composerForm.querySelector("[data-ai-scope-hidden='scope_preview_month']") : null,
    selectedDate: composerForm ? composerForm.querySelector("[data-ai-scope-hidden='scope_selected_date']") : null,
  };

  const scopeOverlay = document.querySelector("[data-ai-scope-overlay]");
  const scopeOpenButtons = Array.from(document.querySelectorAll("[data-ai-scope-open]"));
  const scopeCloseButtons = scopeOverlay ? Array.from(scopeOverlay.querySelectorAll("[data-ai-scope-close]")) : [];
  const scopeForm = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-form]") : null;
  const scopePreviewFrame = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-preview-frame]") : null;
  const scopeSessionInput = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-session-id]") : null;
  const scopeSymbolsInput = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-symbols]") : null;
  const scopeContentKindsInput = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-content-kinds]") : null;
  const scopePreviewMonthInput = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-preview-month]") : null;
  const scopeSelectedDateInput = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-selected-date]") : null;
  const scopeUseStockCheckbox = scopeOverlay ? scopeOverlay.querySelector("[name='use_stock_scope']") : null;
  const scopeUseDateCheckbox = scopeOverlay ? scopeOverlay.querySelector("[name='use_date_scope']") : null;
  const scopeStartDateInput = scopeOverlay ? scopeOverlay.querySelector("[name='start_date']") : null;
  const scopeEndDateInput = scopeOverlay ? scopeOverlay.querySelector("[name='end_date']") : null;
  const scopeStockFilterInput = scopeOverlay ? scopeOverlay.querySelector("[data-ai-stock-filter]") : null;
  const scopeStockGrid = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-stock-grid]") : null;
  const scopeSelectedStocks = scopeOverlay ? scopeOverlay.querySelector("[data-ai-selected-stocks]") : null;
  const scopeStockGroup = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-stock-group]") : null;
  const scopeDateGroup = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-date-group]") : null;
  const modalResetButton = scopeOverlay ? scopeOverlay.querySelector(".ai-scope-actions [data-ai-scope-reset]") : null;

  let scopePreviewTimer = 0;
  let scopeClosingTimer = 0;
  let scopePreviewController = null;

  function setText(node, value) {
    if (node) {
      node.textContent = value;
    }
  }

  function parseSymbolList(rawValue) {
    return String(rawValue || "")
      .split(/[\s,;；]+/)
      .map(function (value) {
        return value.trim().toUpperCase().replace(/^\$/, "").replace(/[^A-Z0-9.\-]/g, "");
      })
      .filter(function (value, index, list) {
        return value && list.indexOf(value) === index;
      });
  }

  function parseContentKinds(rawValue) {
    const parsed = (String(rawValue || "").toLowerCase().match(/report|note|file|transcript/g) || [])
      .map(function (value) {
        return value.trim().toLowerCase();
      })
      .filter(function (value, index, list) {
        return value && allContentKinds.includes(value) && list.indexOf(value) === index;
      });

    return parsed.length ? parsed : allContentKinds.slice();
  }

  function ensureFlashStack() {
    let stack = document.querySelector(".flash-stack");
    if (stack instanceof HTMLElement) {
      return stack;
    }

    stack = document.createElement("div");
    stack.className = "flash-stack";
    document.body.appendChild(stack);
    return stack;
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

  function showFlash(kind, message) {
    const stack = ensureFlashStack();
    const item = document.createElement("div");
    item.className = `flash-item is-${kind}`;
    item.textContent = message;
    stack.appendChild(item);

    window.setTimeout(function () {
      dismissFlash(item);
    }, kind === "error" ? 7000 : 3600);
  }

  function currentScopeState() {
    return {
      useStockScope: hiddenScopeFields.useStockScope && hiddenScopeFields.useStockScope.value === "1",
      symbols: parseSymbolList(hiddenScopeFields.symbols ? hiddenScopeFields.symbols.value : ""),
      contentKinds: parseContentKinds(hiddenScopeFields.contentKinds ? hiddenScopeFields.contentKinds.value : ""),
      useDateScope: hiddenScopeFields.useDateScope && hiddenScopeFields.useDateScope.value === "1",
      startDate: hiddenScopeFields.startDate ? hiddenScopeFields.startDate.value : "",
      endDate: hiddenScopeFields.endDate ? hiddenScopeFields.endDate.value : "",
      previewMonth: hiddenScopeFields.previewMonth ? hiddenScopeFields.previewMonth.value : "",
      selectedDate: hiddenScopeFields.selectedDate ? hiddenScopeFields.selectedDate.value : "",
    };
  }

  function applyScopeToHidden(scope) {
    if (hiddenScopeFields.useStockScope) {
      hiddenScopeFields.useStockScope.value = scope.useStockScope ? "1" : "0";
    }
    if (hiddenScopeFields.symbols) {
      hiddenScopeFields.symbols.value = (scope.symbols || []).join("；");
    }
    if (hiddenScopeFields.contentKinds) {
      hiddenScopeFields.contentKinds.value = (scope.contentKinds || allContentKinds).join("；");
    }
    if (hiddenScopeFields.useDateScope) {
      hiddenScopeFields.useDateScope.value = scope.useDateScope ? "1" : "0";
    }
    if (hiddenScopeFields.startDate) {
      hiddenScopeFields.startDate.value = scope.startDate || "";
    }
    if (hiddenScopeFields.endDate) {
      hiddenScopeFields.endDate.value = scope.endDate || "";
    }
    if (hiddenScopeFields.previewMonth) {
      hiddenScopeFields.previewMonth.value = scope.previewMonth || "";
    }
    if (hiddenScopeFields.selectedDate) {
      hiddenScopeFields.selectedDate.value = scope.selectedDate || "";
    }
  }

  function updateSummary(summary) {
    if (!summary) {
      return;
    }

    setText(summaryHeadline, summary.headline || "当前读取全站资料库");
    setText(summaryDescription, summary.description || "");
    setText(summaryStockLabel, summary.stock_label || "股票范围：全站");
    setText(summaryTimeLabel, summary.time_label || "时间窗口：不限");

    setText(summaryContentLabel, summary.content_label || "资料类型：日报；笔记；文件；转录");

    summaryMetrics.forEach(function (metricNode) {
      const label = metricNode.getAttribute("data-ai-scope-metric") || "";
      const matched = Array.isArray(summary.metrics)
        ? summary.metrics.find(function (item) {
            return item.label === label;
          })
        : null;
      const valueNode = metricNode.querySelector("strong");
      if (valueNode) {
        valueNode.textContent = matched ? String(matched.value) : "0";
      }
    });

    if (summaryResetButton instanceof HTMLElement) {
      summaryResetButton.hidden = !summary.has_filters;
    }
  }

  function syncSidebarButtons() {
    const expanded = !shell.classList.contains("is-sidebar-collapsed");
    sidebarToggleButtons.forEach(function (button) {
      button.setAttribute("aria-expanded", String(expanded));
      const label = button.querySelector(".ai-sidebar-toggle-label");
      if (label) {
        label.textContent = expanded ? "收起历史" : "展开历史";
      }
    });
  }

  function setSidebarCollapsed(collapsed) {
    shell.classList.toggle("is-sidebar-collapsed", collapsed);
    try {
      window.localStorage.setItem(collapsedStorageKey, collapsed ? "1" : "0");
    } catch (error) {
      // ignore storage errors
    }
    syncSidebarButtons();
  }

  function restoreSidebarState() {
    try {
      if (window.localStorage.getItem(collapsedStorageKey) === "1") {
        shell.classList.add("is-sidebar-collapsed");
      }
    } catch (error) {
      // ignore storage errors
    }
    syncSidebarButtons();
  }

  function closeRenameForms() {
    renameForms.forEach(function (form) {
      form.hidden = true;
    });
  }

  function scrollToBottom() {
    if (!messageList) {
      return;
    }
    window.requestAnimationFrame(function () {
      messageList.scrollTop = messageList.scrollHeight;
    });
  }

  function autoGrowTextarea() {
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
  }

  function syncReasoningOptions() {
    if (!modelSelect || !reasoningSelect) {
      return;
    }

    const selectedOption = modelSelect.options[modelSelect.selectedIndex];
    const defaultReasoning = selectedOption.dataset.defaultReasoning || "medium";
    let reasoningLevels = ["medium"];

    try {
      reasoningLevels = JSON.parse(selectedOption.dataset.reasoningLevels || '["medium"]');
    } catch (error) {
      reasoningLevels = ["medium"];
    }

    if (!Array.isArray(reasoningLevels) || reasoningLevels.length === 0) {
      reasoningLevels = ["medium"];
    }

    const currentValue = reasoningSelect.value;
    reasoningSelect.innerHTML = "";
    reasoningLevels.forEach(function (level) {
      const option = document.createElement("option");
      option.value = level;
      option.textContent = level;
      if (level === currentValue || (!reasoningLevels.includes(currentValue) && level === defaultReasoning)) {
        option.selected = true;
      }
      reasoningSelect.appendChild(option);
    });
  }

  function hasPendingBubble() {
    return Boolean(root.querySelector("[data-message-status='pending'], [data-message-status='running']"));
  }

  function startPolling() {
    if (!pollUrl || !hasPendingBubble()) {
      return;
    }

    const tick = async function () {
      try {
        const response = await fetch(pollUrl, {
          headers: {
            Accept: "application/json",
            "X-Requested-With": "XMLHttpRequest",
          },
          cache: "no-store",
        });
        if (!response.ok) {
          return;
        }

        const payload = await response.json();
        if (!payload.has_pending) {
          window.location.reload();
        }
      } catch (error) {
        window.clearInterval(timerId);
      }
    };

    const timerId = window.setInterval(tick, Math.max(pollInterval, 2000));
    tick();
  }

  function setGroupDisabled(group, disabled) {
    if (!(group instanceof HTMLElement)) {
      return;
    }
    group.classList.toggle("is-disabled", disabled);
    group.querySelectorAll("input, select, textarea, button").forEach(function (field) {
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

  function modalScopeState() {
    return {
      useStockScope: scopeUseStockCheckbox instanceof HTMLInputElement ? scopeUseStockCheckbox.checked : false,
      symbols: parseSymbolList(scopeSymbolsInput ? scopeSymbolsInput.value : ""),
      contentKinds: parseContentKinds(scopeContentKindsInput ? scopeContentKindsInput.value : ""),
      useDateScope: scopeUseDateCheckbox instanceof HTMLInputElement ? scopeUseDateCheckbox.checked : false,
      startDate: scopeStartDateInput instanceof HTMLInputElement ? scopeStartDateInput.value : "",
      endDate: scopeEndDateInput instanceof HTMLInputElement ? scopeEndDateInput.value : "",
      previewMonth: scopePreviewMonthInput instanceof HTMLInputElement ? scopePreviewMonthInput.value : "",
      selectedDate: scopeSelectedDateInput instanceof HTMLInputElement ? scopeSelectedDateInput.value : "",
    };
  }

  function writeModalSymbols(symbols) {
    if (scopeSymbolsInput instanceof HTMLInputElement) {
      scopeSymbolsInput.value = symbols.join("；");
    }
  }

  function writeModalContentKinds(contentKinds) {
    if (scopeContentKindsInput instanceof HTMLInputElement) {
      scopeContentKindsInput.value = (contentKinds || allContentKinds).join("；");
    }
  }

  function renderSelectedStocks() {
    if (!(scopeSelectedStocks instanceof HTMLElement)) {
      return;
    }

    const selectedSymbols = parseSymbolList(scopeSymbolsInput ? scopeSymbolsInput.value : "");
    scopeSelectedStocks.innerHTML = "";

    if (!selectedSymbols.length) {
      const empty = document.createElement("p");
      empty.className = "section-caption";
      empty.textContent = "未限定股票时，Codex 会读取全站资料。";
      scopeSelectedStocks.appendChild(empty);
    } else {
      selectedSymbols.forEach(function (symbol) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "ai-selected-stock-chip";
        chip.setAttribute("data-ai-selected-stock-remove", symbol);
        chip.textContent = symbol + " ×";
        scopeSelectedStocks.appendChild(chip);
      });
    }

    if (!(scopeStockGrid instanceof HTMLElement)) {
      return;
    }

    const filterValue = scopeStockFilterInput instanceof HTMLInputElement ? scopeStockFilterInput.value.trim().toUpperCase() : "";
    scopeStockGrid.querySelectorAll("[data-ai-stock-chip]").forEach(function (chip) {
      if (!(chip instanceof HTMLButtonElement)) {
        return;
      }
      const symbol = chip.dataset.symbol || "";
      const matches = !filterValue || symbol.includes(filterValue);
      chip.hidden = !matches;
      chip.classList.toggle("is-selected", selectedSymbols.includes(symbol));
    });
  }

  function syncScopeGroups() {
    const useStockScope = scopeUseStockCheckbox instanceof HTMLInputElement ? scopeUseStockCheckbox.checked : false;
    const useDateScope = scopeUseDateCheckbox instanceof HTMLInputElement ? scopeUseDateCheckbox.checked : false;
    setGroupDisabled(scopeStockGroup, !useStockScope);
    setGroupDisabled(scopeDateGroup, !useDateScope);
    renderSelectedStocks();
  }

  function applyScopeToModal(scope) {
    if (scopeSessionInput instanceof HTMLInputElement) {
      scopeSessionInput.value = root.dataset.aiSessionId || "";
    }
    if (scopeUseStockCheckbox instanceof HTMLInputElement) {
      scopeUseStockCheckbox.checked = Boolean(scope.useStockScope);
    }
    if (scopeUseDateCheckbox instanceof HTMLInputElement) {
      scopeUseDateCheckbox.checked = Boolean(scope.useDateScope);
    }
    if (scopeStartDateInput instanceof HTMLInputElement) {
      scopeStartDateInput.value = scope.startDate || "";
    }
    if (scopeEndDateInput instanceof HTMLInputElement) {
      scopeEndDateInput.value = scope.endDate || "";
    }
    if (scopePreviewMonthInput instanceof HTMLInputElement) {
      scopePreviewMonthInput.value = scope.previewMonth || "";
    }
    if (scopeSelectedDateInput instanceof HTMLInputElement) {
      scopeSelectedDateInput.value = scope.selectedDate || "";
    }
    writeModalSymbols(scope.symbols || []);
    writeModalContentKinds(scope.contentKinds || allContentKinds);
    if (scopeStockFilterInput instanceof HTMLInputElement) {
      scopeStockFilterInput.value = "";
    }
    syncScopeGroups();
  }

  async function requestScopePreview(options) {
    if (!(scopePreviewFrame instanceof HTMLElement) || !scopePreviewUrl) {
      return;
    }

    const state = modalScopeState();
    if (options && Object.prototype.hasOwnProperty.call(options, "month")) {
      state.previewMonth = options.month || "";
    }
    if (options && Object.prototype.hasOwnProperty.call(options, "selectedDate")) {
      state.selectedDate = options.selectedDate || "";
    }

    if (scopePreviewMonthInput instanceof HTMLInputElement) {
      scopePreviewMonthInput.value = state.previewMonth || "";
    }
    if (scopeSelectedDateInput instanceof HTMLInputElement) {
      scopeSelectedDateInput.value = state.selectedDate || "";
    }

    if (state.useStockScope && !(state.symbols || []).length) {
      scopePreviewFrame.innerHTML = '<div class="empty-inline"><p>请先选择至少一只股票，再预览这个范围内的资料时间线。</p></div>';
      return;
    }

    if (state.useDateScope && (!state.startDate || !state.endDate)) {
      scopePreviewFrame.innerHTML = '<div class="empty-inline"><p>请先选完整的起始日期和终止日期，再查看时间窗口预览。</p></div>';
      return;
    }
    if (state.useDateScope && state.startDate && state.endDate && state.startDate > state.endDate) {
      scopePreviewFrame.innerHTML = '<div class="empty-inline"><p>起始日期不能晚于终止日期，请先调整时间窗口。</p></div>';
      return;
    }

    const params = new URLSearchParams();
    params.set("use_stock_scope", state.useStockScope ? "1" : "0");
    params.set("content_kinds", (state.contentKinds || []).join("；"));
    params.set("symbols", (state.symbols || []).join("；"));
    params.set("use_date_scope", state.useDateScope ? "1" : "0");
    params.set("start_date", state.startDate || "");
    params.set("end_date", state.endDate || "");
    params.set("month", state.previewMonth || "");
    params.set("date", state.selectedDate || "");

    if (scopePreviewController) {
      scopePreviewController.abort();
    }
    scopePreviewController = new AbortController();

    scopePreviewFrame.classList.add("is-loading");
    try {
      const response = await fetch(`${scopePreviewUrl}?${params.toString()}`, {
        headers: {
          Accept: "text/html",
          "X-Requested-With": "XMLHttpRequest",
        },
        cache: "no-store",
        signal: scopePreviewController.signal,
      });
      if (!response.ok) {
        throw new Error("preview_failed");
      }

      scopePreviewFrame.innerHTML = await response.text();
      const nextRoot = scopePreviewFrame.querySelector("[data-ai-scope-preview-root]");
      if (nextRoot instanceof HTMLElement) {
        if (scopePreviewMonthInput instanceof HTMLInputElement) {
          scopePreviewMonthInput.value = nextRoot.dataset.previewMonth || state.previewMonth || "";
        }
        if (scopeSelectedDateInput instanceof HTMLInputElement) {
          scopeSelectedDateInput.value = nextRoot.dataset.selectedDate || "";
        }
      }
    } catch (error) {
      if (error && error.name === "AbortError") {
        return;
      }
      scopePreviewFrame.innerHTML = '<div class="empty-inline"><p>当前无法加载范围预览，请稍后再试。</p></div>';
    } finally {
      scopePreviewFrame.classList.remove("is-loading");
    }
  }

  function scheduleScopePreview() {
    window.clearTimeout(scopePreviewTimer);
    scopePreviewTimer = window.setTimeout(function () {
      requestScopePreview();
    }, 160);
  }

  function finishScopeClose() {
    if (!(scopeOverlay instanceof HTMLElement)) {
      return;
    }
    scopeOverlay.hidden = true;
    scopeOverlay.classList.remove("is-open", "is-closing");
    document.body.style.overflow = "";
    scopeClosingTimer = 0;
  }

  function closeScopeModal() {
    if (!(scopeOverlay instanceof HTMLElement) || scopeOverlay.hidden) {
      return;
    }
    scopeOverlay.classList.remove("is-open");
    scopeOverlay.classList.add("is-closing");
    window.clearTimeout(scopeClosingTimer);
    scopeClosingTimer = window.setTimeout(finishScopeClose, 220);
  }

  function openScopeModal() {
    if (!(scopeOverlay instanceof HTMLElement)) {
      return;
    }

    window.clearTimeout(scopeClosingTimer);
    applyScopeToModal(currentScopeState());
    scopeOverlay.hidden = false;
    scopeOverlay.classList.remove("is-closing");
    window.requestAnimationFrame(function () {
      scopeOverlay.classList.add("is-open");
    });
    document.body.style.overflow = "hidden";
    requestScopePreview();
  }

  async function persistScope(scope) {
    if (!scopeSaveUrl) {
      return null;
    }

    const formData = new FormData();
    formData.set("session_id", root.dataset.aiSessionId || "");
    formData.set("use_stock_scope", scope.useStockScope ? "1" : "0");
    formData.set("content_kinds", (scope.contentKinds || []).join("；"));
    formData.set("symbols", (scope.symbols || []).join("；"));
    formData.set("use_date_scope", scope.useDateScope ? "1" : "0");
    formData.set("start_date", scope.startDate || "");
    formData.set("end_date", scope.endDate || "");
    formData.set("preview_month", scope.previewMonth || "");
    formData.set("selected_date", scope.selectedDate || "");

    const response = await fetch(scopeSaveUrl, {
      method: "POST",
      body: formData,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || "保存范围失败。");
    }
    return payload;
  }

  function normalizeScopePayload(scope, payload) {
    const serverScope = payload && payload.scope ? payload.scope : {};
    return {
      useStockScope: Boolean(serverScope.use_stock_scope ?? scope.useStockScope),
      symbols: parseSymbolList(serverScope.symbols_text || (scope.symbols || []).join("；")),
      contentKinds: parseContentKinds(serverScope.content_kinds_text || (scope.contentKinds || []).join("；")),
      useDateScope: Boolean(serverScope.use_date_scope ?? scope.useDateScope),
      startDate: serverScope.start_date || scope.startDate || "",
      endDate: serverScope.end_date || scope.endDate || "",
      previewMonth: payload && payload.preview_month ? payload.preview_month : (serverScope.preview_month || scope.previewMonth || ""),
      selectedDate: payload && Object.prototype.hasOwnProperty.call(payload, "selected_date")
        ? payload.selected_date
        : (serverScope.selected_date || scope.selectedDate || ""),
    };
  }

  sidebarToggleButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      setSidebarCollapsed(!shell.classList.contains("is-sidebar-collapsed"));
    });
  });

  renameToggleButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      const targetId = button.getAttribute("data-ai-target");
      if (!targetId) {
        return;
      }
      const form = document.getElementById(targetId);
      if (!(form instanceof HTMLFormElement)) {
        return;
      }
      const willOpen = form.hidden;
      closeRenameForms();
      form.hidden = !willOpen;
      if (willOpen) {
        const input = form.querySelector("input[name='title']");
        if (input instanceof HTMLInputElement) {
          input.focus();
          input.select();
        }
      }
    });
  });

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.closest("[data-ai-session-rename-toggle]") || target.closest(".ai-session-rename-form")) {
      return;
    }
    closeRenameForms();
  });

  if (modelSelect) {
    modelSelect.addEventListener("change", syncReasoningOptions);
    syncReasoningOptions();
  }

  if (textarea) {
    textarea.addEventListener("input", autoGrowTextarea);
    autoGrowTextarea();
  }

  if (composerForm && submitButton) {
    composerForm.addEventListener("submit", function () {
      submitButton.disabled = true;
      submitButton.textContent = "发送中...";
    });
  }

  if (scopeOverlay instanceof HTMLElement && scopeForm instanceof HTMLFormElement) {
    scopeOpenButtons.forEach(function (button) {
      button.addEventListener("click", openScopeModal);
    });

    scopeCloseButtons.forEach(function (button) {
      button.addEventListener("click", closeScopeModal);
    });

    scopeOverlay.addEventListener("click", function (event) {
      if (event.target === scopeOverlay || event.target === scopeOverlay.querySelector(".compose-overlay-backdrop")) {
        closeScopeModal();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !scopeOverlay.hidden) {
        closeScopeModal();
      }
    });

    if (scopeStockFilterInput instanceof HTMLInputElement) {
      scopeStockFilterInput.addEventListener("input", renderSelectedStocks);
    }

    if (scopeUseStockCheckbox instanceof HTMLInputElement) {
      scopeUseStockCheckbox.addEventListener("change", function () {
        syncScopeGroups();
        scheduleScopePreview();
      });
    }
    if (scopeUseDateCheckbox instanceof HTMLInputElement) {
      scopeUseDateCheckbox.addEventListener("change", function () {
        syncScopeGroups();
        scheduleScopePreview();
      });
    }
    if (scopeStartDateInput instanceof HTMLInputElement) {
      scopeStartDateInput.addEventListener("change", function () {
        if (scopeUseDateCheckbox instanceof HTMLInputElement) {
          scopeUseDateCheckbox.checked = true;
        }
        syncScopeGroups();
        scheduleScopePreview();
      });
    }
    if (scopeEndDateInput instanceof HTMLInputElement) {
      scopeEndDateInput.addEventListener("change", function () {
        if (scopeUseDateCheckbox instanceof HTMLInputElement) {
          scopeUseDateCheckbox.checked = true;
        }
        syncScopeGroups();
        scheduleScopePreview();
      });
    }

    scopeOverlay.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const stockChip = target.closest("[data-ai-stock-chip]");
      if (stockChip instanceof HTMLButtonElement) {
        const symbol = stockChip.dataset.symbol || "";
        const selected = parseSymbolList(scopeSymbolsInput ? scopeSymbolsInput.value : "");
        const nextSymbols = selected.includes(symbol)
          ? selected.filter(function (item) {
              return item !== symbol;
            })
          : selected.concat(symbol);
        if (scopeUseStockCheckbox instanceof HTMLInputElement) {
          scopeUseStockCheckbox.checked = true;
        }
        writeModalSymbols(nextSymbols);
        syncScopeGroups();
        scheduleScopePreview();
        return;
      }

      const removeChip = target.closest("[data-ai-selected-stock-remove]");
      if (removeChip instanceof HTMLButtonElement) {
        const symbol = removeChip.getAttribute("data-ai-selected-stock-remove") || "";
        writeModalSymbols(
          parseSymbolList(scopeSymbolsInput ? scopeSymbolsInput.value : "").filter(function (item) {
            return item !== symbol;
          })
        );
        renderSelectedStocks();
        scheduleScopePreview();
        return;
      }

      const dayButton = target.closest("[data-ai-preview-date]");
      if (dayButton instanceof HTMLButtonElement) {
        const rangeActive =
          scopeUseDateCheckbox instanceof HTMLInputElement &&
          scopeUseDateCheckbox.checked &&
          scopeStartDateInput instanceof HTMLInputElement &&
          scopeEndDateInput instanceof HTMLInputElement &&
          Boolean(scopeStartDateInput.value && scopeEndDateInput.value);
        const isInRange = dayButton.getAttribute("data-ai-preview-in-range") === "1";
        if (rangeActive && !isInRange) {
          return;
        }

        const monthValue = dayButton.getAttribute("data-ai-preview-month") || "";
        const selectedDate = dayButton.getAttribute("data-ai-preview-date") || "";
        const isSelected = dayButton.getAttribute("data-ai-preview-selected") === "1";
        requestScopePreview({ month: monthValue, selectedDate: isSelected ? "" : selectedDate });
        return;
      }

      const monthButton = target.closest("[data-ai-preview-month-link]");
      if (monthButton instanceof HTMLButtonElement) {
        const monthValue = monthButton.getAttribute("data-ai-preview-month-link") || "";
        requestScopePreview({ month: monthValue, selectedDate: "" });
        return;
      }

      const clearDayButton = target.closest("[data-ai-preview-clear-day]");
      if (clearDayButton instanceof HTMLButtonElement) {
        requestScopePreview({ selectedDate: "" });
      }
    });

    scopeOverlay.addEventListener("change", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      if (target.matches("[data-ai-content-kind-toggle]")) {
        const checkedKinds = Array.from(scopeOverlay.querySelectorAll("[data-ai-content-kind-toggle]:checked"))
          .map(function (input) {
            return input instanceof HTMLInputElement ? input.value : "";
          })
          .filter(function (value) {
            return allContentKinds.includes(value);
          });
        if (!checkedKinds.length) {
          if (target instanceof HTMLInputElement) {
            target.checked = true;
          }
          showFlash("error", "至少选择一种资料类型。");
          return;
        }
        scopeOverlay.querySelectorAll(".ai-scope-kind-toggle").forEach(function (label) {
          if (!(label instanceof HTMLElement)) {
            return;
          }
          const input = label.querySelector("input[data-ai-content-kind-toggle]");
          label.classList.toggle("is-checked", input instanceof HTMLInputElement && input.checked);
        });
        writeModalContentKinds(checkedKinds);
        scheduleScopePreview();
        return;
      }

      if (target.matches("[data-ai-preview-year], [data-ai-preview-month-number]")) {
        const yearSelect = scopeOverlay.querySelector("[data-ai-preview-year]");
        const monthSelect = scopeOverlay.querySelector("[data-ai-preview-month-number]");
        if (yearSelect instanceof HTMLSelectElement && monthSelect instanceof HTMLSelectElement) {
          const monthValue = `${yearSelect.value}-${String(monthSelect.value).padStart(2, "0")}`;
          requestScopePreview({ month: monthValue, selectedDate: "" });
        }
      }
    });

    if (modalResetButton instanceof HTMLButtonElement) {
      modalResetButton.addEventListener("click", function () {
        applyScopeToModal({
          useStockScope: false,
          symbols: [],
          contentKinds: allContentKinds.slice(),
          useDateScope: false,
          startDate: "",
          endDate: "",
          previewMonth: scopePreviewMonthInput instanceof HTMLInputElement ? scopePreviewMonthInput.value : "",
          selectedDate: "",
        });
        requestScopePreview({ selectedDate: "" });
      });
    }

    if (summaryResetButton instanceof HTMLButtonElement) {
      summaryResetButton.addEventListener("click", async function () {
        try {
          const payload = await persistScope({
            useStockScope: false,
            symbols: [],
            contentKinds: allContentKinds.slice(),
            useDateScope: false,
            startDate: "",
            endDate: "",
            previewMonth: hiddenScopeFields.previewMonth ? hiddenScopeFields.previewMonth.value : "",
            selectedDate: "",
          });
          const nextScope = normalizeScopePayload(
            {
              useStockScope: false,
              symbols: [],
              contentKinds: allContentKinds.slice(),
              useDateScope: false,
              startDate: "",
              endDate: "",
              previewMonth: payload.preview_month || "",
              selectedDate: payload.selected_date || "",
            },
            payload
          );
          applyScopeToHidden(nextScope);
          updateSummary(payload.summary);
          showFlash("success", "已恢复为全站资料范围。");
        } catch (error) {
          showFlash("error", error instanceof Error ? error.message : "恢复范围失败。");
        }
      });
    }

    scopeForm.addEventListener("submit", async function (event) {
      event.preventDefault();
      const submit = scopeForm.querySelector("button[type='submit']");
      if (submit instanceof HTMLButtonElement) {
        submit.disabled = true;
      }

      try {
        const payload = await persistScope(modalScopeState());
        const nextScope = normalizeScopePayload(modalScopeState(), payload);
        applyScopeToHidden(nextScope);
        updateSummary(payload.summary);
        closeScopeModal();
        showFlash("success", "知识范围已更新。");
      } catch (error) {
        showFlash("error", error instanceof Error ? error.message : "保存范围失败。");
      } finally {
        if (submit instanceof HTMLButtonElement) {
          submit.disabled = false;
        }
      }
    });
  }

  restoreSidebarState();
  scrollToBottom();
  startPolling();
})();
