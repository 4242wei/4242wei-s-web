(function () {
  const root = document.querySelector("[data-export-center-root]");
  if (!root) {
    return;
  }

  const exportScopeSelect = root.querySelector("[data-ai-export-scope]");
  const exportSymbolField = root.querySelector("[data-ai-export-symbol-field]");
  const exportSymbolSelect = root.querySelector("[data-ai-export-symbol]");
  const exportDateModeRadios = Array.from(root.querySelectorAll("[data-ai-export-date-mode]"));
  const exportDaysInput = root.querySelector("[data-ai-export-days]");
  const exportDaysField = root.querySelector("[data-ai-export-days-field]");
  const exportRangeGroup = root.querySelector("[data-ai-export-range-group]");
  const exportStartDateInput = root.querySelector("[data-ai-export-start-date]");
  const exportEndDateInput = root.querySelector("[data-ai-export-end-date]");
  const exportContentMode = root.querySelector("[data-ai-export-content-mode]");
  const exportTypeCheckboxes = Array.from(root.querySelectorAll("[data-ai-export-type]"));
  const exportOriginalFiles = root.querySelector("[data-ai-export-original-files]");
  const exportSourceMedia = root.querySelector("[data-ai-export-source-media]");
  const exportSubmitButton = root.querySelector("[data-ai-export-submit]");

  const artifactForm = root.querySelector("[data-ai-artifact-form]");
  const artifactKindSelect = root.querySelector("[data-ai-artifact-kind]");
  const artifactSymbolsInput = root.querySelector("[data-ai-artifact-symbols]");
  const artifactQueryInput = root.querySelector("[data-ai-artifact-query]");
  const artifactKindsInput = root.querySelector("[data-ai-artifact-kinds]");
  const artifactLimitInput = root.querySelector("[data-ai-artifact-limit]");
  const artifactLimitLabel = root.querySelector("[data-ai-artifact-limit-label]");
  const artifactRefreshInput = root.querySelector("[data-ai-artifact-refresh]");
  const artifactSubmitButton = root.querySelector("[data-ai-artifact-submit]");
  const artifactFeedback = root.querySelector("[data-ai-artifact-feedback]");
  const artifactSummary = root.querySelector("[data-ai-artifact-summary]");
  const artifactList = root.querySelector("[data-ai-artifact-list]");
  const jobList = root.querySelector("[data-ai-job-list]");

  const artifactBootstrapUrl = root.dataset.aiArtifactBootstrapUrl || "";
  const artifactTimelineJobUrl = root.dataset.aiTimelineJobUrl || "";
  const artifactCompareJobUrl = root.dataset.aiCompareJobUrl || "";
  const artifactPollIntervalMs = Math.max(
    1500,
    Number.parseInt(root.dataset.aiArtifactPollInterval || "4000", 10) || 4000,
  );

  let artifactPollTimer = 0;
  let artifactSubmitting = false;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function splitChoiceList(value) {
    return String(value || "")
      .split(/[\s,;|]+/)
      .map(function (part) {
        return part.trim();
      })
      .filter(Boolean);
  }

  function activeDateScope() {
    const checked = exportDateModeRadios.find(function (radio) {
      return radio.checked;
    });
    return checked ? checked.value : "recent";
  }

  function syncExportControls() {
    const scope = exportScopeSelect ? exportScopeSelect.value : "single_stock";
    const dateScope = activeDateScope();
    const contentMode = exportContentMode ? exportContentMode.value : "summary_plus_raw";
    const hasFiles = exportTypeCheckboxes.some(function (checkbox) {
      return checkbox.dataset.aiExportType === "files" && checkbox.checked;
    });
    const hasTranscripts = exportTypeCheckboxes.some(function (checkbox) {
      return checkbox.dataset.aiExportType === "transcripts" && checkbox.checked;
    });
    const hasAnyTypes = exportTypeCheckboxes.some(function (checkbox) {
      return checkbox.checked;
    });

    if (exportSymbolField instanceof HTMLElement) {
      exportSymbolField.classList.toggle("is-disabled", scope !== "single_stock");
    }
    if (exportSymbolSelect instanceof HTMLSelectElement) {
      exportSymbolSelect.disabled = scope !== "single_stock";
    }

    if (exportDaysInput instanceof HTMLInputElement) {
      const disableDays = dateScope !== "recent";
      exportDaysInput.disabled = disableDays;
      if (exportDaysField instanceof HTMLElement) {
        exportDaysField.hidden = disableDays;
        exportDaysField.classList.toggle("is-disabled", disableDays);
      }
    }

    [exportStartDateInput, exportEndDateInput].forEach(function (input) {
      if (!(input instanceof HTMLInputElement)) {
        return;
      }
      const disableDates = dateScope !== "range";
      input.disabled = disableDates;
      const field = input.closest(".form-field");
      if (field instanceof HTMLElement) {
        field.classList.toggle("is-disabled", disableDates);
      }
    });

    if (exportRangeGroup instanceof HTMLElement) {
      const hideRange = dateScope !== "range";
      exportRangeGroup.hidden = hideRange;
      exportRangeGroup.classList.toggle("is-disabled", hideRange);
    }

    root.querySelectorAll(".ai-export-mode-pill").forEach(function (pill) {
      const radio = pill.querySelector("input[type='radio']");
      pill.classList.toggle("is-active", radio instanceof HTMLInputElement && radio.checked);
    });

    const attachmentsLocked = contentMode === "summary_only";
    if (exportOriginalFiles instanceof HTMLInputElement) {
      exportOriginalFiles.disabled = attachmentsLocked || !hasFiles;
      if (exportOriginalFiles.disabled) {
        exportOriginalFiles.checked = false;
      }
    }

    if (exportSourceMedia instanceof HTMLInputElement) {
      exportSourceMedia.disabled = attachmentsLocked || !hasTranscripts;
      if (exportSourceMedia.disabled) {
        exportSourceMedia.checked = false;
      }
    }

    if (exportSubmitButton instanceof HTMLButtonElement) {
      exportSubmitButton.disabled = !hasAnyTypes;
    }
  }

  function setArtifactFeedback(message, tone) {
    if (!(artifactFeedback instanceof HTMLElement)) {
      return;
    }
    artifactFeedback.textContent = message || "";
    artifactFeedback.dataset.tone = tone || "muted";
    artifactFeedback.classList.toggle("is-success", tone === "success");
    artifactFeedback.classList.toggle("is-danger", tone === "danger");
    artifactFeedback.classList.toggle("is-info", tone === "info");
  }

  function syncArtifactControls() {
    if (!(artifactKindSelect instanceof HTMLSelectElement)) {
      return;
    }
    const isCompare = artifactKindSelect.value === "compare";
    if (artifactLimitLabel instanceof HTMLElement) {
      artifactLimitLabel.textContent = isCompare ? "每个股票取样数" : "时间线条数";
    }
    if (artifactLimitInput instanceof HTMLInputElement) {
      artifactLimitInput.value = artifactLimitInput.value || (isCompare ? "6" : "12");
    }
  }

  function renderArtifactSummaryCards(counts) {
    if (!(artifactSummary instanceof HTMLElement)) {
      return;
    }
    const artifactCounts = counts && counts.artifacts ? counts.artifacts : {};
    const jobCounts = counts && counts.jobs ? counts.jobs : {};
    artifactSummary.innerHTML = [
      "<article class=\"mini-fact\">",
      "  <span class=\"mini-label\">产物总数</span>",
      "  <strong>" + escapeHtml(artifactCounts.total || 0) + "</strong>",
      "</article>",
      "<article class=\"mini-fact\">",
      "  <span class=\"mini-label\">排队 / 运行</span>",
      "  <strong>" + escapeHtml(jobCounts.queued || 0) + " / " + escapeHtml(jobCounts.running || 0) + "</strong>",
      "</article>",
      "<article class=\"mini-fact\">",
      "  <span class=\"mini-label\">最近完成</span>",
      "  <strong>" + escapeHtml(jobCounts.completed || 0) + "</strong>",
      "</article>",
    ].join("");
  }

  function renderJobCards(jobs) {
    if (!(jobList instanceof HTMLElement)) {
      return;
    }
    if (!Array.isArray(jobs) || jobs.length === 0) {
      jobList.innerHTML = "<div class=\"empty-inline\"><p>还没有后台分析任务。</p></div>";
      return;
    }
    jobList.innerHTML = jobs
      .map(function (job) {
        return [
          "<article class=\"ai-artifact-card\">",
          "  <div class=\"ai-artifact-card-head\">",
          "    <strong>" + escapeHtml(job.title || "未命名任务") + "</strong>",
          "    <span class=\"status-pill is-" + escapeHtml(job.status_tone || "pending") + "\">" + escapeHtml(job.status_label || job.status || "") + "</span>",
          "  </div>",
          "  <p class=\"section-caption\">" + escapeHtml(job.summary || "") + "</p>",
          "  <div class=\"card-inline-meta\">",
          "    <span class=\"meta-chip\">" + escapeHtml(job.kind_label || job.kind || "") + "</span>",
          "    <span class=\"section-caption\">" + escapeHtml(job.display_updated_at || job.updated_at || "") + "</span>",
          job.artifact_url
            ? "    <a class=\"button button-ghost button-compact\" href=\"" + escapeHtml(job.artifact_url) + "\">Artifact</a>"
            : "",
          "  </div>",
          "</article>",
        ].join("");
      })
      .join("");
  }

  function renderArtifactCards(artifacts) {
    if (!(artifactList instanceof HTMLElement)) {
      return;
    }
    if (!Array.isArray(artifacts) || artifacts.length === 0) {
      artifactList.innerHTML = "<div class=\"empty-inline\"><p>还没有保存过分析产物。</p></div>";
      return;
    }
    artifactList.innerHTML = artifacts
      .map(function (artifact) {
        return [
          "<article class=\"ai-artifact-card\">",
          "  <div class=\"ai-artifact-card-head\">",
          "    <strong>" + escapeHtml(artifact.title || "未命名产物") + "</strong>",
          "    <span class=\"meta-chip\">" + escapeHtml(artifact.kind_label || artifact.kind || "") + "</span>",
          "  </div>",
          "  <p class=\"section-caption\">" + escapeHtml(artifact.summary || "") + "</p>",
          "  <div class=\"card-inline-meta\">",
          "    <span class=\"meta-chip\">" + escapeHtml(artifact.item_count || 0) + " items</span>",
          artifact.markdown_url
            ? "    <a class=\"button button-ghost button-compact\" href=\"" + escapeHtml(artifact.markdown_url) + "\">Markdown</a>"
            : "",
          artifact.detail_url
            ? "    <a class=\"button button-ghost button-compact\" href=\"" + escapeHtml(artifact.detail_url) + "\">JSON</a>"
            : "",
          "  </div>",
          "</article>",
        ].join("");
      })
      .join("");
  }

  function renderArtifactBootstrap(payload) {
    if (!payload || payload.ok === false) {
      return;
    }
    renderArtifactSummaryCards(payload.counts || {});
    renderJobCards(payload.recent_jobs || []);
    renderArtifactCards(payload.recent_artifacts || []);
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, Object.assign({ credentials: "same-origin" }, options || {}));
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    if (!response.ok || (payload && payload.ok === false)) {
      const message = payload && payload.error ? payload.error : "请求失败";
      throw new Error(message);
    }
    return payload || {};
  }

  async function refreshArtifactBootstrap() {
    if (!artifactBootstrapUrl) {
      return null;
    }
    const payload = await fetchJson(artifactBootstrapUrl);
    renderArtifactBootstrap(payload);
    return payload;
  }

  function scheduleArtifactPoll() {
    if (!artifactBootstrapUrl) {
      return;
    }
    window.clearTimeout(artifactPollTimer);
    artifactPollTimer = window.setTimeout(function () {
      refreshArtifactBootstrap()
        .catch(function () {
          return null;
        })
        .finally(function () {
          scheduleArtifactPoll();
        });
    }, artifactPollIntervalMs);
  }

  async function handleArtifactSubmit(event) {
    event.preventDefault();
    if (!(artifactKindSelect instanceof HTMLSelectElement) || artifactSubmitting) {
      return;
    }

    const artifactKind = artifactKindSelect.value === "compare" ? "compare" : "timeline";
    const endpoint = artifactKind === "compare" ? artifactCompareJobUrl : artifactTimelineJobUrl;
    if (!endpoint) {
      setArtifactFeedback("后台队列入口还没有准备好。", "danger");
      return;
    }

    const payload = {
      symbols: splitChoiceList(artifactSymbolsInput instanceof HTMLInputElement ? artifactSymbolsInput.value : ""),
      query: artifactQueryInput instanceof HTMLInputElement ? artifactQueryInput.value.trim() : "",
      kinds: splitChoiceList(artifactKindsInput instanceof HTMLInputElement ? artifactKindsInput.value : ""),
      refresh: artifactRefreshInput instanceof HTMLInputElement ? artifactRefreshInput.checked : false,
    };

    const parsedLimit = Number.parseInt(
      artifactLimitInput instanceof HTMLInputElement ? artifactLimitInput.value : "",
      10,
    );
    if (artifactKind === "compare") {
      payload.per_symbol_limit = Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 6;
    } else {
      payload.limit = Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : 12;
    }

    artifactSubmitting = true;
    if (artifactSubmitButton instanceof HTMLButtonElement) {
      artifactSubmitButton.disabled = true;
    }
    setArtifactFeedback("正在提交后台任务…", "info");

    try {
      const response = await fetchJson(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const job = response.job || {};
      setArtifactFeedback(
        (job.title || "分析任务") + " 已进入后台队列，稍后会自动刷新结果。",
        "success",
      );
      await refreshArtifactBootstrap().catch(function () {
        return null;
      });
    } catch (error) {
      setArtifactFeedback(error instanceof Error ? error.message : "提交失败", "danger");
    } finally {
      artifactSubmitting = false;
      if (artifactSubmitButton instanceof HTMLButtonElement) {
        artifactSubmitButton.disabled = false;
      }
      scheduleArtifactPoll();
    }
  }

  [exportScopeSelect, exportContentMode, exportStartDateInput, exportEndDateInput].forEach(function (element) {
    if (element instanceof HTMLElement) {
      element.addEventListener("change", syncExportControls);
    }
  });

  exportDateModeRadios.forEach(function (radio) {
    radio.addEventListener("change", syncExportControls);
  });

  exportTypeCheckboxes.forEach(function (checkbox) {
    checkbox.addEventListener("change", syncExportControls);
  });

  if (artifactKindSelect instanceof HTMLSelectElement) {
    artifactKindSelect.addEventListener("change", syncArtifactControls);
  }

  if (artifactForm instanceof HTMLFormElement) {
    artifactForm.addEventListener("submit", handleArtifactSubmit);
  }

  syncExportControls();
  syncArtifactControls();

  if (artifactBootstrapUrl) {
    refreshArtifactBootstrap()
      .catch(function () {
        setArtifactFeedback("暂时拿不到分析产物状态，稍后会自动重试。", "danger");
      })
      .finally(function () {
        scheduleArtifactPoll();
      });
  }

  window.addEventListener("beforeunload", function () {
    window.clearTimeout(artifactPollTimer);
  });
})();
