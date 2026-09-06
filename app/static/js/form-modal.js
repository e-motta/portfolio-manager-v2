function getFormModal(id) {
  const modal = document.getElementById(id);
  if (modal && modal.parentElement !== document.body) {
    document.body.appendChild(modal);
  }
  return modal;
}

function openFormModal(id) {
  const modal = getFormModal(id);
  if (!modal) {
    return;
  }
  modal.removeAttribute("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("form-modal-open");
  requestAnimationFrame(() => {
    modal.classList.add("is-open");
    const focusTarget = modal.querySelector("input:not([type=hidden]), select, textarea, button");
    focusTarget?.focus();
  });
}

function closeFormModal(modal) {
  if (!modal) {
    return;
  }
  modal.classList.remove("is-open");
  modal.setAttribute("hidden", "");
  modal.setAttribute("aria-hidden", "true");
  if (!document.querySelector(".form-modal.is-open")) {
    document.body.classList.remove("form-modal-open");
  }
}

function closeAllFormModals() {
  document.querySelectorAll(".form-modal.is-open").forEach((modal) => {
    closeFormModal(modal);
  });
}

function bindFormModals() {
  if (document.body.dataset.formModalDelegated === "1") {
    return;
  }
  document.body.dataset.formModalDelegated = "1";

  document.body.addEventListener("click", (event) => {
    const openTrigger = event.target.closest("[data-form-modal-open]");
    if (openTrigger) {
      event.preventDefault();
      openFormModal(openTrigger.dataset.formModalOpen);
      return;
    }

    const dismissTrigger = event.target.closest("[data-form-modal-dismiss]");
    if (dismissTrigger) {
      const modal = dismissTrigger.closest(".form-modal");
      if (modal) {
        closeFormModal(modal);
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    const openModal = document.querySelector(".form-modal.is-open:not([hidden])");
    if (!openModal) {
      return;
    }
    event.preventDefault();
    closeFormModal(openModal);
  });
}

document.addEventListener("DOMContentLoaded", bindFormModals);
