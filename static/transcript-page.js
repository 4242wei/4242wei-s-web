(function () {
  const MODAL_TRANSITION_MS = 220;
  const REMOVE_TRANSITION_MS = 180;
  const TRANSCRIPT_CATEGORY_LABELS = {
    work: "工作",
    reading: "阅读",
  };
  let activeTranscriptCategoryFilter = "";

  function getTranscriptScopeSymbol() {
    const scopeNode = document.querySelector("[data-transcript-scope-symbol]");
    if (!(scopeNode instanceof HTMLElement)) {
      return "";
    }

    return String(scopeNode.getAttribute("data-transcript-scope-symbol") || "").trim().toUpperCase();
  }

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

  function formatFileSize(bytes) {
    const size = Number(bytes || 0);
    if (!Number.isFinite(size) || size <= 0) {
      return "0 B";
    }

    if (size < 1024) {
      return `${size} B`;
    }
    if (size < 1024 * 1024) {
      return `${(size / 1024).toFixed(size < 10 * 1024 ? 1 : 0)} KB`;
    }
    if (size < 1024 * 1024 * 1024) {
      return `${(size / (1024 * 1024)).toFixed(size < 10 * 1024 * 1024 ? 1 : 0)} MB`;
    }
    return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  }

  function padDatePart(value) {
    return String(value).padStart(2, "0");
  }

  function normalizeInferredDate(year, month, day) {
    const numericYear = Number.parseInt(year, 10);
    const numericMonth = Number.parseInt(month, 10);
    const numericDay = Number.parseInt(day, 10);
    if (
      !Number.isInteger(numericYear) ||
      !Number.isInteger(numericMonth) ||
      !Number.isInteger(numericDay) ||
      numericMonth < 1 ||
      numericMonth > 12 ||
      numericDay < 1 ||
      numericDay > 31
    ) {
      return "";
    }

    const value = new Date(Date.UTC(numericYear, numericMonth - 1, numericDay));
    if (
      value.getUTCFullYear() !== numericYear ||
      value.getUTCMonth() !== numericMonth - 1 ||
      value.getUTCDate() !== numericDay
    ) {
      return "";
    }

    return `${numericYear}-${padDatePart(numericMonth)}-${padDatePart(numericDay)}`;
  }

  function inferMeetingDateFromFilename(filename) {
    const stem = String(filename || "").replace(/\.[^./\\]+$/, "");
    if (!stem) {
      return "";
    }

    const separatorMatch = stem.match(/(?:^|[^\d])(20\d{2})[-_.\s](\d{1,2})[-_.\s](\d{1,2})(?!\d)/);
    if (separatorMatch) {
      return normalizeInferredDate(separatorMatch[1], separatorMatch[2], separatorMatch[3]);
    }

    const compactMatch = stem.match(/(?:^|[^\d])(20\d{2})(\d{2})(\d{2})(?!\d)/);
    if (compactMatch) {
      return normalizeInferredDate(compactMatch[1], compactMatch[2], compactMatch[3]);
    }

    return "";
  }

  function setupTranscriptUpload(form) {
    const root = form.querySelector("[data-transcript-upload-root]");
    const input = form.querySelector("[data-transcript-upload-input]");
    const trigger = form.querySelector("[data-transcript-upload-trigger]");
    const summary = form.querySelector("[data-transcript-upload-summary]");
    const filesContainer = form.querySelector("[data-transcript-upload-files]");
    const copyButton = form.querySelector("[data-transcript-copy-filenames]");
    const dateHint = form.querySelector("[data-transcript-upload-date-hint]");
    const dateInput = form.querySelector("[data-transcript-meeting-date]");
    const manualFlagInput = form.querySelector("[data-transcript-meeting-date-manual]");

    if (
      !(root instanceof HTMLElement) ||
      !(input instanceof HTMLInputElement) ||
      !(trigger instanceof HTMLButtonElement) ||
      !(filesContainer instanceof HTMLElement)
    ) {
      return;
    }

    let dragDepth = 0;

    const updateDateHint = function (message) {
      if (!(dateHint instanceof HTMLElement)) {
        return;
      }

      const text = String(message || "").trim();
      dateHint.hidden = !text;
      dateHint.textContent = text;
    };

    const setMeetingDateFromFiles = function (files) {
      if (!(dateInput instanceof HTMLInputElement) || !(manualFlagInput instanceof HTMLInputElement)) {
        return;
      }

      const firstFile = files.length ? files[0] : null;
      const inferredDate = firstFile ? inferMeetingDateFromFilename(firstFile.name) : "";
      if (!firstFile || !inferredDate) {
        updateDateHint("");
        return;
      }

      if (manualFlagInput.value === "1") {
        updateDateHint(`首个文件名里识别到日期 ${inferredDate}，但你已经手动改过会议日期，所以这次不会自动覆盖。`);
        return;
      }

      dateInput.dataset.programmaticUpdate = "true";
      dateInput.value = inferredDate;
      manualFlagInput.value = "0";
      dateInput.dataset.programmaticUpdate = "";
      updateDateHint(`已按首个文件名自动识别会议日期：${inferredDate}`);
    };

    const renderFiles = function (fileList) {
      const files = Array.from(fileList || []);
      filesContainer.replaceChildren();

      if (!files.length) {
        const placeholder = document.createElement("p");
        placeholder.className = "transcript-upload-placeholder";
        placeholder.textContent = "文件名会显示在这里，你可以直接选中文字复制。";
        filesContainer.appendChild(placeholder);
        if (summary instanceof HTMLElement) {
          summary.textContent = "还没选文件";
        }
        if (copyButton instanceof HTMLButtonElement) {
          copyButton.hidden = true;
        }
        root.classList.remove("has-files");
        updateDateHint("");
        return;
      }

      const list = document.createElement("ol");
      list.className = "transcript-upload-file-items";
      files.forEach(function (file, index) {
        const item = document.createElement("li");
        item.className = "transcript-upload-file-item";

        const fileName = document.createElement("span");
        fileName.className = "transcript-upload-file-name";
        fileName.textContent = file.name;

        const meta = document.createElement("span");
        meta.className = "transcript-upload-file-meta";
        const inferredDate = index === 0 ? inferMeetingDateFromFilename(file.name) : "";
        meta.textContent = inferredDate
          ? `${formatFileSize(file.size)} | 首个文件日期 ${inferredDate}`
          : formatFileSize(file.size);

        item.appendChild(fileName);
        item.appendChild(meta);
        list.appendChild(item);
      });
      filesContainer.appendChild(list);

      if (summary instanceof HTMLElement) {
        summary.textContent =
          files.length === 1
            ? files[0].name
            : `已选 ${files.length} 个文件，会按首个文件日期批量创建任务`;
      }
      if (copyButton instanceof HTMLButtonElement) {
        copyButton.hidden = false;
      }
      root.classList.add("has-files");
      setMeetingDateFromFiles(files);
    };

    const syncFilesToInput = function (fileList) {
      const files = Array.from(fileList || []);
      if (!files.length) {
        renderFiles([]);
        return;
      }

      if (typeof DataTransfer === "function") {
        const transfer = new DataTransfer();
        files.forEach(function (file) {
          transfer.items.add(file);
        });
        input.files = transfer.files;
      } else {
        try {
          input.files = fileList;
        } catch (error) {
          renderFiles(files);
          return;
        }
      }

      renderFiles(input.files);
    };

    const hasDraggedFiles = function (event) {
      if (!event.dataTransfer) {
        return false;
      }

      return Array.from(event.dataTransfer.types || []).indexOf("Files") >= 0;
    };

    if (dateInput instanceof HTMLInputElement && manualFlagInput instanceof HTMLInputElement) {
      const markDateAsManual = function () {
        if (dateInput.dataset.programmaticUpdate === "true") {
          return;
        }
        manualFlagInput.value = "1";
      };

      dateInput.addEventListener("input", markDateAsManual);
      dateInput.addEventListener("change", markDateAsManual);
    }

    trigger.addEventListener("click", function () {
      input.click();
    });

    input.addEventListener("change", function () {
      renderFiles(input.files);
    });

    if (copyButton instanceof HTMLButtonElement) {
      copyButton.addEventListener("click", function () {
        const names = Array.from(input.files || []).map(function (file) {
          return file.name;
        });
        if (!names.length) {
          return;
        }

        if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
          showFlash("error", "当前浏览器不支持直接复制，请手动选中文件名。");
          return;
        }

        navigator.clipboard
          .writeText(names.join("\n"))
          .then(function () {
            showFlash("success", `已复制 ${names.length} 个文件名。`);
          })
          .catch(function () {
            showFlash("error", "复制文件名失败了，你可以直接选中文字再复制。");
          });
      });
    }

    ["dragenter", "dragover"].forEach(function (eventName) {
      root.addEventListener(eventName, function (event) {
        if (!hasDraggedFiles(event)) {
          return;
        }

        event.preventDefault();
        if (eventName === "dragenter") {
          dragDepth += 1;
        }
        root.classList.add("is-dragover");
        if (event.dataTransfer) {
          event.dataTransfer.dropEffect = "copy";
        }
      });
    });

    root.addEventListener("dragleave", function (event) {
      if (!hasDraggedFiles(event)) {
        return;
      }

      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) {
        root.classList.remove("is-dragover");
      }
    });

    root.addEventListener("drop", function (event) {
      if (!hasDraggedFiles(event)) {
        return;
      }

      event.preventDefault();
      dragDepth = 0;
      root.classList.remove("is-dragover");
      syncFilesToInput(event.dataTransfer ? event.dataTransfer.files : []);
    });

    renderFiles(input.files);
  }

  function bindTranscriptValidation(form) {
    const knownSymbols = new Set(parseSymbolList(form.dataset.knownStockSymbols || ""));
    const linkToggle = form.querySelector("[name='link_to_stock']");
    const multiToggle = form.querySelector("[name='link_to_multiple_stocks']");
    const singleSelect = form.querySelector("[name='linked_symbol']");
    const multiInput = form.querySelector("[name='linked_symbols_text']");
    const mediaInput = form.querySelector("[data-transcript-upload-input]");
    const fileUrlHintInput = form.querySelector("[name='file_url_hint']");

    if (!(linkToggle instanceof HTMLInputElement) || !(multiToggle instanceof HTMLInputElement)) {
      return;
    }

    form.addEventListener("submit", function (event) {
      const selectedFiles =
        mediaInput instanceof HTMLInputElement ? Array.from(mediaInput.files || []) : [];
      if (
        selectedFiles.length > 1 &&
        fileUrlHintInput instanceof HTMLInputElement &&
        fileUrlHintInput.value.trim()
      ) {
        event.preventDefault();
        showFlash("error", "批量上传本地文件时，请先清空公网文件地址。");
        fileUrlHintInput.focus();
        return;
      }

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
      const status = card.getAttribute("data-transcript-status") || "";
      return status === "queued" || status === "processing";
    }).length;

    return {
      total: cards.length,
      completed: completed,
      queue: queue,
      linked: linked,
      active: active,
    };
  }

  function computeCategoryCountsFromDom() {
    const countsByCategory = {};
    document.querySelectorAll("[data-transcript-category-card]").forEach(function (card) {
      if (!(card instanceof HTMLElement)) {
        return;
      }

      const key = card.getAttribute("data-transcript-category-card") || "";
      if (!key) {
        return;
      }

      countsByCategory[key] = {
        total: 0,
        completed: 0,
        queue: 0,
      };
    });

    document.querySelectorAll("[data-transcript-card]").forEach(function (card) {
      if (!(card instanceof HTMLElement)) {
        return;
      }

      const key = card.getAttribute("data-transcript-category") || "work";
      if (!countsByCategory[key]) {
        countsByCategory[key] = {
          total: 0,
          completed: 0,
          queue: 0,
        };
      }

      countsByCategory[key].total += 1;
      if (card.getAttribute("data-transcript-group") === "completed") {
        countsByCategory[key].completed += 1;
      } else {
        countsByCategory[key].queue += 1;
      }
    });

    return countsByCategory;
  }

  function getTranscriptCategoryLabel(category) {
    return TRANSCRIPT_CATEGORY_LABELS[category] || TRANSCRIPT_CATEGORY_LABELS.work;
  }

  function normalizeTranscriptCategoryFilter(category) {
    return Object.prototype.hasOwnProperty.call(TRANSCRIPT_CATEGORY_LABELS, category) ? category : "";
  }

  function updateTranscriptCategoryChip(node, category) {
    if (!(node instanceof HTMLElement)) {
      return;
    }

    node.classList.remove("is-work", "is-reading");
    node.classList.add(`is-${category}`);
    node.setAttribute("data-transcript-category", category);
    node.textContent = getTranscriptCategoryLabel(category);
  }

  function updateTranscriptCategoryChipCollection(nodes, transcriptId, category) {
    nodes.forEach(function (node) {
      if (!(node instanceof HTMLElement)) {
        return;
      }

      if ((node.getAttribute("data-transcript-id") || "") !== transcriptId) {
        return;
      }

      updateTranscriptCategoryChip(node, category);
    });
  }

  function setTranscriptCategoryBusy(transcriptId, isBusy) {
    document.querySelectorAll("[data-transcript-category-switcher]").forEach(function (node) {
      if (!(node instanceof HTMLElement)) {
        return;
      }

      if ((node.getAttribute("data-transcript-id") || "") !== transcriptId) {
        return;
      }

      if (isBusy) {
        node.setAttribute("aria-busy", "true");
      } else {
        node.removeAttribute("aria-busy");
      }
    });

    document.querySelectorAll("[data-transcript-category-set]").forEach(function (node) {
      if (!(node instanceof HTMLButtonElement)) {
        return;
      }

      if ((node.getAttribute("data-transcript-id") || "") !== transcriptId) {
        return;
      }

      node.disabled = isBusy;
      node.classList.toggle("is-updating", isBusy);
      if (isBusy) {
        node.setAttribute("aria-busy", "true");
      } else {
        node.removeAttribute("aria-busy");
      }
    });
  }

  function updateTranscriptCategoryButtonCollection(nodes, transcriptId, category) {
    nodes.forEach(function (node) {
      if (!(node instanceof HTMLButtonElement)) {
        return;
      }

      if ((node.getAttribute("data-transcript-id") || "") !== transcriptId) {
        return;
      }

      const targetCategory = node.getAttribute("data-transcript-category-set") || "";
      const isActive = targetCategory === category;
      node.classList.toggle("is-active", isActive);
      node.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function applyTranscriptCategory(transcriptId, category) {
    document.querySelectorAll("[data-transcript-card]").forEach(function (card) {
      if (!(card instanceof HTMLElement)) {
        return;
      }

      if ((card.getAttribute("data-transcript-id") || "") !== transcriptId) {
        return;
      }

      card.setAttribute("data-transcript-category", category);
    });

    updateTranscriptCategoryChipCollection(
      document.querySelectorAll("[data-transcript-category-chip]"),
      transcriptId,
      category
    );
    updateTranscriptCategoryButtonCollection(
      document.querySelectorAll("[data-transcript-category-set]"),
      transcriptId,
      category
    );

    const template = document.getElementById(`transcript-reader-${transcriptId}`);
    if (template instanceof HTMLTemplateElement) {
      updateTranscriptCategoryChipCollection(
        template.content.querySelectorAll("[data-transcript-category-chip]"),
        transcriptId,
        category
      );
      updateTranscriptCategoryButtonCollection(
        template.content.querySelectorAll("[data-transcript-category-set]"),
        transcriptId,
        category
      );
    }

    applyTranscriptCategoryFilter();
    syncTranscriptStats();
  }

  function updateCountNodes(selector, value, unit) {
    document.querySelectorAll(selector).forEach(function (node) {
      if (node instanceof HTMLElement) {
        node.textContent = node.classList.contains("summary-count") ? `${value}` : `${value} ${unit}`;
      }
    });
  }

  function syncQueueEmptyState() {
    const list = document.querySelector("[data-transcript-queue-list]");
    const empty = document.querySelector("[data-transcript-queue-empty]");
    const count = Array.from(document.querySelectorAll("[data-transcript-card][data-transcript-group='queue']")).filter(
      function (card) {
        return card instanceof HTMLElement && !card.hidden;
      }
    ).length;

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
    const count = Array.from(
      document.querySelectorAll("[data-transcript-card][data-transcript-group='completed']")
    ).filter(function (card) {
      return card instanceof HTMLElement && !card.hidden;
    }).length;

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

  function syncTranscriptCategoryCards(nextCountsByCategory) {
    const countsByCategory = nextCountsByCategory || computeCategoryCountsFromDom();

    document.querySelectorAll("[data-transcript-category-card]").forEach(function (card) {
      if (!(card instanceof HTMLElement)) {
        return;
      }

      const key = card.getAttribute("data-transcript-category-card") || "";
      const counts = countsByCategory[key] || { total: 0, completed: 0, queue: 0 };

      const totalNode = card.querySelector("[data-transcript-category-total]");
      if (totalNode instanceof HTMLElement) {
        totalNode.textContent = `${counts.total}`;
      }

      const completedNode = card.querySelector("[data-transcript-category-completed]");
      if (completedNode instanceof HTMLElement) {
        completedNode.textContent = `${counts.completed}`;
      }

      const queueNode = card.querySelector("[data-transcript-category-queue]");
      if (queueNode instanceof HTMLElement) {
        queueNode.textContent = `${counts.queue}`;
      }
    });
  }

  function syncTranscriptCategoryFilterCards() {
    const activeFilter = normalizeTranscriptCategoryFilter(activeTranscriptCategoryFilter);

    document.querySelectorAll("[data-transcript-category-filter]").forEach(function (card) {
      if (!(card instanceof HTMLElement)) {
        return;
      }

      const key = card.getAttribute("data-transcript-category-filter") || "";
      const isActive = Boolean(activeFilter) && key === activeFilter;
      card.classList.toggle("is-filter-active", isActive);
      card.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function applyTranscriptCategoryFilter() {
    const activeFilter = normalizeTranscriptCategoryFilter(activeTranscriptCategoryFilter);

    document.querySelectorAll("[data-transcript-card]").forEach(function (card) {
      if (!(card instanceof HTMLElement)) {
        return;
      }

      const category = card.getAttribute("data-transcript-category") || "work";
      const shouldHide = Boolean(activeFilter) && category !== activeFilter;
      card.hidden = shouldHide;
      card.setAttribute("aria-hidden", shouldHide ? "true" : "false");
    });

    syncTranscriptCategoryFilterCards();
    syncQueueEmptyState();
    syncCompletedEmptyState();
  }

  function setTranscriptCategoryFilter(nextFilter) {
    const normalizedFilter = normalizeTranscriptCategoryFilter(nextFilter);
    if (!normalizedFilter) {
      return;
    }

    activeTranscriptCategoryFilter =
      activeTranscriptCategoryFilter === normalizedFilter ? "" : normalizedFilter;
    applyTranscriptCategoryFilter();
  }

  function syncTranscriptStats(nextCounts) {
    const counts = nextCounts || computeCountsFromDom();

    updateCountNodes("[data-transcript-completed-count]", counts.completed, "条");
    updateCountNodes("[data-transcript-queue-count]", counts.queue, "条");
    updateCountNodes("[data-transcript-linked-count]", counts.linked, "只");

    const totalLabel = document.querySelector("[data-transcript-total-label]");
    if (totalLabel instanceof HTMLElement) {
      totalLabel.textContent = `当前已存 ${counts.total} 条转录任务`;
    }

    syncQueueEmptyState();
    syncCompletedEmptyState();
    syncSyncButton(counts);
    syncTranscriptCategoryCards();
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
    const detachedContentTemplate = document.getElementById(`transcript-content-${transcriptId}`);
    if (detachedContentTemplate instanceof HTMLElement && !card.contains(detachedContentTemplate)) {
      detachedContentTemplate.remove();
    }

    window.setTimeout(function () {
      card.remove();
      syncTranscriptStats(counts);
      if (message) {
        showFlash("success", message);
      }
    }, REMOVE_TRANSITION_MS);
  }

  function setupCategoryToggles() {
    const pendingUpdates = new Set();

    document.addEventListener(
      "click",
      function (event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }

        const button = target.closest("[data-transcript-category-set]");
        if (!(button instanceof HTMLButtonElement)) {
          return;
        }

        event.preventDefault();
        event.stopPropagation();

        const transcriptId = button.getAttribute("data-transcript-id") || "";
        const desiredCategory = button.getAttribute("data-transcript-category-set") || "";
        const switcher = button.closest("[data-transcript-category-switcher]");
        const actionUrl = switcher instanceof HTMLElement ? switcher.getAttribute("data-transcript-category-url") || "" : "";
        const activeChip = document.querySelector(
          `[data-transcript-category-chip][data-transcript-id='${transcriptId}']`
        );
        const currentCategory =
          activeChip instanceof HTMLElement ? activeChip.getAttribute("data-transcript-category") || "work" : "work";
        const scopeSymbol = getTranscriptScopeSymbol();

        if (!transcriptId || !actionUrl || !desiredCategory || pendingUpdates.has(transcriptId)) {
          return;
        }

        if (desiredCategory === currentCategory) {
          return;
        }

        pendingUpdates.add(transcriptId);
        setTranscriptCategoryBusy(transcriptId, true);

        fetch(actionUrl, {
          method: "POST",
          body: new URLSearchParams(
            Object.assign(
              {
                category: desiredCategory,
              },
              scopeSymbol
                ? {
                    scope_symbol: scopeSymbol,
                  }
                : {}
            )
          ),
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            Accept: "application/json",
          },
          cache: "no-store",
        })
          .then(function (response) {
            return response
              .json()
              .catch(function () {
                return null;
              })
              .then(function (payload) {
                if (!response.ok || !payload || payload.ok !== true) {
                  throw new Error((payload && payload.message) || "切换分类失败，请稍后再试。");
                }
                return payload;
              });
          })
          .then(function (payload) {
            const appliedCategory =
              payload &&
              payload.category &&
              typeof payload.category.key === "string" &&
              payload.category.key
                ? payload.category.key
                : desiredCategory;
            applyTranscriptCategory(transcriptId, appliedCategory);
          })
          .catch(function (error) {
            showFlash("error", error instanceof Error ? error.message : "切换分类失败，请稍后再试。");
          })
          .finally(function () {
            pendingUpdates.delete(transcriptId);
            setTranscriptCategoryBusy(transcriptId, false);
          });
      },
      true
    );

    document.addEventListener(
      "keydown",
      function (event) {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
          return;
        }

        if (!target.closest("[data-transcript-category-set]")) {
          return;
        }

        if (event.key === "Enter" || event.key === " ") {
          event.stopPropagation();
        }
      },
      true
    );
  }

  function setupCategoryFilters() {
    document.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const card = target.closest("[data-transcript-category-filter]");
      if (!(card instanceof HTMLElement)) {
        return;
      }

      const nextFilter = card.getAttribute("data-transcript-category-filter") || "";
      if (!nextFilter) {
        return;
      }

      event.preventDefault();
      setTranscriptCategoryFilter(nextFilter);
    });

    document.addEventListener("keydown", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const card = target.closest("[data-transcript-category-filter]");
      if (!(card instanceof HTMLElement)) {
        return;
      }

      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }

      const nextFilter = card.getAttribute("data-transcript-category-filter") || "";
      if (!nextFilter) {
        return;
      }

      event.preventDefault();
      setTranscriptCategoryFilter(nextFilter);
    });

    syncTranscriptCategoryFilterCards();
  }

  function hydrateTranscriptContentHosts(root) {
    if (!root || typeof root.querySelectorAll !== "function") {
      return;
    }

    root.querySelectorAll("[data-transcript-content-host]").forEach(function (host) {
      if (!(host instanceof HTMLElement) || host.dataset.transcriptContentReady === "true") {
        return;
      }

      const transcriptId = host.getAttribute("data-transcript-content-host") || "";
      if (!transcriptId) {
        return;
      }

      const template = document.getElementById(`transcript-content-${transcriptId}`);
      if (!(template instanceof HTMLTemplateElement)) {
        return;
      }

      host.innerHTML = template.innerHTML;
      host.dataset.transcriptContentReady = "true";
    });
  }

  function setupTranscriptContentHydration() {
    document.querySelectorAll("details[data-transcript-card]").forEach(function (card) {
      if (!(card instanceof HTMLDetailsElement)) {
        return;
      }

      if (card.open) {
        hydrateTranscriptContentHosts(card);
      }

      card.addEventListener("toggle", function () {
        if (card.open) {
          hydrateTranscriptContentHosts(card);
        }
      });
    });

    const readerContent = document.querySelector("[data-reader-content]");
    if (!(readerContent instanceof HTMLElement) || typeof MutationObserver === "undefined") {
      return;
    }

    const observer = new MutationObserver(function () {
      hydrateTranscriptContentHosts(readerContent);
    });
    observer.observe(readerContent, {
      childList: true,
      subtree: true,
    });
    hydrateTranscriptContentHosts(readerContent);
  }

  function setupAutoSyncPolling() {
    const syncForm = document.querySelector("form[data-transcript-sync-form]");
    if (!(syncForm instanceof HTMLFormElement) || !syncForm.action) {
      return;
    }

    const rawPollSeconds = Number.parseInt(syncForm.getAttribute("data-transcript-poll-seconds") || "12", 10);
    const pollIntervalMs = Math.max(6, Number.isFinite(rawPollSeconds) ? rawPollSeconds : 12) * 1000;
    let timerId = 0;
    let activeController = null;

    function isOnline() {
      return typeof navigator === "undefined" || typeof navigator.onLine !== "boolean" || navigator.onLine;
    }

    function hasActiveTranscripts() {
      return Array.from(document.querySelectorAll("[data-transcript-card]")).some(function (card) {
        if (!(card instanceof HTMLElement)) {
          return false;
        }

        const status = card.getAttribute("data-transcript-status") || "";
        return status === "queued" || status === "processing";
      });
    }

    function clearTimer() {
      if (!timerId) {
        return;
      }

      window.clearTimeout(timerId);
      timerId = 0;
    }

    function scheduleNextPoll() {
      if (timerId || document.hidden || !isOnline() || !hasActiveTranscripts()) {
        return;
      }

      timerId = window.setTimeout(function () {
        timerId = 0;
        poll();
      }, pollIntervalMs);
    }

    function stopPolling() {
      clearTimer();
      if (activeController instanceof AbortController) {
        activeController.abort();
        activeController = null;
      }
    }

    function handlePayload(payload) {
      if (!payload || payload.ok !== true) {
        scheduleNextPoll();
        return;
      }

      if (payload.should_reload) {
        window.location.reload();
        return;
      }

      if (payload.counts) {
        syncTranscriptStats(payload.counts);
      }

      if (!payload.counts || !payload.counts.active) {
        stopPolling();
        return;
      }

      scheduleNextPoll();
    }

    function poll() {
      if (activeController || document.hidden || !isOnline()) {
        scheduleNextPoll();
        return;
      }

      if (!hasActiveTranscripts()) {
        stopPolling();
        return;
      }

      const controller = new AbortController();
      const timeoutId = window.setTimeout(function () {
        controller.abort();
      }, Math.max(8000, pollIntervalMs));

      activeController = controller;
      fetch(syncForm.action, {
        method: "POST",
        body: new FormData(syncForm),
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
        cache: "no-store",
        signal: controller.signal,
      })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              return null;
            })
            .then(function (payload) {
              if (!response.ok) {
                return null;
              }

              return payload;
            });
        })
        .then(handlePayload)
        .catch(function (error) {
          if (error instanceof Error && error.name === "AbortError") {
            return;
          }

          scheduleNextPoll();
        })
        .finally(function () {
          window.clearTimeout(timeoutId);
          if (activeController === controller) {
            activeController = null;
          }
        });
    }

    poll();

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        stopPolling();
        return;
      }

      poll();
    });

    window.addEventListener("online", function () {
      poll();
    });

    window.addEventListener("pageshow", function () {
      poll();
    });

    window.addEventListener("beforeunload", function () {
      stopPolling();
    });
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
      setupTranscriptUpload(form);
      bindStockLinkMode(form);
      bindTranscriptValidation(form);
      bindToggle(form, "diarization_enabled", "speaker-fields");
      bindToggle(form, "meeting_assistance_enabled", "meeting-assistance-fields");
      bindToggle(form, "summarization_enabled", "summarization-fields");
      bindToggle(form, "custom_prompt_enabled", "prompt-fields");
    }

    setupComposerModal();
    setupCategoryFilters();
    setupCategoryToggles();
    setupDeleteForms();
    setupTranscriptContentHydration();
    syncTranscriptStats();
    setupAutoSyncPolling();
  });
})();
