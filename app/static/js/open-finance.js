(function () {
  const BILLS_CATEGORY = "Bills";

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

  function periodPickerValues(picker) {
    const monthSelect = picker.querySelector(
      "[data-of-period-month], [data-of-bulk-period-month]"
    );
    const yearSelect = picker.querySelector(
      "[data-of-period-year], [data-of-bulk-period-year]"
    );
    return {
      month: Number(monthSelect?.value),
      year: Number(yearSelect?.value),
    };
  }

  function periodPickerDefaults(picker) {
    return {
      month: Number(picker.dataset.defaultMonth),
      year: Number(picker.dataset.defaultYear),
    };
  }

  function periodPickerIsOverridden(picker) {
    const current = periodPickerValues(picker);
    const defaults = periodPickerDefaults(picker);
    return current.month !== defaults.month || current.year !== defaults.year;
  }

  function updatePeriodPicker(picker) {
    if (!picker) {
      return;
    }

    const overridden = periodPickerIsOverridden(picker);
    picker.classList.toggle("of-period-picker--overridden", overridden);
    const reset = picker.querySelector("[data-of-period-reset]");
    if (reset) {
      reset.hidden = !overridden;
    }

    const form = picker.closest("[data-import-preview-form]");
    if (form) {
      updatePeriodOverrideNote(form);
    }
  }

  function updatePeriodOverrideNote(form) {
    const note = form?.querySelector("[data-of-period-override-note]");
    if (!note) {
      return;
    }

    const overriddenCount = form.querySelectorAll(
      ".import-row--new [data-of-period-picker].of-period-picker--overridden"
    ).length;
    if (overriddenCount === 0) {
      note.hidden = true;
      note.textContent = "";
      return;
    }

    note.hidden = false;
    note.textContent =
      `${overriddenCount} row${overriddenCount === 1 ? "" : "s"} with custom month`;
  }

  function bindPeriodPickers(scope) {
    scope.querySelectorAll("[data-of-period-picker]").forEach((picker) => {
      if (picker.dataset.ofPeriodBound === "1") {
        return;
      }
      picker.dataset.ofPeriodBound = "1";

      picker.querySelectorAll("[data-of-period-month], [data-of-period-year]").forEach((select) => {
        select.addEventListener("change", () => updatePeriodPicker(picker));
      });

      picker.querySelector("[data-of-period-reset]")?.addEventListener("click", () => {
        const defaults = periodPickerDefaults(picker);
        const monthSelect = picker.querySelector("[data-of-period-month]");
        const yearSelect = picker.querySelector("[data-of-period-year]");
        if (monthSelect) {
          monthSelect.value = String(defaults.month);
        }
        if (yearSelect) {
          yearSelect.value = String(defaults.year);
        }
        updatePeriodPicker(picker);
      });

      updatePeriodPicker(picker);
    });
  }

  function bindBulkPeriodApply(scope) {
    scope.querySelectorAll("[data-of-apply-bulk-period]").forEach((button) => {
      if (button.dataset.ofBulkPeriodBound === "1") {
        return;
      }
      button.dataset.ofBulkPeriodBound = "1";

      button.addEventListener("click", () => {
        const form = button.closest("[data-import-preview-form]");
        const bulkPicker = form?.querySelector("[data-of-bulk-period-picker]");
        if (!form || !bulkPicker) {
          return;
        }

        const { month, year } = periodPickerValues(bulkPicker);
        if (!month || !year) {
          return;
        }

        form.querySelectorAll(".import-row--new").forEach((row) => {
          const checkbox = row.querySelector('input[name="selected_rows"]');
          if (!checkbox?.checked) {
            return;
          }

          const picker = row.querySelector("[data-of-period-picker]");
          if (!picker) {
            return;
          }

          const monthSelect = picker.querySelector("[data-of-period-month]");
          const yearSelect = picker.querySelector("[data-of-period-year]");
          if (monthSelect) {
            monthSelect.value = String(month);
          }
          if (yearSelect) {
            yearSelect.value = String(year);
          }
          updatePeriodPicker(picker);
        });
      });
    });
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
      if (toggle.dataset.ofImportedToggleBound === "1") {
        return;
      }
      toggle.dataset.ofImportedToggleBound = "1";

      const form = toggle.closest("[data-import-preview-form]");
      if (!form) {
        return;
      }

      const label = toggle.querySelector("[data-of-toggle-label]");
      const count = toggle.querySelector(".import-count-badge__value")?.textContent?.trim() || "";

      const apply = () => {
        const show = toggle.getAttribute("aria-pressed") === "true";
        form.querySelectorAll(".import-row--existing").forEach((row) => {
          row.hidden = !show;
        });
        toggle.classList.toggle("is-active", show);
        if (label) {
          label.textContent = show ? "showing imported" : "already imported";
        }
        toggle.setAttribute(
          "aria-label",
          show
            ? `Hide ${count} already imported transaction${count === "1" ? "" : "s"}`
            : `Show ${count} already imported transaction${count === "1" ? "" : "s"}`
        );
      };

      toggle.addEventListener("click", () => {
        const show = toggle.getAttribute("aria-pressed") !== "true";
        toggle.setAttribute("aria-pressed", show ? "true" : "false");
        apply();
      });

      apply();
    });
  }

  function categorySlug(select) {
    return select.selectedOptions[0]?.dataset.slug || "other";
  }

  function subcategorySlug(select) {
    return select?.selectedOptions[0]?.dataset.slug || "none";
  }

  function setSubcategorySelectEnabled(select, enabled) {
    if (!select) {
      return;
    }

    const storedName = select.dataset.subcategoryName;
    select.disabled = !enabled;
    if (enabled && storedName) {
      select.setAttribute("name", storedName);
    } else {
      select.removeAttribute("name");
      if (!enabled) {
        select.value = "";
      }
    }
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

  function updateRowSubcategoryVisibility(row) {
    const isBills = row.dataset.rowCategory === BILLS_CATEGORY;
    const slot = row.querySelector("[data-of-subcategory-slot]");
    if (!slot) {
      return;
    }

    slot.hidden = !isBills;
    const select = slot.querySelector("[data-of-subcategory-select]");
    const picker = slot.querySelector("[data-of-subcategory-picker]");
    setSubcategorySelectEnabled(select, isBills);
    if (picker) {
      updateSubcategoryPicker(picker);
    }
    updateRowAmountPreview(row);
  }

  function effectiveAmountFor(amount, subcategory) {
    const magnitude = Math.abs(amount);
    let adjusted = magnitude;
    if (subcategory === "Aluguel (/2+114)") {
      adjusted = magnitude / 2 + 114;
    } else if (subcategory === "Outras contas (/2)") {
      adjusted = magnitude / 2;
    }
    adjusted = Math.round(adjusted * 100) / 100;
    if (amount > 0) {
      return adjusted;
    }
    if (amount < 0) {
      return -adjusted;
    }
    return 0;
  }

  function formatSignedBrl(amount) {
    const absolute = Math.abs(amount).toLocaleString("pt-BR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    if (amount > 0) {
      return `+R$\u00a0${absolute}`;
    }
    return `R$\u00a0-${absolute}`;
  }

  function plClass(amount) {
    if (amount > 0) {
      return "pl-positive";
    }
    if (amount < 0) {
      return "pl-negative";
    }
    return "pl-neutral";
  }

  function updateRowAmountPreview(row) {
    const preview = row.querySelector("[data-of-amount-preview]");
    if (!preview) {
      return;
    }

    const rawAmount = Number(row.dataset.rowAmount || "0");
    const isBills = row.dataset.rowCategory === BILLS_CATEGORY;
    const subcategorySelect = row.querySelector("[data-of-subcategory-select]");
    const subcategory = isBills ? (subcategorySelect?.value || "") : "";
    const effective = effectiveAmountFor(rawAmount, subcategory);
    const effectiveEl = preview.querySelector("[data-of-effective-amount]");
    const originalEl = preview.querySelector("[data-of-original-amount]");

    if (effectiveEl) {
      effectiveEl.textContent = formatSignedBrl(effective);
      effectiveEl.className = `money ${plClass(effective)}`;
    }
    if (originalEl) {
      const showOriginal = Boolean(subcategory) && effective !== rawAmount;
      originalEl.hidden = !showOriginal;
      originalEl.textContent = showOriginal ? `Original ${formatSignedBrl(rawAmount)}` : "";
    }
  }

  function updateBulkSubcategoryToolbar(form) {
    const bulkCategory = form?.querySelector("[data-of-bulk-category]");
    const bulkSubcategory = form?.querySelector("[data-of-bulk-subcategory-wrap]");
    if (!bulkCategory || !bulkSubcategory) {
      return;
    }
    bulkSubcategory.hidden = bulkCategory.value !== BILLS_CATEGORY;
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
    row.dataset.rowCategory = select.value;
    updateRowSubcategoryVisibility(row);
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

  function bindSubcategoryPickers(scope) {
    scope.querySelectorAll("[data-of-subcategory-picker]").forEach((picker) => {
      const select = picker.querySelector("[data-of-subcategory-select]");
      if (!select || picker.dataset.ofSubcategoryBound === "1") {
        return;
      }
      picker.dataset.ofSubcategoryBound = "1";
      select.addEventListener("change", () => {
        updateSubcategoryPicker(picker);
        const row = picker.closest("[data-import-row]");
        if (row) {
          updateRowAmountPreview(row);
        }
      });
      updateSubcategoryPicker(picker);
    });
  }

  function bindCategoryPickers(scope) {
    scope.querySelectorAll("[data-of-category-picker], [data-of-bulk-picker]").forEach((picker) => {
      const select = picker.querySelector("[data-of-category-select], [data-of-bulk-category]");
      if (!select || picker.dataset.ofCategoryBound === "1") {
        return;
      }
      picker.dataset.ofCategoryBound = "1";
      select.addEventListener("change", () => {
        updateCategoryPicker(picker);
        const form = picker.closest("[data-import-preview-form]");
        if (picker.hasAttribute("data-of-bulk-picker")) {
          updateBulkSubcategoryToolbar(form);
        }
      });
      updateCategoryPicker(picker);
      if (picker.hasAttribute("data-of-bulk-picker")) {
        updateBulkSubcategoryToolbar(picker.closest("[data-import-preview-form]"));
      }
    });
  }

  function bindBulkSelectionApply(scope) {
    scope.querySelectorAll("[data-of-apply-bulk-selection]").forEach((button) => {
      if (button.dataset.ofBulkSelectionBound === "1") {
        return;
      }
      button.dataset.ofBulkSelectionBound = "1";

      button.addEventListener("click", () => {
        const form = button.closest("[data-import-preview-form]");
        const bulkCategory = form?.querySelector("[data-of-bulk-category]");
        const bulkSubcategory = form?.querySelector("[data-of-bulk-subcategory]");
        if (!form || !bulkCategory?.value) {
          return;
        }

        const category = bulkCategory.value;
        const subcategory = category === BILLS_CATEGORY ? (bulkSubcategory?.value || "") : "";

        form.querySelectorAll(".import-row--new").forEach((row) => {
          const checkbox = row.querySelector('input[name="selected_rows"]');
          if (!checkbox?.checked) {
            return;
          }

          const categorySelect = row.querySelector("[data-of-category-select]");
          const categoryPicker = row.querySelector("[data-of-category-picker]");
          if (categorySelect && categoryPicker) {
            categorySelect.value = category;
            updateCategoryPicker(categoryPicker);
          }

          const subcategorySelect = row.querySelector("[data-of-subcategory-select]");
          const subcategoryPicker = row.querySelector("[data-of-subcategory-picker]");
          if (category === BILLS_CATEGORY && subcategorySelect) {
            subcategorySelect.value = subcategory;
            if (subcategoryPicker) {
              updateSubcategoryPicker(subcategoryPicker);
            }
          }
          updateRowSubcategoryVisibility(row);
        });
      });
    });
  }

  function init(scope) {
    bindMonthPills(scope);
    bindPeriodForms(scope);
    bindDismissibleAlerts(scope);
    bindImportedToggle(scope);
    bindPeriodPickers(scope);
    bindBulkPeriodApply(scope);
    bindCategoryPickers(scope);
    bindSubcategoryPickers(scope);
    bindBulkSelectionApply(scope);
    scope.querySelectorAll("[data-import-preview-form]").forEach((form) => {
      updatePeriodOverrideNote(form);
    });
    scope.querySelectorAll("[data-import-row]").forEach((row) => {
      updateRowSubcategoryVisibility(row);
      updateRowAmountPreview(row);
    });
  }

  document.addEventListener("DOMContentLoaded", () => init(document));
  document.body.addEventListener("htmx:afterSwap", () => init(document));
})();
