(function () {
  function monthLabels(form) {
    return (form?.dataset.ofMonthLabels || "").split("|");
  }

  function ccExpensePeriod(year, month) {
    if (month === 1) {
      return { year: year - 1, month: 12 };
    }
    return { year, month: month - 1 };
  }

  function monthLabel(form, month) {
    return monthLabels(form)[month - 1] || String(month);
  }

  function updatePeriodPreview(form) {
    const preview = form.querySelector("[data-of-period-preview]");
    if (!preview) {
      return;
    }

    const year = Number(form.querySelector('[name="year"]')?.value);
    const month = Number(form.querySelector('[name="month"]:checked')?.value);
    if (!year || !month) {
      return;
    }

    const mode = preview.dataset.ofPeriodMode || "calendar";
    if (mode === "credit_card") {
      const cc = ccExpensePeriod(year, month);
      preview.textContent =
        `Statement ${monthLabel(form, month)} ${year} → expenses in ${monthLabel(form, cc.month)} ${cc.year}`;
      return;
    }

    preview.textContent = `${monthLabel(form, month)} ${year}`;
  }

  function bindMonthPills(scope) {
    scope.querySelectorAll(".open-finance-period .finance-months__pill input").forEach((input) => {
      input.addEventListener("change", () => {
        input.closest(".finance-months")?.querySelectorAll(".finance-months__pill").forEach((pill) => {
          pill.classList.toggle("is-active", pill.querySelector("input")?.checked);
        });
        const form = input.closest("form");
        if (form) {
          updatePeriodPreview(form);
        }
      });
    });
  }

  function bindPeriodForms(scope) {
    scope.querySelectorAll("[data-of-finance-form]").forEach((form) => {
      form.querySelector('[name="year"]')?.addEventListener("change", () => updatePeriodPreview(form));
      updatePeriodPreview(form);
    });
  }

  function bindDismissibleAlerts(scope) {
    scope.querySelectorAll("[data-of-alert-dismiss]").forEach((button) => {
      button.addEventListener("click", () => {
        button.closest(".open-finance-alert")?.remove();
      });
    });
  }

  function bindImportedToggle(scope) {
    scope.querySelectorAll("[data-of-toggle-imported]").forEach((toggle) => {
      const form = toggle.closest("[data-import-preview-form]");
      if (!form) {
        return;
      }

      const apply = () => {
        form.querySelectorAll(".import-row--existing").forEach((row) => {
          row.hidden = !toggle.checked;
        });
      };

      toggle.addEventListener("change", apply);
      apply();
    });
  }

  function categorySlug(select) {
    return select.selectedOptions[0]?.dataset.slug || "other";
  }

  function updateCategoryPicker(picker) {
    const select = picker.querySelector("[data-of-category-select], [data-of-bulk-category]");
    if (!select) {
      return;
    }

    const slug = categorySlug(select);
    const isToolbar = picker.hasAttribute("data-of-bulk-picker");
    picker.className = isToolbar
      ? `of-category-picker of-category-picker--toolbar of-category-picker--${slug}`
      : `of-category-picker of-category-picker--${slug}`;
    picker.dataset.category = select.value;
    select.setAttribute("aria-label", select.value);

    if (!select.matches("[data-of-category-select]")) {
      return;
    }

    const row = picker.closest("[data-import-row]");
    if (!row) {
      return;
    }

    row.classList.toggle("import-row--needs-category", select.value === "Outros");
    const status = row.querySelector(".status-pill");
    if (
      status
      && !status.classList.contains("muted")
      && !status.classList.contains("status-pill--reversal")
    ) {
      if (select.value === "Outros") {
        status.className = "status-pill warn";
        status.textContent = "Review";
      } else {
        status.className = "status-pill ok";
        status.textContent = "New";
      }
    }
  }

  function bindCategoryPickers(scope) {
    scope.querySelectorAll("[data-of-category-picker], [data-of-bulk-picker]").forEach((picker) => {
      const select = picker.querySelector("[data-of-category-select], [data-of-bulk-category]");
      if (!select || picker.dataset.ofCategoryBound === "1") {
        return;
      }
      picker.dataset.ofCategoryBound = "1";
      select.addEventListener("change", () => updateCategoryPicker(picker));
      updateCategoryPicker(picker);
    });
  }

  function bindBulkCategoryApply(scope) {
    scope.querySelectorAll("[data-of-apply-bulk-category]").forEach((button) => {
      if (button.dataset.ofBulkBound === "1") {
        return;
      }
      button.dataset.ofBulkBound = "1";

      button.addEventListener("click", () => {
        const form = button.closest("[data-import-preview-form]");
        const bulkSelect = form?.querySelector("[data-of-bulk-category]");
        if (!form || !bulkSelect?.value) {
          return;
        }

        const category = bulkSelect.value;
        form.querySelectorAll(".import-row--new").forEach((row) => {
          const checkbox = row.querySelector('input[name="selected_rows"]');
          if (!checkbox?.checked) {
            return;
          }
          const select = row.querySelector("[data-of-category-select]");
          const picker = row.querySelector("[data-of-category-picker]");
          if (!select || !picker) {
            return;
          }
          select.value = category;
          updateCategoryPicker(picker);
        });
      });
    });
  }

  function init(scope) {
    bindMonthPills(scope);
    bindPeriodForms(scope);
    bindDismissibleAlerts(scope);
    bindImportedToggle(scope);
    bindCategoryPickers(scope);
    bindBulkCategoryApply(scope);
  }

  document.addEventListener("DOMContentLoaded", () => init(document));
})();
