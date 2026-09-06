import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteJson, getJson, sendForm } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { FinanceTabs } from "../components/FinanceTabs";
import { Modal } from "../components/Modal";
import { MonthChart } from "../components/MonthChart";
import { PeriodBar } from "../components/PeriodBar";
import { QueryFlash } from "../components/QueryFlash";
import { formatBrl } from "../lib/format";
import { useFinancePeriod } from "../lib/finance";

type Entry = {
  id: string;
  month: number;
  category: string;
  description: string;
  amount: string;
};

type Payload = {
  year: number;
  selected_month: number | null;
  filter_month: number | null;
  year_options: number[];
  month_labels: string[];
  income_categories: string[];
  entries: Entry[];
  year_total: string;
  monthly_chart: { points: Array<{ month: number; label: string; value: number }> };
};

export function FinanceIncomePage() {
  const { query } = useFinancePeriod();
  const navigate = useNavigate();
  const client = useQueryClient();
  const dataQuery = useQuery({
    queryKey: ["finance-income", query],
    queryFn: () => getJson<Payload>(`/api/finance/income?${query}`),
  });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ month: "", category: "", description: "", amount: "" });
  const [pending, setPending] = useState<Entry | null>(null);

  const create = useMutation({
    mutationFn: (data: Record<string, string>) => sendForm("/api/finance/income", data),
    onSuccess: () => {
      setOpen(false);
      void client.invalidateQueries({ queryKey: ["finance-income"] });
    },
  });

  if (dataQuery.isLoading) return <p className="empty">Loading income…</p>;
  const data = dataQuery.data!;

  return (
    <>
      <FinanceTabs />
      <QueryFlash />
      <PeriodBar year={data.year} month={data.filter_month} yearOptions={data.year_options} basePath="/finance/income" />
      <div className="toolbar">
        <div className="stat" style={{ minWidth: "12rem" }}><dt>Year total</dt><dd>{formatBrl(data.year_total)}</dd></div>
        <button type="button" className="btn" onClick={() => setOpen(true)}>Add income</button>
      </div>
      <section className="panel">
        <div className="panel-body">
          <MonthChart points={data.monthly_chart.points} selectedMonth={data.filter_month} variant="income" onSelect={(next) => navigate(`/finance/income?year=${data.year}&month=${next}`)} />
        </div>
      </section>
      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                {data.filter_month == null ? <th>Month</th> : null}
                <th>Category</th>
                <th>Description</th>
                <th className="num">Amount</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!data.entries.length ? (
                <tr><td colSpan={5}><EmptyState title="No income in this period" body="Add income or import account credits from Open Finance." /></td></tr>
              ) : null}
              {data.entries.map((entry) => {
                const isEditing = editing === entry.id;
                return (
                  <tr key={entry.id}>
                    {data.filter_month == null ? <td>{isEditing ? <select className="compact" value={draft.month} onChange={(e) => setDraft({ ...draft, month: e.target.value })}>{data.month_labels.map((label, index) => <option key={label} value={index + 1}>{label}</option>)}</select> : data.month_labels[entry.month - 1]}</td> : null}
                    <td>{isEditing ? <select className="compact wide" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>{data.income_categories.map((category) => <option key={category}>{category}</option>)}</select> : entry.category}</td>
                    <td>{isEditing ? <input className="compact wide" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /> : entry.description}</td>
                    <td className="num">{isEditing ? <input className="compact" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} /> : formatBrl(entry.amount)}</td>
                    <td className="num">
                      {isEditing ? (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--sm" onClick={async () => {
                            await sendForm(`/api/finance/income/${entry.id}`, draft);
                            setEditing(null);
                            void client.invalidateQueries({ queryKey: ["finance-income"] });
                          }}>Save</button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>Cancel</button>
                        </div>
                      ) : (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => { setEditing(entry.id); setDraft({ month: String(entry.month), category: entry.category, description: entry.description, amount: entry.amount }); }}>Edit</button>
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
      </section>
      <Modal open={open} title="Add income" onClose={() => setOpen(false)} footer={<button form="add-income" className="btn" type="submit">Save</button>}>
        <form id="add-income" className="form-grid" onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          create.mutate({
            year: String(data.year),
            month: String(form.get("month") || data.filter_month || data.selected_month || 1),
            category: String(form.get("category") || "Outros"),
            description: String(form.get("description") || ""),
            amount: String(form.get("amount") || ""),
          });
        }}>
          <label className="field">Month<select name="month" defaultValue={data.filter_month || data.selected_month || 1}>{data.month_labels.map((label, index) => <option key={label} value={index + 1}>{label}</option>)}</select></label>
          <label className="field">Category<select name="category">{data.income_categories.map((category) => <option key={category}>{category}</option>)}</select></label>
          <label className="field">Description<input name="description" required /></label>
          <label className="field">Amount<input name="amount" required /></label>
        </form>
      </Modal>
      <ConfirmDialog open={Boolean(pending)} title="Delete income" message={`Delete ${pending?.description}?`} onClose={() => setPending(null)} onConfirm={async () => {
        if (pending) await deleteJson(`/api/finance/income/${pending.id}`);
        setPending(null);
        void client.invalidateQueries({ queryKey: ["finance-income"] });
      }} />
    </>
  );
}
