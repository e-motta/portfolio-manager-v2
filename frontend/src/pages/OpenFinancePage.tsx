import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getJson, pathFromRedirect, redirectLocation, sendForm } from "../api/client";
import { Alert } from "../components/Alert";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { QueryFlash } from "../components/QueryFlash";
import { formatBrl, formatDate } from "../lib/format";

const FALLBACK_MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

type Status = {
  connected: boolean;
  connected_at: string | null;
};

type Tools = {
  has_credit_card_tools: boolean;
  has_account_tools: boolean;
  has_investment_tools: boolean;
  tools_error: string | null;
  default_year: number;
  default_month: number;
  month_labels: string[];
  year_options: number[];
  tool_names: string[];
};

type PreviewKind = "credit_card" | "account_debits" | "account_credits" | "investments";

type Preview = {
  error?: string | null;
  warnings?: string[];
  rows?: Array<Record<string, unknown>>;
  import_token?: string;
  confirm_action?: string;
  allow_transfer_import?: boolean;
  import_title?: string;
  import_subtitle?: string;
  period_label?: string;
  expense_mapping?: string;
  month_label?: string;
  year?: number;
  month?: number;
  new_count?: number;
  existing_count?: number;
  update_count?: number;
  expense_categories?: string[];
  expense_category_groups?: Array<[string, string[]]>;
  bills_subcategories?: string[];
  bills_category?: string;
  month_labels?: string[];
  year_options?: number[];
  default_import_year?: number;
  default_import_month?: number;
  transfer_accounts?: string[];
  investment_brokers?: Array<[string, string]>;
  preview_kind?: PreviewKind;
};

type Period = { year: number; month: number };

