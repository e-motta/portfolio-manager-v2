import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getJson, sendForm } from "../api/client";
import { Modal } from "../components/Modal";
import { formatBrl, formatDate, formatDateTime } from "../lib/format";

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
};

type Preview = Record<string, unknown> & {
  error?: string;
  rows?: Array<Record<string, unknown>>;
  import_token?: string;
  confirm_action?: string;
  allow_transfer_import?: boolean;
};

export function OpenFinancePage() {
  const client = useQueryClient();
  const [params] = useSearchParams();
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
  const [year, setYear] = useState<number | null>(null);
  const [month, setMonth] = useState<number | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const disconnect = useMutation({
    mutationFn: () => sendForm("/api/open-finance/disconnect", {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["open-finance"] }),
  });

  const resolvedYear = year ?? tools.data?.default_year ?? new Date().getFullYear();
  const resolvedMonth = month ?? tools.data?.default_month ?? 1;

  async function runPreview(path: string) {
    const response = await sendForm(path, {
      year: String(resolvedYear),
      month: String(resolvedMonth),
    });
    const payload = (await response.json()) as Preview;
    setPreview(payload);
    setSelected((payload.rows || []).filter((row) => !row.already_exists).map((row) => String(row.row_key)));
    setOverrides({});
  }

  const confirmAction = String(preview?.confirm_action || "");

  async function confirm() {
    const data: Record<string, string | string[]> = {
      import_token: String(preview?.import_token || ""),
      selected_rows: selected,
      ...overrides,
    };
    await sendForm(confirmAction, data);
    setPreview(null);
    window.location.assign("/open-finance");
  }

  const notice = params.get("connected") ? "Open Finance connected." :
    params.get("disconnected") ? "Disconnected." :
    params.get("error");

  if (status.isLoading) return <p className="empty">Loading Open Finance…</p>;
  const connected = status.data?.connected;

  return (
    <>
      <p className="page-lead">Preview bank data before importing expenses, income, transfers, or balances.</p>
      {notice ? <p className={params.get("error") ? "login-error" : "preview-note"}>{notice}</p> : null}
      {!connected ? (
        <a className="btn" href="/auth/cumbuca">Connect bank</a>
      ) : (
        <>
          <div className="toolbar">
            <p className="preview-note" style={{ margin: 0 }}>
              Connected {status.data?.connected_at ? formatDateTime(status.data.connected_at) : ""}
            </p>
            <button type="button" className="btn btn--ghost" onClick={() => disconnect.mutate()}>Disconnect</button>
          </div>
          {tools.data?.tools_error ? <p className="login-error">{tools.data.tools_error}</p> : null}
          <div className="btn-row" style={{ marginBottom: "1rem" }}>
            <label className="field">
              Year
              <select value={resolvedYear} onChange={(event) => setYear(Number(event.target.value))}>
                {(tools.data?.year_options || [resolvedYear]).map((option) => <option key={option}>{option}</option>)}
              </select>
            </label>
            <label className="field">
              Month
              <select value={resolvedMonth} onChange={(event) => setMonth(Number(event.target.value))}>
                {(tools.data?.month_labels || []).map((label, index) => <option key={label} value={index + 1}>{label}</option>)}
              </select>
            </label>
          </div>
          <div className="cards">
            {tools.data?.has_credit_card_tools ? (
              <article className="summary-card">
                <h3>Credit card charges</h3>
                <p>Import as expenses</p>
                <button type="button" className="btn" onClick={() => void runPreview("/api/open-finance/sync/credit-card/preview")}>Preview</button>
              </article>
            ) : null}
            {tools.data?.has_account_tools ? (
              <article className="summary-card">
                <h3>Account debits</h3>
                <p>Expense, transfer, or investment</p>
                <button type="button" className="btn" onClick={() => void runPreview("/api/open-finance/sync/account-debits/preview")}>Preview</button>
              </article>
            ) : null}
            {tools.data?.has_account_tools ? (
              <article className="summary-card">
                <h3>Account credits</h3>
                <p>Income or investment contribution</p>
                <button type="button" className="btn" onClick={() => void runPreview("/api/open-finance/sync/account-credits/preview")}>Preview</button>
              </article>
            ) : null}
            {tools.data?.has_investment_tools ? (
              <article className="summary-card">
                <h3>Investment balances</h3>
                <p>Update Other investments</p>
                <button type="button" className="btn" onClick={() => void runPreview("/api/open-finance/sync/investments/preview")}>Preview</button>
              </article>
            ) : null}
          </div>
        </>
      )}
      <Modal
        open={Boolean(preview)}
        wide
        title={String(preview?.import_title || "Review import")}
        onClose={() => setPreview(null)}
        footer={preview?.import_token ? <button type="button" className="btn" onClick={() => void confirm()}>Import selected</button> : null}
      >
        {preview?.error ? <p className="login-error">{preview.error}</p> : null}
        <p className="preview-note">{String(preview?.import_subtitle || preview?.expense_mapping || "")}</p>
        <ImportRows preview={preview} selected={selected} setSelected={setSelected} overrides={overrides} setOverrides={setOverrides} />
      </Modal>
    </>
  );
}

