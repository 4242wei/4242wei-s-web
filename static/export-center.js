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

  function activeDateScope() {
    const checked = exportDateModeRadios.find((radio) => radio.checked);
    return checked ? checked.value : "recent";
  }

  function syncExportControls() {
    const scope = exportScopeSelect ? exportScopeSelect.value : "single_stock";
    const dateScope = activeDateScope();
    const contentMode = exportContentMode ? exportContentMode.value : "summary_plus_raw";
    const hasFiles = exportTypeCheckboxes.some((checkbox) => checkbox.dataset.aiExportType === "files" && checkbox.checked);
    const hasTranscripts = exportTypeCheckboxes.some((checkbox) => checkbox.dataset.aiExportType === "transcripts" && checkbox.checked);
    const hasAnyTypes = exportTypeCheckboxes.some((checkbox) => checkbox.checked);

    if (exportSymbolField instanceof HTMLElement) {
      exportSymbolField.classList.toggle("is-disabled", scope !== "single_stock");
    }
    if (exportSymbolSelect instanceof HTMLSelectElement) {
      exportSymbolSelect.disabled = scope !== "single_stock";
    }

    if (exportDaysInput instanceof HTMLInputElement) {
      const disableDays = dateScope !== "recent";
      exportDaysInput.disabled = disableDays;
      exportDaysField?.classList.toggle("is-disabled", disableDays);
      if (exportDaysField instanceof HTMLElement) {
        exportDaysField.hidden = disableDays;
      }
    }

    [exportStartDateInput, exportEndDateInput].forEach(function (input) {
      if (!(input instanceof HTMLInputElement)) {
        return;
      }
      const disableDates = dateScope !== "range";
      input.disabled = disableDates;
      input.closest(".form-field")?.classList.toggle("is-disabled", disableDates);
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

  syncExportControls();
})();