function connectedSince(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function kindOf(preview: Preview): PreviewKind {
  if (preview.preview_kind) return preview.preview_kind;
  const action = String(preview.confirm_action || "");
  if (action.includes("investments")) return "investments";
  if (action.includes("credits") || action.includes("deposits")) return "account_credits";
  if (preview.allow_transfer_import || action.includes("debits")) return "account_debits";
  return "credit_card";
}

function Icon({ name }: { name: "bank" | "shield" | "preview" | "card" | "out" | "in" | "bag" }) {
  const common = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.75, "aria-hidden": true as const };
  if (name === "bank") {
    return (
      <svg {...common}>
        <path d="M3 10h18M5 10v8m14-8v8M3 18h18M12 4l9 6H3z" />
      </svg>
    );
  }
  if (name === "shield") {
    return (
      <svg {...common}>
        <path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    );
  }
  if (name === "preview") {
    return (
      <svg {...common}>
        <rect x="4" y="5" width="16" height="14" rx="2" />
        <path d="M8 9h8M8 13h5" />
      </svg>
    );
  }
  if (name === "card") {
    return (
      <svg {...common}>
        <rect x="3" y="6" width="18" height="12" rx="2" />
        <path d="M3 10h18" />
      </svg>
    );
  }
  if (name === "out") {
    return (
      <svg {...common}>
        <path d="M12 5v14M6 13l6 6 6-6" />
      </svg>
    );
  }
  if (name === "in") {
    return (
      <svg {...common}>
        <path d="M12 19V5M6 11l6-6 6 6" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M6 8h12v11H6zM9 8V6h6v2" />
    </svg>
  );
}

export function OpenFinancePage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const status = useQuery({
    queryKey: ["open-finance"],
    queryFn: () => getJson<Status>("/api/open-finance"),
  });
  const tools = useQuery({
    queryKey: ["open-finance-tools"],
    queryFn: () => getJson<Tools>("/api/open-finance/partials/tools"),
    enabled: Boolean(status.data?.connected),
    retry: false,
  });
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewing, setPreviewing] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [ccPeriod, setCcPeriod] = useState<Period | null>(null);
  const [debitPeriod, setDebitPeriod] = useState<Period | null>(null);
  const [creditPeriod, setCreditPeriod] = useState<Period | null>(null);
  const [disconnectOpen, setDisconnectOpen] = useState(false);

  const disconnect = useMutation({
    mutationFn: () => sendForm("/api/open-finance/disconnect", {}),
    onSuccess: (response) => {
      setDisconnectOpen(false);
      void client.invalidateQueries({ queryKey: ["open-finance"] });
      const loc = redirectLocation(response);
      if (loc) navigate(pathFromRedirect(loc), { replace: true });
    },
  });

  const defaults: Period = {
    year: tools.data?.default_year ?? new Date().getFullYear(),
    month: tools.data?.default_month ?? new Date().getMonth() + 1,
  };
  const months = tools.data?.month_labels?.length ? tools.data.month_labels : FALLBACK_MONTHS;
  const years = tools.data?.year_options?.length ? tools.data.year_options : [defaults.year];

  async function runPreview(path: string, period?: Period) {
    setPreviewing(path);
    setPreviewError(null);
    try {
      const body = period ? { year: String(period.year), month: String(period.month) } : {};
      const response = await sendForm(path, body);
      const payload = (await response.json()) as Preview;
      setPreview(payload);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Could not load preview.");
    } finally {
      setPreviewing(null);
    }
  }

  if (status.isLoading) return <p className="empty">Loading Open Finance…</p>;
  const connected = Boolean(status.data?.connected);

  if (preview) {
    return (
      <OpenFinancePreview
        preview={preview}
        onBack={() => setPreview(null)}
        onImported={(path) => {
          setPreview(null);
          void client.invalidateQueries();
          navigate(path);
        }}
      />
    );
  }

  return (
    <>
      <p className="page-lead">
        Import credit card charges, account debits, credits, and investment balances — each with its own preview.
      </p>
      <QueryFlash />
      {previewError ? <Alert tone="error">{previewError}</Alert> : null}

      {!connected ? (
        <DisconnectedHub />
      ) : (
        <>
          <div className="of-status">
            <div className="of-status__dot" aria-hidden="true" />
            <div className="of-status__body">
              <div className="of-status__title">Bank connected</div>
              <div className="of-status__meta">
                {connectedSince(status.data?.connected_at || null) ? (
                  <>
                    <span>Since {connectedSince(status.data?.connected_at || null)}</span>
                    <span aria-hidden="true"> · </span>
                  </>
                ) : null}
                <span>
                  {tools.isLoading
                    ? "Loading data sources…"
                    : `${tools.data?.tool_names?.length ?? 0} data source${(tools.data?.tool_names?.length ?? 0) === 1 ? "" : "s"} available`}
                </span>
              </div>
            </div>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDisconnectOpen(true)}>
              Disconnect
            </button>
          </div>

          {tools.data?.tools_error ? <Alert tone="error">{tools.data.tools_error}</Alert> : null}
          {tools.isError ? <Alert tone="error">{tools.error instanceof Error ? tools.error.message : "Could not load bank tools."}</Alert> : null}

          {tools.isLoading ? (
            <p className="empty">Loading import options from your bank…</p>
          ) : (
            <>
              <section className="of-section">
                <h2 className="of-section__title">Finance</h2>
                <div className="of-actions of-actions--finance">
                  <ImportCard
                    tone="card"
                    icon="card"
                    title="Credit card charges"
                    description={
                      <>
                        Import card statement charges into <Link to="/finance/expenses">Finance expenses</Link>.
                      </>
                    }
                    available={Boolean(tools.data?.has_credit_card_tools)}
                    unavailable="Credit card tools are not available for your bank connection."
                    periodLabel="Statement month"
                    period={ccPeriod ?? defaults}
                    months={months}
                    years={years}
                    onPeriod={setCcPeriod}
                    loading={previewing === "/api/open-finance/sync/credit-card/preview"}
                    submitLabel="Preview charges"
                    onPreview={() => void runPreview("/api/open-finance/sync/credit-card/preview", ccPeriod ?? defaults)}
                  />
                  <ImportCard
                    tone="debits"
                    icon="out"
                    title="Account debits"
                    description={
                      <>
                        Import PIX, boletos, and account outflows as <Link to="/finance/expenses">expenses</Link>,{" "}
                        <Link to="/finance/transfers">transfers</Link>, or <Link to="/finance/investments">investments</Link>.
                      </>
                    }
                    available={Boolean(tools.data?.has_account_tools)}
                    unavailable="Account transaction tools are not available for your bank connection."
                    periodLabel="Month"
                    period={debitPeriod ?? defaults}
                    months={months}
                    years={years}
                    onPeriod={setDebitPeriod}
                    loading={previewing === "/api/open-finance/sync/account-debits/preview"}
                    submitLabel="Preview debits"
                    onPreview={() => void runPreview("/api/open-finance/sync/account-debits/preview", debitPeriod ?? defaults)}
                  />
                  <ImportCard
                    tone="credits"
                    icon="in"
                    title="Account credits"
                    description={
                      <>
                        Import salary, transfers in, and other credits as <Link to="/finance/income">income</Link> or{" "}
                        <Link to="/finance/investments">investments</Link>.
                      </>
                    }
                    available={Boolean(tools.data?.has_account_tools)}
                    unavailable="Account transaction tools are not available for your bank connection."
                    periodLabel="Month"
                    period={creditPeriod ?? defaults}
                    months={months}
                    years={years}
                    onPeriod={setCreditPeriod}
                    loading={previewing === "/api/open-finance/sync/account-credits/preview"}
                    submitLabel="Preview credits"
                    onPreview={() => void runPreview("/api/open-finance/sync/account-credits/preview", creditPeriod ?? defaults)}
                  />
                </div>
              </section>

              <section className="of-section">
                <h2 className="of-section__title">Investments</h2>
                <div className="of-actions of-actions--investments">
                  <ImportCard
                    tone="investments"
                    icon="bag"
                    title="Other investments"
                    description={
                      <>
                        Sync fixed-income and savings balances in <Link to="/portfolio/investments">Other investments</Link>.
                        Exchange-traded positions stay in Securities.
                      </>
                    }
                    available={Boolean(tools.data?.has_investment_tools)}
                    unavailable="Investment tools are not exposed by Cumbuca for your bank yet."
                    note="Pulls all importable non-exchange positions from your bank in one step."
                    loading={previewing === "/api/open-finance/sync/investments/preview"}
                    submitLabel="Preview investment sync"
                    onPreview={() => void runPreview("/api/open-finance/sync/investments/preview")}
                  />
                </div>
              </section>

              {tools.data?.tool_names?.length ? (
                <details className="of-details">
                  <summary>
                    Technical details
                    <span>{tools.data.tool_names.length} MCP tools</span>
                  </summary>
                  <p>Tools exposed by your bank through the Cumbuca MCP server.</p>
                  <ul>
                    {tools.data.tool_names.map((tool) => (
                      <li key={tool}><code>{tool}</code></li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </>
          )}
        </>
      )}

      <ConfirmDialog
        open={disconnectOpen}
        title="Disconnect Open Finance"
        message="Disconnect Open Finance? You will need to reconnect to import again."
        confirmLabel="Disconnect"
        danger={false}
        onClose={() => setDisconnectOpen(false)}
        onConfirm={() => disconnect.mutate()}
      />
    </>
  );
}

function DisconnectedHub() {
  return (
    <div className="of-hero">
      <div className="of-hero__panel">
        <div className="of-hero__icon" aria-hidden="true"><Icon name="bank" /></div>
        <h2>Connect your bank</h2>
        <p>
          Authorize read-only access through Open Finance (CPF + your bank). Data is fetched in real time
          and is not stored by Cumbuca.
        </p>
        <a href="/auth/cumbuca" className="btn of-hero__cta">Connect via Open Finance</a>
        <p className="of-hero__note">You will be redirected to Cumbuca to complete authorization.</p>
      </div>
      <div className="of-features">
        <article className="of-feature">
          <div className="of-feature__icon of-feature__icon--shield"><Icon name="shield" /></div>
          <h3>Read-only access</h3>
          <p>Portfolio Manager can read transactions and balances, not move money.</p>
        </article>
        <article className="of-feature">
          <div className="of-feature__icon of-feature__icon--preview"><Icon name="preview" /></div>
          <h3>Preview every row</h3>
          <p>Nothing is saved until you review and confirm the import.</p>
        </article>
        <article className="of-feature">
          <div className="of-feature__icon of-feature__icon--bank"><Icon name="bank" /></div>
          <h3>One bank at a time</h3>
          <p>The current Cumbuca connection links a single account per user.</p>
        </article>
      </div>
    </div>
  );
}

function ImportCard({
  tone,
  icon,
  title,
  description,
  available,
  unavailable,
  periodLabel,
  period,
  months,
  years,
  onPeriod,
  note,
  loading,
  submitLabel,
  onPreview,
}: {
  tone: "card" | "debits" | "credits" | "investments";
  icon: "card" | "out" | "in" | "bag";
  title: string;
  description: ReactNode;
  available: boolean;
  unavailable: string;
  periodLabel?: string;
  period?: Period;
  months?: string[];
  years?: number[];
  onPeriod?: (period: Period) => void;
  note?: string;
  loading: boolean;
  submitLabel: string;
  onPreview: () => void;
}) {
  return (
    <article className={`of-card of-card--${tone}${available ? "" : " is-unavailable"}`}>
      <div className="of-card__head">
        <div className="of-card__icon"><Icon name={icon} /></div>
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
      </div>
      {available ? (
        <div className="of-card__form">
          {period && months && years && onPeriod ? (
            <div className="of-period">
              <span className="of-period__label">{periodLabel}</span>
              <div className="of-period__fields">
                <label className="field">
                  <span className="sr-only">Month</span>
                  <select
                    value={period.month}
                    onChange={(event) => onPeriod({ ...period, month: Number(event.target.value) })}
                  >
                    {months.map((label, index) => (
                      <option key={label} value={index + 1}>{label}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="sr-only">Year</span>
                  <select
                    value={period.year}
                    onChange={(event) => onPeriod({ ...period, year: Number(event.target.value) })}
                  >
                    {years.map((year) => (
                      <option key={year} value={year}>{year}</option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          ) : note ? (
            <p className="of-card__note">{note}</p>
          ) : null}
          <button type="button" className="btn" disabled={loading} onClick={onPreview}>
            {loading ? "Loading preview…" : submitLabel}
          </button>
        </div>
      ) : (
        <div className="of-card__unavailable">
          <p>{unavailable}</p>
        </div>
      )}
    </article>
  );
}

function OpenFinancePreview({
  preview,
  onBack,
  onImported,
}: {
  preview: Preview;
  onBack: () => void;
  onImported: (path: string) => void;
}) {
  const kind = kindOf(preview);
  const rows = preview.rows || [];
  const months = preview.month_labels?.length ? preview.month_labels : FALLBACK_MONTHS;
  const years = preview.year_options?.length ? preview.year_options : [preview.year || new Date().getFullYear()];
  const billsCategory = preview.bills_category || "Bills";
  const categories = preview.expense_categories || [];
  const groups = preview.expense_category_groups || [];
  const brokers = preview.investment_brokers || [];
  const accounts = preview.transfer_accounts || [];
  const isInvestments = kind === "investments";

  const selectable = useMemo(
    () => rows.filter((row) => isInvestments || !row.already_exists).map((row) => String(row.row_key)),
    [rows, isInvestments],
  );

  const [selected, setSelected] = useState<string[]>(selectable);
  const [overrides, setOverrides] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const row of rows) {
      const key = String(row.row_key);
      if (row.already_exists && !isInvestments) continue;
      if (row.category) initial[`category_${key}`] = String(row.category);
      if (row.subcategory) initial[`subcategory_${key}`] = String(row.subcategory);
      if (row.import_kind) initial[`import_kind_${key}`] = String(row.import_kind);
      if (row.month) initial[`import_month_${key}`] = String(row.month);
      if (row.year) initial[`import_year_${key}`] = String(row.year);
      if (row.broker) initial[`broker_${key}`] = String(row.broker);
      if (row.to_account) initial[`to_account_${key}`] = String(row.to_account);
      if (row.description) initial[`description_${key}`] = String(row.description);
    }
    return initial;
  });
  const [showImported, setShowImported] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [bulkMonth, setBulkMonth] = useState(String(preview.default_import_month || preview.month || 1));
  const [bulkYear, setBulkYear] = useState(String(preview.default_import_year || preview.year || new Date().getFullYear()));
  const [bulkKind, setBulkKind] = useState(kind === "account_credits" ? "income" : "expense");
  const [bulkCategory, setBulkCategory] = useState(categories[0] || "");
  const [bulkSubcategory, setBulkSubcategory] = useState("");

  function setOverride(name: string, value: string) {
    setOverrides((current) => ({ ...current, [name]: value }));
  }

  function applyToSelected(patch: Record<string, string>) {
    setOverrides((current) => {
      const next = { ...current };
      for (const key of selected) {
        for (const [field, value] of Object.entries(patch)) {
          next[`${field}_${key}`] = value;
        }
      }
      return next;
    });
  }

  const visibleRows = rows.filter((row) => showImported || isInvestments || !row.already_exists);
  const existingCount = preview.existing_count || rows.filter((row) => row.already_exists).length;

  async function confirm() {
    const action = String(preview.confirm_action || "");
    if (!action) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const response = await sendForm(action, {
        import_token: String(preview.import_token || ""),
        selected_rows: selected,
        ...overrides,
      });
      const loc = redirectLocation(response) || "/open-finance";
      onImported(pathFromRedirect(loc));
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : "Import failed.");
    } finally {
      setConfirming(false);
    }
  }

  if (preview.error && !rows.length) {
    return (
      <div className="of-preview">
        <button type="button" className="btn btn--ghost" onClick={onBack}>Back to Open Finance</button>
        <Alert tone="error">{preview.error}</Alert>
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="of-preview">
        <button type="button" className="btn btn--ghost" onClick={onBack}>Back to Open Finance</button>
        <EmptyState
          title="No rows to import"
          body="Nothing came back from your bank for this source and period."
        />
      </div>
    );
  }

  return (
    <div className="of-preview">
      <div className="of-preview__nav">
        <button type="button" className="btn btn--ghost" onClick={onBack}>Back</button>
        <h2>{preview.import_title || "Review import"}</h2>
      </div>
      {preview.error ? <Alert tone="error">{preview.error}</Alert> : null}
      {confirmError ? <Alert tone="error">{confirmError}</Alert> : null}
      {preview.warnings?.length ? (
        <Alert tone="warn">
          <div>
            <strong>Some sources were skipped</strong>
            <ul className="alert-list">
              {preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          </div>
        </Alert>
      ) : null}

      <div className="of-preview__summary">
        <div>
          <div className="of-preview__eyebrow">{preview.period_label || (isInvestments ? "Investment sync" : "Month")}</div>
          <div className="of-preview__date">
            {isInvestments
              ? `${rows.length} position${rows.length === 1 ? "" : "s"} found`
              : `${preview.month_label || ""} ${preview.year || ""}`}
          </div>
          {preview.import_subtitle || preview.expense_mapping ? (
            <p className="of-preview__mapping">{preview.import_subtitle || preview.expense_mapping}</p>
          ) : null}
        </div>
        <div className="of-preview__badges">
          <span className="count-badge count-badge--new">
            <strong>{preview.new_count ?? selectable.filter((key) => !rows.find((row) => String(row.row_key) === key && row.already_exists)).length}</strong>
            new
          </span>
          {isInvestments && (preview.update_count || 0) > 0 ? (
            <span className="count-badge">
              <strong>{preview.update_count}</strong>
              updates
            </span>
          ) : null}
          {!isInvestments && existingCount > 0 ? (
            <button
              type="button"
              className={`count-badge count-badge--toggle${showImported ? " is-active" : ""}`}
              onClick={() => setShowImported((value) => !value)}
            >
              <strong>{existingCount}</strong>
              {showImported ? "hiding imported" : "already imported"}
            </button>
          ) : null}
        </div>
      </div>

      {!isInvestments && selectable.length > 0 ? (
        <div className="of-bulk">
          <div className="of-bulk__group">
            <span>Import month</span>
            <div className="of-bulk__controls">
              <select value={bulkMonth} onChange={(event) => setBulkMonth(event.target.value)}>
                {months.map((label, index) => <option key={label} value={index + 1}>{label}</option>)}
              </select>
              <select value={bulkYear} onChange={(event) => setBulkYear(event.target.value)}>
                {years.map((year) => <option key={year} value={year}>{year}</option>)}
              </select>
              <button type="button" className="btn btn--ghost btn--sm" onClick={() => applyToSelected({ import_month: bulkMonth, import_year: bulkYear })}>
                Apply
              </button>
            </div>
          </div>
          {(kind === "account_debits" || kind === "account_credits") ? (
            <div className="of-bulk__group">
              <span>Import as</span>
              <div className="of-bulk__controls">
                <select value={bulkKind} onChange={(event) => setBulkKind(event.target.value)}>
                  {kind === "account_credits" ? (
                    <>
                      <option value="income">Income</option>
                      <option value="investment">Investment</option>
                    </>
                  ) : (
                    <>
                      <option value="expense">Expense</option>
                      <option value="transfer">Transfer</option>
                      <option value="investment">Investment</option>
                    </>
                  )}
                </select>
                <button type="button" className="btn btn--ghost btn--sm" onClick={() => applyToSelected({ import_kind: bulkKind })}>
                  Apply
                </button>
              </div>
            </div>
          ) : null}
          {kind !== "account_credits" ? (
            <div className="of-bulk__group">
              <span>Category</span>
              <div className="of-bulk__controls">
                <select value={bulkCategory} onChange={(event) => { setBulkCategory(event.target.value); setBulkSubcategory(""); }}>
                  <CategoryOptions categories={categories} groups={groups} />
                </select>
                {bulkCategory === billsCategory ? (
                  <select value={bulkSubcategory} onChange={(event) => setBulkSubcategory(event.target.value)}>
                    <option value="">—</option>
                    {(preview.bills_subcategories || []).map((item) => <option key={item}>{item}</option>)}
                  </select>
                ) : null}
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() => applyToSelected({ category: bulkCategory, subcategory: bulkSubcategory, import_kind: "expense" })}
                >
                  Apply
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <section className="panel">
        <div className="table-wrap">
          <table className="data of-table">
            <thead>
              <tr>
                <th className="col-check">
                  {selectable.length ? (
                    <input
                      type="checkbox"
                      checked={selectable.every((key) => selected.includes(key)) && selectable.length > 0}
                      onChange={(event) => setSelected(event.target.checked ? selectable : [])}
                      aria-label="Select all"
                    />
                  ) : null}
                </th>
                {isInvestments ? (
                  <>
                    <th>Institution</th>
                    <th>Name</th>
                    <th>Asset class</th>
                    <th className="num">Value</th>
                    <th>Status</th>
                  </>
                ) : (
                  <>
                    <th>Date</th>
                    <th>{kind === "account_credits" ? "Description" : "Vendor"}</th>
                    <th>Import to</th>
                    {kind === "credit_card" ? (
                      <>
                        <th>Category</th>
                        <th>Subcategory</th>
                        <th>Account</th>
                      </>
                    ) : (
                      <>
                        <th>Import as</th>
                        <th>Details</th>
                        {kind === "account_credits" ? <th>Account</th> : null}
                      </>
                    )}
                    <th className="num">Amount</th>
                    <th>Status</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => {
                const key = String(row.row_key);
                const existing = Boolean(row.already_exists) && !isInvestments;
                const importKind = overrides[`import_kind_${key}`] || String(row.import_kind || (kind === "account_credits" ? "income" : "expense"));
                const category = overrides[`category_${key}`] || String(row.category || "");
                return (
                  <tr key={key} className={existing ? "is-imported" : category === "Outros" && importKind === "expense" ? "needs-category" : ""}>
                    <td className="col-check">
                      {existing ? null : (
                        <input
                          type="checkbox"
                          checked={selected.includes(key)}
                          onChange={(event) => setSelected(event.target.checked ? [...selected, key] : selected.filter((item) => item !== key))}
                          aria-label="Select row"
                        />
                      )}
                    </td>
                    {isInvestments ? (
                      <>
                        <td>{String(row.institution || "")}</td>
                        <td className="cell-wrap">{String(row.name || "")}</td>
                        <td>{String(row.asset_type_slug || "")}</td>
                        <td className="num">{formatBrl(row.current_value)}</td>
                        <td>
                          <span className={`badge ${row.is_update ? "badge--warn" : "badge--ok"}`}>
                            {row.is_update ? "Update" : "New"}
                          </span>
                        </td>
                      </>
                    ) : (
                      <>
                        <td>{formatDate(row.transaction_date)}</td>
                        <td className="cell-wrap">
                          <div>{String(row.vendor || row.description || "")}</div>
                          {existing ? (
                            row.description && row.vendor ? <div className="cell-sub">{String(row.description)}</div> : null
                          ) : kind !== "account_credits" ? (
                            <input
                              className="compact wide"
                              placeholder="Description (optional)"
                              value={overrides[`description_${key}`] || ""}
                              onChange={(event) => setOverride(`description_${key}`, event.target.value)}
                            />
                          ) : null}
                        </td>
                        <td>
                          {existing ? (
                            <span className="badge badge--src">
                              {months[Number(row.month) - 1] || String(row.month || "")} {String(row.year || "")}
                            </span>
                          ) : (
                            <span className="of-period-inline">
                              <select
                                className="compact"
                                value={overrides[`import_month_${key}`] || String(row.month || "")}
                                onChange={(event) => setOverride(`import_month_${key}`, event.target.value)}
                              >
                                {months.map((label, index) => <option key={label} value={index + 1}>{label.slice(0, 3)}</option>)}
                              </select>
                              <select
                                className="compact"
                                value={overrides[`import_year_${key}`] || String(row.year || "")}
                                onChange={(event) => setOverride(`import_year_${key}`, event.target.value)}
                              >
                                {years.map((year) => <option key={year} value={year}>{year}</option>)}
                              </select>
                            </span>
                          )}
                        </td>
                        {kind === "credit_card" ? (
                          <>
                            <td>
                              {existing ? category : (
                                <select className="compact wide" value={category} onChange={(event) => setOverride(`category_${key}`, event.target.value)}>
                                  <CategoryOptions categories={categories} groups={groups} />
                                </select>
                              )}
                            </td>
                            <td>
                              {category === billsCategory ? (
                                existing ? String(row.subcategory || "—") : (
                                  <select
                                    className="compact wide"
                                    value={overrides[`subcategory_${key}`] || String(row.subcategory || "")}
                                    onChange={(event) => setOverride(`subcategory_${key}`, event.target.value)}
                                  >
                                    <option value="">—</option>
                                    {(preview.bills_subcategories || []).map((item) => <option key={item}>{item}</option>)}
                                  </select>
                                )
                              ) : "—"}
                            </td>
                            <td><span className="badge badge--src">{String(row.payment_account || "")}</span></td>
                          </>
                        ) : (
                          <>
                            <td>
                              {existing ? (
                                <span className="badge badge--src">{importKind}</span>
                              ) : (
                                <select className="compact wide" value={importKind} onChange={(event) => setOverride(`import_kind_${key}`, event.target.value)}>
                                  {kind === "account_credits" ? (
                                    <>
                                      <option value="income">Income</option>
                                      <option value="investment">Investment</option>
                                    </>
                                  ) : (
                                    <>
                                      <option value="expense">Expense</option>
                                      <option value="transfer">Transfer</option>
                                      <option value="investment">Investment</option>
                                    </>
                                  )}
                                </select>
                              )}
                            </td>
                            <td>
                              {importKind === "investment" ? (
                                existing ? brokerLabel(brokers, String(row.broker || "")) : (
                                  <select
                                    className="compact wide"
                                    value={overrides[`broker_${key}`] || String(row.broker || brokers[0]?.[0] || "")}
                                    onChange={(event) => setOverride(`broker_${key}`, event.target.value)}
                                  >
                                    {brokers.map((broker) => <option key={broker[0]} value={broker[0]}>{broker[1]}</option>)}
                                  </select>
                                )
                              ) : importKind === "transfer" ? (
                                existing ? String(row.to_account || "") : (
                                  <select
                                    className="compact wide"
                                    value={overrides[`to_account_${key}`] || String(row.to_account || accounts[0] || "")}
                                    onChange={(event) => setOverride(`to_account_${key}`, event.target.value)}
                                  >
                                    {accounts.map((account) => <option key={account}>{account}</option>)}
                                  </select>
                                )
                              ) : kind === "account_debits" ? (
                                existing ? category : (
                                  <span className="of-period-inline">
                                    <select className="compact wide" value={category} onChange={(event) => setOverride(`category_${key}`, event.target.value)}>
                                      <CategoryOptions categories={categories} groups={groups} />
                                    </select>
                                    {category === billsCategory ? (
                                      <select
                                        className="compact wide"
                                        value={overrides[`subcategory_${key}`] || String(row.subcategory || "")}
                                        onChange={(event) => setOverride(`subcategory_${key}`, event.target.value)}
                                      >
                                        <option value="">—</option>
                                        {(preview.bills_subcategories || []).map((item) => <option key={item}>{item}</option>)}
                                      </select>
                                    ) : null}
                                  </span>
                                )
                              ) : (
                                <span className="cell-sub">Finance income</span>
                              )}
                            </td>
                            {kind === "account_credits" ? <td><span className="badge badge--src">{String(row.payment_account || "")}</span></td> : null}
                          </>
                        )}
                        <td className="num">{formatBrl(row.amount)}</td>
                        <td>
                          <span className={`badge ${existing ? "badge--src" : "badge--ok"}`}>
                            {existing ? "Imported" : "New"}
                          </span>
                        </td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="of-preview__foot">
        <p>{selected.length} selected</p>
        <div className="btn-row">
          <button type="button" className="btn btn--ghost" onClick={onBack}>Cancel</button>
          <button type="button" className="btn" disabled={!selected.length || confirming} onClick={() => void confirm()}>
            {confirming ? "Importing…" : "Import selected"}
          </button>
        </div>
      </div>
    </div>
  );
}

function brokerLabel(brokers: Array<[string, string]>, value: string): string {
  return brokers.find((item) => item[0] === value)?.[1] || value || "—";
}

function CategoryOptions({
  categories,
  groups,
}: {
  categories: string[];
  groups: Array<[string, string[]]>;
}) {
  if (groups.length) {
    return (
      <>
        {groups.map(([group, items]) => (
          <optgroup key={group} label={group}>
            {items.map((item) => <option key={item}>{item}</option>)}
          </optgroup>
        ))}
      </>
    );
  }
  return (
    <>
      {categories.map((item) => <option key={item}>{item}</option>)}
    </>
  );
}
