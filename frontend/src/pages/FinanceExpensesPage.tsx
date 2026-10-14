import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, Fragment, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteJson, getJson, pathFromRedirect, redirectLocation, sendForm } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { FinanceTabs } from "../components/FinanceTabs";
import { Modal } from "../components/Modal";
import { MonthChart } from "../components/MonthChart";
import { PageState } from "../components/PageState";
import { PeriodBar } from "../components/PeriodBar";
import { QueryFlash } from "../components/QueryFlash";
import { RankedBars } from "../components/RankedBars";
import { MoneyInput, showToast } from "../components/inputs";
import { asNumber, formatBrl, formatDate, parseDecimalInput } from "../lib/format";
import { useFinancePeriod } from "../lib/finance";

type Entry = {
  id: string;
  month: number;
  transaction_date: string | null;
  category: string;
  vendor: string;
  description: string;
  payment_account: string;
  amount: string;
  effective_amount: string;
  subcategory: string | null;
  source_label: string;
  is_reversal: boolean;
  category_slug: string;
};

type ExpenseDraft = {
  month: string;
  category: string;
  vendor: string;
  description: string;
  payment_account: string;
  amount: string;
  transaction_date: string;
  subcategory: string;
};

type Payload = {
  year: number;
  selected_month: number | null;
  filter_month: number | null;
  form_default_month: number;
  year_options: number[];
  month_labels: string[];
  expense_categories: string[];
  expense_category_groups: Array<[string, string[]]>;
  bills_subcategories: string[];
  bills_category: string;
  payment_accounts: string[];
  entries: Entry[];
  categories: Record<string, Entry[]>;
  category_totals: Array<{ category: string; slug: string; total: string; count: number }>;
  year_total: string;
  monthly_chart: { points: Array<{ month: number; label: string; value: number }> };
  vendor_rules: Record<string, { category: string; subcategory: string | null; description: string }>;
  link_targets: Record<string, Entry[]>;
};

export function FinanceExpensesPage() {
  const { query } = useFinancePeriod();
  const client = useQueryClient();
  const dataQuery = useQuery({
    queryKey: ["finance-expenses", query],
    queryFn: () => getJson<Payload>(`/api/finance/expenses?${query}`),
  });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<ExpenseDraft>({
    month: "",
    category: "",
    vendor: "",
    description: "",
    payment_account: "",
    amount: "",
    transaction_date: "",
    subcategory: "",
  });
  const [pending, setPending] = useState<Entry | null>(null);
  const [linkFor, setLinkFor] = useState<Entry | null>(null);
  const [targetId, setTargetId] = useState("");

  const create = useMutation({
    mutationFn: (data: Record<string, string>) => sendForm("/api/finance/expenses", data),
    onSuccess: () => {
      setOpen(false);
      void client.invalidateQueries({ queryKey: ["finance-expenses"] });
    },
  });

  return (
    <PageState query={dataQuery} loadingText="Loading expenses…">
      <FinanceExpensesContent
        data={dataQuery.data!}
        create={create}
        editing={editing}
        draft={draft}
        setEditing={setEditing}
        setDraft={setDraft}
        pending={pending}
        setPending={setPending}
        linkFor={linkFor}
        setLinkFor={setLinkFor}
        targetId={targetId}
        setTargetId={setTargetId}
        open={open}
        setOpen={setOpen}
        client={client}
      />
    </PageState>
  );
}

