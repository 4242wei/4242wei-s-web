(function () {
  const overlay = document.querySelector("[data-clipboard-overlay]");
  const launcher = document.querySelector("[data-clipboard-open]");

  if (!(overlay instanceof HTMLElement) || !(launcher instanceof HTMLButtonElement)) {
    return;
  }

  const list = overlay.querySelector("[data-clipboard-list]");
  const emptyState = overlay.querySelector("[data-clipboard-empty]");
  const status = overlay.querySelector("[data-clipboard-status]");
  const count = overlay.querySelector("[data-clipboard-count]");
  const createText = overlay.querySelector("[data-clipboard-create-text]");
  const createFiles = overlay.querySelector("[data-clipboard-create-files]");
  const createSummary = overlay.querySelector("[data-clipboard-create-summary]");
  const createSubmit = overlay.querySelector("[data-clipboard-create-submit]");
  const refreshButton = overlay.querySelector("[data-clipboard-refresh]");

  if (
    !(list instanceof HTMLElement) ||
    !(emptyState instanceof HTMLElement) ||
    !(status instanceof HTMLElement) ||
    !(count instanceof HTMLElement) ||
    !(createText instanceof HTMLTextAreaElement) ||
    !(createFiles instanceof HTMLInputElement) ||
    !(createSummary instanceof HTMLElement) ||
    !(createSubmit instanceof HTMLButtonElement) ||
    !(refreshButton instanceof HTMLButtonElement)
  ) {
    return;
  }

  const bootstrapUrl = overlay.getAttribute("data-clipboard-bootstrap-url") || "";
  const createUrl = overlay.getAttribute("data-clipboard-create-url") || "";
  const updateUrlTemplate = overlay.getAttribute("data-clipboard-update-url-template") || "";
  const deleteUrlTemplate = overlay.getAttribute("data-clipboard-delete-url-template") || "";
  let statusTimer = 0;
  let requestInFlight = false;

  function setBodyLock(isLocked) {
    document.body.style.overflow = isLocked ? "hidden" : "";
  }

  function openOverlay() {
    overlay.hidden = false;
    overlay.classList.add("is-open");
    launcher.setAttribute("aria-expanded", "true");
    setBodyLock(true);
    void loadBootstrap({ silent: true });
  }

  function closeOverlay() {
    overlay.classList.remove("is-open");
    overlay.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    setBodyLock(false);
  }

  function clearStatus(immediately) {
    window.clearTimeout(statusTimer);
    if (immediately) {
      status.hidden = true;
      status.textContent = "";
      status.className = "clipboard-status";
      return;
    }

    statusTimer = window.setTimeout(function () {
      status.hidden = true;
      status.textContent = "";
      status.className = "clipboard-status";
    }, 2400);
  }

  function showStatus(message, tone, persist) {
    window.clearTimeout(statusTimer);
    status.hidden = false;
    status.textContent = message;
    status.className = "clipboard-status";
    if (tone) {
      status.classList.add(`is-${tone}`);
    }
    if (!persist) {
      clearStatus(false);
    }
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fileSummaryText(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) {
      return "还没选图片。";
    }

    return files
      .map(function (file) {
        return file.name;
      })
      .join(" / ");
  }

  function updateFileSummary(input, summary) {
    if (!(input instanceof HTMLInputElement) || !(summary instanceof HTMLElement)) {
      return;
    }
    summary.textContent = fileSummaryText(input.files);
  }

  function buildItemUrl(template, itemId) {
    return template.replace("__ITEM_ID__", encodeURIComponent(itemId));
  }

  async function requestJson(url, options) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
      ...options,
    });

    const contentType = response.headers.get("content-type") || "";
    if (response.redirected && !contentType.includes("application/json")) {
      window.location.href = response.url;
      throw new Error("登录状态已过期，请重新进入。");
    }

    let payload = null;
    if (contentType.includes("application/json")) {
      payload = await response.json();
    } else {
      const fallbackText = (await response.text()).trim();
      throw new Error(fallbackText || "请求失败，请稍后再试。");
    }

    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message || "请求失败，请稍后再试。");
    }

    return payload;
  }

  function renderItem(item) {
    const images = Array.isArray(item.images) ? item.images : [];
    const gallery = images.length
      ? images
          .map(function (image) {
            return `
              <figure class="clipboard-image-card">
                <img src="${escapeHtml(image.url)}" alt="${escapeHtml(image.original_name)}" loading="lazy">
                <figcaption class="clipboard-image-meta">
                  <div class="clipboard-image-copy">
                    <span class="clipboard-image-name">${escapeHtml(image.original_name)}</span>
                    <span class="clipboard-image-time">${escapeHtml(image.display_uploaded_at || "")}</span>
                  </div>
                  <button
                    class="clipboard-image-remove"
                    type="button"
                    data-clipboard-remove-image
                    data-clipboard-item-id="${escapeHtml(item.id)}"
                    data-clipboard-image-id="${escapeHtml(image.id)}"
                  >
                    删图
                  </button>
                </figcaption>
              </figure>
            `;
          })
          .join("")
      : '<div class="clipboard-entry-placeholder">这条还没有图片，可以后面再补。</div>';

    return `
      <article class="clipboard-entry" data-clipboard-item="${escapeHtml(item.id)}">
        <div class="clipboard-entry-head">
          <div>
            <p class="eyebrow">共享条目</p>
            <h4>${escapeHtml(item.display_updated_at || "刚刚更新")}</h4>
          </div>
          <div class="clipboard-entry-head-actions">
            <span class="meta-chip">${escapeHtml(String(item.image_count || 0))} 张图</span>
            <button class="danger-button danger-button-compact" type="button" data-clipboard-delete="${escapeHtml(item.id)}">删除</button>
          </div>
        </div>

        <textarea
          class="clipboard-entry-textarea"
          rows="5"
          maxlength="40000"
          data-clipboard-edit-text
          data-clipboard-paste-target
        >${escapeHtml(item.text || "")}</textarea>

        <div class="clipboard-entry-gallery">${gallery}</div>

        <div class="clipboard-entry-footer">
          <label class="clipboard-inline-upload">
            <span>补图片</span>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif,image/bmp"
              multiple
              data-clipboard-edit-files
            >
          </label>
          <div class="clipboard-file-summary" data-clipboard-file-summary>可追加图片，也可以在文字框里直接粘贴截图。</div>
          <button class="button button-secondary button-compact" type="button" data-clipboard-save="${escapeHtml(item.id)}">保存</button>
        </div>
      </article>
    `;
  }

  function applyPayload(payload) {
    const items = Array.isArray(payload?.items) ? payload.items : [];
    list.innerHTML = items.map(renderItem).join("");
    emptyState.hidden = items.length > 0;
    count.textContent = String(payload?.item_count || items.length || 0);
    createText.maxLength = Number(payload?.limits?.max_text_chars || 40000);
  }

  async function loadBootstrap(options) {
    if (!bootstrapUrl || requestInFlight) {
      return;
    }

    requestInFlight = true;
    if (!options?.silent) {
      showStatus("正在同步剪贴板...", "muted", true);
    }

    try {
      const payload = await requestJson(bootstrapUrl, { method: "GET" });
      applyPayload(payload);
      if (!options?.silent) {
        showStatus("剪贴板已刷新。", "success", false);
      } else {
        clearStatus(true);
      }
    } catch (error) {
      showStatus(error instanceof Error ? error.message : "剪贴板加载失败。", "error", true);
    } finally {
      requestInFlight = false;
    }
  }

  function buildCardFormData(card, options) {
    const formData = new FormData();
    const textArea = card.querySelector("[data-clipboard-edit-text]");
    const fileInput = card.querySelector("[data-clipboard-edit-files]");
    if (textArea instanceof HTMLTextAreaElement) {
      formData.append("text", textArea.value);
    }
    if (fileInput instanceof HTMLInputElement) {
      Array.from(fileInput.files || []).forEach(function (file) {
        formData.append("images", file);
      });
    }
    if (options?.removeImageId) {
      formData.append("remove_image_ids", options.removeImageId);
    }
    return formData;
  }

  async function submitCreate() {
    if (!createUrl || requestInFlight) {
      return;
    }

    const formData = new FormData();
    formData.append("text", createText.value);
    Array.from(createFiles.files || []).forEach(function (file) {
      formData.append("images", file);
    });

    requestInFlight = true;
    showStatus("正在保存到剪贴板...", "muted", true);
    try {
      const payload = await requestJson(createUrl, {
        method: "POST",
        body: formData,
      });
      applyPayload(payload);
      createText.value = "";
      createFiles.value = "";
      updateFileSummary(createFiles, createSummary);
      showStatus("已经放进剪贴板。", "success", false);
    } catch (error) {
      showStatus(error instanceof Error ? error.message : "剪贴板保存失败。", "error", true);
    } finally {
      requestInFlight = false;
    }
  }

  async function submitUpdate(itemId, options) {
    if (!updateUrlTemplate || requestInFlight) {
      return;
    }

    const card = overlay.querySelector(`[data-clipboard-item="${itemId}"]`);
    if (!(card instanceof HTMLElement)) {
      return;
    }

    requestInFlight = true;
    showStatus(options?.removeImageId ? "正在更新图片..." : "正在保存修改...", "muted", true);
    try {
      const payload = await requestJson(buildItemUrl(updateUrlTemplate, itemId), {
        method: "POST",
        body: buildCardFormData(card, options),
      });
      applyPayload(payload);
      showStatus(options?.removeImageId ? "图片已更新。" : "剪贴板已保存。", "success", false);
    } catch (error) {
      showStatus(error instanceof Error ? error.message : "剪贴板保存失败。", "error", true);
    } finally {
      requestInFlight = false;
    }
  }

  async function submitDelete(itemId) {
    if (!deleteUrlTemplate || requestInFlight) {
      return;
    }

    if (!window.confirm("把这条剪贴板内容删掉吗？")) {
      return;
    }

    requestInFlight = true;
    showStatus("正在删除...", "muted", true);
    try {
      const payload = await requestJson(buildItemUrl(deleteUrlTemplate, itemId), {
        method: "POST",
      });
      applyPayload(payload);
      showStatus("这条内容已经删掉。", "success", false);
    } catch (error) {
      showStatus(error instanceof Error ? error.message : "删除失败。", "error", true);
    } finally {
      requestInFlight = false;
    }
  }

  function extractClipboardImages(event) {
    const clipboardData = event.clipboardData;
    if (!clipboardData || !clipboardData.items) {
      return [];
    }

    const files = [];
    for (const item of clipboardData.items) {
      if (item.kind !== "file" || !item.type.startsWith("image/")) {
        continue;
      }
      const file = item.getAsFile();
      if (file) {
        files.push(file);
      }
    }
    return files;
  }

  function mergeFilesIntoInput(input, files) {
    if (!(input instanceof HTMLInputElement) || !files.length || typeof DataTransfer === "undefined") {
      return false;
    }

    const transfer = new DataTransfer();
    Array.from(input.files || []).forEach(function (file) {
      transfer.items.add(file);
    });
    files.forEach(function (file) {
      transfer.items.add(file);
    });
    input.files = transfer.files;
    return true;
  }

  launcher.addEventListener("click", function () {
    openOverlay();
  });

  createSubmit.addEventListener("click", function () {
    void submitCreate();
  });

  refreshButton.addEventListener("click", function () {
    void loadBootstrap();
  });

  createFiles.addEventListener("change", function () {
    updateFileSummary(createFiles, createSummary);
  });

  overlay.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target.closest("[data-clipboard-close]")) {
      closeOverlay();
      return;
    }

    const saveButton = target.closest("[data-clipboard-save]");
    if (saveButton instanceof HTMLElement) {
      const itemId = saveButton.getAttribute("data-clipboard-save") || "";
      if (itemId) {
        void submitUpdate(itemId, {});
      }
      return;
    }

    const deleteButton = target.closest("[data-clipboard-delete]");
    if (deleteButton instanceof HTMLElement) {
      const itemId = deleteButton.getAttribute("data-clipboard-delete") || "";
      if (itemId) {
        void submitDelete(itemId);
      }
      return;
    }

    const removeImageButton = target.closest("[data-clipboard-remove-image]");
    if (removeImageButton instanceof HTMLElement) {
      const itemId = removeImageButton.getAttribute("data-clipboard-item-id") || "";
      const imageId = removeImageButton.getAttribute("data-clipboard-image-id") || "";
      if (itemId && imageId) {
        void submitUpdate(itemId, { removeImageId: imageId });
      }
      return;
    }

    if (target === overlay) {
      closeOverlay();
    }
  });

  overlay.addEventListener("change", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target instanceof HTMLInputElement && target.matches("[data-clipboard-edit-files]")) {
      const card = target.closest("[data-clipboard-item]");
      const summary = card?.querySelector("[data-clipboard-file-summary]");
      if (summary instanceof HTMLElement) {
        updateFileSummary(target, summary);
      }
    }
  });

  overlay.addEventListener("paste", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement) || !target.matches("[data-clipboard-paste-target]")) {
      return;
    }

    const files = extractClipboardImages(event);
    if (!files.length) {
      return;
    }

    const card = target.closest("[data-clipboard-item]");
    if (card instanceof HTMLElement) {
      const fileInput = card.querySelector("[data-clipboard-edit-files]");
      const summary = card.querySelector("[data-clipboard-file-summary]");
      if (mergeFilesIntoInput(fileInput, files) && summary instanceof HTMLElement) {
        updateFileSummary(fileInput, summary);
        showStatus(`已加入 ${files.length} 张截图，记得点保存。`, "muted", false);
      }
      return;
    }

    if (mergeFilesIntoInput(createFiles, files)) {
      updateFileSummary(createFiles, createSummary);
      showStatus(`已加入 ${files.length} 张截图。`, "muted", false);
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !overlay.hidden) {
      closeOverlay();
    }
  });

  window.addEventListener("beforeunload", function () {
    setBodyLock(false);
  });
})();
