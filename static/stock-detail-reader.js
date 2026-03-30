(function () {
  const overlay = document.querySelector("[data-reader-overlay]");
  const content = document.querySelector("[data-reader-content]");
  const scrollShell = overlay ? overlay.querySelector(".reader-dialog-content") : null;
  const CLOSE_TRANSITION_MS = 220;
  let closeTimer = null;

  if (!overlay || !content) {
    return;
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

  function openOverlay(html) {
    content.innerHTML = html;
    showOverlay();
    scrollReaderToTop();
    focusCloseButton();
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
      content.innerHTML = "";
      closeTimer = null;
    }, CLOSE_TRANSITION_MS);
  }

  async function openRemote(url) {
    content.innerHTML = '<div class="reader-loading">正在加载预览...</div>';
    showOverlay();
    scrollReaderToTop();

    const response = await fetch(url, {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });

    if (!response.ok) {
      throw new Error("加载预览失败");
    }

    content.innerHTML = await response.text();
    scrollReaderToTop();
    focusCloseButton();
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
    if (!(element instanceof HTMLElement)) {
      return;
    }

    let current = element.parentElement;
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

    if (kind === "note") {
      return `note-${itemId}`;
    }
    if (kind === "file") {
      return `file-${itemId}`;
    }
    if (kind === "transcript") {
      return `transcript-${itemId}`;
    }
    if (kind === "earnings_call") {
      return `earnings-call-${itemId}`;
    }
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

    if (!changed) {
      return;
    }

    const nextUrl = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState({}, "", nextUrl);
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
      } else if (kind === "transcript" || kind === "earnings_call") {
        const template = document.getElementById(
          kind === "earnings_call"
            ? `stock-earnings-call-reader-${itemId}`
            : `stock-transcript-reader-${itemId}`
        );
        if (template instanceof HTMLTemplateElement) {
          openOverlay(template.innerHTML);
        }
      } else if (kind === "file") {
        const link = resolvedTarget.querySelector("[data-reader-url]");
        if (link instanceof HTMLAnchorElement) {
          openRemote(link.href).catch(function () {
            content.innerHTML = '<div class="reader-loading">当前无法加载这个预览，请稍后再试。</div>';
            focusCloseButton();
          });
        }
      }

      cleanAutoOpenParams();
    };

    window.requestAnimationFrame(applyOpen);
    window.setTimeout(applyOpen, 120);
  }

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
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
    if (remoteTrigger instanceof HTMLAnchorElement) {
      event.preventDefault();
      openRemote(remoteTrigger.href).catch(function () {
        content.innerHTML = '<div class="reader-loading">当前无法加载这个预览，请稍后再试。</div>';
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
    if (target instanceof HTMLElement && target.hasAttribute("data-reader-close")) {
      closeOverlay();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !overlay.hidden) {
      closeOverlay();
    }
  });

  autoOpenFromLocation();
})();
