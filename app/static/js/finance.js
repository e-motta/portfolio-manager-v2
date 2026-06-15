function subcategorySlug(select) {
  return select?.selectedOptions[0]?.dataset.slug || "none";
}

function categorySlug(select) {
  return select?.selectedOptions[0]?.dataset.slug || "other";
}

function updateCategoryPicker(picker) {
  const select = picker?.querySelector("[data-of-category-select]");
  if (!select) {
    return;
  }

  const slug = categorySlug(select);
  picker.className = `of-category-picker of-category-picker--${slug}`;
  picker.dataset.category = select.value;
  select.setAttribute("aria-label", select.value);
}

function updateSubcategoryPicker(picker) {
  const select = picker?.querySelector("[data-of-subcategory-select]");
  if (!select) {
    return;
  }

  const slug = subcategorySlug(select);
  const isToolbar = picker.classList.contains("of-category-picker--toolbar");
  picker.className = isToolbar
    ? `of-category-picker of-category-picker--toolbar of-category-picker--${slug}`
    : `of-category-picker of-category-picker--${slug}`;
  picker.dataset.subcategory = select.value;
  select.setAttribute("aria-label", select.value || "No subcategory");
}

function bindFinanceSubcategoryPickers(scope) {
  scope.querySelectorAll("[data-of-subcategory-picker]").forEach((picker) => {
    if (picker.dataset.financeSubcategoryBound === "1") {
      return;
    }
    picker.dataset.financeSubcategoryBound = "1";
    const select = picker.querySelector("[data-of-subcategory-select]");
    select?.addEventListener("change", () => updateSubcategoryPicker(picker));
    updateSubcategoryPicker(picker);
  });
}

function bindFinanceCategoryPickers(scope) {
  scope.querySelectorAll("[data-of-category-picker]").forEach((picker) => {
    if (picker.dataset.financeCategoryBound === "1") {
      return;
    }
    picker.dataset.financeCategoryBound = "1";
    const select = picker.querySelector("[data-of-category-select]");
    select?.addEventListener("change", () => {
      updateCategoryPicker(picker);
      const row = picker.closest(".editable-row");
      if (row) {
        syncExpenseRowSubcategory(row);
      }
    });
    updateCategoryPicker(picker);
  });
}

function syncExpenseRowSubcategory(row) {
  const form = row?.querySelector(".row-form-table");
  if (!form) {
    return;
  }

  const categorySelect = form.querySelector("[data-of-category-select]");
  const subcategoryCell = form.querySelector("[data-finance-bills-subcategory]");
  const subcategorySelect = subcategoryCell?.querySelector(
    '[name="subcategory"], [data-of-subcategory-select]'
  );
  if (!categorySelect || !subcategoryCell || !subcategorySelect) {
    return;
  }

  const isBills = categorySelect.value === "Bills";
  subcategoryCell.classList.toggle("col-subcategory--inactive", !isBills);
  subcategorySelect.disabled = !isBills;
  if (!isBills) {
    subcategorySelect.value = "";
    const picker = subcategorySelect.closest("[data-of-subcategory-picker]");
    if (picker) {
      updateSubcategoryPicker(picker);
    }
  }
}

function syncBillsSubcategoryField(container) {
  const categorySelect = container.querySelector(
    '#add-expense-category, [data-of-category-select], [name="category"]'
  );
  const subcategoryField = container.querySelector("[data-finance-bills-subcategory]");
  const select = subcategoryField?.querySelector(
    '[name="subcategory"], [data-of-subcategory-select]'
  );
  if (!categorySelect || !subcategoryField || !select) {
    return;
  }

  const isBills = categorySelect.value === "Bills";
  subcategoryField.hidden = !isBills;
  select.disabled = !isBills;
  if (!isBills) {
    select.value = "";
    const picker = select.closest("[data-of-subcategory-picker]");
    if (picker) {
      updateSubcategoryPicker(picker);
    }
  }
}

function queryFinanceContainers(scope) {
  const root = scope && scope.querySelectorAll ? scope : document;
  const nodes = [...root.querySelectorAll("#add-expense-modal, .finance-quick-form, .editable-row")];
  if (root !== document && root.matches?.("#add-expense-modal, .finance-quick-form, .editable-row")) {
    nodes.unshift(root);
  }
  return nodes;
}

