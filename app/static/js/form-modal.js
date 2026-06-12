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
  document.querySelectorAll("[data-form-modal-open]").forEach((trigger) => {
    if (trigger.dataset.formModalBound === "1") {
      return;
    }
    trigger.dataset.formModalBound = "1";
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      openFormModal(trigger.dataset.formModalOpen);
    });
  });

  document.querySelectorAll(".form-modal").forEach((modal) => {
    if (modal.dataset.formModalBound === "1") {
      return;
    }
    modal.dataset.formModalBound = "1";

    modal.querySelectorAll("[data-form-modal-dismiss]").forEach((element) => {
      element.addEventListener("click", () => closeFormModal(modal));
    });
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
