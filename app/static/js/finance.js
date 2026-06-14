function subcategorySlug(select) {
  return select?.selectedOptions[0]?.dataset.slug || "none";
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

function syncBillsSubcategoryField(container) {
  const categorySelect = container.querySelector(
    '#add-expense-category, [name="category"]'
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

function bindFinanceBillsSubcategory() {
  document.querySelectorAll("#add-expense-modal, .finance-quick-form").forEach((container) => {
    if (container.dataset.financeBillsSubcategoryBound === "1") {
      return;
    }
    container.dataset.financeBillsSubcategoryBound = "1";
    const categorySelect = container.querySelector(
      '#add-expense-category, [name="category"]'
    );
    if (!categorySelect) {
      return;
    }
    categorySelect.addEventListener("change", () => syncBillsSubcategoryField(container));
    syncBillsSubcategoryField(container);
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

function bindFinancePage() {
  bindFinanceForms();
  bindFinanceInstallments();
  bindFinanceBillsSubcategory();
  bindFinanceSubcategoryPickers(document);
}

document.addEventListener("DOMContentLoaded", bindFinancePage);
document.body.addEventListener("htmx:afterSwap", bindFinancePage);
