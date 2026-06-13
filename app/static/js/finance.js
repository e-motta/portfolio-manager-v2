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
}

document.addEventListener("DOMContentLoaded", bindFinancePage);
document.body.addEventListener("htmx:afterSwap", bindFinancePage);