function bindFinanceBillsSubcategory(scope = document) {
  queryFinanceContainers(scope).forEach((container) => {
    if (container.dataset.financeBillsSubcategoryBound === "1") {
      return;
    }
    container.dataset.financeBillsSubcategoryBound = "1";
    const categorySelect = container.querySelector(
      '#add-expense-category, [data-of-category-select], [name="category"]'
    );
    if (!categorySelect) {
      return;
    }
    categorySelect.addEventListener("change", () => {
      if (container.classList.contains("editable-row")) {
        syncExpenseRowSubcategory(container);
        return;
      }
      syncBillsSubcategoryField(container);
    });
    if (container.classList.contains("editable-row")) {
      syncExpenseRowSubcategory(container);
    } else {
      syncBillsSubcategoryField(container);
    }
  });
}

function bindFinanceForms() {
  document.querySelectorAll(".year-selector__control").forEach((select) => {
    if (select.dataset.financeBound === "1") {
      return;
    }
    select.dataset.financeBound = "1";
    select.addEventListener("change", () => select.form?.requestSubmit());
  });
}

function syncInstallmentsPanel(container) {
  const toggle = container.querySelector("[data-finance-installments-toggle]");
  const panel = container.querySelector("[data-finance-installments-panel]");
  const input = panel?.querySelector('input[name="installments"]');
  if (!toggle || !panel || !input) {
    return;
  }

  const enabled = toggle.checked;
  panel.hidden = !enabled;
  input.disabled = !enabled;
  input.required = enabled;
}

function bindFinanceInstallments() {
  document.querySelectorAll("[data-finance-installments]").forEach((container) => {
    if (container.dataset.financeInstallmentsBound === "1") {
      return;
    }
    container.dataset.financeInstallmentsBound = "1";
    const toggle = container.querySelector("[data-finance-installments-toggle]");
    if (!toggle) {
      return;
    }
    toggle.addEventListener("change", () => syncInstallmentsPanel(container));
    syncInstallmentsPanel(container);
  });
}

function clearHtmxIndicator() {
  const indicator = document.getElementById("global-indicator");
  indicator?.classList.remove("htmx-request");
  document.body.classList.remove("htmx-request");
}

function bindFinanceHtmxRedirects() {
  if (document.body.dataset.financeHtmxRedirectBound === "1") {
    return;
  }
  document.body.dataset.financeHtmxRedirectBound = "1";

  document.body.addEventListener("htmx:responseError", clearHtmxIndicator);
  document.body.addEventListener("htmx:sendError", clearHtmxIndicator);
  document.body.addEventListener("htmx:timeout", clearHtmxIndicator);

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    const redirect = event.detail.xhr?.getResponseHeader("X-Finance-Redirect");
    if (!redirect) {
      return;
    }
    event.preventDefault();
    clearHtmxIndicator();
    document.querySelectorAll(".editable-row.is-editing").forEach((row) => {
      row.classList.remove("is-editing");
      row.querySelector("form")?.reset();
    });
    window.location.assign(redirect);
  });
}

function resetEditableRow(row) {
  if (!row) {
    return;
  }
  row.classList.remove("is-editing");
  row.querySelector("form")?.reset();
}

function bindFinancePage(scope = document) {
  bindFinanceForms();
  bindFinanceInstallments();
  bindFinanceCategoryPickers(scope);
  bindFinanceBillsSubcategory(scope);
  bindFinanceSubcategoryPickers(scope);
}

function handleFinanceHtmxSwap(event) {
  clearHtmxIndicator();
  const target = event.detail.target;
  if (!target) {
    bindFinancePage();
    return;
  }

  if (typeof htmx !== "undefined") {
    htmx.process(target);
  }

  if (target.matches?.(".editable-row")) {
    resetEditableRow(target);
  } else {
    target.querySelectorAll?.(".editable-row").forEach(resetEditableRow);
  }

  bindFinancePage(target);
}

document.addEventListener("DOMContentLoaded", () => {
  bindFinanceHtmxRedirects();
  bindFinancePage();
});
document.body.addEventListener("htmx:afterSwap", handleFinanceHtmxSwap);
