(function () {
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

  window.addEventListener("DOMContentLoaded", function () {
    const flashNodes = document.querySelectorAll("[data-flash-message]");
    if (!flashNodes.length) {
      return;
    }

    flashNodes.forEach(function (node) {
      const kind = node.getAttribute("data-flash-kind") || "";
      const body = node.querySelector(".flash-body");
      const closeButton = node.querySelector("[data-flash-close]");
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
    });
  });
})();
