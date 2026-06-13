function clearEditError(container) {
  container?.querySelector(".edit-error")?.remove();
}

function showEditError(form, message) {
  const container = form.closest(".editable-cell, .editable-row");
  if (!container) {
    return;
  }
  container.classList.add("is-editing");
  clearEditError(container);
  const error = document.createElement("div");
  error.className = "edit-error";
  error.textContent = message;
  form.appendChild(error);
}

function syncFinanceSectionEditing(section) {
  if (!section?.classList.contains("finance-section--editable")) {
    return;
  }
  const hasEditingRow = Boolean(section.querySelector(".editable-row.is-editing"));
  section.classList.toggle("is-editing", hasEditingRow);
}

document.body.addEventListener("click", (event) => {
  const editSectionButton = event.target.closest(".btn-edit-section");
  if (editSectionButton) {
    const section = editSectionButton.closest(".finance-section--editable");
    if (!section) {
      return;
    }
    section.classList.add("is-editing");
    section.querySelectorAll(".editable-row").forEach((row) => {
      clearEditError(row);
      row.classList.add("is-editing");
    });
    const field = section.querySelector(".editable-row .edit-mode input, .editable-row .edit-mode select, .editable-row .edit-mode textarea");
    field?.focus();
    if (field?.select && field.type !== "date") {
      field.select();
    }
    return;
  }

  const cancelSectionButton = event.target.closest(".btn-cancel-section");
  if (cancelSectionButton) {
    const section = cancelSectionButton.closest(".finance-section--editable");
    if (!section) {
      return;
    }
    section.classList.remove("is-editing");
    section.querySelector(".finance-section-form")?.reset();
    section.querySelectorAll(".editable-row").forEach((row) => {
      clearEditError(row);
      row.classList.remove("is-editing");
    });
    return;
  }

  const editButton = event.target.closest(".btn-edit");
  if (editButton) {
    const container = editButton.closest(".editable-cell, .editable-row");
    if (!container) {
      return;
    }
    clearEditError(container);
    container.classList.add("is-editing");
    const field = container.querySelector(".edit-mode input, .edit-mode select, .edit-mode textarea");
    field?.focus();
    if (field?.select && field.type !== "date") {
      field.select();
    }
    return;
  }

  const clearTargetButton = event.target.closest(".btn-clear-target");
  if (clearTargetButton) {
    const row = clearTargetButton.closest(".editable-row");
    const input = row?.querySelector('input[name="target_pct"]');
    if (input) {
      input.value = "";
      input.focus();
    }
    return;
  }

  const cancelButton = event.target.closest(".btn-cancel-edit");
  if (cancelButton) {
    const container = cancelButton.closest(".editable-cell, .editable-row");
    if (!container) {
      return;
    }
    clearEditError(container);
    container.classList.remove("is-editing");
    container.querySelector("form")?.reset();
    syncFinanceSectionEditing(container.closest(".finance-section--editable"));
  }
});

document.body.addEventListener("htmx:responseError", (event) => {
  const form = event.detail.elt;
  if (!(form instanceof HTMLFormElement) || !form.matches("form[hx-post*='/portfolio/holdings/symbols/']")) {
    return;
  }
  let message = "Could not save target weight.";
  try {
    const payload = JSON.parse(event.detail.xhr.responseText);
    if (typeof payload.detail === "string") {
      message = payload.detail;
    } else if (Array.isArray(payload.detail)) {
      message = payload.detail.map((item) => item.msg).join(", ");
    }
  } catch (_) {
    // keep default message
  }
  showEditError(form, message);
});

document.body.addEventListener("htmx:afterSwap", () => {
  document.querySelectorAll(".editable-cell.is-editing, .editable-row.is-editing").forEach((el) => {
    el.classList.remove("is-editing");
  });
  document.querySelectorAll(".finance-section.is-editing").forEach((el) => {
    el.classList.remove("is-editing");
  });
});

document.body.addEventListener("targetTotalRefresh", (event) => {
  const pill = document.getElementById("target-weight-status");
  if (!pill || event.detail?.value === undefined) {
    return;
  }
  const total = parseFloat(event.detail.value);
  if (total === 0) {
    pill.textContent = "No target weights set";
    pill.classList.remove("ok");
    pill.classList.add("warn");
  } else if (event.detail.balanced) {
    pill.textContent = "Targets = 100%";
    pill.classList.remove("warn");
    pill.classList.add("ok");
  } else {
    pill.textContent = `Targets = ${event.detail.value}%`;
    pill.classList.remove("ok");
    pill.classList.add("warn");
  }
});
