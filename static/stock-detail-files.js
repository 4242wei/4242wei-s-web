(function () {
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

  function buildFileMarkup(file) {
    const item = document.createElement("li");
    item.className = "transcript-upload-file-item";

    const name = document.createElement("span");
    name.className = "transcript-upload-file-name";
    name.textContent = file.name || "Unnamed file";

    const meta = document.createElement("span");
    meta.className = "transcript-upload-file-meta";
    meta.textContent = formatFileSize(file.size);

    item.append(name, meta);
    return item;
  }

  function assignFiles(input, files) {
    const selectedFiles = Array.from(files || []).slice(0, 1);
    if (!selectedFiles.length) {
      return;
    }

    if (typeof DataTransfer === "function") {
      const dataTransfer = new DataTransfer();
      selectedFiles.forEach(function (file) {
        dataTransfer.items.add(file);
      });
      input.files = dataTransfer.files;
      return;
    }

    input.files = files;
  }

  function bindUploadRoot(root) {
    const input = root.querySelector("[data-stock-file-upload-input]");
    const trigger = root.querySelector("[data-stock-file-upload-trigger]");
    const summary = root.querySelector("[data-stock-file-upload-summary]");
    const filesNode = root.querySelector("[data-stock-file-upload-files]");

    if (
      !(input instanceof HTMLInputElement) ||
      !(trigger instanceof HTMLButtonElement) ||
      !(summary instanceof HTMLElement) ||
      !(filesNode instanceof HTMLElement)
    ) {
      return;
    }

    const syncSelection = function () {
      const files = Array.from(input.files || []).slice(0, 1);
      filesNode.innerHTML = "";

      if (!files.length) {
        summary.textContent = "No file selected";
        const placeholder = document.createElement("p");
        placeholder.className = "transcript-upload-placeholder";
        placeholder.textContent = "The selected file will appear here. You can also drag it into the area above.";
        filesNode.appendChild(placeholder);
        return;
      }

      const [file] = files;
      summary.textContent = file.name || "1 file selected";

      const list = document.createElement("ul");
      list.className = "transcript-upload-file-items";
      list.appendChild(buildFileMarkup(file));
      filesNode.appendChild(list);
    };

    const preventDefaults = function (event) {
      event.preventDefault();
      event.stopPropagation();
    };

    trigger.addEventListener("click", function () {
      input.click();
    });

    input.addEventListener("change", syncSelection);

    ["dragenter", "dragover"].forEach(function (eventName) {
      root.addEventListener(eventName, function (event) {
        preventDefaults(event);
        root.classList.add("is-dragover");
      });
    });

    ["dragleave", "dragend"].forEach(function (eventName) {
      root.addEventListener(eventName, function (event) {
        preventDefaults(event);
        if (event.target === root || !root.contains(event.relatedTarget)) {
          root.classList.remove("is-dragover");
        }
      });
    });

    root.addEventListener("drop", function (event) {
      preventDefaults(event);
      root.classList.remove("is-dragover");
      const droppedFiles = event.dataTransfer ? event.dataTransfer.files : null;
      if (!droppedFiles || !droppedFiles.length) {
        return;
      }
      assignFiles(input, droppedFiles);
      syncSelection();
    });

    syncSelection();
  }

  document.querySelectorAll("[data-stock-file-upload-root]").forEach(function (root) {
    if (root instanceof HTMLElement) {
      bindUploadRoot(root);
    }
  });
})();
