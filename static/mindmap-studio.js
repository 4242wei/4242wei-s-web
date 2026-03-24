(function () {
  const root = document.querySelector("[data-studio-root]");
  if (!root) {
    return;
  }

  const state = {
    documents: [],
    activeDocument: null,
    templateOptions: [],
    themeOptions: [],
    surfaceOptions: [],
    densityOptions: [],
    layoutOptions: [],
    kindOptions: [],
    relationTones: [],
    originOptions: [],
    verifyOptions: [],
    scale: 1,
    showRelations: true,
    dirty: false,
    saving: false,
    saveTimer: 0,
    renderFrame: 0,
    isApplyingServerPayload: false,
  };

  const bootstrapUrl = root.dataset.bootstrapUrl || "";
  const createUrl = root.dataset.createUrl || "";
  const currentUrl = root.dataset.currentUrl || "";
  const requestedDocId = root.dataset.requestedDoc || "";
  const saveUrlTemplate = root.dataset.saveUrlTemplate || "";
  const duplicateUrlTemplate = root.dataset.duplicateUrlTemplate || "";
  const deleteUrlTemplate = root.dataset.deleteUrlTemplate || "";
  const exportUrlTemplate = root.dataset.exportUrlTemplate || "";

  const templateGrid = root.querySelector("[data-studio-template-grid]");
  const documentList = root.querySelector("[data-studio-document-list]");
  const refreshButton = root.querySelector("[data-studio-refresh]");

  const documentTitleInput = root.querySelector("[data-studio-document-title]");
  const layoutSelect = root.querySelector("[data-studio-layout-select]");
  const themeSelect = root.querySelector("[data-studio-theme-select]");
  const surfaceSelect = root.querySelector("[data-studio-surface-select]");
  const densitySelect = root.querySelector("[data-studio-density-select]");
  const saveState = root.querySelector("[data-studio-save-state]");
  const documentMeta = root.querySelector("[data-studio-document-meta]");
  const duplicateButton = root.querySelector("[data-studio-duplicate]");
  const deleteButton = root.querySelector("[data-studio-delete]");
  const exportButton = root.querySelector("[data-studio-export]");
  const baselineButton = root.querySelector("[data-studio-baseline]");

  const canvasHeading = root.querySelector("[data-studio-canvas-heading]");
  const canvasDescription = root.querySelector("[data-studio-canvas-description]");
  const statRow = root.querySelector("[data-studio-stat-row]");
  const surfaceFrame = root.querySelector("[data-studio-surface-frame]");
  const baselinePill = root.querySelector("[data-studio-baseline-pill]");
  const referencePill = root.querySelector("[data-studio-reference-pill]");
  const mapViewport = root.querySelector("[data-studio-map-viewport]");
  const mapScaler = root.querySelector("[data-studio-map-scaler]");
  const branchLinksLayer = root.querySelector("[data-studio-branch-links]");
  const relationLayer = root.querySelector("[data-studio-relations]");
  const mapCanvas = root.querySelector("[data-studio-map-canvas]");
  const toggleRelationsButton = root.querySelector("[data-studio-toggle-relations]");
  const recenterButton = root.querySelector("[data-studio-recenter]");
  const zoomOutButton = root.querySelector("[data-studio-zoom-out]");
  const zoomResetButton = root.querySelector("[data-studio-zoom-reset]");
  const zoomInButton = root.querySelector("[data-studio-zoom-in]");

  const nodeHeading = root.querySelector("[data-studio-node-heading]");
  const nodeMeta = root.querySelector("[data-studio-node-meta]");
  const addChildButton = root.querySelector("[data-studio-add-child]");
  const addSiblingButton = root.querySelector("[data-studio-add-sibling]");
  const moveUpButton = root.querySelector("[data-studio-move-up]");
  const moveDownButton = root.querySelector("[data-studio-move-down]");
  const toggleCollapseButton = root.querySelector("[data-studio-toggle-collapse]");
  const removeNodeButton = root.querySelector("[data-studio-remove-node]");

  const nodeLabelInput = root.querySelector("[data-studio-node-label]");
  const nodeSummaryInput = root.querySelector("[data-studio-node-summary]");
  const nodeNoteInput = root.querySelector("[data-studio-node-note]");
  const nodeKindSelect = root.querySelector("[data-studio-node-kind]");
  const nodeVerifySelect = root.querySelector("[data-studio-node-verify]");
  const nodeSideSelect = root.querySelector("[data-studio-node-side]");
  const nodeOriginInput = root.querySelector("[data-studio-node-origin]");
  const nodeTimeInput = root.querySelector("[data-studio-node-time]");
  const nodeSnapshotInput = root.querySelector("[data-studio-node-snapshot]");
  const nodeSymbolsInput = root.querySelector("[data-studio-node-symbols]");
  const nodeTagsInput = root.querySelector("[data-studio-node-tags]");

  const relationTargetSelect = root.querySelector("[data-studio-relation-target]");
  const relationToneSelect = root.querySelector("[data-studio-relation-tone]");
  const relationLabelInput = root.querySelector("[data-studio-relation-label]");
  const addRelationButton = root.querySelector("[data-studio-add-relation]");
  const relationList = root.querySelector("[data-studio-relation-list]");
  const referenceList = root.querySelector("[data-studio-reference-list]");
  const baselineBox = root.querySelector("[data-studio-baseline-box]");

  function urlFor(template, documentId) {
    return String(template || "").replace("__DOC_ID__", encodeURIComponent(documentId || ""));
  }

  function nowIso() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "");
  }

  function sanitizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function parseTokenList(rawValue) {
    return String(rawValue || "")
      .split(/[\s,;，；、]+/)
      .map(function (item) {
        return item.trim();
      })
      .filter(function (item, index, list) {
        return item && list.indexOf(item) === index;
      });
  }

  function ensureToastStack() {
    let stack = document.querySelector(".studio-toast-stack");
    if (stack instanceof HTMLElement) {
      return stack;
    }
    stack = window.document.createElement("div");
    stack.className = "studio-toast-stack";
    document.body.appendChild(stack);
    return stack;
  }

  function showToast(kind, message) {
    const stack = ensureToastStack();
    const item = window.document.createElement("div");
    item.className = "studio-toast is-" + kind;
    item.textContent = message;
    stack.appendChild(item);
    window.setTimeout(function () {
      item.classList.add("is-leaving");
      window.setTimeout(function () {
        item.remove();
      }, 220);
    }, kind === "error" ? 5000 : 2600);
  }

  function requestJson(url, options) {
    return fetch(url, options).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "请求失败。");
        }
        return payload;
      });
    });
  }

  function getOptionMeta(options, key) {
    return (options || []).find(function (item) {
      return item.key === key;
    }) || null;
  }

  function activeDocument() {
    return state.activeDocument;
  }

  function nodeMap(document) {
    const map = new Map();
    (document && document.nodes ? document.nodes : []).forEach(function (node) {
      map.set(node.id, node);
    });
    return map;
  }

  function childMap(document) {
    const map = new Map();
    (document && document.nodes ? document.nodes : []).forEach(function (node) {
      const parentId = node.parent_id || "";
      if (!map.has(parentId)) {
        map.set(parentId, []);
      }
      map.get(parentId).push(node);
    });
    map.forEach(function (items) {
      items.sort(function (left, right) {
        return (left.order || 0) - (right.order || 0);
      });
    });
    return map;
  }

  function computeDocumentStats(document) {
    if (!document) {
      return {
        node_count: 0,
        relationship_count: 0,
        leaf_count: 0,
        max_depth: 0,
      };
    }
    const childrenLookup = childMap(document);
    function walk(nodeId, depth) {
      const children = childrenLookup.get(nodeId) || [];
      if (!children.length) {
        return {
          leaf_count: 1,
          max_depth: depth,
        };
      }
      return children.reduce(
        function (accumulator, child) {
          const next = walk(child.id, depth + 1);
          accumulator.leaf_count += next.leaf_count;
          accumulator.max_depth = Math.max(accumulator.max_depth, next.max_depth);
          return accumulator;
        },
        { leaf_count: 0, max_depth: depth }
      );
    }
    const walked = walk(document.root_id, 1);
    return {
      node_count: Array.isArray(document.nodes) ? document.nodes.length : 0,
      relationship_count: Array.isArray(document.relationships) ? document.relationships.length : 0,
      leaf_count: walked.leaf_count,
      max_depth: walked.max_depth,
    };
  }

  function activeDocumentStats() {
    return computeDocumentStats(activeDocument());
  }

  function selectedNode(document) {
    if (!document) {
      return null;
    }
    const map = nodeMap(document);
    return map.get(document.active_node_id) || map.get(document.root_id) || null;
  }

  function touchNode(node, options) {
    if (!node) {
      return;
    }
    node.updated_at = nowIso();
    if (options && options.manual) {
      if (node.origin_mode !== "manual" && node.verify_state === "stable") {
        node.verify_state = "needs_verify";
      }
      if (node.origin_mode === "seed" && node.verify_state === "draft") {
        node.verify_state = "needs_verify";
      }
    }
  }

  function markDirty(message) {
    state.dirty = true;
    updateSaveState();
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(function () {
      saveDocument(false);
    }, 700);
    if (message) {
      showToast("info", message);
    }
  }

  function replaceUrl(documentId) {
    if (!currentUrl || !window.history || !window.history.replaceState) {
      return;
    }
    const nextUrl = documentId ? currentUrl + "?doc=" + encodeURIComponent(documentId) : currentUrl;
    window.history.replaceState({}, "", nextUrl);
  }

  function buildStatChip(text) {
    const chip = window.document.createElement("span");
    chip.className = "studio-stat-chip";
    chip.textContent = text;
    return chip;
  }

  function cloneDocument(document) {
    return JSON.parse(JSON.stringify(document));
  }

  function applyBootstrapPayload(payload) {
    state.documents = Array.isArray(payload.documents) ? payload.documents : [];
    state.templateOptions = Array.isArray(payload.template_options) ? payload.template_options : [];
    state.themeOptions = Array.isArray(payload.theme_options) ? payload.theme_options : [];
    state.surfaceOptions = Array.isArray(payload.surface_options) ? payload.surface_options : [];
    state.densityOptions = Array.isArray(payload.density_options) ? payload.density_options : [];
    state.layoutOptions = Array.isArray(payload.layout_options) ? payload.layout_options : [];
    state.kindOptions = Array.isArray(payload.kind_options) ? payload.kind_options : [];
    state.relationTones = Array.isArray(payload.relation_tones) ? payload.relation_tones : [];
    state.originOptions = Array.isArray(payload.origin_options) ? payload.origin_options : [];
    state.verifyOptions = Array.isArray(payload.verify_options) ? payload.verify_options : [];
    state.activeDocument = payload.active_document ? cloneDocument(payload.active_document) : null;
    state.scale = 1;
    state.dirty = false;
    state.saving = false;
    updateSaveState();
    replaceUrl(state.activeDocument ? state.activeDocument.id : "");
    renderShell();
    recenterViewport();
  }

  async function loadBootstrap(documentId) {
    const url = new URL(bootstrapUrl, window.location.origin);
    if (documentId) {
      url.searchParams.set("doc", documentId);
    }
    const payload = await requestJson(url.toString(), {
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      cache: "no-store",
    });
    applyBootstrapPayload(payload);
  }

  async function createDocument(templateKey) {
    const templateMeta = getOptionMeta(state.templateOptions, templateKey);
    const payload = await requestJson(createUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({
        template_key: templateKey,
        title: templateMeta ? templateMeta.label : "新导图",
      }),
    });
    applyBootstrapPayload(payload);
    showToast("success", "已创建新的导图工作台。");
  }

  async function duplicateDocument() {
    const document = activeDocument();
    if (!document) {
      return;
    }
    const payload = await requestJson(urlFor(duplicateUrlTemplate, document.id), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    applyBootstrapPayload(payload);
    showToast("success", "已复制一份导图。");
  }

  async function deleteDocument() {
    const document = activeDocument();
    if (!document) {
      return;
    }
    if (!window.confirm("删除这张导图吗？系统会自动保留一个新的空白工作台。")) {
      return;
    }
    const payload = await requestJson(urlFor(deleteUrlTemplate, document.id), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    applyBootstrapPayload(payload);
    showToast("success", "导图已删除。");
  }

  async function saveDocument(immediate) {
    const document = activeDocument();
    if (!document || state.saving || (!state.dirty && !immediate)) {
      return;
    }
    window.clearTimeout(state.saveTimer);
    state.saving = true;
    updateSaveState();

    try {
      const payload = await requestJson(urlFor(saveUrlTemplate, document.id), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          document: document,
        }),
      });
      applyBootstrapPayload(payload);
      return payload;
    } catch (error) {
      state.saving = false;
      updateSaveState(error instanceof Error ? error.message : "保存失败。");
      showToast("error", error instanceof Error ? error.message : "保存失败。");
      throw error;
    }
  }

  function updateSaveState(message) {
    if (!(saveState instanceof HTMLElement)) {
      return;
    }
    if (message) {
      saveState.textContent = message;
      saveState.dataset.state = "error";
      return;
    }
    if (state.saving) {
      saveState.textContent = "保存中";
      saveState.dataset.state = "saving";
      return;
    }
    if (state.dirty) {
      saveState.textContent = "待保存";
      saveState.dataset.state = "dirty";
      return;
    }
    saveState.textContent = "已同步";
    saveState.dataset.state = "saved";
  }

  function updateDocumentField(key, value) {
    const document = activeDocument();
    if (!document) {
      return;
    }
    document[key] = value;
    document.updated_at = nowIso();
    const shouldRecenter = key === "layout_key" || key === "surface_key" || key === "density_key";
    markDirty();
    renderShell();
    if (shouldRecenter) {
      recenterViewport();
    }
  }

  function updateSelectedNode(mutator) {
    const document = activeDocument();
    const node = selectedNode(document);
    if (!document || !node || typeof mutator !== "function") {
      return;
    }
    mutator(node);
    touchNode(node, { manual: true });
    document.updated_at = nowIso();
    markDirty();
    renderShell();
  }

  function siblingsFor(document, node) {
    if (!document || !node) {
      return [];
    }
    const siblings = document.nodes.filter(function (item) {
      return (item.parent_id || "") === (node.parent_id || "");
    });
    siblings.sort(function (left, right) {
      return (left.order || 0) - (right.order || 0);
    });
    return siblings;
  }

  function reindexSiblings(document, parentId) {
    const siblings = document.nodes
      .filter(function (item) {
        return (item.parent_id || "") === (parentId || "");
      })
      .sort(function (left, right) {
        return (left.order || 0) - (right.order || 0);
      });
    siblings.forEach(function (item, index) {
      item.order = index;
    });
  }

  function nextSideForRoot(document) {
    const rootChildren = document.nodes.filter(function (item) {
      return item.parent_id === document.root_id;
    });
    const leftCount = rootChildren.filter(function (item) {
      return item.side === "left";
    }).length;
    const rightCount = rootChildren.length - leftCount;
    return leftCount <= rightCount ? "left" : "right";
  }

  function createNode(document, partial) {
    const node = {
      id: "node-" + Math.random().toString(36).slice(2, 10),
      parent_id: partial.parent_id || document.root_id,
      side: partial.side || "right",
      order: typeof partial.order === "number" ? partial.order : 0,
      label: partial.label || "新节点",
      summary: partial.summary || "",
      note: partial.note || "",
      kind: partial.kind || "topic",
      origin_mode: partial.origin_mode || "manual",
      verify_state: partial.verify_state || "needs_verify",
      origin_snapshot_node_id: partial.origin_snapshot_node_id || "",
      symbols: Array.isArray(partial.symbols) ? partial.symbols.slice() : [],
      tags: Array.isArray(partial.tags) ? partial.tags.slice() : [],
      time_hint: partial.time_hint || "",
      collapsed: false,
      created_at: nowIso(),
      updated_at: nowIso(),
    };
    document.nodes.push(node);
    reindexSiblings(document, node.parent_id);
    return node;
  }

  function addChildNode() {
    const document = activeDocument();
    const node = selectedNode(document);
    if (!document || !node) {
      return;
    }
    const side = node.id === document.root_id ? nextSideForRoot(document) : node.side || "right";
    const childCount = document.nodes.filter(function (item) {
      return item.parent_id === node.id;
    }).length;
    const child = createNode(document, {
      parent_id: node.id,
      side: side,
      order: childCount,
      kind: document.layout_key === "logic" ? "thesis" : "topic",
    });
    node.collapsed = false;
    document.active_node_id = child.id;
    document.updated_at = nowIso();
    markDirty();
    renderShell();
  }

  function addSiblingNode() {
    const document = activeDocument();
    const node = selectedNode(document);
    if (!document || !node || node.id === document.root_id) {
      return;
    }
    const siblings = siblingsFor(document, node);
    siblings.forEach(function (item, index) {
      item.order = index;
    });
    const insertAt = siblings.findIndex(function (item) {
      return item.id === node.id;
    }) + 1;
    siblings.forEach(function (item) {
      if (item.order >= insertAt) {
        item.order += 1;
      }
    });
    const sibling = createNode(document, {
      parent_id: node.parent_id,
      side: node.side,
      order: insertAt,
      kind: "topic",
    });
    document.active_node_id = sibling.id;
    document.updated_at = nowIso();
    markDirty();
    renderShell();
  }

  function moveNode(direction) {
    const document = activeDocument();
    const node = selectedNode(document);
    if (!document || !node || node.id === document.root_id) {
      return;
    }
    const siblings = siblingsFor(document, node);
    const index = siblings.findIndex(function (item) {
      return item.id === node.id;
    });
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (index < 0 || targetIndex < 0 || targetIndex >= siblings.length) {
      return;
    }
    const target = siblings[targetIndex];
    const currentOrder = node.order;
    node.order = target.order;
    target.order = currentOrder;
    touchNode(node, { manual: true });
    touchNode(target, { manual: true });
    document.updated_at = nowIso();
    markDirty();
    renderShell();
  }

  function toggleCollapse() {
    updateSelectedNode(function (node) {
      node.collapsed = !node.collapsed;
    });
  }

  function removeNode() {
    const document = activeDocument();
    const node = selectedNode(document);
    if (!document || !node || node.id === document.root_id) {
      return;
    }
    const descendantIds = new Set();
    const queue = [node.id];
    while (queue.length) {
      const currentId = queue.shift();
      if (!currentId || descendantIds.has(currentId)) {
        continue;
      }
      descendantIds.add(currentId);
      document.nodes.forEach(function (item) {
        if (item.parent_id === currentId) {
          queue.push(item.id);
        }
      });
    }
    document.nodes = document.nodes.filter(function (item) {
      return !descendantIds.has(item.id);
    });
    document.relationships = document.relationships.filter(function (relationship) {
      return !descendantIds.has(relationship.from_node_id) && !descendantIds.has(relationship.to_node_id);
    });
    reindexSiblings(document, node.parent_id);
    document.active_node_id = document.root_id;
    document.updated_at = nowIso();
    markDirty();
    renderShell();
  }

  function recordBaselineSnapshot() {
    const document = activeDocument();
    if (!document) {
      return;
    }
    document.generated_snapshot = {
      generated_at: nowIso(),
      reference_document_ids: Array.isArray(document.reference_document_ids) ? document.reference_document_ids.slice() : [],
      nodes: document.nodes.map(function (node) {
        return JSON.parse(JSON.stringify(node));
      }),
      relationships: document.relationships.map(function (relationship) {
        return JSON.parse(JSON.stringify(relationship));
      }),
    };
    document.nodes.forEach(function (node) {
      if (!node.origin_snapshot_node_id) {
        node.origin_snapshot_node_id = node.id;
      }
      if (node.verify_state === "draft") {
        node.verify_state = "stable";
      }
    });
    document.updated_at = nowIso();
    markDirty();
    renderShell();
    showToast("success", "当前结构已记录为生成基线。");
  }

  function renderSelectOptions(select, options, value) {
    if (!(select instanceof HTMLSelectElement)) {
      return;
    }
    select.innerHTML = "";
    (options || []).forEach(function (item) {
      const option = window.document.createElement("option");
      option.value = item.key;
      option.textContent = item.label;
      if (item.key === value) {
        option.selected = true;
      }
      select.appendChild(option);
    });
  }

  function renderTemplateButtons() {
    if (!(templateGrid instanceof HTMLElement)) {
      return;
    }
    templateGrid.innerHTML = "";
    state.templateOptions.forEach(function (template) {
      const button = window.document.createElement("button");
      button.type = "button";
      button.className = "studio-template-button";
      button.innerHTML = "<strong>" + template.label + "</strong><span>" + template.description + "</span>";
      button.addEventListener("click", function () {
        createDocument(template.key).catch(function (error) {
          showToast("error", error instanceof Error ? error.message : "创建失败。");
        });
      });
      templateGrid.appendChild(button);
    });
  }

  function renderDocumentList() {
    if (!(documentList instanceof HTMLElement)) {
      return;
    }
    documentList.innerHTML = "";
    state.documents.forEach(function (document) {
      const isActive = state.activeDocument && state.activeDocument.id === document.id;
      const cardDocument = isActive ? state.activeDocument : document;
      const cardStats = computeDocumentStats(cardDocument);
      const layoutMeta = getOptionMeta(state.layoutOptions, cardDocument.layout_key || document.layout_key);
      const button = window.document.createElement("button");
      button.type = "button";
      button.className = "studio-document-card";
      if (isActive) {
        button.classList.add("is-active");
      }
      button.innerHTML =
        "<strong>" + (cardDocument.title || document.title) + "</strong>" +
        "<span>" + (layoutMeta ? layoutMeta.label : (document.layout_label || "导图")) + " · " + cardStats.node_count + " 节点 · " + cardStats.relationship_count + " 关系</span>" +
        "<span>" + (isActive && state.dirty ? "待保存" : document.updated_label) + "</span>";
      button.addEventListener("click", function () {
        const switchDocument = function () {
          loadBootstrap(document.id).catch(function (error) {
            showToast("error", error instanceof Error ? error.message : "切换失败。");
          });
        };
        if (state.dirty) {
          saveDocument(true)
            .then(switchDocument)
            .catch(function () {
              return;
            });
        } else {
          switchDocument();
        }
      });
      documentList.appendChild(button);
    });
  }

  function renderHeader() {
    const document = activeDocument();
    if (!document) {
      return;
    }
    const stats = activeDocumentStats();
    if (documentTitleInput instanceof HTMLInputElement) {
      documentTitleInput.value = document.title || "";
    }
    renderSelectOptions(layoutSelect, state.layoutOptions, document.layout_key);
    renderSelectOptions(themeSelect, state.themeOptions, document.theme_key);
    renderSelectOptions(surfaceSelect, state.surfaceOptions, document.surface_key);
    renderSelectOptions(densitySelect, state.densityOptions, document.density_key);

    const layoutMeta = getOptionMeta(state.layoutOptions, document.layout_key);
    const themeMeta = getOptionMeta(state.themeOptions, document.theme_key);
    const baselineText = document.generated_snapshot ? "已记录基线" : "无基线";
    setText(
      documentMeta,
      [
        layoutMeta ? layoutMeta.label : document.layout_label || "",
        themeMeta ? themeMeta.label : document.theme_label || "",
        "最后编辑 " + (document.updated_at || ""),
        baselineText,
        stats.node_count + " 节点",
      ]
        .filter(Boolean)
        .join(" · ")
    );

    const surfaceMeta = getOptionMeta(state.surfaceOptions, document.surface_key);
    if (surfaceFrame instanceof HTMLElement && surfaceMeta && surfaceMeta.frame_width) {
      surfaceFrame.style.setProperty("--studio-surface-width", String(surfaceMeta.frame_width) + "px");
    }
    root.dataset.themeKey = document.theme_key || "graphite";
    root.dataset.layoutKey = document.layout_key || "mindmap";
    root.dataset.densityKey = document.density_key || "roomy";
    baselinePill.textContent = document.generated_snapshot ? "基线 " + document.generated_snapshot.generated_at : "无生成基线";
    referencePill.textContent = (document.reference_document_ids || []).length
      ? "参考 " + document.reference_document_ids.length + " 张导图"
      : "无参考导图";
  }

  function renderStats() {
    const document = activeDocument();
    if (!(statRow instanceof HTMLElement) || !document) {
      return;
    }
    const stats = activeDocumentStats();
    const layoutMeta = getOptionMeta(state.layoutOptions, document.layout_key);
    statRow.innerHTML = "";
    statRow.appendChild(buildStatChip(layoutMeta ? layoutMeta.label : "导图"));
    statRow.appendChild(buildStatChip(stats.node_count + " 节点"));
    statRow.appendChild(buildStatChip(stats.relationship_count + " 关系"));
    statRow.appendChild(buildStatChip(stats.max_depth + " 层"));
    statRow.appendChild(buildStatChip(stats.leaf_count + " 叶子"));
  }

  function setText(node, value) {
    if (node instanceof HTMLElement) {
      node.textContent = value;
    }
  }

  function renderCanvasMeta() {
    const document = activeDocument();
    if (!document) {
      return;
    }
    const layoutMeta = getOptionMeta(state.layoutOptions, document.layout_key);
    const surfaceMeta = getOptionMeta(state.surfaceOptions, document.surface_key);
    setText(canvasHeading, layoutMeta ? layoutMeta.label : "结构视图");
    setText(
      canvasDescription,
      [
        layoutMeta ? layoutMeta.description : "",
        surfaceMeta ? "当前画面：" + surfaceMeta.label : "",
      ]
        .filter(Boolean)
        .join(" ")
    );
    if (zoomResetButton instanceof HTMLButtonElement) {
      zoomResetButton.textContent = Math.round(state.scale * 100) + "%";
    }
    if (toggleRelationsButton instanceof HTMLButtonElement) {
      toggleRelationsButton.textContent = state.showRelations ? "隐藏关系线" : "显示关系线";
    }
  }

  function buildNodeLookup() {
    return nodeMap(activeDocument());
  }

  function buildChildrenLookup() {
    return childMap(activeDocument());
  }

  function createNodeShell(node, options) {
    const shell = window.document.createElement("div");
    shell.className = "studio-node-shell";
    shell.dataset.side = options.side || node.side || "right";

    const button = window.document.createElement("button");
    button.type = "button";
    button.className = "studio-node-card";
    if (state.activeDocument && state.activeDocument.active_node_id === node.id) {
      button.classList.add("is-active");
    }
    button.dataset.nodeId = node.id;
    button.dataset.kind = node.kind || "topic";
    button.dataset.side = options.side || node.side || "right";

    const title = window.document.createElement("strong");
    title.textContent = node.label || "未命名节点";
    button.appendChild(title);

    if (node.summary) {
      const summary = window.document.createElement("span");
      summary.className = "studio-node-summary";
      summary.textContent = node.summary;
      button.appendChild(summary);
    }

    const meta = window.document.createElement("div");
    meta.className = "studio-node-meta-row";
    meta.appendChild(buildStatChip((state.kindOptions.find(function (item) { return item.key === node.kind; }) || { label: "节点" }).label));
    meta.appendChild(buildStatChip((state.verifyOptions.find(function (item) { return item.key === node.verify_state; }) || { label: "草稿" }).label));
    meta.appendChild(buildStatChip((state.originOptions.find(function (item) { return item.key === node.origin_mode; }) || { label: "手动" }).label));
    if (node.time_hint) {
      meta.appendChild(buildStatChip(node.time_hint));
    }
    button.appendChild(meta);

    button.addEventListener("click", function () {
      const document = activeDocument();
      if (!document) {
        return;
      }
      document.active_node_id = node.id;
      renderShell();
    });
    shell.appendChild(button);

    const childrenLookup = buildChildrenLookup();
    const children = childrenLookup.get(node.id) || [];
    if (children.length) {
      const toggle = window.document.createElement("button");
      toggle.type = "button";
      toggle.className = "studio-node-toggle";
      toggle.textContent = node.collapsed ? "+" : "−";
      toggle.setAttribute("aria-label", node.collapsed ? "展开分支" : "折叠分支");
      toggle.addEventListener("click", function (event) {
        event.stopPropagation();
        const documentState = activeDocument();
        if (!documentState) {
          return;
        }
        const currentNode = buildNodeLookup().get(node.id);
        if (!currentNode) {
          return;
        }
        currentNode.collapsed = !currentNode.collapsed;
        touchNode(currentNode, { manual: true });
        documentState.updated_at = nowIso();
        markDirty();
        renderShell();
      });
      shell.appendChild(toggle);
    }

    return shell;
  }

  function createBranch(node, direction) {
    const childrenLookup = buildChildrenLookup();
    const branch = window.document.createElement("div");
    branch.className = "studio-branch";
    branch.dataset.side = direction;

    const nodeShell = createNodeShell(node, { side: direction });
    const children = childrenLookup.get(node.id) || [];

    if (children.length && !node.collapsed) {
      const childWrap = window.document.createElement("div");
      childWrap.className = "studio-branch-children";
      childWrap.dataset.side = direction;
      children.forEach(function (child) {
        childWrap.appendChild(createBranch(child, direction));
      });
      if (direction === "left") {
        branch.appendChild(childWrap);
        branch.appendChild(nodeShell);
      } else {
        branch.appendChild(nodeShell);
        branch.appendChild(childWrap);
      }
    } else {
      branch.appendChild(nodeShell);
    }

    return branch;
  }

  function renderMindmapLayout(document) {
    const lookup = buildNodeLookup();
    const childrenLookup = buildChildrenLookup();
    const rootNode = lookup.get(document.root_id);
    const shell = window.document.createElement("div");
    shell.className = "studio-layout studio-layout-mindmap";

    const leftSide = window.document.createElement("div");
    leftSide.className = "studio-layout-side is-left";
    const center = window.document.createElement("div");
    center.className = "studio-layout-center";
    const rightSide = window.document.createElement("div");
    rightSide.className = "studio-layout-side is-right";

    const rootShell = createNodeShell(rootNode, { side: "center" });
    rootShell.classList.add("is-root");
    center.appendChild(rootShell);

    (childrenLookup.get(document.root_id) || []).forEach(function (child) {
      if (child.side === "left") {
        leftSide.appendChild(createBranch(child, "left"));
      } else {
        rightSide.appendChild(createBranch(child, "right"));
      }
    });

    shell.appendChild(leftSide);
    shell.appendChild(center);
    shell.appendChild(rightSide);
    return shell;
  }

  function renderLogicLayout(document) {
    const lookup = buildNodeLookup();
    const childrenLookup = buildChildrenLookup();
    const rootNode = lookup.get(document.root_id);
    const shell = window.document.createElement("div");
    shell.className = "studio-layout studio-layout-logic";

    const rootSlot = window.document.createElement("div");
    rootSlot.className = "studio-logic-root";
    const treeSlot = window.document.createElement("div");
    treeSlot.className = "studio-logic-tree";

    const rootShell = createNodeShell(rootNode, { side: "right" });
    rootShell.classList.add("is-root");
    rootSlot.appendChild(rootShell);
    (childrenLookup.get(document.root_id) || []).forEach(function (child) {
      treeSlot.appendChild(createBranch(child, "right"));
    });
    shell.appendChild(rootSlot);
    shell.appendChild(treeSlot);
    return shell;
  }

  function createLaneStack(node) {
    const childrenLookup = buildChildrenLookup();
    const card = window.document.createElement("div");
    card.className = "studio-lane-stack";
    card.appendChild(createNodeShell(node, { side: "right" }));

    const children = childrenLookup.get(node.id) || [];
    if (children.length && !node.collapsed) {
      const body = window.document.createElement("div");
      body.className = "studio-lane-children";
      children.forEach(function (child) {
        body.appendChild(createLaneStack(child));
      });
      card.appendChild(body);
    }
    return card;
  }

  function renderLaneLayout(document) {
    const lookup = buildNodeLookup();
    const childrenLookup = buildChildrenLookup();
    const shell = window.document.createElement("div");
    shell.className = "studio-layout studio-layout-lanes";

    const rootNode = lookup.get(document.root_id);
    const rootSlot = window.document.createElement("div");
    rootSlot.className = "studio-lane-root";
    const rootShell = createNodeShell(rootNode, { side: "center" });
    rootShell.classList.add("is-root");
    rootSlot.appendChild(rootShell);
    shell.appendChild(rootSlot);

    const laneGrid = window.document.createElement("div");
    laneGrid.className = "studio-lane-grid";
    (childrenLookup.get(document.root_id) || []).forEach(function (child) {
      const lane = window.document.createElement("section");
      lane.className = "studio-lane";
      lane.appendChild(createLaneStack(child));
      laneGrid.appendChild(lane);
    });
    shell.appendChild(laneGrid);
    return shell;
  }

  function scheduleConnectorRender() {
    if (state.renderFrame) {
      window.cancelAnimationFrame(state.renderFrame);
    }
    state.renderFrame = window.requestAnimationFrame(function () {
      state.renderFrame = 0;
      renderConnectors();
    });
  }

  function pathBetween(startX, startY, endX, endY) {
    const delta = Math.max(Math.abs(endX - startX) * 0.4, 36);
    return "M " + startX + " " + startY + " C " + (startX + delta) + " " + startY + ", " + (endX - delta) + " " + endY + ", " + endX + " " + endY;
  }

  function renderConnectors() {
    if (!(mapCanvas instanceof HTMLElement) || !(mapScaler instanceof HTMLElement) || !(branchLinksLayer instanceof SVGElement) || !(relationLayer instanceof SVGElement)) {
      return;
    }
    const document = activeDocument();
    if (!document) {
      branchLinksLayer.innerHTML = "";
      relationLayer.innerHTML = "";
      return;
    }

    const cards = new Map();
    mapCanvas.querySelectorAll("[data-node-id]").forEach(function (card) {
      if (card instanceof HTMLElement) {
        cards.set(card.dataset.nodeId || "", card);
      }
    });

    const scalerRect = mapScaler.getBoundingClientRect();
    const width = Math.max(mapCanvas.scrollWidth + 120, scalerRect.width || 960);
    const height = Math.max(mapCanvas.scrollHeight + 120, scalerRect.height || 720);
    [branchLinksLayer, relationLayer].forEach(function (layer) {
      layer.setAttribute("viewBox", "0 0 " + width + " " + height);
      layer.setAttribute("width", String(width));
      layer.setAttribute("height", String(height));
      layer.innerHTML = "";
    });

    document.nodes.forEach(function (node) {
      if (!node.parent_id || !cards.has(node.id) || !cards.has(node.parent_id)) {
        return;
      }
      const card = cards.get(node.id);
      const parent = cards.get(node.parent_id);
      const cardRect = card.getBoundingClientRect();
      const parentRect = parent.getBoundingClientRect();
      const cardSide = card.dataset.side || node.side || "right";
      const startX = (cardSide === "left" ? (parentRect.left - scalerRect.left) : (parentRect.right - scalerRect.left)) / state.scale;
      const endX = (cardSide === "left" ? (cardRect.right - scalerRect.left) : (cardRect.left - scalerRect.left)) / state.scale;
      const startY = (parentRect.top + parentRect.height / 2 - scalerRect.top) / state.scale;
      const endY = (cardRect.top + cardRect.height / 2 - scalerRect.top) / state.scale;
      const path = window.document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("class", "studio-branch-link");
      path.setAttribute("d", pathBetween(startX, startY, endX, endY));
      branchLinksLayer.appendChild(path);
    });

    relationLayer.classList.toggle("is-hidden", !state.showRelations);
    if (!state.showRelations) {
      return;
    }

    document.relationships.forEach(function (relationship) {
      const from = cards.get(relationship.from_node_id);
      const to = cards.get(relationship.to_node_id);
      if (!(from instanceof HTMLElement) || !(to instanceof HTMLElement)) {
        return;
      }
      const fromRect = from.getBoundingClientRect();
      const toRect = to.getBoundingClientRect();
      const startX = (fromRect.left + fromRect.width / 2 - scalerRect.left) / state.scale;
      const startY = (fromRect.top + fromRect.height / 2 - scalerRect.top) / state.scale;
      const endX = (toRect.left + toRect.width / 2 - scalerRect.left) / state.scale;
      const endY = (toRect.top + toRect.height / 2 - scalerRect.top) / state.scale;

      const path = window.document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("class", "studio-relation-link is-" + (relationship.tone || "support"));
      path.setAttribute("d", pathBetween(startX, startY, endX, endY));
      relationLayer.appendChild(path);

      const label = window.document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("class", "studio-relation-label");
      label.setAttribute("x", String((startX + endX) / 2));
      label.setAttribute("y", String((startY + endY) / 2 - 8));
      label.textContent = relationship.label;
      relationLayer.appendChild(label);
    });
  }

  function renderMap() {
    const document = activeDocument();
    if (!(mapCanvas instanceof HTMLElement)) {
      return;
    }
    mapCanvas.innerHTML = "";
    if (!document) {
      return;
    }
    let view = null;
    if (document.layout_key === "logic") {
      view = renderLogicLayout(document);
    } else if (document.layout_key === "lanes") {
      view = renderLaneLayout(document);
    } else {
      view = renderMindmapLayout(document);
    }
    mapCanvas.appendChild(view);
    applyScale();
    scheduleConnectorRender();
  }

  function applyScale() {
    if (!(mapScaler instanceof HTMLElement)) {
      return;
    }
    mapScaler.style.transform = "scale(" + state.scale + ")";
    mapScaler.style.transformOrigin = "top left";
    if (zoomResetButton instanceof HTMLButtonElement) {
      zoomResetButton.textContent = Math.round(state.scale * 100) + "%";
    }
  }

  function recenterViewport() {
    if (!(mapViewport instanceof HTMLElement) || !(mapCanvas instanceof HTMLElement)) {
      return;
    }
    window.requestAnimationFrame(function () {
      mapViewport.scrollLeft = Math.max((mapCanvas.scrollWidth * state.scale - mapViewport.clientWidth) / 2, 0);
      mapViewport.scrollTop = Math.max((mapCanvas.scrollHeight * state.scale - mapViewport.clientHeight) / 2 - 80, 0);
    });
  }

  function renderRelationComposer() {
    const document = activeDocument();
    const node = selectedNode(document);
    renderSelectOptions(relationToneSelect, state.relationTones, "support");
    if (!(relationTargetSelect instanceof HTMLSelectElement) || !document || !node) {
      return;
    }
    relationTargetSelect.innerHTML = "";
    document.nodes
      .filter(function (candidate) {
        return candidate.id !== node.id;
      })
      .forEach(function (candidate) {
        const option = window.document.createElement("option");
        option.value = candidate.id;
        option.textContent = candidate.label;
        relationTargetSelect.appendChild(option);
      });
  }

  function renderRelationList() {
    const document = activeDocument();
    const node = selectedNode(document);
    if (!(relationList instanceof HTMLElement) || !document || !node) {
      return;
    }
    relationList.innerHTML = "";
    const related = document.relationships.filter(function (relationship) {
      return relationship.from_node_id === node.id || relationship.to_node_id === node.id;
    });
    if (!related.length) {
      relationList.innerHTML = '<p class="studio-muted">这个节点还没有关系线。</p>';
      return;
    }
    const lookup = buildNodeLookup();
    related.forEach(function (relationship) {
      const item = window.document.createElement("div");
      item.className = "studio-relation-item";
      const text = window.document.createElement("div");
      text.innerHTML =
        "<strong>" + relationship.label + "</strong>" +
        "<span>" +
        ((lookup.get(relationship.from_node_id) || {}).label || "未知") +
        " → " +
        ((lookup.get(relationship.to_node_id) || {}).label || "未知") +
        "</span>";
      const remove = window.document.createElement("button");
      remove.type = "button";
      remove.className = "studio-mini-button";
      remove.textContent = "移除";
      remove.addEventListener("click", function () {
        document.relationships = document.relationships.filter(function (item) {
          return item.id !== relationship.id;
        });
        document.updated_at = nowIso();
        markDirty();
        renderShell();
      });
      item.appendChild(text);
      item.appendChild(remove);
      relationList.appendChild(item);
    });
  }

  function renderReferenceList() {
    const document = activeDocument();
    if (!(referenceList instanceof HTMLElement) || !document) {
      return;
    }
    referenceList.innerHTML = "";
    const options = state.documents.filter(function (item) {
      return item.id !== document.id;
    });
    if (!options.length) {
      referenceList.innerHTML = '<p class="studio-muted">还没有其他导图可供参考。</p>';
      return;
    }
    options.forEach(function (item) {
      const label = window.document.createElement("label");
      label.className = "studio-reference-option";
      const input = window.document.createElement("input");
      input.type = "checkbox";
      input.checked = (document.reference_document_ids || []).includes(item.id);
      input.addEventListener("change", function () {
        const current = new Set(document.reference_document_ids || []);
        if (input.checked) {
          current.add(item.id);
        } else {
          current.delete(item.id);
        }
        document.reference_document_ids = Array.from(current);
        document.updated_at = nowIso();
        markDirty();
        renderHeader();
        renderBaselineBox();
      });
      const copy = window.document.createElement("span");
      copy.innerHTML = "<strong>" + item.title + "</strong><span>" + item.layout_label + " · " + item.node_count + " 节点</span>";
      label.appendChild(input);
      label.appendChild(copy);
      referenceList.appendChild(label);
    });
  }

  function renderBaselineBox() {
    const document = activeDocument();
    if (!(baselineBox instanceof HTMLElement) || !document) {
      return;
    }
    baselineBox.innerHTML = "";
    const snapshot = document.generated_snapshot;
    if (!snapshot) {
      baselineBox.innerHTML = '<p class="studio-muted">当前还没有生成基线。你可以先整理出一版结构，再点击上方“记录当前为基线”。</p>';
      return;
    }
    const meta = window.document.createElement("div");
    meta.className = "studio-baseline-meta";
    meta.appendChild(buildStatChip("基线时间 " + snapshot.generated_at));
    meta.appendChild(buildStatChip((snapshot.nodes || []).length + " 节点"));
    meta.appendChild(buildStatChip((snapshot.relationships || []).length + " 关系"));
    baselineBox.appendChild(meta);

    const note = window.document.createElement("p");
    note.className = "studio-muted";
    note.textContent =
      (snapshot.reference_document_ids || []).length
        ? "这版基线生成时参考了 " + snapshot.reference_document_ids.length + " 张旧导图。"
        : "这版基线没有挂任何旧导图参考。";
    baselineBox.appendChild(note);
  }

  function renderInspector() {
    const document = activeDocument();
    const node = selectedNode(document);
    if (!document || !node) {
      return;
    }
    setText(nodeHeading, node.label || "未命名节点");
    setText(
      nodeMeta,
      [
        "创建 " + (node.created_at || ""),
        "更新 " + (node.updated_at || ""),
        "来源 " + ((state.originOptions.find(function (item) { return item.key === node.origin_mode; }) || { label: "手动" }).label),
      ].join(" · ")
    );

    if (nodeLabelInput instanceof HTMLInputElement) {
      nodeLabelInput.value = node.label || "";
    }
    if (nodeSummaryInput instanceof HTMLTextAreaElement) {
      nodeSummaryInput.value = node.summary || "";
    }
    if (nodeNoteInput instanceof HTMLTextAreaElement) {
      nodeNoteInput.value = node.note || "";
    }
    renderSelectOptions(nodeKindSelect, state.kindOptions, node.kind);
    renderSelectOptions(nodeVerifySelect, state.verifyOptions, node.verify_state);
    if (nodeSideSelect instanceof HTMLSelectElement) {
      nodeSideSelect.value = node.side === "left" ? "left" : "right";
      nodeSideSelect.disabled = node.id === document.root_id || node.parent_id !== document.root_id;
    }
    if (nodeOriginInput instanceof HTMLInputElement) {
      nodeOriginInput.value = (state.originOptions.find(function (item) { return item.key === node.origin_mode; }) || { label: "手动" }).label;
    }
    if (nodeTimeInput instanceof HTMLInputElement) {
      nodeTimeInput.value = node.time_hint || "";
    }
    if (nodeSnapshotInput instanceof HTMLInputElement) {
      nodeSnapshotInput.value = node.origin_snapshot_node_id || "";
    }
    if (nodeSymbolsInput instanceof HTMLInputElement) {
      nodeSymbolsInput.value = Array.isArray(node.symbols) ? node.symbols.join(", ") : "";
    }
    if (nodeTagsInput instanceof HTMLInputElement) {
      nodeTagsInput.value = Array.isArray(node.tags) ? node.tags.join(", ") : "";
    }

    const isRoot = node.id === document.root_id;
    addSiblingButton.disabled = isRoot;
    removeNodeButton.disabled = isRoot;
    moveUpButton.disabled = isRoot;
    moveDownButton.disabled = isRoot;
    toggleCollapseButton.textContent = node.collapsed ? "展开" : "折叠";

    renderRelationComposer();
    renderRelationList();
    renderReferenceList();
    renderBaselineBox();
  }

  function renderShell() {
    renderTemplateButtons();
    renderDocumentList();
    renderHeader();
    renderStats();
    renderCanvasMeta();
    renderMap();
    renderInspector();
  }

  function addRelation() {
    const document = activeDocument();
    const node = selectedNode(document);
    if (!document || !node || !(relationTargetSelect instanceof HTMLSelectElement) || !(relationLabelInput instanceof HTMLInputElement)) {
      return;
    }
    const targetId = relationTargetSelect.value;
    const label = sanitizeText(relationLabelInput.value);
    const tone = relationToneSelect instanceof HTMLSelectElement ? relationToneSelect.value : "support";
    if (!targetId || !label) {
      showToast("error", "请先选目标节点并填写关系标签。");
      return;
    }
    const exists = document.relationships.some(function (relationship) {
      return relationship.from_node_id === node.id && relationship.to_node_id === targetId && relationship.label === label;
    });
    if (exists) {
      showToast("error", "这条关系线已经存在。");
      return;
    }
    document.relationships.push({
      id: "rel-" + Math.random().toString(36).slice(2, 10),
      from_node_id: node.id,
      to_node_id: targetId,
      label: label,
      tone: tone,
    });
    document.updated_at = nowIso();
    relationLabelInput.value = "";
    markDirty();
    renderShell();
  }

  function bindFieldEvents() {
    if (refreshButton instanceof HTMLButtonElement) {
      refreshButton.addEventListener("click", function () {
        loadBootstrap(state.activeDocument ? state.activeDocument.id : requestedDocId).catch(function (error) {
          showToast("error", error instanceof Error ? error.message : "刷新失败。");
        });
      });
    }

    if (documentTitleInput instanceof HTMLInputElement) {
      documentTitleInput.addEventListener("change", function () {
        updateDocumentField("title", sanitizeText(documentTitleInput.value) || "新导图");
      });
    }
    if (layoutSelect instanceof HTMLSelectElement) {
      layoutSelect.addEventListener("change", function () {
        updateDocumentField("layout_key", layoutSelect.value);
      });
    }
    if (themeSelect instanceof HTMLSelectElement) {
      themeSelect.addEventListener("change", function () {
        updateDocumentField("theme_key", themeSelect.value);
      });
    }
    if (surfaceSelect instanceof HTMLSelectElement) {
      surfaceSelect.addEventListener("change", function () {
        updateDocumentField("surface_key", surfaceSelect.value);
      });
    }
    if (densitySelect instanceof HTMLSelectElement) {
      densitySelect.addEventListener("change", function () {
        updateDocumentField("density_key", densitySelect.value);
      });
    }

    if (duplicateButton instanceof HTMLButtonElement) {
      duplicateButton.addEventListener("click", function () {
        duplicateDocument().catch(function (error) {
          showToast("error", error instanceof Error ? error.message : "复制失败。");
        });
      });
    }
    if (deleteButton instanceof HTMLButtonElement) {
      deleteButton.addEventListener("click", function () {
        deleteDocument().catch(function (error) {
          showToast("error", error instanceof Error ? error.message : "删除失败。");
        });
      });
    }
    if (exportButton instanceof HTMLButtonElement) {
      exportButton.addEventListener("click", function () {
        const document = activeDocument();
        if (!document) {
          return;
        }
        window.location.href = urlFor(exportUrlTemplate, document.id);
      });
    }
    if (baselineButton instanceof HTMLButtonElement) {
      baselineButton.addEventListener("click", recordBaselineSnapshot);
    }

    if (addChildButton instanceof HTMLButtonElement) {
      addChildButton.addEventListener("click", addChildNode);
    }
    if (addSiblingButton instanceof HTMLButtonElement) {
      addSiblingButton.addEventListener("click", addSiblingNode);
    }
    if (moveUpButton instanceof HTMLButtonElement) {
      moveUpButton.addEventListener("click", function () {
        moveNode("up");
      });
    }
    if (moveDownButton instanceof HTMLButtonElement) {
      moveDownButton.addEventListener("click", function () {
        moveNode("down");
      });
    }
    if (toggleCollapseButton instanceof HTMLButtonElement) {
      toggleCollapseButton.addEventListener("click", toggleCollapse);
    }
    if (removeNodeButton instanceof HTMLButtonElement) {
      removeNodeButton.addEventListener("click", removeNode);
    }

    if (nodeLabelInput instanceof HTMLInputElement) {
      nodeLabelInput.addEventListener("change", function () {
        updateSelectedNode(function (node) {
          node.label = sanitizeText(nodeLabelInput.value) || "未命名节点";
        });
      });
    }
    if (nodeSummaryInput instanceof HTMLTextAreaElement) {
      nodeSummaryInput.addEventListener("change", function () {
        updateSelectedNode(function (node) {
          node.summary = sanitizeText(nodeSummaryInput.value);
        });
      });
    }
    if (nodeNoteInput instanceof HTMLTextAreaElement) {
      nodeNoteInput.addEventListener("change", function () {
        updateSelectedNode(function (node) {
          node.note = nodeNoteInput.value.trim();
        });
      });
    }
    if (nodeKindSelect instanceof HTMLSelectElement) {
      nodeKindSelect.addEventListener("change", function () {
        updateSelectedNode(function (node) {
          node.kind = nodeKindSelect.value;
        });
      });
    }
    if (nodeVerifySelect instanceof HTMLSelectElement) {
      nodeVerifySelect.addEventListener("change", function () {
        updateSelectedNode(function (node) {
          node.verify_state = nodeVerifySelect.value;
        });
      });
    }
    if (nodeSideSelect instanceof HTMLSelectElement) {
      nodeSideSelect.addEventListener("change", function () {
        const document = activeDocument();
        const node = selectedNode(document);
        if (!document || !node || node.id === document.root_id || node.parent_id !== document.root_id) {
          return;
        }
        const sideValue = nodeSideSelect.value === "left" ? "left" : "right";
        const queue = [node.id];
        while (queue.length) {
          const currentId = queue.shift();
          document.nodes.forEach(function (item) {
            if (item.id === currentId) {
              item.side = sideValue;
              touchNode(item, { manual: true });
            }
            if (item.parent_id === currentId) {
              queue.push(item.id);
            }
          });
        }
        document.updated_at = nowIso();
        markDirty();
        renderShell();
      });
    }
    if (nodeTimeInput instanceof HTMLInputElement) {
      nodeTimeInput.addEventListener("change", function () {
        updateSelectedNode(function (node) {
          node.time_hint = sanitizeText(nodeTimeInput.value);
        });
      });
    }
    if (nodeSymbolsInput instanceof HTMLInputElement) {
      nodeSymbolsInput.addEventListener("change", function () {
        updateSelectedNode(function (node) {
          node.symbols = parseTokenList(nodeSymbolsInput.value);
        });
      });
    }
    if (nodeTagsInput instanceof HTMLInputElement) {
      nodeTagsInput.addEventListener("change", function () {
        updateSelectedNode(function (node) {
          node.tags = parseTokenList(nodeTagsInput.value);
        });
      });
    }

    if (addRelationButton instanceof HTMLButtonElement) {
      addRelationButton.addEventListener("click", addRelation);
    }

    if (toggleRelationsButton instanceof HTMLButtonElement) {
      toggleRelationsButton.addEventListener("click", function () {
        state.showRelations = !state.showRelations;
        renderCanvasMeta();
        scheduleConnectorRender();
      });
    }
    if (recenterButton instanceof HTMLButtonElement) {
      recenterButton.addEventListener("click", recenterViewport);
    }
    if (zoomOutButton instanceof HTMLButtonElement) {
      zoomOutButton.addEventListener("click", function () {
        state.scale = Math.max(0.7, state.scale - 0.1);
        applyScale();
        scheduleConnectorRender();
      });
    }
    if (zoomResetButton instanceof HTMLButtonElement) {
      zoomResetButton.addEventListener("click", function () {
        state.scale = 1;
        applyScale();
        scheduleConnectorRender();
      });
    }
    if (zoomInButton instanceof HTMLButtonElement) {
      zoomInButton.addEventListener("click", function () {
        state.scale = Math.min(1.5, state.scale + 0.1);
        applyScale();
        scheduleConnectorRender();
      });
    }

    window.addEventListener("resize", scheduleConnectorRender);
    window.addEventListener("beforeunload", function (event) {
      if (!state.dirty) {
        return;
      }
      event.preventDefault();
      event.returnValue = "";
    });
  }

  bindFieldEvents();
  loadBootstrap(requestedDocId).then(function () {
    recenterViewport();
  }).catch(function (error) {
    showToast("error", error instanceof Error ? error.message : "初始化失败。");
  });
})();