function FinanceExpensesContent({
  data,
  create,
  editing,
  draft,
  setEditing,
  setDraft,
  pending,
  setPending,
  linkFor,
  setLinkFor,
  targetId,
  setTargetId,
  open,
  setOpen,
  client,
}: {
  data: Payload;
  create: ReturnType<typeof useMutation<unknown, Error, Record<string, string>>>;
  editing: string | null;
  draft: ExpenseDraft;
  setEditing: (id: string | null) => void;
  setDraft: (value: ExpenseDraft) => void;
  pending: Entry | null;
  setPending: (entry: Entry | null) => void;
  linkFor: Entry | null;
  setLinkFor: (entry: Entry | null) => void;
  targetId: string;
  setTargetId: (id: string) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
  client: ReturnType<typeof useQueryClient>;
}) {
  const navigate = useNavigate();
  const grouped: Array<[string, string[]]> = data.expense_category_groups.length
    ? data.expense_category_groups
    : [["All", data.expense_categories]];

  return (
    <>
      <FinanceTabs />
      <QueryFlash />
      <PeriodBar year={data.year} month={data.filter_month} yearOptions={data.year_options} basePath="/finance/expenses" />
      <div className="toolbar">
        <div className="stat" style={{ minWidth: "12rem" }}><dt>Year total</dt><dd>{formatBrl(data.year_total)}</dd></div>
        <button type="button" className="btn" onClick={() => setOpen(true)}>Add expense</button>
      </div>
      <section className="panel">
        <div className="panel-body">
          <MonthChart points={data.monthly_chart.points} selectedMonth={data.filter_month} variant="expense" onSelect={(next) => navigate(`/finance/expenses?year=${data.year}&month=${next}`)} />
        </div>
      </section>
      {data.category_totals.length ? (
        <section className="panel">
          <div className="panel-head"><h2>By category</h2></div>
          <div className="panel-body">
            <RankedBars
              items={data.category_totals.map((row) => ({
                label: row.category,
                slug: row.slug,
                value: asNumber(row.total),
                count: row.count,
              }))}
              topN={8}
              showGroupLegend={true}
            />
          </div>
        </section>
      ) : null}
      {!data.entries.length ? (
        <EmptyState title="No expenses in this period" body="Add an expense or import from Open Finance." />
      ) : null}
      {grouped.map(([groupName, categories]) => (
        <Fragment key={groupName}>
          {categories.map((category) => {
            const entries = data.categories?.[category] || data.entries.filter((entry) => entry.category === category);
            if (!entries.length) return null;
            const slug = entries[0]?.category_slug || category.toLowerCase();
            return (
              <section className="panel" key={category} id={`category-${slug}`}>
                <div className="panel-head">
                  <h2>{category}</h2>
                  {groupName !== category ? <span className="badge badge--src">{groupName}</span> : null}
                </div>
                <ExpenseTable
                  entries={entries}
                  data={data}
                  editing={editing}
                  draft={draft}
                  setEditing={setEditing}
                  setDraft={setDraft}
                  setPending={setPending}
                  setLinkFor={setLinkFor}
                  client={client}
                />
              </section>
            );
          })}
        </Fragment>
      ))}
      <Modal open={open} title="Add expense" onClose={() => setOpen(false)} footer={
        <button form="add-expense" className="btn" type="submit" disabled={create.isPending}>
          {create.isPending ? "Saving…" : "Save"}
        </button>
      }>
        <ExpenseForm data={data} onSubmit={(values) => create.mutate(values)} />
      </Modal>
      <Modal open={Boolean(linkFor)} title="Unify reversal" onClose={() => setLinkFor(null)} footer={<button type="button" className="btn" onClick={async () => {
        if (!linkFor) return;
        await sendForm(`/api/finance/expenses/${linkFor.id}/link`, { target_id: targetId });
        setLinkFor(null);
        void client.invalidateQueries({ queryKey: ["finance-expenses"] });
      }}>Unify</button>}>
        <p>Link this reversal to the original charge.</p>
        <label className="field">
          Original expense
          <select value={targetId} onChange={(event) => setTargetId(event.target.value)}>
            <option value="">Select</option>
            {(data.link_targets[linkFor?.id || ""] || []).map((target) => (
              <option key={target.id} value={target.id}>{target.vendor} · {formatBrl(target.amount)}</option>
            ))}
          </select>
        </label>
      </Modal>
      <ConfirmDialog open={Boolean(pending)} title="Delete expense" message={`Delete ${pending?.vendor}?`} onClose={() => setPending(null)} onConfirm={async () => {
        if (pending) await deleteJson(`/api/finance/expenses/${pending.id}`);
        setPending(null);
        void client.invalidateQueries({ queryKey: ["finance-expenses"] });
      }} />
    </>
  );
}

function formatExpenseAmount(amount: string | number): string {
  const num = typeof amount === "string" ? parseFloat(amount) : amount;
  const abs = Math.abs(num);
  return formatBrl(abs);
}

