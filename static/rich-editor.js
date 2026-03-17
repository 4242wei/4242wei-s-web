(function () {
  function isEditorSurface(node) {
    return node instanceof HTMLElement && node.matches("[data-editor-surface]");
  }

  function getEditorContainer(node) {
    return node instanceof HTMLElement ? node.closest("[data-rich-editor]") : null;
  }

  function getEditorSurface(editor) {
    const surface = editor?.querySelector("[data-editor-surface]");
    return surface instanceof HTMLElement ? surface : null;
  }

  function syncEditor(editor) {
    const surface = getEditorSurface(editor);
    const htmlField = editor?.querySelector("[data-editor-html]");
    const textField = editor?.querySelector("[data-editor-text]");

    if (!(surface instanceof HTMLElement) || !(htmlField instanceof HTMLTextAreaElement) || !(textField instanceof HTMLTextAreaElement)) {
      return;
    }

    const html = surface.innerHTML.trim();
    htmlField.value = html;
    textField.value = surface.innerText.trim();
  }

  function initializeEditor(editor) {
    const surface = getEditorSurface(editor);
    const htmlField = editor?.querySelector("[data-editor-html]");
    if (!(surface instanceof HTMLElement) || !(htmlField instanceof HTMLTextAreaElement)) {
      return;
    }

    if (!surface.innerHTML.trim() && htmlField.value.trim()) {
      surface.innerHTML = htmlField.value;
    }

    syncEditor(editor);
  }

  function saveSelection(editor) {
    const surface = getEditorSurface(editor);
    const selection = window.getSelection();
    if (!surface || !selection || selection.rangeCount === 0) {
      return;
    }

    const range = selection.getRangeAt(0);
    if (!surface.contains(range.commonAncestorContainer)) {
      return;
    }

    editor.dataset.savedSelection = "true";
    editor._savedRange = range.cloneRange();
  }

  function restoreSelection(editor) {
    const surface = getEditorSurface(editor);
    const selection = window.getSelection();
    const savedRange = editor?._savedRange;
    if (!surface || !selection) {
      return;
    }

    surface.focus();

    if (!savedRange) {
      return;
    }

    selection.removeAllRanges();
    selection.addRange(savedRange);
  }

  function getActiveRange(editor) {
    const surface = getEditorSurface(editor);
    const selection = window.getSelection();
    if (!surface || !selection) {
      return null;
    }

    restoreSelection(editor);

    if (selection.rangeCount > 0) {
      const range = selection.getRangeAt(0);
      if (surface.contains(range.commonAncestorContainer)) {
        return range;
      }
    }

    const range = document.createRange();
    range.selectNodeContents(surface);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
    return range;
  }

  function normalizeCommandValue(command, value) {
    if (command === "formatBlock" && value) {
      return value.startsWith("<") ? value : `<${value}>`;
    }
    return value;
  }

  function runCommand(editor, command, value) {
    restoreSelection(editor);
    document.execCommand("styleWithCSS", false, true);
    document.execCommand(command, false, normalizeCommandValue(command, value));
    saveSelection(editor);
    syncEditor(editor);
  }

  function normalizeFontSizeNodes(surface, size) {
    surface.querySelectorAll("font[size]").forEach(function (node) {
      const span = document.createElement("span");
      span.style.fontSize = size;
      span.innerHTML = node.innerHTML;
      node.replaceWith(span);
    });
  }

  function applyFontSize(editor, size) {
    const surface = getEditorSurface(editor);
    if (!surface || !size) {
      return;
    }

    restoreSelection(editor);
    document.execCommand("styleWithCSS", false, true);
    document.execCommand("fontSize", false, "7");
    normalizeFontSizeNodes(surface, size);
    saveSelection(editor);
    syncEditor(editor);
  }

  function insertHtmlAtSelection(editor, html) {
    const range = getActiveRange(editor);
    const surface = getEditorSurface(editor);
    const selection = window.getSelection();
    if (!range || !surface || !selection) {
      return;
    }

    range.deleteContents();
    const fragment = range.createContextualFragment(html);
    const lastNode = fragment.lastChild;
    range.insertNode(fragment);

    if (lastNode) {
      range.setStartAfter(lastNode);
      range.collapse(true);
      selection.removeAllRanges();
      selection.addRange(range);
    }

    saveSelection(editor);
    syncEditor(editor);
  }

  function readFileAsDataUrl(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function () {
        resolve(typeof reader.result === "string" ? reader.result : "");
      };
      reader.onerror = function () {
        reject(new Error("图片读取失败"));
      };
      reader.readAsDataURL(file);
    });
  }

  function loadImage(dataUrl) {
    return new Promise(function (resolve, reject) {
      const image = new Image();
      image.onload = function () {
        resolve(image);
      };
      image.onerror = function () {
        reject(new Error("图片加载失败"));
      };
      image.src = dataUrl;
    });
  }

  async function optimizeImageFile(file) {
    const originalDataUrl = await readFileAsDataUrl(file);
    const image = await loadImage(originalDataUrl);
    const maxEdge = 1600;
    const longestEdge = Math.max(image.naturalWidth || image.width, image.naturalHeight || image.height, 1);
    if (longestEdge <= maxEdge && file.size <= 1_500_000) {
      return originalDataUrl;
    }

    const scale = maxEdge / longestEdge;
    const width = Math.max(1, Math.round((image.naturalWidth || image.width) * scale));
    const height = Math.max(1, Math.round((image.naturalHeight || image.height) * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const context = canvas.getContext("2d");
    if (!context) {
      return originalDataUrl;
    }

    context.drawImage(image, 0, 0, width, height);
    const mimeType = file.type === "image/png" ? "image/png" : "image/jpeg";
    return canvas.toDataURL(mimeType, mimeType === "image/png" ? undefined : 0.86);
  }

  async function insertImageFile(editor, file) {
    if (!(file instanceof File) || !file.type.startsWith("image/")) {
      return;
    }

    const dataUrl = await optimizeImageFile(file);
    const safeAlt = (file.name || "插图")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
    insertHtmlAtSelection(editor, `<p><img src="${dataUrl}" alt="${safeAlt}"></p>`);
  }

  function bindSurface(surface, editor) {
    ["input", "blur", "keyup", "mouseup", "focus"].forEach(function (eventName) {
      surface.addEventListener(eventName, function () {
        saveSelection(editor);
        syncEditor(editor);
      });
    });

    surface.addEventListener("paste", function (event) {
      const clipboardItems = Array.from(event.clipboardData?.items || []);
      const imageFiles = clipboardItems
        .filter(function (item) {
          return item.type && item.type.startsWith("image/");
        })
        .map(function (item) {
          return item.getAsFile();
        })
        .filter(Boolean);

      if (!imageFiles.length) {
        return;
      }

      event.preventDefault();
      imageFiles.reduce(function (promise, file) {
        return promise.then(function () {
          return insertImageFile(editor, file);
        });
      }, Promise.resolve());
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    const editors = document.querySelectorAll("[data-rich-editor]");
    if (!editors.length) {
      return;
    }

    editors.forEach(function (editor) {
      const surface = getEditorSurface(editor);
      if (surface) {
        bindSurface(surface, editor);
      }

      initializeEditor(editor);

      const form = editor.closest("form");
      if (form instanceof HTMLFormElement) {
        form.addEventListener("submit", function () {
          syncEditor(editor);
        });
      }

      const buttonTools = editor.querySelectorAll("[data-editor-command], [data-editor-color-command]");
      buttonTools.forEach(function (button) {
        button.addEventListener("mousedown", function (event) {
          event.preventDefault();
        });
      });
    });

    document.addEventListener("selectionchange", function () {
      const active = document.activeElement;
      const editor = getEditorContainer(active);
      if (editor) {
        saveSelection(editor);
      }
    });

    document.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const commandButton = target.closest("[data-editor-command]");
      if (commandButton instanceof HTMLElement) {
        event.preventDefault();
        const editor = getEditorContainer(commandButton);
        const command = commandButton.getAttribute("data-editor-command");
        if (!editor || !command) {
          return;
        }
        runCommand(editor, command);
        return;
      }

      const colorButton = target.closest("[data-editor-color-command]");
      if (colorButton instanceof HTMLElement) {
        event.preventDefault();
        const editor = getEditorContainer(colorButton);
        const command = colorButton.getAttribute("data-editor-color-command");
        const value = colorButton.getAttribute("data-editor-color-value");
        if (!editor || !command || !value) {
          return;
        }
        runCommand(editor, command, value);
      }
    });

    document.addEventListener("change", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      if (target.matches("[data-editor-block]")) {
        const editor = getEditorContainer(target);
        if (!editor || !target.value) {
          return;
        }
        runCommand(editor, "formatBlock", target.value);
        target.value = "";
        return;
      }

      if (target.matches("[data-editor-font]")) {
        const editor = getEditorContainer(target);
        if (!editor || !target.value) {
          return;
        }
        runCommand(editor, "fontName", target.value);
        target.value = "";
        return;
      }

      if (target.matches("[data-editor-font-size]")) {
        const editor = getEditorContainer(target);
        if (!editor || !target.value) {
          return;
        }
        applyFontSize(editor, target.value);
        target.value = "";
        return;
      }

      if (target.matches("[data-editor-color]")) {
        const editor = getEditorContainer(target);
        const command = target.getAttribute("data-editor-color");
        if (!editor || !command) {
          return;
        }
        runCommand(editor, command, target.value);
        return;
      }

      if (target.matches("[data-editor-image-input]")) {
        const editor = getEditorContainer(target);
        const files = Array.from(target.files || []);
        if (!editor || !files.length) {
          return;
        }

        files.reduce(function (promise, file) {
          return promise.then(function () {
            return insertImageFile(editor, file);
          });
        }, Promise.resolve()).finally(function () {
          target.value = "";
        });
      }
    });
  });
})();
