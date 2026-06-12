function openCsvFilePicker(onSelect) {
  const picker = document.createElement("input");
  picker.type = "file";
  picker.accept = ".csv,text/csv";
  picker.addEventListener("change", () => {
    const file = picker.files?.[0];
    picker.remove();
    if (file) {
      onSelect(file);
    }
  });
  picker.addEventListener("cancel", () => {
    picker.remove();
  });
  document.body.appendChild(picker);
  picker.click();
}

function setImportIndicator(active) {
  const indicator = document.getElementById("global-indicator");
  if (!indicator) {
    return;
  }
  indicator.classList.toggle("htmx-request", active);
}

function getImportModal() {
  const modal = document.getElementById("import-modal");
  if (modal && modal.parentElement !== document.body) {
    document.body.appendChild(modal);
  }
  return modal;
}

function getImportModalBody() {
  return document.getElementById("import-modal-body");
}

function openImportModal() {
  const modal = getImportModal();
  if (!modal) {
    return;
  }
  modal.removeAttribute("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("import-modal-open");
  requestAnimationFrame(() => {
    modal.classList.add("is-open");
    const focusTarget = modal.querySelector("[data-import-select-all], [data-import-modal-cancel]");
    focusTarget?.focus();
  });
}

function closeImportModal() {
  const modal = getImportModal();
  const body = getImportModalBody();
  if (!modal) {
    return;
  }
  modal.classList.remove("is-open");
  document.body.classList.remove("import-modal-open");
  modal.setAttribute("hidden", "");
  modal.setAttribute("aria-hidden", "true");
  if (body) {
    body.replaceChildren();
  }
}

function bindImportModalDismiss() {
  const modal = getImportModal();
  if (!modal || modal.dataset.importBound === "1") {
    return;
  }
  modal.dataset.importBound = "1";

  modal.querySelectorAll("[data-import-modal-dismiss]").forEach((element) => {
    element.addEventListener("click", closeImportModal);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || modal.hasAttribute("hidden")) {
      return;
    }
    event.preventDefault();
    closeImportModal();
  });
}

function showImportModalError(message) {
  const body = getImportModalBody();
  if (!body) {
    return;
  }
  const error = document.createElement("p");
  error.className = "import-modal-error";
  error.setAttribute("role", "alert");
  error.textContent = message;

  const footer = document.createElement("div");
  footer.className = "import-modal__footer";
  const actions = document.createElement("div");
  actions.className = "import-modal__footer-actions";
  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "btn btn-secondary";
  closeButton.dataset.importModalCancel = "";
  closeButton.textContent = "Close";
  closeButton.addEventListener("click", closeImportModal);
  actions.appendChild(closeButton);
  footer.appendChild(actions);

  body.replaceChildren(error, footer);
  openImportModal();
}

async function uploadStatementPreview(form, file, url) {
  const body = getImportModalBody();
  if (!url || !body || !file) {
    return;
  }

  if (typeof closeAllFormModals === "function") {
    closeAllFormModals();
  }

  const formData = new FormData();
  formData.append("statement", file, file.name);

  setImportIndicator(true);
  try {
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      let message = "Could not upload statement.";
      try {
        const payload = await response.json();
        if (payload.detail) {
          message = payload.detail;
        }
      } catch {
        // keep default message
      }
      showImportModalError(message);
      return;
    }
    body.innerHTML = await response.text();
    if (typeof htmx !== "undefined") {
      htmx.process(body);
    }
    initImportPreview(body);
    openImportModal();
  } finally {
    setImportIndicator(false);
  }
}

function initImportDropzoneForm(form) {
  if (!form || form.dataset.importBound === "1") {
    return;
  }
  form.dataset.importBound = "1";

  const dropzone = form.querySelector("[data-import-dropzone]");
  const actions = form.querySelector("[data-import-actions]");
  const browse = form.querySelector("[data-import-browse]");
  const fileLabel = form.querySelector("[data-import-filename]");
  let selectedFile = null;

  if (!dropzone) {
    return;
  }

  const setFile = (file) => {
    if (!file) {
      return;
    }
    selectedFile = file;
    dropzone.classList.add("has-file");
    if (fileLabel) {
      fileLabel.textContent = file.name;
      fileLabel.hidden = false;
    }
    if (actions) {
      actions.hidden = false;
    }
  };

  const clearFile = () => {
    selectedFile = null;
    dropzone.classList.remove("has-file", "is-dragover");
    if (fileLabel) {
      fileLabel.textContent = "";
      fileLabel.hidden = true;
    }
    if (actions) {
      actions.hidden = true;
    }
  };

  form.querySelectorAll("[data-import-preview]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      if (!selectedFile) {
        return;
      }
      uploadStatementPreview(form, selectedFile, button.dataset.importUrl);
    });
  });

  browse?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openCsvFilePicker(setFile);
  });

  dropzone.addEventListener("click", (event) => {
    if (event.target.closest("[data-import-browse]")) {
      return;
    }
    openCsvFilePicker(setFile);
  });

  ["dragenter", "dragover"].forEach((type) => {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
    });
  });

  ["dragleave", "drop"].forEach((type) => {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragover");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      setFile(file);
    }
  });

  form.querySelector("[data-import-clear]")?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    clearFile();
  });
}

function initImportDropzone(root) {
  root.querySelectorAll("[data-import-upload-form]").forEach((form) => {
    initImportDropzoneForm(form);
  });
}

function getImportItemName(form) {
  return form.dataset.importItemName || "lots";
}

function updateImportSelection(form) {
  const itemName = getImportItemName(form);
  const boxes = [...form.querySelectorAll(`input[name="${itemName}"]:not(:disabled)`)];
  const checked = boxes.filter((box) => box.checked);
  const submit = form.querySelector("[data-import-confirm]");
  const count = form.querySelector("[data-import-selected-count]");
  const selectAll = form.querySelector("[data-import-select-all]");

  if (count) {
    count.textContent = String(checked.length);
  }
  if (submit) {
    submit.disabled = checked.length === 0;
  }
  if (selectAll && boxes.length > 0) {
    selectAll.indeterminate = checked.length > 0 && checked.length < boxes.length;
    selectAll.checked = checked.length === boxes.length;
  }
}

function initImportPreview(root) {
  const form = root.querySelector("[data-import-preview-form]");
  if (!form || form.dataset.importBound === "1") {
    root.querySelectorAll("[data-import-modal-cancel]").forEach((button) => {
      button.addEventListener("click", closeImportModal);
    });
    return;
  }
  form.dataset.importBound = "1";

  root.querySelectorAll("[data-import-modal-cancel]").forEach((button) => {
    button.addEventListener("click", closeImportModal);
  });

  const selectAll = form.querySelector("[data-import-select-all]");
  const itemName = getImportItemName(form);
  const boxes = () => [...form.querySelectorAll(`input[name="${itemName}"]:not(:disabled)`)];

  selectAll?.addEventListener("change", () => {
    boxes().forEach((box) => {
      box.checked = selectAll.checked;
    });
    updateImportSelection(form);
  });

  form.querySelectorAll("[data-import-row]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("input, button, a, label")) {
        return;
      }
      const box = row.querySelector(`input[name="${itemName}"]:not(:disabled)`);
      if (!box) {
        return;
      }
      box.checked = !box.checked;
      updateImportSelection(form);
    });
  });

  boxes().forEach((box) => {
    box.addEventListener("change", () => updateImportSelection(form));
  });

  updateImportSelection(form);
}

document.addEventListener("DOMContentLoaded", () => {
  bindImportModalDismiss();
  initImportDropzone(document);
});
