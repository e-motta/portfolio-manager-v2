(function () {
  const modal = document.getElementById("confirm-modal");
  if (!modal) {
    return;
  }

  const messageEl = document.getElementById("confirm-modal-message");
  const cancelButton = modal.querySelector("[data-confirm-cancel]");
  const confirmButton = modal.querySelector("[data-confirm-ok]");
  const dismissTargets = modal.querySelectorAll("[data-confirm-dismiss]");

  let pendingResolve = null;

  function closeModal(confirmed) {
    if (!pendingResolve) {
      return;
    }
    modal.classList.remove("is-open");
    modal.setAttribute("hidden", "");
    document.body.classList.remove("confirm-modal-open");
    const resolve = pendingResolve;
    pendingResolve = null;
    resolve(confirmed);
  }

  function openModal(message) {
    if (pendingResolve) {
      return Promise.resolve(false);
    }

    messageEl.textContent = message;
    modal.removeAttribute("hidden");
    document.body.classList.add("confirm-modal-open");
    requestAnimationFrame(() => {
      modal.classList.add("is-open");
      cancelButton.focus();
    });

    return new Promise((resolve) => {
      pendingResolve = resolve;
    });
  }

  cancelButton.addEventListener("click", () => closeModal(false));
  confirmButton.addEventListener("click", () => closeModal(true));
  dismissTargets.forEach((el) => {
    el.addEventListener("click", () => closeModal(false));
  });

  document.addEventListener("keydown", (event) => {
    if (!pendingResolve) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal(false);
    }
  });

  document.addEventListener("htmx:confirm", (event) => {
    const question = event.detail.question;
    if (!question) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    openModal(question).then((confirmed) => {
      if (confirmed) {
        event.detail.issueRequest(true);
      }
    });
  });
})();
