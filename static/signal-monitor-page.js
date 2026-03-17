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

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function updateCountNodes(selector, value, formatter) {
    document.querySelectorAll(selector).forEach(function (node) {
      if (!(node instanceof HTMLElement)) {
        return;
      }
      node.textContent = typeof formatter === "function" ? formatter(value, node) : String(value);
    });
  }

  function setReportCount(value) {
    updateCountNodes("[data-signal-report-count]", value, function (count, node) {
      return node.classList.contains("summary-count") ? String(count) : `${count} 份`;
    });
  }

  function setTodayCount(value) {
    updateCountNodes("[data-signal-today-count]", value, function (count) {
      return `${count} 份`;
    });
  }

  function setSourceCount(value) {
    updateCountNodes("[data-signal-source-count]", value, function (count, node) {
      return node.classList.contains("summary-count") ? String(count) : `${count} 个`;
    });
  }

  function syncEmptyState() {
    const list = document.querySelector("[data-signal-report-list]");
    const emptyState = document.querySelector("[data-signal-report-empty-state]");
    const count = document.querySelectorAll("[data-signal-report-card]").length;
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
      showFlash("success", (payload && payload.message) || "信息监控报告已移入回收站。");
    }, REMOVE_TRANSITION_MS);
  }

  function bindReportDeleteForms() {
    document.querySelectorAll("form[data-signal-report-delete-form]").forEach(function (form) {
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
            const card = form.closest("[data-signal-report-card]");
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

  function extractXHandle(rawValue) {
    const input = String(rawValue || "").trim();
    if (!input) {
      return "";
    }

    let candidate = input;
    const lowered = input.toLowerCase();
    if (lowered.includes("x.com/") || lowered.includes("twitter.com/")) {
      const normalized = input.includes("://") ? input : `https://${input}`;
      try {
        const parsed = new URL(normalized);
        candidate = parsed.pathname.replace(/^\/+/, "").split("/")[0] || "";
      } catch (error) {
        candidate = input;
      }
    }

    candidate = candidate.replace(/^@+/, "");
    candidate = candidate.replace(/[^A-Za-z0-9_]/g, "");
    return candidate.slice(0, 15);
  }

  function sourceKey(source) {
    if (source.source_type === "x" && source.handle) {
      return `x:${String(source.handle).toLowerCase()}`;
    }
    return `name:${String(source.query || source.display_name || "").trim().toLowerCase()}`;
  }

  function normalizeSource(rawSource, existingKeys) {
    if (!rawSource || typeof rawSource !== "object") {
      return null;
    }

    const query = String(rawSource.query || rawSource.profile_url || rawSource.handle || rawSource.url || "").trim();
    const displayName = String(rawSource.display_name || rawSource.name || "").trim();
    const handle = extractXHandle(query || displayName);
    let sourceType = String(rawSource.source_type || "").trim().toLowerCase();
    if (sourceType !== "x" && sourceType !== "name") {
      sourceType = handle ? "x" : "name";
    }
    if (sourceType === "x" && !handle) {
      sourceType = "name";
    }

    const normalized = {
      id: String(rawSource.id || "").trim(),
      display_name: (displayName || handle || query).slice(0, 120),
      source_type: sourceType,
      handle: handle,
      profile_url: sourceType === "x" && handle ? `https://x.com/${handle}` : String(rawSource.profile_url || "").trim().slice(0, 400),
      query: (query || displayName).slice(0, 400),
      notes: String(rawSource.notes || "").trim().slice(0, 240),
      enabled: rawSource.enabled !== false,
    };

    if (!normalized.display_name) {
      return null;
    }

    const key = sourceKey(normalized);
    if (existingKeys.has(key)) {
      return null;
    }
    existingKeys.add(key);
    return normalized;
  }

  function buildSource(rawValue, rawNotes) {
    const cleanValue = String(rawValue || "").trim();
    if (!cleanValue) {
      return null;
    }

    return normalizeSource(
      {
        display_name: extractXHandle(cleanValue) || cleanValue,
        query: cleanValue,
        notes: rawNotes,
      },
      new Set()
    );
  }

  function parseSeedSources() {
    const seedNode = document.querySelector("[data-signal-source-seed]");
    if (!(seedNode instanceof HTMLScriptElement)) {
      return [];
    }

    try {
      const parsed = JSON.parse(seedNode.textContent || "[]");
      if (!Array.isArray(parsed)) {
        return [];
      }
      const keys = new Set();
      return parsed
        .map(function (item) {
          return normalizeSource(item, keys);
        })
        .filter(Boolean);
    } catch (error) {
      return [];
    }
  }

  function setupSourceBuilder() {
    const form = document.querySelector("[data-signal-source-form]");
    const terminateForm = document.querySelector("[data-signal-terminate-form]");
    if (!(form instanceof HTMLFormElement)) {
      return;
    }

    const hiddenInput = form.querySelector("[data-signal-source-hidden]");
    const confirmInput = form.querySelector("[data-signal-confirm-existing]");
    const sourceList = form.querySelector("[data-signal-source-list]");
    const sourceInput = form.querySelector("[data-signal-source-input]");
    const noteInput = form.querySelector("[data-signal-source-note]");
    const addButton = form.querySelector("[data-signal-source-add]");
    const exampleButtons = form.querySelectorAll("[data-signal-example]");

    let sources = parseSeedSources();

    function syncHidden() {
      if (hiddenInput instanceof HTMLInputElement) {
        hiddenInput.value = JSON.stringify(sources);
      }
      setSourceCount(sources.length);
    }

    function renderSources() {
      if (!(sourceList instanceof HTMLElement)) {
        syncHidden();
        return;
      }

      sourceList.innerHTML = "";
      if (!sources.length) {
        const empty = document.createElement("div");
        empty.className = "empty-card signal-source-empty";
        empty.innerHTML = "<p class=\"empty-title\">还没有监控来源</p><p>先加一个 X 地址、@handle 或名称。这里默认支持把 `SemiAnalysis` 当成第一个示例。</p>";
        sourceList.appendChild(empty);
        syncHidden();
        return;
      }

      sources.forEach(function (source, index) {
        const card = document.createElement("article");
        card.className = "module-card signal-source-card";
        card.setAttribute("data-signal-source-index", String(index));
        card.innerHTML =
          `<div class="signal-source-card-head">` +
          `<div>` +
          `<div class="card-inline-meta">` +
          `<span class="meta-chip">${source.source_type === "x" ? "X / Twitter" : "名称线索"}</span>` +
          `${source.handle ? `<span class="meta-chip">@${escapeHtml(source.handle)}</span>` : ""}` +
          `${!source.enabled ? `<span class="meta-chip">已停用</span>` : ""}` +
          `</div>` +
          `<h4>${escapeHtml(source.display_name || "未命名来源")}</h4>` +
          `</div>` +
          `<button class="danger-button danger-button-compact" type="button" data-signal-remove="${index}">移除</button>` +
          `</div>` +
          `<div class="signal-source-fields">` +
          `<label class="form-field">` +
          `<span class="field-label">显示名称</span>` +
          `<input type="text" value="${escapeHtml(source.display_name || "")}" data-signal-field="display_name" data-signal-index="${index}">` +
          `</label>` +
          `<label class="form-field">` +
          `<span class="field-label">备注</span>` +
          `<input type="text" value="${escapeHtml(source.notes || "")}" placeholder="例如：半导体 / AI 供应链 / 舆论变化" data-signal-field="notes" data-signal-index="${index}">` +
          `</label>` +
          `</div>` +
          `<div class="signal-source-card-foot">` +
          `<span class="signal-source-url">${escapeHtml(source.profile_url || source.query)}</span>` +
          `<label class="signal-source-toggle">` +
          `<input type="checkbox" ${source.enabled ? "checked" : ""} data-signal-enabled="${index}">` +
          `<span>引入监控</span>` +
          `</label>` +
          `</div>`;
        sourceList.appendChild(card);
      });

      syncHidden();
    }

    function addSource(rawValue, rawNotes) {
      const candidate = buildSource(rawValue, rawNotes);
      if (!candidate) {
        return 0;
      }

      const key = sourceKey(candidate);
      const existingKeys = new Set(sources.map(sourceKey));
      if (existingKeys.has(key)) {
        return 0;
      }

      sources.push(candidate);
      renderSources();
      return 1;
    }

    function resetConfirmFlag() {
      if (confirmInput instanceof HTMLInputElement) {
        confirmInput.value = "0";
      }
    }

    renderSources();

    if (addButton instanceof HTMLButtonElement) {
      addButton.addEventListener("click", function () {
        const rawValue = sourceInput instanceof HTMLInputElement ? sourceInput.value : "";
        const rawNotes = noteInput instanceof HTMLInputElement ? noteInput.value : "";
        if (addSource(rawValue, rawNotes)) {
          if (sourceInput instanceof HTMLInputElement) {
            sourceInput.value = "";
            sourceInput.focus();
          }
          if (noteInput instanceof HTMLInputElement) {
            noteInput.value = "";
          }
          resetConfirmFlag();
          return;
        }

        if (String(rawValue || "").trim()) {
          showFlash("error", "请输入有效且未重复的来源。");
        }
      });
    }

    if (sourceInput instanceof HTMLInputElement) {
      sourceInput.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") {
          return;
        }
        event.preventDefault();
        if (addSource(sourceInput.value, noteInput instanceof HTMLInputElement ? noteInput.value : "")) {
          sourceInput.value = "";
          if (noteInput instanceof HTMLInputElement) {
            noteInput.value = "";
          }
          resetConfirmFlag();
          return;
        }
        if (sourceInput.value.trim()) {
          showFlash("error", "请输入有效且未重复的来源。");
        }
      });
    }

    if (sourceList instanceof HTMLElement) {
      sourceList.addEventListener("click", function (event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        const removeButton = target.closest("[data-signal-remove]");
        if (!(removeButton instanceof HTMLElement)) {
          return;
        }
        const index = Number.parseInt(removeButton.getAttribute("data-signal-remove") || "-1", 10);
        if (Number.isNaN(index) || index < 0) {
          return;
        }
        sources.splice(index, 1);
        renderSources();
        resetConfirmFlag();
      });

      sourceList.addEventListener("input", function (event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }
        const field = target.getAttribute("data-signal-field");
        const index = Number.parseInt(target.getAttribute("data-signal-index") || "-1", 10);
        if (Number.isNaN(index) || index < 0 || !sources[index]) {
          return;
        }
        if (field === "display_name" && target instanceof HTMLInputElement) {
          sources[index].display_name = target.value.slice(0, 120);
          syncHidden();
        }
        if (field === "notes" && target instanceof HTMLInputElement) {
          sources[index].notes = target.value.slice(0, 240);
          syncHidden();
        }
      });

      sourceList.addEventListener("change", function (event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
          return;
        }
        const index = Number.parseInt(target.getAttribute("data-signal-enabled") || "-1", 10);
        if (Number.isNaN(index) || index < 0 || !sources[index]) {
          return;
        }
        sources[index].enabled = target.checked;
        syncHidden();
      });
    }

    exampleButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        const exampleValue = button.getAttribute("data-signal-example") || "";
        if (!addSource(exampleValue, "")) {
          showFlash("error", "这个示例已经在当前监控名单里了。");
        }
        resetConfirmFlag();
      });
    });

    form.addEventListener("submit", function (event) {
      const submitter = event.submitter;
      syncHidden();

      if (!sources.length) {
        event.preventDefault();
        showFlash("error", "请先添加至少一个来源。");
        if (sourceInput instanceof HTMLInputElement) {
          sourceInput.focus();
        }
        return;
      }

      if (!sources.some(function (source) { return source.enabled !== false; })) {
        event.preventDefault();
        showFlash("error", "请至少保留一个启用中的来源。");
        return;
      }

      const isRunAction = submitter instanceof HTMLButtonElement && submitter.hasAttribute("data-signal-run-button");
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
    const panel = document.querySelector("[data-signal-status-panel]");
    updateCountNodes("[data-signal-status-label]", runtime.status_label || "待运行");
    updateCountNodes("[data-signal-runtime-label]", runtime.status_label || "待运行");
    updateCountNodes("[data-signal-started-at]", runtime.started_at_label || "尚未运行");
    updateCountNodes("[data-signal-finished-at]", runtime.finished_at_label || "尚未完成");
    updateCountNodes("[data-signal-runtime-sources]", (runtime.source_ids || []).length, function (count) {
      return `${count} 个`;
    });
    setTodayCount(payload.today_report_count || 0);
    setReportCount(payload.report_count || 0);
    setSourceCount(payload.source_count || 0);

    const form = document.querySelector("[data-signal-source-form]");
    const runButton = document.querySelector("[data-signal-run-button]");
    if (form instanceof HTMLElement) {
      form.dataset.running = runtime.is_running ? "true" : "false";
      form.dataset.todayExists = payload.today_report_count ? "true" : "false";
    }
    if (runButton instanceof HTMLButtonElement) {
      runButton.textContent = runtime.is_running ? "监控运行中" : "运行监控";
    }
    if (panel instanceof HTMLElement) {
      panel.setAttribute("data-signal-running", runtime.is_running ? "true" : "false");
      panel.setAttribute("data-signal-status", runtime.status || "idle");
    }

    const messageNode = document.querySelector("[data-signal-message]");
    if (messageNode instanceof HTMLElement) {
      const message = runtime.message || "";
      messageNode.textContent = message;
      messageNode.hidden = !message;
    }

    const errorNode = document.querySelector("[data-signal-error]");
    if (errorNode instanceof HTMLElement) {
      const error = runtime.error || "";
      errorNode.textContent = error;
      errorNode.hidden = !error;
    }
  }

  function setupStatusPolling() {
    const panel = document.querySelector("[data-signal-status-panel]");
    if (!(panel instanceof HTMLElement)) {
      return;
    }

    const statusUrl = panel.getAttribute("data-status-url") || "";
    const pollSeconds = Number.parseInt(panel.getAttribute("data-signal-poll-seconds") || "5", 10);
    let previousStatus = panel.getAttribute("data-signal-status") || "idle";
    let previousReportFilename = panel.getAttribute("data-signal-report-filename") || "";
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
          const latestReportFilename =
            payload.latest_report && payload.latest_report.filename
              ? String(payload.latest_report.filename)
              : "";
          if (previousStatus === "running" && nextStatus !== "running") {
            if (latestReportFilename) {
              window.location.href = `/signals?report=${encodeURIComponent(latestReportFilename)}#signal-reading-panel`;
            } else {
              window.location.reload();
            }
            return;
          }
          if (latestReportFilename && latestReportFilename !== previousReportFilename) {
            previousReportFilename = latestReportFilename;
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

    if (panel.getAttribute("data-signal-running") === "true") {
      startPolling();
    }

    window.addEventListener("pageshow", function () {
      poll();
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    setupSourceBuilder();
    bindReportDeleteForms();
    setupStatusPolling();
    syncEmptyState();
  });
})();
