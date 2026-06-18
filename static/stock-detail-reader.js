(function () {
  const overlay = document.querySelector("[data-reader-overlay]");
  const content = document.querySelector("[data-reader-content]");
  const scrollShell = overlay ? overlay.querySelector(".reader-dialog-content") : null;
  const CLOSE_TRANSITION_MS = 220;
  const OPEN_EVENT_DEDUP_MS = 1200;
  const PROGRESS_SAVE_DEBOUNCE_MS = 900;
  const TOOLBAR_OFFSET = 12;
  const VIEWPORT_PADDING = 12;
  let closeTimer = null;
  let selectionFrame = 0;
  let progressTimer = 0;
  let lastOpenFingerprint = "";
  let lastOpenTimestamp = 0;
  let lastPointer = { x: 0, y: 0 };
  let activeReaderContext = null;
  const readerStateCache = new Map();
  const ANNOTATION_KIND_ORDER = { highlight: 0, underline: 1, note: 2 };
  const ANNOTATION_KIND_LABELS = {
    highlight: "\u9ad8\u4eae",
    underline: "\u753b\u7ebf",
    note: "\u9644\u6ce8",
  };

  if (!overlay || !content) {
    return;
  }

  const selectionToolbar = createSelectionToolbar();
  const noteComposer = createNoteComposer();
  const annotationMenu = createAnnotationMenu();
  const toast = createToast();
  overlay.append(selectionToolbar, noteComposer, annotationMenu, toast);

  function createIcon(kind) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("fill", "currentColor");
    const dMap = {
      highlight: "M4.7 16.3 13.9 7l3.1 3.1-9.2 9.2H4.7v-3Zm10.2-10.2 1.2-1.2a1.8 1.8 0 0 1 2.5 0l.5.5a1.8 1.8 0 0 1 0 2.5L17.9 9l-3-3Zm-11 14.4h16v1.8H3.9v-1.8Z",
      underline: "M7.1 4.3v6.8a4.9 4.9 0 1 0 9.8 0V4.3h-2.2v6.7a2.7 2.7 0 1 1-5.4 0V4.3H7.1Zm-1.6 15h13v1.9h-13v-1.9Z",
      note: "M5.8 4.5h12.4A2.6 2.6 0 0 1 20.8 7v7a2.6 2.6 0 0 1-2.6 2.6H12l-3.7 3.1c-.8.7-2 .1-2-.9v-2.2H5.8A2.6 2.6 0 0 1 3.2 14V7a2.6 2.6 0 0 1 2.6-2.5Zm2.3 4.2h7.8V7.1H8.1v1.6Zm0 3.4h5.2v-1.6H8.1v1.6Z",
      trash: "M9.3 3.9h5.4l.7 1.2h4v1.8H4.6V5.1h4l.7-1.2Zm-2 5.1h1.9v8.4H7.3V9Zm3.8 0H13v8.4h-1.9V9Zm3.8 0H17v8.4h-1.9V9Z",
      check: "M9.3 16.7 5 12.4l1.5-1.5 2.8 2.8 8.2-8.2 1.5 1.5-9.7 9.7Z",
      close: "m6.2 6.2 11.6 11.6-1.4 1.4L4.8 7.6l1.4-1.4Zm11.6 0 1.4 1.4L7.6 19.2l-1.4-1.4 11.6-11.6Z",
      resume: "M12 4.4a7.6 7.6 0 1 1-5.4 2.2H4.2V4.8h4v4H6.4a5.7 5.7 0 1 0 4.2-1.9V4.4Zm-1 3.3h2v4.1l3 1.8-1 1.7-4-2.4V7.7Z",
    };
    path.setAttribute("d", dMap[kind] || dMap.note);
    svg.appendChild(path);
    return svg;
  }

  function createSelectionToolbar() {
    const node = document.createElement("div");
    node.className = "reader-annotation-toolbar";
    node.hidden = true;
    [
      ["highlight", "\u9ad8\u4eae"],
      ["underline", "\u753b\u7ebf"],
      ["note", "\u6dfb\u52a0\u9644\u6ce8"],
    ].forEach(function (item) {
      const button = document.createElement("button");
      button.className = "reader-annotation-action";
      button.type = "button";
      button.dataset.readerAction = item[0];
      button.title = item[1];
      button.setAttribute("aria-label", item[1]);
      button.appendChild(createIcon(item[0]));
      node.appendChild(button);
    });
    return node;
  }

  function createNoteComposer() {
    const node = document.createElement("div");
    node.className = "reader-note-composer";
    node.hidden = true;
    const textarea = document.createElement("textarea");
    textarea.className = "reader-note-textarea";
    textarea.rows = 3;
    textarea.maxLength = 280;
    textarea.placeholder = "\u5199\u4e00\u53e5\u9644\u6ce8";
    textarea.setAttribute("data-reader-note-input", "");
    const actions = document.createElement("div");
    actions.className = "reader-note-actions";
    [
      ["cancel", "\u53d6\u6d88", "close", ""],
      ["submit", "\u4fdd\u5b58\u9644\u6ce8", "check", " is-primary"],
    ].forEach(function (item) {
      const button = document.createElement("button");
      button.className = `reader-note-action${item[3]}`;
      button.type = "button";
      button.dataset.readerNoteAction = item[0];
      button.title = item[1];
      button.setAttribute("aria-label", item[1]);
      button.appendChild(createIcon(item[2]));
      actions.appendChild(button);
    });
    node.append(textarea, actions);
    return node;
  }

  function createAnnotationMenu() {
    const node = document.createElement("div");
    node.className = "reader-annotation-menu";
    node.hidden = true;
    const body = document.createElement("div");
    body.className = "reader-annotation-menu-body";
    body.setAttribute("data-reader-annotation-menu-body", "");
    node.append(body);
    return node;
  }

  function createToast() {
    const node = document.createElement("div");
    node.className = "reader-toast";
    node.hidden = true;
    return node;
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function showToast(message, tone) {
    toast.textContent = String(message || "").trim();
    if (!toast.textContent) {
      toast.hidden = true;
      return;
    }
    toast.dataset.tone = tone || "neutral";
    toast.hidden = false;
    toast.classList.add("is-visible");
    window.clearTimeout(Number(toast.dataset.timeoutId || 0));
    toast.dataset.timeoutId = String(window.setTimeout(function () {
      toast.classList.remove("is-visible");
      toast.hidden = true;
    }, 2200));
  }

  function lockBody() {
    document.body.style.overflow = "hidden";
  }

  function unlockBody() {
    document.body.style.overflow = "";
  }

  function scrollReaderToTop() {
    if (scrollShell instanceof HTMLElement) {
      scrollShell.scrollTop = 0;
    }
  }

  function showOverlay() {
    if (closeTimer) {
      window.clearTimeout(closeTimer);
      closeTimer = null;
    }
    overlay.hidden = false;
    overlay.classList.remove("is-closing");
    lockBody();
    window.requestAnimationFrame(function () {
      overlay.classList.add("is-open");
    });
  }

  function focusCloseButton() {
    const closeButton = content.querySelector("[data-reader-close]");
    if (closeButton instanceof HTMLElement) {
      window.requestAnimationFrame(function () {
        closeButton.focus({ preventScroll: true });
      });
    }
  }

  function normalizeReaderActivity(raw, fallback) {
    const source = raw && typeof raw === "object" ? raw : {};
    const base = fallback && typeof fallback === "object" ? fallback : {};
    const ratio = Number.isFinite(Number(source.last_scroll_ratio))
      ? Number(source.last_scroll_ratio)
      : Number(base.last_scroll_ratio || 0);
    return {
      open_count: Math.max(0, Number.parseInt(source.open_count || base.open_count || 0, 10) || 0),
      last_opened_at: String(source.last_opened_at || base.last_opened_at || ""),
      last_read_at: String(source.last_read_at || base.last_read_at || ""),
      last_scroll_ratio: clamp(Number.isFinite(ratio) ? ratio : 0, 0, 1),
      progress_percent: Math.max(0, Number.parseInt(source.progress_percent || base.progress_percent || Math.round((ratio || 0) * 100), 10) || 0),
      display_last_opened_at: String(source.display_last_opened_at || base.display_last_opened_at || "\u8fd8\u6ca1\u6709\u9605\u8bfb\u8bb0\u5f55"),
      display_last_read_at: String(source.display_last_read_at || base.display_last_read_at || "\u8fd8\u6ca1\u6709\u9605\u8bfb\u8bb0\u5f55"),
      annotation_count: Math.max(0, Number.parseInt(source.annotation_count || base.annotation_count || 0, 10) || 0),
    };
  }

  function normalizeReaderAnnotation(raw) {
    if (!raw || typeof raw !== "object") {
      return null;
    }
    const startOffset = Number.parseInt(raw.start_offset, 10);
    const endOffset = Number.parseInt(raw.end_offset, 10);
    const kind = String(raw.kind || "").trim();
    if (!Number.isInteger(startOffset) || !Number.isInteger(endOffset) || endOffset <= startOffset || !kind) {
      return null;
    }
    return {
      id: String(raw.id || ""),
      kind: kind,
      start_offset: startOffset,
      end_offset: endOffset,
      quote_text: String(raw.quote_text || ""),
      note_text: String(raw.note_text || ""),
      kind_label: String(raw.kind_label || kind),
      display_created_at: String(raw.display_created_at || ""),
      is_pending: Boolean(raw.is_pending),
    };
  }

  function sortReaderAnnotations(annotations) {
    return annotations.map(normalizeReaderAnnotation).filter(Boolean).sort(function (left, right) {
      return left.start_offset - right.start_offset
        || left.end_offset - right.end_offset
        || (ANNOTATION_KIND_ORDER[left.kind] || 9) - (ANNOTATION_KIND_ORDER[right.kind] || 9)
        || String(left.id || "").localeCompare(String(right.id || ""));
    });
  }

  function normalizeReaderState(raw, fallback) {
    const source = raw && typeof raw === "object" ? raw : {};
    const base = fallback && typeof fallback === "object" ? fallback : {};
    const annotations = Array.isArray(source.annotations) ? source.annotations : Array.isArray(base.annotations) ? base.annotations : [];
    const normalizedAnnotations = sortReaderAnnotations(annotations);
    const activity = normalizeReaderActivity(source.activity, base.activity);
    activity.annotation_count = normalizedAnnotations.length;
    activity.progress_percent = Math.round((activity.last_scroll_ratio || 0) * 100);
    return {
      kind: String(source.kind || base.kind || ""),
      item_id: String(source.item_id || base.item_id || ""),
      save_url: String(source.save_url || base.save_url || ""),
      content_signature: String(source.content_signature || base.content_signature || ""),
      annotations: normalizedAnnotations,
      activity: activity,
    };
  }

  function cloneState(state) {
    return normalizeReaderState(JSON.parse(JSON.stringify(state || {})));
  }

  function buildAnnotationFingerprint(annotations) {
    return sortReaderAnnotations(annotations).map(function (annotation) {
      return [
        annotation.id,
        annotation.kind,
        annotation.start_offset,
        annotation.end_offset,
        annotation.note_text,
        annotation.is_pending ? "1" : "0",
      ].join("::");
    }).join("||");
  }

  function buildOptimisticAnnotation(selection, kind, noteText) {
    const now = new Date();
    return normalizeReaderAnnotation({
      id: `temp-${now.getTime().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      kind: kind,
      start_offset: selection.start_offset,
      end_offset: selection.end_offset,
      quote_text: selection.quote_text,
      note_text: String(noteText || ""),
      kind_label: ANNOTATION_KIND_LABELS[kind] || kind,
      display_created_at: "\u6b63\u5728\u4fdd\u5b58",
      is_pending: true,
    });
  }

  function applyPendingMutationToState(state, mutation) {
    const nextState = cloneState(state);
    if (mutation.type === "add_annotation" && mutation.annotation) {
      nextState.annotations = sortReaderAnnotations(nextState.annotations.concat([mutation.annotation]));
    } else if (mutation.type === "delete_annotation" && mutation.annotation_id) {
      nextState.annotations = nextState.annotations.filter(function (annotation) {
        return annotation.id !== mutation.annotation_id;
      });
    }
    nextState.activity.annotation_count = nextState.annotations.length;
    nextState.activity.progress_percent = Math.round((nextState.activity.last_scroll_ratio || 0) * 100);
    return nextState;
  }

  function rebuildVisibleState(context) {
    if (!context) {
      return null;
    }
    let visibleState = cloneState(context.serverState || context.state);
    (context.pendingMutations || []).forEach(function (mutation) {
      visibleState = applyPendingMutationToState(visibleState, mutation);
    });
    context.state = cloneState(visibleState);
    readerStateCache.set(context.key, cloneState(context.state));
    if (activeReaderContext && activeReaderContext.key === context.key && activeReaderContext.prose.isConnected) {
      activeReaderContext.state = cloneState(context.state);
      renderReaderState(activeReaderContext);
    }
    return context.state;
  }

  function commitServerState(context, nextState) {
    const merged = normalizeReaderState(nextState, context.serverState || context.state);
    context.serverState = cloneState(merged);
    return rebuildVisibleState(context);
  }

  function buildReaderKey(state) {
    return `${String(state.kind || "")}:${String(state.item_id || "")}`;
  }

  function activatePanel(panelName) {
    if (!panelName) {
      return;
    }
    const trigger = document.querySelector(`[data-stock-detail-panel-target="${panelName}"]`);
    if (trigger instanceof HTMLButtonElement) {
      trigger.click();
    }
  }

  function openAncestorDetails(element) {
    let current = element instanceof HTMLElement ? element.parentElement : null;
    while (current) {
      if (current instanceof HTMLDetailsElement) {
        current.open = true;
      }
      current = current.parentElement;
    }
  }

  function buildTargetId(kind, itemId) {
    if (!kind || !itemId) {
      return "";
    }
    if (kind === "note") return `note-${itemId}`;
    if (kind === "file") return `file-${itemId}`;
    if (kind === "transcript") return `transcript-${itemId}`;
    if (kind === "earnings_call") return `earnings-call-${itemId}`;
    return "";
  }

  function cleanAutoOpenParams() {
    const url = new URL(window.location.href);
    let changed = false;
    ["open_kind", "open_id", "panel"].forEach(function (key) {
      if (url.searchParams.has(key)) {
        url.searchParams.delete(key);
        changed = true;
      }
    });
    if (changed) {
      window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
    }
  }

  function autoOpenFromLocation() {
    const params = new URLSearchParams(window.location.search);
    const panel = params.get("panel") || "";
    const kind = params.get("open_kind") || "";
    const itemId = params.get("open_id") || "";
    const targetId = buildTargetId(kind, itemId);
    const target = targetId ? document.getElementById(targetId) : null;
    if (!panel && !targetId) {
      return;
    }
    activatePanel(panel);
    const applyOpen = function () {
      const resolvedTarget = targetId ? document.getElementById(targetId) : target;
      if (!(resolvedTarget instanceof HTMLElement)) {
        cleanAutoOpenParams();
        return;
      }
      openAncestorDetails(resolvedTarget);
      resolvedTarget.scrollIntoView({ block: "center" });
      if (kind === "note") {
        const button = resolvedTarget.querySelector(`[data-reader-template="note-reader-${itemId}"]`);
        if (button instanceof HTMLElement) {
          openOverlay(document.getElementById(`note-reader-${itemId}`)?.innerHTML || "");
        }
      } else if (kind === "transcript" || kind === "earnings_call" || kind === "file") {
        const link = resolvedTarget.querySelector("[data-reader-url]");
        if (link instanceof HTMLElement) {
          const remoteUrl = link instanceof HTMLAnchorElement
            ? link.href
            : String(link.getAttribute("data-reader-url") || "").trim();
          if (!remoteUrl) {
            cleanAutoOpenParams();
            return;
          }
          openRemote(remoteUrl).catch(function () {
            content.innerHTML = '<div class="reader-loading">\u5f53\u524d\u65e0\u6cd5\u52a0\u8f7d\u8fd9\u4e2a\u9884\u89c8\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002</div>';
            focusCloseButton();
          });
        }
      }
      cleanAutoOpenParams();
    };
    window.requestAnimationFrame(applyOpen);
    window.setTimeout(applyOpen, 120);
  }

  function hideSelectionToolbar() {
    selectionToolbar.hidden = true;
    if (activeReaderContext) {
      activeReaderContext.pendingSelection = null;
    }
  }

  function hideNoteComposer() {
    noteComposer.hidden = true;
    noteComposer.removeAttribute("data-reader-context-key");
    const input = noteComposer.querySelector("[data-reader-note-input]");
    if (input instanceof HTMLTextAreaElement) {
      input.value = "";
    }
  }

  function hideAnnotationMenu() {
    annotationMenu.hidden = true;
    annotationMenu.removeAttribute("data-reader-annotation-id");
    annotationMenu.removeAttribute("data-reader-context-key");
    const body = annotationMenu.querySelector("[data-reader-annotation-menu-body]");
    if (body instanceof HTMLElement) {
      body.replaceChildren();
    }
  }

  function hideFloatingUi() {
    hideSelectionToolbar();
    hideNoteComposer();
    hideAnnotationMenu();
  }

  function openOverlay(html) {
    teardownActiveReader({ persist: true });
    content.innerHTML = html;
    showOverlay();
    scrollReaderToTop();
    initializeReaderExperience();
    focusCloseButton();
  }

  function closeOverlay() {
    if (overlay.hidden) {
      return;
    }
    teardownActiveReader({ persist: true });
    overlay.classList.remove("is-open");
    overlay.classList.add("is-closing");
    unlockBody();
    if (closeTimer) {
      window.clearTimeout(closeTimer);
    }
    closeTimer = window.setTimeout(function () {
      overlay.hidden = true;
      overlay.classList.remove("is-closing");
      content.innerHTML = "";
      closeTimer = null;
    }, CLOSE_TRANSITION_MS);
  }

  async function openRemote(url) {
    teardownActiveReader({ persist: true });
    content.innerHTML = '<div class="reader-loading">\u6b63\u5728\u52a0\u8f7d\u9884\u89c8...</div>';
    showOverlay();
    scrollReaderToTop();
    const response = await fetch(url, {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    if (!response.ok) {
      throw new Error("\u52a0\u8f7d\u9884\u89c8\u5931\u8d25");
    }
    content.innerHTML = await response.text();
    scrollReaderToTop();
    initializeReaderExperience();
    focusCloseButton();
  }

  function parseReaderBootstrap() {
    const bootstrapNode = content.querySelector("[data-reader-bootstrap]");
    const annotatable = content.querySelector("[data-reader-annotatable]");
    const prose = content.querySelector("[data-reader-prose]");
    if (!(bootstrapNode instanceof HTMLScriptElement) || !(annotatable instanceof HTMLElement) || !(prose instanceof HTMLElement)) {
      return null;
    }
    try {
      const parsed = JSON.parse(bootstrapNode.textContent || "{}");
      const state = normalizeReaderState(parsed);
      if (!state.save_url || !state.content_signature) {
        return null;
      }
      return {
        annotatable: annotatable,
        prose: prose,
        state: state,
      };
    } catch (error) {
      console.warn("reader bootstrap parse failed", error);
      return null;
    }
  }

  function initializeReaderExperience() {
    hideFloatingUi();
    const bootstrap = parseReaderBootstrap();
    if (!bootstrap) {
      activeReaderContext = null;
      return;
    }
    const key = buildReaderKey(bootstrap.state);
    const cachedState = readerStateCache.get(key);
    const initialState = cachedState ? normalizeReaderState(cachedState, bootstrap.state) : bootstrap.state;
    readerStateCache.set(key, cloneState(initialState));
    activeReaderContext = {
      key: key,
      annotatable: bootstrap.annotatable,
      prose: bootstrap.prose,
      baseHtml: bootstrap.prose.innerHTML,
      serverState: cloneState(initialState),
      state: cloneState(initialState),
      pendingMutations: [],
      mutationQueue: Promise.resolve(),
      pendingSelection: null,
    };
    renderReaderState(activeReaderContext);
    const fingerprint = `${key}:${initialState.content_signature}`;
    const now = Date.now();
    if (fingerprint !== lastOpenFingerprint || now - lastOpenTimestamp > OPEN_EVENT_DEDUP_MS) {
      lastOpenFingerprint = fingerprint;
      lastOpenTimestamp = now;
      sendReaderAction(activeReaderContext, {
        action: "open",
        content_signature: activeReaderContext.state.content_signature,
      }).catch(function (error) {
        console.warn("reader open event failed", error);
      });
    }
  }

  function teardownActiveReader(options) {
    const settings = options || {};
    window.clearTimeout(progressTimer);
    progressTimer = 0;
    if (activeReaderContext && settings.persist !== false) {
      persistActiveReaderProgress(true);
    }
    hideFloatingUi();
    activeReaderContext = null;
  }

  function createRangeFromOffsets(root, startOffset, endOffset) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        return node.textContent ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    let currentOffset = 0;
    let startNode = null;
    let endNode = null;
    let startInNode = 0;
    let endInNode = 0;
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const nextOffset = currentOffset + node.textContent.length;
      if (!startNode && startOffset <= nextOffset) {
        startNode = node;
        startInNode = Math.max(0, startOffset - currentOffset);
      }
      if (!endNode && endOffset <= nextOffset) {
        endNode = node;
        endInNode = Math.max(0, endOffset - currentOffset);
        break;
      }
      currentOffset = nextOffset;
    }
    if (!startNode || !endNode) {
      return null;
    }
    const range = document.createRange();
    range.setStart(startNode, startInNode);
    range.setEnd(endNode, endInNode);
    return range.collapsed ? null : range;
  }

  function createNoteBubble(annotation) {
    const button = document.createElement("button");
    button.className = "reader-note-bubble";
    button.type = "button";
    button.dataset.readerNoteBubble = "true";
    button.dataset.readerAnnotationId = annotation.id;
    button.title = annotation.note_text || annotation.kind_label || "\u9644\u6ce8";
    button.setAttribute("aria-label", "\u67e5\u770b\u9644\u6ce8");
    if (annotation.is_pending) {
      button.classList.add("is-pending");
    }
    button.appendChild(createIcon("note"));
    return button;
  }

  function buildAnnotationSegments(annotations) {
    const normalizedAnnotations = sortReaderAnnotations(annotations);
    const boundaries = Array.from(new Set(normalizedAnnotations.flatMap(function (annotation) {
      return [annotation.start_offset, annotation.end_offset];
    }))).sort(function (left, right) {
      return left - right;
    });
    const segments = [];
    for (let index = 0; index < boundaries.length - 1; index += 1) {
      const startOffset = boundaries[index];
      const endOffset = boundaries[index + 1];
      if (!(endOffset > startOffset)) {
        continue;
      }
      const activeAnnotations = normalizedAnnotations.filter(function (annotation) {
        return annotation.start_offset <= startOffset && annotation.end_offset >= endOffset;
      });
      if (!activeAnnotations.length) {
        continue;
      }
      segments.push({
        start_offset: startOffset,
        end_offset: endOffset,
        annotations: activeAnnotations,
        note_annotations_ending: activeAnnotations.filter(function (annotation) {
          return annotation.kind === "note" && annotation.end_offset === endOffset;
        }),
      });
    }
    return segments;
  }

  function renderReaderState(context) {
    if (!context || !(context.prose instanceof HTMLElement)) {
      return;
    }
    const annotationFingerprint = buildAnnotationFingerprint(context.state.annotations);
    const shouldRefreshBody = context.renderedAnnotationFingerprint !== annotationFingerprint;
    if (shouldRefreshBody) {
      context.prose.innerHTML = context.baseHtml;
      buildAnnotationSegments(context.state.annotations).slice().sort(function (left, right) {
        return right.start_offset - left.start_offset || right.end_offset - left.end_offset;
      }).forEach(function (segment) {
        const range = createRangeFromOffsets(context.prose, segment.start_offset, segment.end_offset);
        if (!range) {
          return;
        }
        const hasPending = segment.annotations.some(function (annotation) {
          return annotation.is_pending;
        });
        const wrapper = document.createElement("span");
        wrapper.className = "reader-annotation-mark";
        segment.annotations.forEach(function (annotation) {
          wrapper.classList.add(`is-${annotation.kind}`);
        });
        if (hasPending) {
          wrapper.classList.add("is-pending");
        }
        wrapper.dataset.readerAnnotationIds = segment.annotations.map(function (annotation) {
          return annotation.id;
        }).join(" ");
        wrapper.setAttribute("tabindex", "0");
        wrapper.setAttribute("role", "button");
        wrapper.setAttribute("aria-label", segment.annotations.map(function (annotation) {
          return annotation.kind_label || "\u6807\u6ce8";
        }).join(" / "));
        const fragment = range.extractContents();
        wrapper.appendChild(fragment);
        segment.note_annotations_ending.forEach(function (annotation) {
          wrapper.appendChild(createNoteBubble(annotation));
        });
        range.insertNode(wrapper);
      });
      context.renderedAnnotationFingerprint = annotationFingerprint;
      hideAnnotationMenu();
    }
    syncHistoryPanel(context);
  }

  function syncHistoryPanel(context) {
    const panel = content.querySelector("[data-reader-history-panel]");
    const meta = content.querySelector("[data-reader-history-meta]");
    const resume = content.querySelector("[data-reader-history-resume]");
    if (!(panel instanceof HTMLElement) || !(meta instanceof HTMLElement) || !(resume instanceof HTMLButtonElement)) {
      return;
    }
    meta.replaceChildren();
    [
      `\u6700\u8fd1\u9605\u8bfb ${context.state.activity.display_last_opened_at || "\u8fd8\u6ca1\u6709\u9605\u8bfb\u8bb0\u5f55"}`,
      `\u8fdb\u5ea6 ${context.state.activity.progress_percent || 0}%`,
      `\u6807\u6ce8 ${context.state.annotations.length}`,
    ].forEach(function (label) {
      const pill = document.createElement("span");
      pill.className = "reader-memory-pill";
      pill.textContent = label;
      meta.appendChild(pill);
    });
    resume.hidden = !(context.state.activity.last_scroll_ratio > 0.02);
    resume.dataset.readerContextKey = context.key;
    panel.hidden = false;
  }

  async function requestReaderAction(context, payload, options) {
    const settings = options || {};
    const response = await fetch(context.state.save_url, {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
      keepalive: Boolean(settings.keepalive),
    });
    const result = await response.json().catch(function () {
      return { ok: false, message: "\u4fdd\u5b58\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002" };
    });
    if (!response.ok || !result.ok) {
      throw new Error(String(result.message || "\u4fdd\u5b58\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002"));
    }
    return result;
  }

  async function sendReaderAction(context, payload, options) {
    const result = await requestReaderAction(context, payload, options);
    if (result.state) {
      commitServerState(context, Object.assign({}, result.state, {
        kind: context.state.kind,
        item_id: context.state.item_id,
        save_url: context.state.save_url,
        content_signature: context.state.content_signature,
      }));
    }
    return result;
  }
  function clearBrowserSelection() {
    const selection = window.getSelection();
    if (selection) {
      selection.removeAllRanges();
    }
  }

  function computeScrollRatio() {
    if (!(scrollShell instanceof HTMLElement)) {
      return 0;
    }
    const maxScrollTop = scrollShell.scrollHeight - scrollShell.clientHeight;
    return maxScrollTop > 0 ? clamp(scrollShell.scrollTop / maxScrollTop, 0, 1) : 0;
  }

  async function persistActiveReaderProgress(forceSave) {
    const context = activeReaderContext;
    if (!context) {
      return;
    }
    const ratio = computeScrollRatio();
    const previous = Number(context.state.activity.last_scroll_ratio || 0);
    if (!forceSave && Math.abs(ratio - previous) < 0.03) {
      return;
    }
    context.state.activity.last_scroll_ratio = ratio;
    context.state.activity.progress_percent = Math.round(ratio * 100);
    if (context.serverState && context.serverState.activity) {
      context.serverState.activity.last_scroll_ratio = ratio;
      context.serverState.activity.progress_percent = Math.round(ratio * 100);
    }
    readerStateCache.set(context.key, cloneState(context.state));
    syncHistoryPanel(context);
    try {
      await sendReaderAction(context, {
        action: "progress",
        scroll_ratio: ratio,
        content_signature: context.state.content_signature,
      }, {
        keepalive: Boolean(forceSave),
      });
    } catch (error) {
      console.warn("reader progress save failed", error);
    }
  }

  function restoreReaderProgress() {
    if (!(scrollShell instanceof HTMLElement) || !activeReaderContext) {
      return;
    }
    const ratio = clamp(Number(activeReaderContext.state.activity.last_scroll_ratio || 0), 0, 1);
    const maxScrollTop = scrollShell.scrollHeight - scrollShell.clientHeight;
    scrollShell.scrollTop = maxScrollTop > 0 ? Math.round(maxScrollTop * ratio) : 0;
  }

  function positionFloatingNode(node, rect) {
    node.hidden = false;
    const bounds = node.getBoundingClientRect();
    let left = Number.isFinite(lastPointer.x) ? lastPointer.x - bounds.width / 2 : rect.left + rect.width / 2 - bounds.width / 2;
    let top = rect.top - bounds.height - TOOLBAR_OFFSET;
    if (top < VIEWPORT_PADDING) {
      top = rect.bottom + TOOLBAR_OFFSET;
    }
    left = clamp(left, VIEWPORT_PADDING, window.innerWidth - bounds.width - VIEWPORT_PADDING);
    top = clamp(top, VIEWPORT_PADDING, window.innerHeight - bounds.height - VIEWPORT_PADDING);
    node.style.left = `${left}px`;
    node.style.top = `${top}px`;
  }

  function getSelectionOffsets(root, range) {
    try {
      const before = document.createRange();
      before.selectNodeContents(root);
      before.setEnd(range.startContainer, range.startOffset);
      const startOffset = before.toString().length;
      return {
        start_offset: startOffset,
        end_offset: startOffset + range.toString().length,
      };
    } catch (error) {
      return null;
    }
  }

  function trimSelectionEdges(text, startOffset, endOffset) {
    let start = startOffset;
    let end = endOffset;
    while (start < end && /\s/.test(text.charAt(start))) {
      start += 1;
    }
    while (end > start && /\s/.test(text.charAt(end - 1))) {
      end -= 1;
    }
    return { start: start, end: end };
  }

  function scheduleSelectionRefresh() {
    if (selectionFrame) {
      window.cancelAnimationFrame(selectionFrame);
    }
    selectionFrame = window.requestAnimationFrame(function () {
      selectionFrame = 0;
      if (!activeReaderContext || !noteComposer.hidden) {
        return;
      }
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
        hideSelectionToolbar();
        return;
      }
      const range = selection.getRangeAt(0);
      const commonNode = range.commonAncestorContainer;
      const commonElement = commonNode instanceof Element ? commonNode : commonNode.parentElement;
      if (!(commonElement instanceof HTMLElement) || !activeReaderContext.prose.contains(commonElement)) {
        hideSelectionToolbar();
        return;
      }
      const offsets = getSelectionOffsets(activeReaderContext.prose, range);
      if (!offsets) {
        hideSelectionToolbar();
        return;
      }
      const trimmed = trimSelectionEdges(activeReaderContext.prose.textContent || "", offsets.start_offset, offsets.end_offset);
      if (trimmed.end <= trimmed.start || trimmed.end - trimmed.start > 800) {
        hideSelectionToolbar();
        return;
      }
      const quoteText = (activeReaderContext.prose.textContent || "").slice(trimmed.start, trimmed.end).trim();
      const rect = range.getBoundingClientRect();
      if (!quoteText || (rect.width === 0 && rect.height === 0)) {
        hideSelectionToolbar();
        return;
      }
      activeReaderContext.pendingSelection = {
        start_offset: trimmed.start,
        end_offset: trimmed.end,
        quote_text: quoteText,
        rect: rect,
      };
      positionFloatingNode(selectionToolbar, rect);
    });
  }

  function removePendingMutation(context, mutationId) {
    context.pendingMutations = (context.pendingMutations || []).filter(function (mutation) {
      return mutation.id !== mutationId;
    });
  }

  function queueOptimisticMutation(context, mutation, payload) {
    context.pendingMutations = (context.pendingMutations || []).concat([mutation]);
    rebuildVisibleState(context);
    const runMutation = async function () {
      try {
        const result = await requestReaderAction(context, payload);
        removePendingMutation(context, mutation.id);
        if (result.state) {
          commitServerState(context, Object.assign({}, result.state, {
            kind: context.state.kind,
            item_id: context.state.item_id,
            save_url: context.state.save_url,
            content_signature: context.state.content_signature,
          }));
        } else {
          rebuildVisibleState(context);
        }
      } catch (error) {
        removePendingMutation(context, mutation.id);
        rebuildVisibleState(context);
        throw error;
      }
    };
    const queue = context.mutationQueue || Promise.resolve();
    const task = queue.catch(function () {
      return null;
    }).then(runMutation);
    context.mutationQueue = task.catch(function () {
      return null;
    });
    return task;
  }

  async function saveAnnotation(kind, noteText) {
    if (!activeReaderContext || !activeReaderContext.pendingSelection) {
      return;
    }
    const selection = Object.assign({}, activeReaderContext.pendingSelection);
    const optimisticAnnotation = buildOptimisticAnnotation(selection, kind, noteText);
    if (!optimisticAnnotation) {
      return;
    }
    clearBrowserSelection();
    hideFloatingUi();
    try {
      await queueOptimisticMutation(activeReaderContext, {
        id: `add-${optimisticAnnotation.id}`,
        type: "add_annotation",
        annotation: optimisticAnnotation,
      }, {
        action: "add_annotation",
        kind: kind,
        start_offset: selection.start_offset,
        end_offset: selection.end_offset,
        quote_text: selection.quote_text,
        note_text: String(noteText || ""),
        content_signature: activeReaderContext.state.content_signature,
      });
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  async function deleteAnnotation(annotationId) {
    if (!activeReaderContext || !annotationId) {
      return;
    }
    hideAnnotationMenu();
    clearBrowserSelection();
    try {
      await queueOptimisticMutation(activeReaderContext, {
        id: `delete-${annotationId}`,
        type: "delete_annotation",
        annotation_id: annotationId,
      }, {
        action: "delete_annotation",
        annotation_id: annotationId,
        content_signature: activeReaderContext.state.content_signature,
      });
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function openAnnotationMenu(target) {
    const bubbleElement = target.closest("[data-reader-note-bubble]");
    const annotationElement = bubbleElement || target.closest("[data-reader-annotation-ids]");
    if (!activeReaderContext || !(annotationElement instanceof HTMLElement)) {
      return;
    }
    const annotationIds = bubbleElement
      ? [String(bubbleElement.getAttribute("data-reader-annotation-id") || "").trim()].filter(Boolean)
      : String(annotationElement.getAttribute("data-reader-annotation-ids") || "").trim().split(/\s+/).filter(Boolean);
    const annotations = annotationIds.map(function (annotationId) {
      return activeReaderContext.state.annotations.find(function (item) {
        return item.id === annotationId;
      }) || null;
    }).filter(Boolean);
    if (!annotations.length) {
      return;
    }
    annotationMenu.dataset.readerContextKey = activeReaderContext.key;
    const body = annotationMenu.querySelector("[data-reader-annotation-menu-body]");
    if (!(body instanceof HTMLElement)) {
      return;
    }
    body.replaceChildren();
    annotations.forEach(function (annotation) {
      const entry = document.createElement("div");
      entry.className = "reader-annotation-menu-entry";
      if (annotation.note_text) {
        const note = document.createElement("p");
        note.className = "reader-annotation-menu-note";
        note.textContent = annotation.note_text;
        entry.appendChild(note);
      }
      const meta = document.createElement("p");
      meta.className = "reader-annotation-menu-meta";
      meta.textContent = annotation.display_created_at
        ? `${annotation.kind_label || "\u6807\u6ce8"} | ${annotation.display_created_at}`
        : (annotation.kind_label || "\u6807\u6ce8");
      entry.appendChild(meta);
      const remove = document.createElement("button");
      remove.className = "reader-annotation-menu-remove";
      remove.type = "button";
      remove.dataset.readerAnnotationMenuAction = "delete";
      remove.dataset.readerAnnotationId = annotation.id;
      remove.appendChild(createIcon("trash"));
      remove.append(`\u79fb\u9664${annotation.kind_label || "\u6807\u6ce8"}`);
      entry.appendChild(remove);
      body.appendChild(entry);
    });
    positionFloatingNode(annotationMenu, annotationElement.getBoundingClientRect());
  }

  function handleReaderUiClick(target, event) {
    const toolbarButton = target.closest("[data-reader-action]");
    if (toolbarButton instanceof HTMLButtonElement) {
      event.preventDefault();
      const action = toolbarButton.dataset.readerAction || "";
      if (action === "note") {
        if (activeReaderContext && activeReaderContext.pendingSelection) {
          positionFloatingNode(noteComposer, activeReaderContext.pendingSelection.rect);
          noteComposer.dataset.readerContextKey = activeReaderContext.key;
          selectionToolbar.hidden = true;
          const input = noteComposer.querySelector("[data-reader-note-input]");
          if (input instanceof HTMLTextAreaElement) {
            input.value = "";
            window.requestAnimationFrame(function () {
              input.focus();
            });
          }
        }
      } else {
        saveAnnotation(action, "");
      }
      return true;
    }

    const noteButton = target.closest("[data-reader-note-action]");
    if (noteButton instanceof HTMLButtonElement) {
      event.preventDefault();
      const action = noteButton.dataset.readerNoteAction || "";
      if (action === "cancel") {
        hideNoteComposer();
      } else if (action === "submit") {
        const input = noteComposer.querySelector("[data-reader-note-input]");
        const noteText = input instanceof HTMLTextAreaElement ? input.value.trim() : "";
        if (!noteText) {
          showToast("\u9644\u6ce8\u5185\u5bb9\u8fd8\u6ca1\u5199\u3002", "error");
          if (input instanceof HTMLTextAreaElement) {
            input.focus();
          }
          return true;
        }
        saveAnnotation("note", noteText);
      }
      return true;
    }

    if (target.closest("[data-reader-history-resume]")) {
      event.preventDefault();
      restoreReaderProgress();
      return true;
    }

    if (target.closest("[data-reader-annotation-menu-action='delete']")) {
      event.preventDefault();
      const deleteButton = target.closest("[data-reader-annotation-menu-action='delete']");
      deleteAnnotation(deleteButton instanceof HTMLElement ? String(deleteButton.getAttribute("data-reader-annotation-id") || "").trim() : "");
      return true;
    }

    if (target.closest("[data-reader-note-bubble], [data-reader-annotation-ids]")) {
      event.preventDefault();
      openAnnotationMenu(target);
      return true;
    }

    if (!target.closest(".reader-annotation-toolbar") && !target.closest(".reader-note-composer")) {
      hideSelectionToolbar();
      if (!target.closest(".reader-annotation-menu")) {
        hideAnnotationMenu();
      }
    }
    return false;
  }

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    if (handleReaderUiClick(target, event)) {
      return;
    }
    const templateTrigger = target.closest("[data-reader-open]");
    if (templateTrigger instanceof HTMLElement) {
      const templateId = templateTrigger.getAttribute("data-reader-template");
      const template = templateId ? document.getElementById(templateId) : null;
      if (template instanceof HTMLTemplateElement) {
        openOverlay(template.innerHTML);
      }
      return;
    }
    const remoteTrigger = target.closest("[data-reader-url]");
    if (remoteTrigger instanceof HTMLElement) {
      event.preventDefault();
      const remoteUrl = remoteTrigger instanceof HTMLAnchorElement
        ? remoteTrigger.href
        : String(remoteTrigger.getAttribute("data-reader-url") || "").trim();
      if (!remoteUrl) {
        return;
      }
      openRemote(remoteUrl).catch(function () {
        content.innerHTML = '<div class="reader-loading">\u5f53\u524d\u65e0\u6cd5\u52a0\u8f7d\u8fd9\u4e2a\u9884\u89c8\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5\u3002</div>';
        focusCloseButton();
      });
      return;
    }
    if (target.closest("[data-reader-close]")) {
      closeOverlay();
    }
  });

  overlay.addEventListener("click", function (event) {
    const target = event.target;
    if (target instanceof Element && target.hasAttribute("data-reader-close")) {
      closeOverlay();
    }
  });

  overlay.addEventListener("mousedown", function (event) {
    const target = event.target;
    if (target instanceof Element && target.closest(".reader-annotation-toolbar, .reader-note-composer, .reader-annotation-menu")) {
      event.preventDefault();
    }
  }, true);

  overlay.addEventListener("pointerup", function (event) {
    if (!overlay.hidden) {
      lastPointer = { x: event.clientX, y: event.clientY };
      scheduleSelectionRefresh();
    }
  }, true);

  overlay.addEventListener("touchend", function (event) {
    const touch = event.changedTouches && event.changedTouches[0];
    if (touch) {
      lastPointer = { x: touch.clientX, y: touch.clientY };
    }
    scheduleSelectionRefresh();
  }, { passive: true, capture: true });

  document.addEventListener("selectionchange", function () {
    if (!overlay.hidden && activeReaderContext) {
      scheduleSelectionRefresh();
    }
  });

  if (scrollShell instanceof HTMLElement) {
    scrollShell.addEventListener("scroll", function () {
      if (!overlay.hidden) {
        hideSelectionToolbar();
        hideAnnotationMenu();
      }
      if (!activeReaderContext) {
        return;
      }
      window.clearTimeout(progressTimer);
      progressTimer = window.setTimeout(function () {
        persistActiveReaderProgress(false);
      }, PROGRESS_SAVE_DEBOUNCE_MS);
    });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden && activeReaderContext) {
      persistActiveReaderProgress(true);
    }
  });

  window.addEventListener("resize", function () {
    hideSelectionToolbar();
    hideAnnotationMenu();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      if (!noteComposer.hidden) {
        hideNoteComposer();
        return;
      }
      if (!annotationMenu.hidden) {
        hideAnnotationMenu();
        return;
      }
      if (!overlay.hidden) {
        closeOverlay();
      }
    }
  });

  autoOpenFromLocation();
})();
