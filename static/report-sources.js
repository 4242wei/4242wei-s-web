(function () {
  function bindReportSourceToggles() {
    document.addEventListener("click", function (event) {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }

      const closeButton = target.closest("[data-report-source-close]");
      if (!(closeButton instanceof HTMLElement)) {
        return;
      }

      const disclosure = closeButton.closest(".report-source-disclosure");
      if (!(disclosure instanceof HTMLDetailsElement)) {
        return;
      }

      disclosure.open = false;
    });
  }

  window.addEventListener("DOMContentLoaded", bindReportSourceToggles);
})();
