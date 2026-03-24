(function () {
  function revealInScrollContainer(target, container, padding) {
    if (!(target instanceof HTMLElement) || !(container instanceof HTMLElement)) {
      return;
    }

    const safePadding = typeof padding === "number" ? padding : 16;
    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const topGap = targetRect.top - containerRect.top - safePadding;
    const bottomGap = targetRect.bottom - containerRect.bottom + safePadding;

    if (topGap < 0) {
      container.scrollBy({ top: topGap, behavior: "smooth" });
    } else if (bottomGap > 0) {
      container.scrollBy({ top: bottomGap, behavior: "smooth" });
    }
  }

  function syncExpandedDirectoryBlock(details) {
    if (!(details instanceof HTMLDetailsElement) || !details.open) {
      return;
    }

    const container = details.closest(".experts-directory-sections");
    if (!(container instanceof HTMLElement)) {
      return;
    }

    window.requestAnimationFrame(function () {
      if (details.classList.contains("experts-directory-supergroup")) {
        const openGroup = details.querySelector(".experts-directory-group[open]");
        const firstGroup = details.querySelector(".experts-directory-group");
        if (!openGroup && firstGroup instanceof HTMLDetailsElement) {
          firstGroup.open = true;
          revealInScrollContainer(firstGroup, container, 18);
          return;
        }
      }

      const summary = details.querySelector("summary");
      const body = summary instanceof HTMLElement ? summary.nextElementSibling : null;
      const target = body instanceof HTMLElement ? body : details;
      revealInScrollContainer(target, container, 18);
    });
  }

  function setupExpertsDirectory() {
    const sections = document.querySelector(".experts-directory-sections");
    if (!(sections instanceof HTMLElement)) {
      return;
    }

    const detailsBlocks = sections.querySelectorAll("details[data-preserve-open-state]");
    detailsBlocks.forEach(function (details) {
      details.addEventListener("toggle", function () {
        syncExpandedDirectoryBlock(details);
      });
    });

    const selectedItem = sections.querySelector(".experts-directory-item.is-selected");
    if (selectedItem instanceof HTMLElement) {
      window.requestAnimationFrame(function () {
        revealInScrollContainer(selectedItem, sections, 20);
      });
    }
  }

  function setupExpertsResourceModal() {
    const overlay = document.querySelector("[data-experts-resource-modal]");
    const openButtons = document.querySelectorAll("[data-experts-resource-modal-open]");
    const CLOSE_TRANSITION_MS = 220;
    let closeTimer = null;

    if (!overlay || !openButtons.length) {
      return;
    }

    function lockBody() {
      document.body.style.overflow = "hidden";
    }

    function unlockBody() {
      document.body.style.overflow = "";
    }

    function focusCloseButton() {
      const closeButton = overlay.querySelector("[data-experts-resource-modal-close]");
      if (closeButton instanceof HTMLElement) {
        window.requestAnimationFrame(function () {
          closeButton.focus({ preventScroll: true });
        });
      }
    }

    function openOverlay() {
      if (closeTimer) {
        window.clearTimeout(closeTimer);
        closeTimer = null;
      }
      overlay.hidden = false;
      overlay.classList.remove("is-closing");
      lockBody();
      window.requestAnimationFrame(function () {
        overlay.classList.add("is-open");
        focusCloseButton();
      });
    }

    function closeOverlay() {
      if (overlay.hidden) {
        return;
      }
      overlay.classList.remove("is-open");
      overlay.classList.add("is-closing");
      unlockBody();
      if (closeTimer) {
        window.clearTimeout(closeTimer);
      }
      closeTimer = window.setTimeout(function () {
        overlay.hidden = true;
        overlay.classList.remove("is-closing");
        closeTimer = null;
      }, CLOSE_TRANSITION_MS);
    }

    openButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        openOverlay();
      });
    });

    overlay.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (target.closest("[data-experts-resource-modal-close]")) {
        closeOverlay();
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !overlay.hidden) {
        closeOverlay();
      }
    });
  }

  setupExpertsDirectory();
  setupExpertsResourceModal();
})();
