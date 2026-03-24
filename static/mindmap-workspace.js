(function () {
  const root = document.querySelector("[data-mindmap-root]");
  if (!root) {
    return;
  }

  const allContentKinds = ["report", "note", "file", "transcript"];
  const kindLabels = {
    root: "主轴",
    theme: "分支",
    topic: "主题",
    question: "待验证",
    catalyst: "催化",
    risk: "风险",
    evidence: "证据",
  };

  const summaryHeadline = document.querySelector("[data-ai-scope-headline]");
  const summaryDescription = document.querySelector("[data-ai-scope-description]");
  const summaryStockLabel = document.querySelector("[data-ai-scope-stock-label]");
  const summaryTimeLabel = document.querySelector("[data-ai-scope-time-label]");
  const summaryContentLabel = document.querySelector("[data-ai-scope-content-label]");
  const summaryMetrics = Array.from(document.querySelectorAll("[data-ai-scope-metric]"));
  const summaryResetButton = document.querySelector("[data-ai-scope-summary-card] [data-ai-scope-reset]");

  const composerForm = root.querySelector(".mindmap-composer");
  const modelSelect = root.querySelector("[data-mindmap-model-select]");
  const reasoningSelect = root.querySelector("[data-mindmap-reasoning-select]");
  const submitButton = composerForm ? composerForm.querySelector("button[type='submit']") : null;

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
  const scopeApplyButton = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-apply]") : null;
  const scopePreviewFrame = scopeOverlay ? scopeOverlay.querySelector("[data-ai-scope-preview-frame]") : null;
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

  const previewUrl = root.dataset.mindmapPreviewUrl || "";
  const saveUrl = root.dataset.mindmapSaveUrl || "";
  const statusUrl = root.dataset.mindmapStatusUrl || "";
  const pollInterval = Number.parseInt(root.dataset.mindmapPollInterval || "5000", 10);

  const scalerShell = root.querySelector("[data-mindmap-scaler]");
  const stage = root.querySelector("[data-mindmap-stage]");
  const linksSvg = root.querySelector("[data-mindmap-links]");
  const outlineShell = root.querySelector("[data-mindmap-outline]");
  const resultShell = root.querySelector("[data-mindmap-result-shell]");
  const board = root.querySelector("[data-mindmap-board]");
  const stageViewport = root.querySelector("[data-mindmap-stage-viewport]");
  const zoomOutButton = root.querySelector("[data-mindmap-zoom-out]");
  const zoomInButton = root.querySelector("[data-mindmap-zoom-in]");
  const zoomLabel = root.querySelector("[data-mindmap-zoom-label]");
  const fullscreenToggleButton = root.querySelector("[data-mindmap-fullscreen-toggle]");
  const panHint = root.querySelector("[data-mindmap-pan-hint]");
  const viewButtons = Array.from(root.querySelectorAll("[data-mindmap-view]"));
  const viewPanels = Array.from(root.querySelectorAll("[data-mindmap-view-panel]"));
  const stopButton = root.querySelector("form[action*='/stop'] button[type='submit']");

  const inspectorTitle = root.querySelector("[data-mindmap-node-title]");
  const inspectorPath = root.querySelector("[data-mindmap-node-path]");
  const inspectorSummary = root.querySelector("[data-mindmap-node-summary]");
  const inspectorSymbolsBlock = root.querySelector("[data-mindmap-node-symbols-block]");
  const inspectorSymbols = root.querySelector("[data-mindmap-node-symbols]");
  const inspectorEvidence = root.querySelector("[data-mindmap-node-evidence]");
  const inspectorTimeline = root.querySelector("[data-mindmap-timeline]");
  const inspectorSourceRelations = root.querySelector("[data-mindmap-source-relations]");
  const inspectorInsights = root.querySelector("[data-mindmap-insights]");
  const payloadScript = document.getElementById("mindmap-payload-json");

  let scopePreviewTimer = 0;
  let scopeClosingTimer = 0;
  let scopePreviewController = null;
  let renderFrame = 0;
  let currentScale = 1;
  let activeView = "canvas";
  let activeNodeId = "";
  let payload = null;
  let pseudoFullscreen = false;
  let lastFullscreenState = false;
  let dragState = null;
  let viewportMetrics = {
    offsetX: 0,
    offsetY: 0,
    stageWidth: 0,
    stageHeight: 0,
  };
  let viewportRefreshFrame = 0;
  const nodeIndex = new Map();
  const pathIndex = new Map();
  const collapsedNodes = new Set();

  function setText(node, value) {
    if (node instanceof HTMLElement) {
      node.textContent = value;
    }
  }

  function isFullscreenActive() {
    return pseudoFullscreen || (resultShell instanceof HTMLElement && document.fullscreenElement === resultShell);
  }

  function syncPanHint() {
    if (!(panHint instanceof HTMLElement)) {
      return;
    }
    if (activeView !== "canvas") {
      panHint.textContent = "切回导图后可拖动画布";
      return;
    }
    panHint.textContent = isFullscreenActive() ? "全屏中：空白处拖动画布" : "空白处可拖动画布";
  }

  function syncFullscreenState() {
    const active = isFullscreenActive();
    if (resultShell instanceof HTMLElement) {
      resultShell.classList.toggle("is-pseudo-fullscreen", pseudoFullscreen);
    }
    document.body.classList.toggle("mindmap-fullscreen-open", active);
    if (fullscreenToggleButton instanceof HTMLButtonElement) {
      fullscreenToggleButton.textContent = active ? "退出全屏" : "全屏查看";
      fullscreenToggleButton.setAttribute("aria-pressed", active ? "true" : "false");
    }
    syncPanHint();
    window.requestAnimationFrame(function () {
      scheduleDrawCrossLinks();
    });
  }

  async function toggleFullscreen() {
    if (!(resultShell instanceof HTMLElement)) {
      return;
    }
    if (document.fullscreenElement === resultShell) {
      await document.exitFullscreen();
      return;
    }
    if (pseudoFullscreen) {
      pseudoFullscreen = false;
      syncFullscreenState();
      return;
    }

    const canUseNativeFullscreen = typeof resultShell.requestFullscreen === "function" && document.fullscreenEnabled;
    if (!canUseNativeFullscreen) {
      pseudoFullscreen = true;
      syncFullscreenState();
      return;
    }

    try {
      await resultShell.requestFullscreen();
    } catch (error) {
      pseudoFullscreen = true;
      syncFullscreenState();
    }
  }

  function parseSymbolList(rawValue) {
    return String(rawValue || "")
      .split(/[\s,;，、]+/)
      .map(function (value) {
        return value.trim().toUpperCase().replace(/^\$/, "").replace(/[^A-Z0-9.\-]/g, "");
      })
      .filter(function (value, index, list) {
        return value && list.indexOf(value) === index;
      });
  }

  function parseContentKinds(rawValue) {
    const parsed = (String(rawValue || "").toLowerCase().match(/report|note|file|transcript/g) || []).filter(function (
      value,
      index,
      list
    ) {
      return allContentKinds.includes(value) && list.indexOf(value) === index;
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
    item.className = "flash-item is-" + kind;
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
      scopeSymbolsInput.value = symbols.join(", ");
    }
  }

  function writeModalContentKinds(contentKinds) {
    if (scopeContentKindsInput instanceof HTMLInputElement) {
      scopeContentKindsInput.value = (contentKinds || allContentKinds).join(", ");
    }
  }

  function applyScopeToHidden(scope) {
    if (hiddenScopeFields.useStockScope) {
      hiddenScopeFields.useStockScope.value = scope.useStockScope ? "1" : "0";
    }
    if (hiddenScopeFields.symbols) {
      hiddenScopeFields.symbols.value = (scope.symbols || []).join(", ");
    }
    if (hiddenScopeFields.contentKinds) {
      hiddenScopeFields.contentKinds.value = (scope.contentKinds || allContentKinds).join(", ");
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
    setText(summaryHeadline, summary.headline || "当前读取全站资料");
    setText(summaryDescription, summary.description || "");
    setText(summaryStockLabel, summary.stock_label || "股票范围：全站");
    setText(summaryTimeLabel, summary.time_label || "时间窗口：不限");
    setText(summaryContentLabel, summary.content_label || "资料类型：日报、笔记、文件、转录");
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
    if (summaryResetButton instanceof HTMLButtonElement) {
      summaryResetButton.hidden = !summary.has_filters;
    }
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

  function renderSelectedStocks() {
    const selectedSymbols = parseSymbolList(scopeSymbolsInput ? scopeSymbolsInput.value : "");
    if (scopeSelectedStocks instanceof HTMLElement) {
      scopeSelectedStocks.innerHTML = "";
      if (!selectedSymbols.length) {
        const empty = document.createElement("p");
        empty.className = "section-caption";
        empty.textContent = "未限定股票时，导图会读取当前范围内的全部资料。";
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
    if (!(scopePreviewFrame instanceof HTMLElement) || !previewUrl) {
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
      scopePreviewFrame.innerHTML = '<div class="empty-inline"><p>请先至少选择一只股票，再预览这个范围内的资料时间线。</p></div>';
      return;
    }
    if (state.useDateScope && (!state.startDate || !state.endDate)) {
      scopePreviewFrame.innerHTML = '<div class="empty-inline"><p>请先补全起止日期，再查看时间窗口预览。</p></div>';
      return;
    }
    if (state.useDateScope && state.startDate && state.endDate && state.startDate > state.endDate) {
      scopePreviewFrame.innerHTML = '<div class="empty-inline"><p>起始日期不能晚于结束日期，请先调整时间窗口。</p></div>';
      return;
    }

    const params = new URLSearchParams();
    params.set("use_stock_scope", state.useStockScope ? "1" : "0");
    params.set("content_kinds", (state.contentKinds || []).join(", "));
    params.set("symbols", (state.symbols || []).join(", "));
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
      const response = await fetch(previewUrl + "?" + params.toString(), {
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
    if (!saveUrl) {
      return null;
    }
    const formData = new FormData();
    formData.set("session_id", "");
    formData.set("use_stock_scope", scope.useStockScope ? "1" : "0");
    formData.set("content_kinds", (scope.contentKinds || []).join(", "));
    formData.set("symbols", (scope.symbols || []).join(", "));
    formData.set("use_date_scope", scope.useDateScope ? "1" : "0");
    formData.set("start_date", scope.startDate || "");
    formData.set("end_date", scope.endDate || "");
    formData.set("preview_month", scope.previewMonth || "");
    formData.set("selected_date", scope.selectedDate || "");

    const response = await fetch(saveUrl, {
      method: "POST",
      body: formData,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.message || "保存范围失败。");
    }
    return data;
  }

  function normalizeScopePayload(scope, response) {
    const serverScope = response && response.scope ? response.scope : {};
    return {
      useStockScope: Boolean(serverScope.use_stock_scope ?? scope.useStockScope),
      symbols: parseSymbolList(serverScope.symbols_text || (scope.symbols || []).join(", ")),
      contentKinds: parseContentKinds(serverScope.content_kinds_text || (scope.contentKinds || []).join(", ")),
      useDateScope: Boolean(serverScope.use_date_scope ?? scope.useDateScope),
      startDate: serverScope.start_date || scope.startDate || "",
      endDate: serverScope.end_date || scope.endDate || "",
      previewMonth: response && response.preview_month ? response.preview_month : serverScope.preview_month || scope.previewMonth || "",
      selectedDate: response && Object.prototype.hasOwnProperty.call(response, "selected_date")
        ? response.selected_date
        : serverScope.selected_date || scope.selectedDate || "",
    };
  }

  function syncReasoningOptions() {
    if (!(modelSelect instanceof HTMLSelectElement) || !(reasoningSelect instanceof HTMLSelectElement)) {
      return;
    }
    const selectedOption = modelSelect.options[modelSelect.selectedIndex];
    const defaultReasoning = selectedOption ? selectedOption.dataset.defaultReasoning || "medium" : "medium";
    let levels = ["medium"];
    try {
      levels = JSON.parse((selectedOption && selectedOption.dataset.reasoningLevels) || '["medium"]');
    } catch (error) {
      levels = ["medium"];
    }
    if (!Array.isArray(levels) || !levels.length) {
      levels = ["medium"];
    }

    const currentValue = reasoningSelect.value;
    reasoningSelect.innerHTML = "";
    levels.forEach(function (level) {
      const option = document.createElement("option");
      option.value = level;
      option.textContent = level;
      if (level === currentValue || (!levels.includes(currentValue) && level === defaultReasoning)) {
        option.selected = true;
      }
      reasoningSelect.appendChild(option);
    });
  }

  function readPayload() {
    if (!(payloadScript instanceof HTMLScriptElement)) {
      return null;
    }
    try {
      return JSON.parse(payloadScript.textContent || "null");
    } catch (error) {
      return null;
    }
  }

  function ensureTransformLayer() {
    if (!(scalerShell instanceof HTMLElement) || !(stage instanceof HTMLElement) || !(linksSvg instanceof SVGElement)) {
      return null;
    }
    let layer = scalerShell.querySelector(".mindmap-stage-transform");
    if (layer instanceof HTMLElement) {
      return layer;
    }
    layer = document.createElement("div");
    layer.className = "mindmap-stage-transform";
    layer.appendChild(linksSvg);
    layer.appendChild(stage);
    scalerShell.appendChild(layer);
    return layer;
  }

  function endViewportDrag(pointerId) {
    if (!(stageViewport instanceof HTMLElement) || !dragState) {
      return;
    }
    if (typeof pointerId === "number" && dragState.pointerId !== pointerId) {
      return;
    }
    dragState = null;
    stageViewport.classList.remove("is-dragging");
  }

  function bindViewportDragging() {
    if (!(stageViewport instanceof HTMLElement)) {
      return;
    }

    stageViewport.addEventListener("pointerdown", function (event) {
      if (activeView !== "canvas" || event.button !== 0) {
        return;
      }
      if (!(event.target instanceof HTMLElement)) {
        return;
      }
      if (event.target.closest("[data-node-button], .mindmap-collapse-toggle")) {
        return;
      }

      dragState = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        scrollLeft: stageViewport.scrollLeft,
        scrollTop: stageViewport.scrollTop,
      };
      stageViewport.classList.add("is-dragging");
      event.preventDefault();
    });

    document.addEventListener("pointermove", function (event) {
      if (!dragState || dragState.pointerId !== event.pointerId) {
        return;
      }
      const deltaX = event.clientX - dragState.startX;
      const deltaY = event.clientY - dragState.startY;
      if (stageViewport instanceof HTMLElement) {
        stageViewport.scrollLeft = dragState.scrollLeft - deltaX;
        stageViewport.scrollTop = dragState.scrollTop - deltaY;
      }
    });

    document.addEventListener("pointerup", function (event) {
      endViewportDrag(event.pointerId);
    });
    document.addEventListener("pointercancel", function (event) {
      endViewportDrag(event.pointerId);
    });
  }

  function buildNodeIndex(node, path) {
    if (!node || typeof node !== "object") {
      return;
    }
    const nextPath = path.concat(node.label || "");
    nodeIndex.set(node.id, node);
    pathIndex.set(node.id, nextPath);
    (node.children || []).forEach(function (child) {
      buildNodeIndex(child, nextPath);
    });
  }

  function createMetaChip(text) {
    const chip = document.createElement("span");
    chip.className = "mindmap-node-chip";
    chip.textContent = text;
    return chip;
  }

  function renderList(container, items, emptyText) {
    if (!(container instanceof HTMLElement)) {
      return;
    }
    container.innerHTML = "";
    if (!Array.isArray(items) || !items.length) {
      const empty = document.createElement("li");
      empty.className = "mindmap-empty-item";
      empty.textContent = emptyText;
      container.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      const row = document.createElement("li");
      row.textContent = item;
      container.appendChild(row);
    });
  }

  function renderTimeline(node) {
    if (!(inspectorTimeline instanceof HTMLElement)) {
      return;
    }
    inspectorTimeline.innerHTML = "";

    if (Array.isArray(node.time_signals) && node.time_signals.length) {
      node.time_signals.forEach(function (item) {
        const card = document.createElement("article");
        card.className = "mindmap-timeline-item";
        const body = document.createElement("p");
        body.textContent = item;
        card.appendChild(body);
        inspectorTimeline.appendChild(card);
      });
      return;
    }

    if (!Array.isArray(payload.timeline_highlights) || !payload.timeline_highlights.length) {
      const empty = document.createElement("p");
      empty.className = "section-caption";
      empty.textContent = "当前节点没有明显的时间演化线索。";
      inspectorTimeline.appendChild(empty);
      return;
    }

    payload.timeline_highlights.forEach(function (item) {
      const card = document.createElement("article");
      card.className = "mindmap-timeline-item";
      const head = document.createElement("div");
      head.className = "mindmap-timeline-head";
      const date = document.createElement("span");
      date.className = "meta-chip";
      date.textContent = item.date || "时间线";
      const label = document.createElement("strong");
      label.textContent = item.label || "关键节点";
      head.appendChild(date);
      head.appendChild(label);
      card.appendChild(head);
      if (item.summary) {
        const body = document.createElement("p");
        body.textContent = item.summary;
        card.appendChild(body);
      }
      inspectorTimeline.appendChild(card);
    });
  }

  function renderSourceRelations(node) {
    if (!(inspectorSourceRelations instanceof HTMLElement)) {
      return;
    }
    inspectorSourceRelations.innerHTML = "";

    if (Array.isArray(node.source_notes) && node.source_notes.length) {
      node.source_notes.forEach(function (item) {
        const card = document.createElement("article");
        card.className = "mindmap-source-relation-card";
        const tag = document.createElement("span");
        tag.className = "meta-chip";
        tag.textContent = "节点备注";
        const body = document.createElement("p");
        body.textContent = item;
        card.appendChild(tag);
        card.appendChild(body);
        inspectorSourceRelations.appendChild(card);
      });
      return;
    }

    if (!Array.isArray(payload.source_relations) || !payload.source_relations.length) {
      const empty = document.createElement("p");
      empty.className = "section-caption";
      empty.textContent = "当前节点没有额外的资料关系备注。";
      inspectorSourceRelations.appendChild(empty);
      return;
    }

    payload.source_relations.forEach(function (item) {
      const card = document.createElement("article");
      card.className = "mindmap-source-relation-card";
      const top = document.createElement("div");
      top.className = "mindmap-source-relation-head";
      top.appendChild(createMetaChip(item.label || "关系"));
      const route = document.createElement("strong");
      route.textContent = (item.from || "资料 A") + " → " + (item.to || "资料 B");
      top.appendChild(route);
      card.appendChild(top);
      if (item.summary) {
        const body = document.createElement("p");
        body.textContent = item.summary;
        card.appendChild(body);
      }
      inspectorSourceRelations.appendChild(card);
    });
  }

  function updateInspector(node) {
    if (!node) {
      return;
    }

    setText(inspectorTitle, node.label || payload.title || "研究导图");
    setText(inspectorPath, (pathIndex.get(node.id) || [payload.title || node.label || "导图"]).join(" / "));
    setText(inspectorSummary, node.summary || payload.summary || "这里会显示当前节点的摘要。");

    if (inspectorSymbolsBlock instanceof HTMLElement) {
      const symbols = Array.isArray(node.symbols) ? node.symbols : [];
      inspectorSymbolsBlock.hidden = !symbols.length;
      if (inspectorSymbols instanceof HTMLElement) {
        inspectorSymbols.innerHTML = "";
        symbols.forEach(function (symbol) {
          inspectorSymbols.appendChild(createMetaChip(symbol));
        });
      }
    }

    renderList(inspectorEvidence, Array.isArray(node.evidence) ? node.evidence : [], "当前节点没有单独抽出的证据锚点。");
    renderTimeline(node);
    renderSourceRelations(node);
    renderList(inspectorInsights, Array.isArray(payload.insights) ? payload.insights : [], "当前导图没有额外摘要。");
  }

  function selectNode(nodeId, options) {
    const node = nodeIndex.get(nodeId) || payload.root;
    activeNodeId = node.id;

    root.querySelectorAll("[data-node-button]").forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }
      button.classList.toggle("is-active", button.getAttribute("data-node-button") === activeNodeId);
    });
    root.querySelectorAll("[data-mindmap-outline-button]").forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }
      button.classList.toggle("is-active", button.getAttribute("data-mindmap-outline-button") === activeNodeId);
    });

    updateInspector(node);
    if (options && options.scroll) {
      const selectedButton = root.querySelector("[data-node-button='" + activeNodeId + "']");
      if (selectedButton instanceof HTMLElement) {
        selectedButton.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
      }
    }
  }

  function createNodeBranch(node, depth) {
    const branch = document.createElement("div");
    branch.className = "mindmap-branch";
    branch.dataset.nodeId = node.id;
    branch.style.setProperty("--mindmap-depth", String(depth));

    const shell = document.createElement("div");
    shell.className = "mindmap-node-shell";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "mindmap-node-button";
    button.setAttribute("data-node-button", node.id);
    button.dataset.kind = node.kind || "topic";

    const copy = document.createElement("span");
    copy.className = "mindmap-node-copy";
    const title = document.createElement("strong");
    title.textContent = node.label || "未命名节点";
    copy.appendChild(title);
    if (node.summary) {
      const summary = document.createElement("span");
      summary.className = "mindmap-node-summary";
      summary.textContent = node.summary;
      copy.appendChild(summary);
    }

    const meta = document.createElement("span");
    meta.className = "mindmap-node-meta";
    meta.appendChild(createMetaChip(kindLabels[node.kind] || "节点"));
    if (Array.isArray(node.symbols) && node.symbols.length) {
      meta.appendChild(createMetaChip(node.symbols.join(" / ")));
    }
    if (Array.isArray(node.time_signals) && node.time_signals.length) {
      meta.appendChild(createMetaChip("时间 " + node.time_signals.length));
    }
    if (Array.isArray(node.source_notes) && node.source_notes.length) {
      meta.appendChild(createMetaChip("关系 " + node.source_notes.length));
    }
    if (Array.isArray(node.children) && node.children.length) {
      meta.appendChild(createMetaChip("子节点 " + node.children.length));
    }
    copy.appendChild(meta);
    button.appendChild(copy);
    button.addEventListener("click", function () {
      selectNode(node.id);
    });
    shell.appendChild(button);

    const hasChildren = Array.isArray(node.children) && node.children.length;
    if (hasChildren) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "mindmap-collapse-toggle";
      toggle.setAttribute("aria-label", collapsedNodes.has(node.id) ? "展开分支" : "折叠分支");
      toggle.setAttribute("aria-expanded", collapsedNodes.has(node.id) ? "false" : "true");
      toggle.textContent = collapsedNodes.has(node.id) ? "+" : "−";
      toggle.addEventListener("click", function (event) {
        event.stopPropagation();
        if (collapsedNodes.has(node.id)) {
          collapsedNodes.delete(node.id);
        } else {
          collapsedNodes.add(node.id);
        }
        renderMindmap();
      });
      shell.appendChild(toggle);
    }
    branch.appendChild(shell);

    if (hasChildren) {
      const children = document.createElement("div");
      children.className = "mindmap-node-children";
      children.hidden = collapsedNodes.has(node.id);
      node.children.forEach(function (child) {
        children.appendChild(createNodeBranch(child, depth + 1));
      });
      branch.appendChild(children);
    }

    return branch;
  }

  function renderOutlineNode(node, depth, container) {
    const entry = document.createElement("div");
    entry.className = "mindmap-outline-entry";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "mindmap-outline-button";
    button.setAttribute("data-mindmap-outline-button", node.id);
    button.style.setProperty("--outline-depth", String(depth));
    const title = document.createElement("strong");
    title.textContent = node.label || "未命名节点";
    button.appendChild(title);
    if (node.summary) {
      const summary = document.createElement("span");
      summary.textContent = node.summary;
      button.appendChild(summary);
    }
    button.addEventListener("click", function () {
      activeView = "canvas";
      switchView("canvas");
      selectNode(node.id, { scroll: true });
    });
    entry.appendChild(button);
    container.appendChild(entry);

    (node.children || []).forEach(function (child) {
      renderOutlineNode(child, depth + 1, container);
    });
  }

  function scheduleDrawCrossLinks() {
    if (renderFrame) {
      window.cancelAnimationFrame(renderFrame);
    }
    renderFrame = window.requestAnimationFrame(function () {
      renderFrame = 0;
      drawCrossLinks();
    });
  }

  function drawCrossLinks() {
    const transformLayer = ensureTransformLayer();
    if (!(transformLayer instanceof HTMLElement) || !(stage instanceof HTMLElement) || !(linksSvg instanceof SVGElement)) {
      return;
    }
    if (activeView !== "canvas" || !payload || !Array.isArray(payload.cross_links)) {
      linksSvg.innerHTML = "";
      return;
    }

    const width = Math.max(stage.scrollWidth + 80, 880);
    const height = Math.max(stage.scrollHeight + 80, 480);
    linksSvg.setAttribute("viewBox", "0 0 " + width + " " + height);
    linksSvg.setAttribute("width", String(width));
    linksSvg.setAttribute("height", String(height));
    linksSvg.innerHTML = "";

    const layerRect = transformLayer.getBoundingClientRect();
    payload.cross_links.forEach(function (link) {
      const from = stage.querySelector("[data-node-button='" + link.from + "']");
      const to = stage.querySelector("[data-node-button='" + link.to + "']");
      if (!(from instanceof HTMLElement) || !(to instanceof HTMLElement) || !from.offsetParent || !to.offsetParent) {
        return;
      }

      const fromRect = from.getBoundingClientRect();
      const toRect = to.getBoundingClientRect();
      const startX = (fromRect.right - layerRect.left) / currentScale;
      const startY = (fromRect.top + fromRect.height / 2 - layerRect.top) / currentScale;
      const endX = (toRect.left - layerRect.left) / currentScale;
      const endY = (toRect.top + toRect.height / 2 - layerRect.top) / currentScale;
      const bend = Math.max((endX - startX) * 0.4, 50);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("class", "mindmap-cross-link");
      path.setAttribute("d", "M " + startX + " " + startY + " C " + (startX + bend) + " " + startY + ", " + (endX - bend) + " " + endY + ", " + endX + " " + endY);
      linksSvg.appendChild(path);

      if (link.label) {
        const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
        label.setAttribute("class", "mindmap-cross-link-label");
        label.setAttribute("x", String((startX + endX) / 2));
        label.setAttribute("y", String((startY + endY) / 2 - 8));
        label.textContent = link.label;
        linksSvg.appendChild(label);
      }
    });
  }

  function setScale(nextScale) {
    const transformLayer = ensureTransformLayer();
    if (!(transformLayer instanceof HTMLElement) || !(scalerShell instanceof HTMLElement) || !(stage instanceof HTMLElement)) {
      return;
    }
    currentScale = Math.min(1.55, Math.max(0.72, nextScale));
    const width = Math.max(stage.scrollWidth + 80, 880);
    const height = Math.max(stage.scrollHeight + 80, 480);
    scalerShell.style.width = width * currentScale + "px";
    scalerShell.style.height = height * currentScale + "px";
    transformLayer.style.width = width + "px";
    transformLayer.style.height = height + "px";
    transformLayer.style.transform = "scale(" + currentScale + ")";
    if (zoomLabel instanceof HTMLElement) {
      zoomLabel.textContent = Math.round(currentScale * 100) + "%";
    }
    scheduleDrawCrossLinks();
  }

  function switchView(nextView) {
    activeView = nextView === "outline" ? "outline" : "canvas";
    endViewportDrag();
    viewButtons.forEach(function (button) {
      button.classList.toggle("is-active", button.getAttribute("data-mindmap-view") === activeView);
    });
    viewPanels.forEach(function (panel) {
      const match = panel.getAttribute("data-mindmap-view-panel") === activeView;
      panel.hidden = !match;
    });
    if (board instanceof HTMLElement) {
      board.dataset.activeView = activeView;
    }
    if (stageViewport instanceof HTMLElement) {
      stageViewport.classList.toggle("is-outline-hidden", activeView !== "canvas");
    }
    syncPanHint();
    scheduleDrawCrossLinks();
  }

  function renderMindmap() {
    payload = readPayload();
    if (!payload || !payload.root || !(stage instanceof HTMLElement) || !(outlineShell instanceof HTMLElement)) {
      return;
    }

    nodeIndex.clear();
    pathIndex.clear();
    buildNodeIndex(payload.root, []);

    stage.innerHTML = "";
    outlineShell.innerHTML = "";
    stage.appendChild(createNodeBranch(payload.root, 0));
    renderOutlineNode(payload.root, 0, outlineShell);

    if (!nodeIndex.has(activeNodeId)) {
      activeNodeId = payload.root.id;
    }
    selectNode(activeNodeId);
    switchView(activeView);
    setScale(currentScale);
  }

  function clampScale(nextScale) {
    return Math.min(1.55, Math.max(0.72, nextScale));
  }

  function queueViewportRefresh(options) {
    if (viewportRefreshFrame) {
      window.cancelAnimationFrame(viewportRefreshFrame);
    }
    viewportRefreshFrame = window.requestAnimationFrame(function () {
      viewportRefreshFrame = 0;
      refreshViewportLayout(options);
    });
  }

  function syncPanHint() {
    if (!(panHint instanceof HTMLElement)) {
      return;
    }
    if (activeView !== "canvas") {
      panHint.textContent = "\u5207\u56de\u5bfc\u56fe\u540e\u53ef\u62d6\u52a8\u753b\u5e03";
      return;
    }
    panHint.textContent = isFullscreenActive()
      ? "\u5168\u5c4f\u4e2d\uff1a\u6eda\u8f6e\u7f29\u653e\uff0c\u6309\u4f4f\u62d6\u52a8\u753b\u5e03"
      : "\u7a7a\u767d\u5904\u53ef\u62d6\u52a8\u753b\u5e03";
  }

  function syncFullscreenState() {
    const active = isFullscreenActive();
    if (resultShell instanceof HTMLElement) {
      resultShell.classList.toggle("is-pseudo-fullscreen", pseudoFullscreen);
    }
    document.body.classList.toggle("mindmap-fullscreen-open", active);
    if (fullscreenToggleButton instanceof HTMLButtonElement) {
      fullscreenToggleButton.textContent = active ? "\u9000\u51fa\u5168\u5c4f" : "\u5168\u5c4f\u67e5\u770b";
      fullscreenToggleButton.setAttribute("aria-pressed", active ? "true" : "false");
    }
    syncPanHint();
    queueViewportRefresh({
      focusNodeId: !lastFullscreenState && active ? activeNodeId : "",
      behavior: "auto",
      redraw: true,
    });
    lastFullscreenState = active;
  }

  function updateViewportMetrics() {
    const transformLayer = ensureTransformLayer();
    if (
      !(transformLayer instanceof HTMLElement) ||
      !(scalerShell instanceof HTMLElement) ||
      !(stage instanceof HTMLElement) ||
      !(stageViewport instanceof HTMLElement)
    ) {
      return viewportMetrics;
    }

    const stageWidth = Math.max(stage.scrollWidth + 80, 880);
    const stageHeight = Math.max(stage.scrollHeight + 80, 480);
    const viewportWidth = Math.max(stageViewport.clientWidth, 0);
    const viewportHeight = Math.max(stageViewport.clientHeight, 0);
    const sidePadding = isFullscreenActive() ? Math.max(260, Math.round(viewportWidth * 0.32)) : Math.max(170, Math.round(viewportWidth * 0.18));
    const verticalPadding = isFullscreenActive()
      ? Math.max(190, Math.round(viewportHeight * 0.26))
      : Math.max(120, Math.round(viewportHeight * 0.16));
    const scaledWidth = stageWidth * currentScale;
    const scaledHeight = stageHeight * currentScale;
    const workspaceWidth = Math.max(scaledWidth + sidePadding * 2, viewportWidth + sidePadding * 2);
    const workspaceHeight = Math.max(scaledHeight + verticalPadding * 2, viewportHeight + verticalPadding * 2);
    const offsetX = Math.max(sidePadding, Math.round((workspaceWidth - scaledWidth) / 2));
    const offsetY = Math.max(verticalPadding, Math.round((workspaceHeight - scaledHeight) / 2));

    scalerShell.style.width = workspaceWidth + "px";
    scalerShell.style.height = workspaceHeight + "px";
    transformLayer.style.width = stageWidth + "px";
    transformLayer.style.height = stageHeight + "px";
    transformLayer.style.transform = "translate3d(" + offsetX + "px, " + offsetY + "px, 0) scale(" + currentScale + ")";

    if (zoomLabel instanceof HTMLElement) {
      zoomLabel.textContent = Math.round(currentScale * 100) + "%";
    }

    viewportMetrics = {
      offsetX: offsetX,
      offsetY: offsetY,
      stageWidth: stageWidth,
      stageHeight: stageHeight,
    };
    return viewportMetrics;
  }

  function clampViewportScroll() {
    if (!(stageViewport instanceof HTMLElement)) {
      return;
    }
    const maxScrollLeft = Math.max(0, stageViewport.scrollWidth - stageViewport.clientWidth);
    const maxScrollTop = Math.max(0, stageViewport.scrollHeight - stageViewport.clientHeight);
    stageViewport.scrollLeft = Math.min(maxScrollLeft, Math.max(0, stageViewport.scrollLeft));
    stageViewport.scrollTop = Math.min(maxScrollTop, Math.max(0, stageViewport.scrollTop));
  }

  function focusNodeInViewport(nodeId, behavior) {
    if (!(stageViewport instanceof HTMLElement) || activeView !== "canvas") {
      return;
    }
    const selectedButton = root.querySelector("[data-node-button='" + nodeId + "']");
    if (!(selectedButton instanceof HTMLElement)) {
      return;
    }
    const viewportRect = stageViewport.getBoundingClientRect();
    const buttonRect = selectedButton.getBoundingClientRect();
    const nextLeft = stageViewport.scrollLeft + (buttonRect.left + buttonRect.width / 2 - (viewportRect.left + viewportRect.width / 2));
    const nextTop = stageViewport.scrollTop + (buttonRect.top + buttonRect.height / 2 - (viewportRect.top + viewportRect.height / 2));
    stageViewport.scrollTo({
      left: Math.max(0, nextLeft),
      top: Math.max(0, nextTop),
      behavior: behavior || "smooth",
    });
  }

  function refreshViewportLayout(options) {
    if (!(stageViewport instanceof HTMLElement) || activeView !== "canvas" || stageViewport.offsetParent === null) {
      if (!options || options.redraw !== false) {
        scheduleDrawCrossLinks();
      }
      return;
    }

    const previousMetrics =
      viewportMetrics.stageWidth && viewportMetrics.stageHeight
        ? viewportMetrics
        : {
            offsetX: 0,
            offsetY: 0,
            stageWidth: 0,
            stageHeight: 0,
          };
    const centerX = stageViewport.clientWidth / 2;
    const centerY = stageViewport.clientHeight / 2;
    const worldX = currentScale ? (stageViewport.scrollLeft + centerX - previousMetrics.offsetX) / currentScale : 0;
    const worldY = currentScale ? (stageViewport.scrollTop + centerY - previousMetrics.offsetY) / currentScale : 0;
    const nextMetrics = updateViewportMetrics();
    stageViewport.scrollLeft = worldX * currentScale + nextMetrics.offsetX - centerX;
    stageViewport.scrollTop = worldY * currentScale + nextMetrics.offsetY - centerY;
    clampViewportScroll();

    if (options && options.focusNodeId) {
      focusNodeInViewport(options.focusNodeId, options.behavior || "auto");
    }

    if (!options || options.redraw !== false) {
      scheduleDrawCrossLinks();
    }
  }

  function endViewportDrag(pointerId) {
    if (!(stageViewport instanceof HTMLElement) || !dragState) {
      return;
    }
    if (typeof pointerId === "number" && dragState.pointerId !== pointerId) {
      return;
    }
    if (typeof dragState.pointerId === "number" && typeof stageViewport.releasePointerCapture === "function") {
      try {
        stageViewport.releasePointerCapture(dragState.pointerId);
      } catch (error) {
        // Ignore browsers that already released the capture.
      }
    }
    dragState = null;
    stageViewport.classList.remove("is-dragging");
  }

  function bindViewportDragging() {
    if (!(stageViewport instanceof HTMLElement)) {
      return;
    }

    stageViewport.addEventListener("pointerdown", function (event) {
      if (activeView !== "canvas" || (event.button !== 0 && event.button !== 1)) {
        return;
      }
      if (!(event.target instanceof HTMLElement)) {
        return;
      }
      if (event.button === 0 && event.target.closest("[data-node-button], .mindmap-collapse-toggle")) {
        return;
      }

      dragState = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        scrollLeft: stageViewport.scrollLeft,
        scrollTop: stageViewport.scrollTop,
      };
      stageViewport.classList.add("is-dragging");
      if (typeof stageViewport.setPointerCapture === "function") {
        try {
          stageViewport.setPointerCapture(event.pointerId);
        } catch (error) {
          // Ignore browsers that do not support pointer capture here.
        }
      }
      event.preventDefault();
    });

    document.addEventListener("pointermove", function (event) {
      if (!dragState || dragState.pointerId !== event.pointerId) {
        return;
      }
      const deltaX = event.clientX - dragState.startX;
      const deltaY = event.clientY - dragState.startY;
      if (stageViewport instanceof HTMLElement) {
        stageViewport.scrollLeft = dragState.scrollLeft - deltaX;
        stageViewport.scrollTop = dragState.scrollTop - deltaY;
      }
    });

    document.addEventListener("pointerup", function (event) {
      endViewportDrag(event.pointerId);
    });
    document.addEventListener("pointercancel", function (event) {
      endViewportDrag(event.pointerId);
    });
    stageViewport.addEventListener("lostpointercapture", function (event) {
      endViewportDrag(event.pointerId);
    });
    stageViewport.addEventListener("auxclick", function (event) {
      if (event.button === 1) {
        event.preventDefault();
      }
    });
  }

  function bindViewportZooming() {
    if (!(stageViewport instanceof HTMLElement)) {
      return;
    }

    stageViewport.addEventListener(
      "wheel",
      function (event) {
        if (activeView !== "canvas") {
          return;
        }
        const shouldZoom = isFullscreenActive() || event.ctrlKey || event.metaKey;
        if (!shouldZoom) {
          return;
        }

        const normalizedDelta = event.deltaMode === 1 ? event.deltaY * 18 : event.deltaY;
        const zoomFactor = Math.exp(-normalizedDelta / 960);
        event.preventDefault();
        setScale(currentScale * zoomFactor, {
          anchorClientX: event.clientX,
          anchorClientY: event.clientY,
        });
      },
      { passive: false }
    );
  }

  function selectNode(nodeId, options) {
    const node = nodeIndex.get(nodeId) || payload.root;
    activeNodeId = node.id;

    root.querySelectorAll("[data-node-button]").forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }
      button.classList.toggle("is-active", button.getAttribute("data-node-button") === activeNodeId);
    });
    root.querySelectorAll("[data-mindmap-outline-button]").forEach(function (button) {
      if (!(button instanceof HTMLButtonElement)) {
        return;
      }
      button.classList.toggle("is-active", button.getAttribute("data-mindmap-outline-button") === activeNodeId);
    });

    updateInspector(node);
    if (options && options.scroll) {
      focusNodeInViewport(activeNodeId, options.behavior || "smooth");
    }
  }

  function setScale(nextScale, options) {
    if (
      !(stageViewport instanceof HTMLElement) ||
      !(scalerShell instanceof HTMLElement) ||
      !(stage instanceof HTMLElement) ||
      activeView !== "canvas" ||
      stageViewport.offsetParent === null
    ) {
      return;
    }
    const previousScale = currentScale;
    const previousMetrics = updateViewportMetrics();
    const viewportRect = stageViewport.getBoundingClientRect();
    const anchorClientX = options && typeof options.anchorClientX === "number" ? options.anchorClientX : viewportRect.left + viewportRect.width / 2;
    const anchorClientY = options && typeof options.anchorClientY === "number" ? options.anchorClientY : viewportRect.top + viewportRect.height / 2;
    const anchorViewportX = anchorClientX - viewportRect.left;
    const anchorViewportY = anchorClientY - viewportRect.top;
    const worldX = previousScale ? (stageViewport.scrollLeft + anchorViewportX - previousMetrics.offsetX) / previousScale : 0;
    const worldY = previousScale ? (stageViewport.scrollTop + anchorViewportY - previousMetrics.offsetY) / previousScale : 0;

    currentScale = clampScale(nextScale);
    const nextMetrics = updateViewportMetrics();
    stageViewport.scrollLeft = worldX * currentScale + nextMetrics.offsetX - anchorViewportX;
    stageViewport.scrollTop = worldY * currentScale + nextMetrics.offsetY - anchorViewportY;
    clampViewportScroll();
  }

  function switchView(nextView) {
    activeView = nextView === "outline" ? "outline" : "canvas";
    endViewportDrag();
    viewButtons.forEach(function (button) {
      button.classList.toggle("is-active", button.getAttribute("data-mindmap-view") === activeView);
    });
    viewPanels.forEach(function (panel) {
      const match = panel.getAttribute("data-mindmap-view-panel") === activeView;
      panel.hidden = !match;
    });
    if (board instanceof HTMLElement) {
      board.dataset.activeView = activeView;
    }
    if (stageViewport instanceof HTMLElement) {
      stageViewport.classList.toggle("is-outline-hidden", activeView !== "canvas");
    }
    if (zoomOutButton instanceof HTMLButtonElement) {
      zoomOutButton.disabled = activeView !== "canvas";
    }
    if (zoomInButton instanceof HTMLButtonElement) {
      zoomInButton.disabled = activeView !== "canvas";
    }
    syncPanHint();
    if (activeView === "canvas") {
      queueViewportRefresh({
        focusNodeId: activeNodeId,
        behavior: "auto",
        redraw: true,
      });
      return;
    }
    scheduleDrawCrossLinks();
  }

  function startPolling() {
    if (!statusUrl || !(stopButton instanceof HTMLButtonElement)) {
      return;
    }
    const tick = async function () {
      try {
        const response = await fetch(statusUrl, {
          headers: {
            Accept: "application/json",
            "X-Requested-With": "XMLHttpRequest",
          },
          cache: "no-store",
        });
        if (!response.ok) {
          return;
        }
        const data = await response.json();
        if (!data.has_pending) {
          window.location.reload();
        }
      } catch (error) {
        window.clearInterval(timerId);
      }
    };
    const timerId = window.setInterval(tick, Math.max(pollInterval, 2000));
    tick();
  }

  if (modelSelect instanceof HTMLSelectElement) {
    modelSelect.addEventListener("change", syncReasoningOptions);
    syncReasoningOptions();
  }

  if (composerForm instanceof HTMLFormElement && submitButton instanceof HTMLButtonElement) {
    composerForm.addEventListener("submit", function () {
      submitButton.disabled = true;
      submitButton.textContent = "生成中...";
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
        const monthValue = dayButton.getAttribute("data-ai-preview-month") || "";
        const selectedDate = dayButton.getAttribute("data-ai-preview-date") || "";
        const isSelected = dayButton.getAttribute("data-ai-preview-selected") === "1";
        requestScopePreview({ month: monthValue, selectedDate: isSelected ? "" : selectedDate });
        return;
      }

      const monthButton = target.closest("[data-ai-preview-month-link]");
      if (monthButton instanceof HTMLButtonElement) {
        requestScopePreview({ month: monthButton.getAttribute("data-ai-preview-month-link") || "", selectedDate: "" });
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
          requestScopePreview({ month: yearSelect.value + "-" + String(monthSelect.value).padStart(2, "0"), selectedDate: "" });
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
          const response = await persistScope({
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
              previewMonth: response.preview_month || "",
              selectedDate: response.selected_date || "",
            },
            response
          );
          applyScopeToHidden(nextScope);
          updateSummary(response.summary);
          showFlash("success", "已恢复为全站资料范围。");
        } catch (error) {
          showFlash("error", error instanceof Error ? error.message : "恢复范围失败。");
        }
      });
    }

    const applyScope = async function () {
      if (!(scopeApplyButton instanceof HTMLButtonElement)) {
        return;
      }
      scopeApplyButton.disabled = true;
      try {
        const response = await persistScope(modalScopeState());
        const nextScope = normalizeScopePayload(modalScopeState(), response);
        applyScopeToHidden(nextScope);
        updateSummary(response.summary);
        closeScopeModal();
        showFlash("success", "导图读取范围已更新。");
      } catch (error) {
        showFlash("error", error instanceof Error ? error.message : "保存范围失败。");
      } finally {
        scopeApplyButton.disabled = false;
      }
    };

    if (scopeApplyButton instanceof HTMLButtonElement) {
      scopeApplyButton.addEventListener("click", applyScope);
    }
    scopeForm.addEventListener("submit", function (event) {
      event.preventDefault();
      applyScope();
    });
  }

  viewButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      switchView(button.getAttribute("data-mindmap-view") || "canvas");
    });
  });

  if (zoomOutButton instanceof HTMLButtonElement) {
    zoomOutButton.addEventListener("click", function () {
      setScale(currentScale - 0.1);
    });
  }
  if (zoomInButton instanceof HTMLButtonElement) {
    zoomInButton.addEventListener("click", function () {
      setScale(currentScale + 0.1);
    });
  }
  if (fullscreenToggleButton instanceof HTMLButtonElement) {
    fullscreenToggleButton.addEventListener("click", function () {
      toggleFullscreen();
    });
  }
  document.addEventListener("fullscreenchange", function () {
    if (document.fullscreenElement !== resultShell) {
      pseudoFullscreen = false;
    }
    syncFullscreenState();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && pseudoFullscreen) {
      pseudoFullscreen = false;
      syncFullscreenState();
    }
  });
  bindViewportDragging();
  bindViewportZooming();
  window.addEventListener("resize", function () {
    queueViewportRefresh({
      redraw: true,
    });
  });

  payload = readPayload();
  if (payload && payload.root) {
    activeNodeId = payload.root.id;
    renderMindmap();
  }
  syncFullscreenState();
  startPolling();
})();