function ImportRows({
  preview,
  selected,
  setSelected,
  overrides,
  setOverrides,
}: {
  preview: Preview | null;
  selected: string[];
  setSelected: (keys: string[]) => void;
  overrides: Record<string, string>;
  setOverrides: (value: Record<string, string>) => void;
}) {
  const rows = preview?.rows || [];
  const categories = (preview?.expense_categories as string[]) || [];
  const brokers = (preview?.investment_brokers as Array<[string, string]>) || [];
  const accounts = (preview?.transfer_accounts as string[]) || [];

  if (!rows.length) return <p>No rows to import.</p>;

  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th></th>
            <th>Vendor / name</th>
            <th>Date</th>
            <th className="num">Amount</th>
            <th>Import as</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = String(row.row_key);
            return (
              <tr key={key}>
                <td>
                  <input
                    type="checkbox"
                    disabled={Boolean(row.already_exists)}
                    checked={selected.includes(key)}
                    onChange={(event) => setSelected(event.target.checked ? [...selected, key] : selected.filter((item) => item !== key))}
                  />
                </td>
                <td>
                  <div>{String(row.vendor || row.name || row.description || "")}</div>
                  <div className="cell-sub">{row.already_exists ? "already imported" : "New"}</div>
                </td>
                <td>{formatDate(row.transaction_date)}</td>
                <td className="num">{formatBrl(row.amount || row.current_value)}</td>
                <td>
                  {preview?.allow_transfer_import ? (
                    <select
                      className="compact wide"
                      value={overrides[`import_kind_${key}`] || String(row.import_kind || "expense")}
                      onChange={(event) => setOverrides({ ...overrides, [`import_kind_${key}`]: event.target.value })}
                    >
                      <option value="expense">Expense</option>
                      <option value="transfer">Transfer</option>
                      <option value="investment">Investment</option>
                    </select>
                  ) : null}
                  {categories.length ? (
                    <select
                      className="compact wide"
                      value={overrides[`category_${key}`] || String(row.category || "")}
                      onChange={(event) => setOverrides({ ...overrides, [`category_${key}`]: event.target.value })}
                    >
                      {categories.map((category) => <option key={category}>{category}</option>)}
                    </select>
                  ) : null}
                  {(overrides[`import_kind_${key}`] || row.import_kind) === "investment" && brokers.length ? (
                    <select
                      className="compact wide"
                      value={overrides[`broker_${key}`] || String(row.broker || brokers[0]?.[0] || "")}
                      onChange={(event) => setOverrides({ ...overrides, [`broker_${key}`]: event.target.value })}
                    >
                      {brokers.map((broker) => <option key={broker[0]} value={broker[0]}>{broker[1]}</option>)}
                    </select>
                  ) : null}
                  {(overrides[`import_kind_${key}`] || row.import_kind) === "transfer" && accounts.length ? (
                    <select
                      className="compact wide"
                      value={overrides[`to_account_${key}`] || String(row.to_account || accounts[0] || "")}
                      onChange={(event) => setOverrides({ ...overrides, [`to_account_${key}`]: event.target.value })}
                    >
                      {accounts.map((account) => <option key={account}>{account}</option>)}
                    </select>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
