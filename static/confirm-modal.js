(function () {
  const overlay = document.querySelector("[data-confirm-overlay]");
  const messageNode = document.querySelector("[data-confirm-message]");
  const acceptButton = document.querySelector("[data-confirm-accept]");

  if (!overlay || !messageNode || !acceptButton) {
    return;
  }

  let activeForm = null;

  function closeOverlay() {
    overlay.hidden = true;
    overlay.classList.remove("is-open");
    document.body.style.overflow = "";
    activeForm = null;
  }

  function openOverlay(message, form) {
    activeForm = form;
    messageNode.textContent = message || "Are you sure you want to delete this item?";
    overlay.hidden = false;
    overlay.classList.add("is-open");
    document.body.style.overflow = "hidden";
  }

  document.addEventListener(
    "submit",
    function (event) {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) {
        return;
      }

      if (!form.matches("form[data-confirm-delete]")) {
        return;
      }

      if (form.dataset.confirmBypass === "true") {
        form.dataset.confirmBypass = "";
        return;
      }

      event.preventDefault();
      openOverlay(form.getAttribute("data-confirm-message"), form);
    },
    true
  );

  acceptButton.addEventListener("click", function () {
    if (!activeForm) {
      closeOverlay();
      return;
    }

    const confirmedForm = activeForm;
    confirmedForm.dataset.confirmBypass = "true";
    closeOverlay();
    window.requestAnimationFrame(function () {
      confirmedForm.requestSubmit();
    });
  });

  overlay.addEventListener("click", function (event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }

    if (target.closest("[data-confirm-close]")) {
      closeOverlay();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !overlay.hidden) {
      closeOverlay();
    }
  });
})();