function ExpenseTable({
  entries,
  data,
  editing,
  draft,
  setEditing,
  setDraft,
  setPending,
  setLinkFor,
  client,
}: {
  entries: Entry[];
  data: Payload;
  editing: string | null;
  draft: ExpenseDraft;
  setEditing: (id: string | null) => void;
  setDraft: (value: ExpenseDraft) => void;
  setPending: (entry: Entry) => void;
  setLinkFor: (entry: Entry) => void;
  client: ReturnType<typeof useQueryClient>;
}) {
  const navigate = useNavigate();
  const hasBills = entries.some((entry) => entry.category === data.bills_category);

  async function handleSave(entry: Entry) {
    try {
      const parsedAmount = parseDecimalInput(draft.amount);
      const response = await sendForm(`/api/finance/expenses/${entry.id}`, {
        ...draft,
        amount: parsedAmount || draft.amount,
        return_year: String(data.year),
        return_month: data.filter_month ? String(data.filter_month) : "",
      });
      const redirect = redirectLocation(response);
      setEditing(null);
      if (redirect) {
        navigate(pathFromRedirect(redirect));
        return;
      }
      void client.invalidateQueries({ queryKey: ["finance-expenses"] });
    } catch (error) {
      showToast(`Error saving: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  return (
    <div className="table-wrap">
      <table className="data cards-sm">
        <thead>
          <tr>
            {data.filter_month == null ? <th>Month</th> : null}
            <th>Date</th>
            <th>Vendor</th>
            <th>Description</th>
            {hasBills ? <th>Subcategory</th> : null}
            <th>Account</th>
            <th className="num">Amount</th>
            <th>Source</th>
            <th className="num">Actions</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => {
            const isEditing = editing === entry.id;
            const isRefund = entry.is_reversal || asNumber(entry.effective_amount) > 0;
            return (
              <tr key={entry.id}>
                {data.filter_month == null ? (
                  <td data-label="Month">
                    {isEditing ? (
                      <select className="compact" value={draft.month} onChange={(e) => setDraft({ ...draft, month: e.target.value })}>
                        {data.month_labels.map((label, index) => <option key={label} value={index + 1}>{label}</option>)}
                      </select>
                    ) : data.month_labels[entry.month - 1]}
                  </td>
                ) : null}
                <td data-label="Date">
                  {isEditing ? (
                    <input className="compact wide" type="date" value={draft.transaction_date} onChange={(e) => setDraft({ ...draft, transaction_date: e.target.value })} />
                  ) : formatDate(entry.transaction_date)}
                </td>
                <td className="card-primary" data-label="Vendor">
                  {isEditing ? (
                    <input className="compact wide" value={draft.vendor} onChange={(e) => setDraft({ ...draft, vendor: e.target.value })} />
                  ) : entry.vendor}
                </td>
                <td data-label="Description">
                  {isEditing ? (
                    <input className="compact wide" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
                  ) : (
                    <>
                      {entry.description || (entry.is_reversal ? "Reversal" : "")}
                      {isRefund && !entry.is_reversal ? <span className="badge badge--ok" style={{ marginLeft: "0.35rem" }}>Refund</span> : null}
                    </>
                  )}
                </td>
                {hasBills ? (
                  <td data-label="Subcategory">
                    {isEditing && draft.category === data.bills_category ? (
                      <select className="compact wide" value={draft.subcategory} onChange={(e) => setDraft({ ...draft, subcategory: e.target.value })}>
                        <option value="">—</option>
                        {data.bills_subcategories.map((item) => <option key={item}>{item}</option>)}
                      </select>
                    ) : entry.subcategory || "—"}
                  </td>
                ) : null}
                <td data-label="Account">
                  {isEditing ? (
                    <select className="compact wide" value={draft.payment_account} onChange={(e) => setDraft({ ...draft, payment_account: e.target.value })}>
                      {data.payment_accounts.map((account) => <option key={account}>{account}</option>)}
                    </select>
                  ) : <span className="badge badge--src">{entry.payment_account}</span>}
                </td>
                <td className="num" data-label="Amount">
                  {isEditing ? (
                    <input
                      className="compact"
                      inputMode="decimal"
                      value={draft.amount}
                      onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
                    />
                  ) : (
                    <span className={isRefund ? "is-positive" : ""}>
                      {isRefund ? `+${formatExpenseAmount(entry.effective_amount)}` : formatExpenseAmount(entry.effective_amount)}
                    </span>
                  )}
                </td>
                <td data-label="Source"><span className="badge badge--src">{entry.source_label}</span></td>
                <td className="num card-actions">
                  {isEditing ? (
                    <div className="inline-edit">
                      <select className="compact wide" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
                        {data.expense_categories.map((category) => <option key={category}>{category}</option>)}
                      </select>
                      <button type="button" className="btn btn--sm" onClick={() => void handleSave(entry)}>Save</button>
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>Cancel</button>
                    </div>
                  ) : (
                    <div className="inline-edit">
                      {entry.is_reversal ? <button type="button" className="btn btn--ghost btn--sm" onClick={() => setLinkFor(entry)}>Unify</button> : null}
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => {
                        setEditing(entry.id);
                        setDraft({
                          month: String(entry.month),
                          category: entry.category,
                          vendor: entry.vendor,
                          description: entry.description,
                          payment_account: entry.payment_account,
                          amount: String(Math.abs(Number(entry.amount))),
                          transaction_date: entry.transaction_date || "",
                          subcategory: entry.subcategory || "",
                        });
                      }}>Edit</button>
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPending(entry)}>Delete</button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function localDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function parseYearMonth(dateStr: string): { year: number; month: number } | null {
  if (!dateStr || dateStr.length < 7) return null;
  const year = parseInt(dateStr.slice(0, 4), 10);
  const month = parseInt(dateStr.slice(5, 7), 10);
  if (isNaN(year) || isNaN(month) || month < 1 || month > 12) return null;
  return { year, month };
}

function ExpenseForm({ data, onSubmit }: { data: Payload; onSubmit: (values: Record<string, string>) => void }) {
  const [category, setCategory] = useState(data.expense_categories[0] || "");
  const [vendor, setVendor] = useState("");
  const [installmentsEnabled, setInstallmentsEnabled] = useState(false);
  const [amount, setAmount] = useState("");
  const [amountError, setAmountError] = useState<string | null>(null);

  const todayStr = localDateStr(new Date());
  const [transactionDate, setTransactionDate] = useState(todayStr);
  const parsed = parseYearMonth(transactionDate);
  const derivedYear = parsed?.year ?? data.year;
  const derivedMonth = parsed?.month ?? data.form_default_month;

  async function onVendorBlur() {
    if (!vendor) return;
    const suggestion = await getJson<{ category: string }>(`/api/finance/suggest-category?vendor=${encodeURIComponent(vendor)}`);
    if (suggestion.category) setCategory(suggestion.category);
  }

  function handleAmountChange(value: string, error: string | null) {
    setAmount(value);
    setAmountError(error);
  }

  return (
    <form id="add-expense" className="form-grid" onSubmit={(event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (amountError) return;
      const form = new FormData(event.currentTarget);
      onSubmit({
        year: String(derivedYear),
        month: String(derivedMonth),
        category,
        vendor: String(form.get("vendor") || ""),
        payment_account: String(form.get("payment_account") || ""),
        amount: amount,
        transaction_date: transactionDate,
        installments: installmentsEnabled ? String(form.get("installments") || "") : "",
        installments_enabled: installmentsEnabled ? "1" : "",
        subcategory: String(form.get("subcategory") || ""),
        description: String(form.get("description") || ""),
      });
    }}>
      <label className="field">
        Date
        <input
          name="transaction_date"
          type="date"
          value={transactionDate}
          onChange={(e) => setTransactionDate(e.target.value)}
          autoFocus
        />
      </label>
      <label className="field">
        Month
        <input type="text" value={data.month_labels[derivedMonth - 1] || ""} readOnly disabled />
      </label>
      <label className="field">Vendor<input name="vendor" value={vendor} onChange={(e) => setVendor(e.target.value)} onBlur={() => void onVendorBlur()} required /></label>
      <label className="field">
        Category
        <select name="category" value={category} onChange={(e) => setCategory(e.target.value)}>
          {data.expense_categories.map((item) => <option key={item}>{item}</option>)}
        </select>
      </label>
      {category === data.bills_category ? (
        <label className="field">
          Subcategory
          <select name="subcategory">
            <option value="">—</option>
            {data.bills_subcategories.map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
      ) : null}
      <label className="field">Payment account<select name="payment_account">{data.payment_accounts.map((account) => <option key={account}>{account}</option>)}</select></label>
      <MoneyInput label="Amount" name="amount" onValueChange={handleAmountChange} error={amountError ?? undefined} required />
      <label className="field">Description<input name="description" /></label>
      <label className="field">
        <span style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <input
            type="checkbox"
            checked={installmentsEnabled}
            onChange={(e) => setInstallmentsEnabled(e.target.checked)}
          />
          Installments
        </span>
        {installmentsEnabled && (
          <input name="installments" placeholder="2–48" inputMode="numeric" style={{ marginTop: "0.35rem" }} />
        )}
      </label>
    </form>
  );
}
