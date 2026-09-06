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
import { formatBrl, formatDate } from "../lib/format";
import { useFinancePeriod } from "../lib/finance";

type Entry = {
  id: string;
  month: number;
  from_account: string;
  to_account: string;
  amount: string;
  description: string;
  transaction_date: string | null;
};

type Payload = {
  year: number;
  filter_month: number | null;
  selected_month: number | null;
  form_default_month: number;
  year_options: number[];
  month_labels: string[];
  transfer_accounts: string[];
  entries: Entry[];
  year_total: string;
  monthly_chart: { points: Array<{ month: number; label: string; value: number }> };
};

export function FinanceTransfersPage() {
  const { query } = useFinancePeriod();
  const navigate = useNavigate();
  const client = useQueryClient();
  const dataQuery = useQuery({
    queryKey: ["finance-transfers", query],
    queryFn: () => getJson<Payload>(`/api/finance/transfers?${query}`),
  });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ month: "", from_account: "", to_account: "", amount: "", description: "", transaction_date: "" });
  const [pending, setPending] = useState<Entry | null>(null);
  const create = useMutation({
    mutationFn: (data: Record<string, string>) => sendForm("/api/finance/transfers", data),
    onSuccess: () => {
      setOpen(false);
      void client.invalidateQueries({ queryKey: ["finance-transfers"] });
    },
  });

  if (dataQuery.isLoading) return <p className="empty">Loading transfers…</p>;
  const data = dataQuery.data!;

  return (
    <>
      <FinanceTabs />
      <QueryFlash />
      <PeriodBar year={data.year} month={data.filter_month} yearOptions={data.year_options} basePath="/finance/transfers" />
      <div className="toolbar">
        <div className="stat"><dt>Year total</dt><dd>{formatBrl(data.year_total)}</dd></div>
        <button type="button" className="btn" onClick={() => setOpen(true)}>Add transfer</button>
      </div>
      <section className="panel">
        <div className="panel-body">
          <MonthChart points={data.monthly_chart.points} selectedMonth={data.filter_month} onSelect={(next) => navigate(`/finance/transfers?year=${data.year}&month=${next}`)} />
        </div>
      </section>
      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                {data.filter_month == null ? <th>Month</th> : null}
                <th>Date</th>
                <th>From</th>
                <th>To</th>
                <th>Description</th>
                <th className="num">Amount</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!data.entries.length ? (
                <tr><td colSpan={7}><EmptyState title="No transfers in this period" /></td></tr>
              ) : null}
              {data.entries.map((entry) => {
                const isEditing = editing === entry.id;
                return (
                  <tr key={entry.id}>
                    {data.filter_month == null ? <td>{isEditing ? <select className="compact" value={draft.month} onChange={(e) => setDraft({ ...draft, month: e.target.value })}>{data.month_labels.map((label, i) => <option key={label} value={i + 1}>{label}</option>)}</select> : data.month_labels[entry.month - 1]}</td> : null}
                    <td>{isEditing ? <input className="compact wide" type="date" value={draft.transaction_date} onChange={(e) => setDraft({ ...draft, transaction_date: e.target.value })} /> : formatDate(entry.transaction_date)}</td>
                    <td>{isEditing ? <select className="compact wide" value={draft.from_account} onChange={(e) => setDraft({ ...draft, from_account: e.target.value })}>{data.transfer_accounts.map((account) => <option key={account}>{account}</option>)}</select> : entry.from_account}</td>
                    <td>{isEditing ? <select className="compact wide" value={draft.to_account} onChange={(e) => setDraft({ ...draft, to_account: e.target.value })}>{data.transfer_accounts.map((account) => <option key={account}>{account}</option>)}</select> : entry.to_account}</td>
                    <td>{isEditing ? <input className="compact wide" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /> : entry.description}</td>
                    <td className="num">{isEditing ? <input className="compact" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} /> : formatBrl(entry.amount)}</td>
                    <td className="num">
                      {isEditing ? (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--sm" onClick={async () => {
                            await sendForm(`/api/finance/transfers/${entry.id}`, draft);
                            setEditing(null);
                            void client.invalidateQueries({ queryKey: ["finance-transfers"] });
                          }}>Save</button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>Cancel</button>
                        </div>
                      ) : (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => {
                            setEditing(entry.id);
                            setDraft({
                              month: String(entry.month),
                              from_account: entry.from_account,
                              to_account: entry.to_account,
                              amount: entry.amount,
                              description: entry.description,
                              transaction_date: entry.transaction_date || "",
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
      </section>
      <Modal open={open} title="Add transfer" onClose={() => setOpen(false)} footer={<button form="add-transfer" className="btn" type="submit">Save</button>}>
        <form id="add-transfer" className="form-grid" onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          create.mutate({
            year: String(data.year),
            month: String(form.get("month") || data.form_default_month),
            from_account: String(form.get("from_account") || ""),
            to_account: String(form.get("to_account") || ""),
            amount: String(form.get("amount") || ""),
            description: String(form.get("description") || ""),
            transaction_date: String(form.get("transaction_date") || ""),
          });
        }}>
          <label className="field">Month<select name="month" defaultValue={data.form_default_month}>{data.month_labels.map((label, i) => <option key={label} value={i + 1}>{label}</option>)}</select></label>
          <label className="field">Date<input type="date" name="transaction_date" /></label>
          <label className="field">From<select name="from_account">{data.transfer_accounts.map((account) => <option key={account}>{account}</option>)}</select></label>
          <label className="field">To<select name="to_account">{data.transfer_accounts.map((account) => <option key={account}>{account}</option>)}</select></label>
          <label className="field">Amount<input name="amount" required /></label>
          <label className="field">Description<input name="description" /></label>
        </form>
      </Modal>
      <ConfirmDialog open={Boolean(pending)} title="Delete transfer" message="Delete this transfer?" onClose={() => setPending(null)} onConfirm={async () => {
        if (pending) await deleteJson(`/api/finance/transfers/${pending.id}`);
        setPending(null);
        void client.invalidateQueries({ queryKey: ["finance-transfers"] });
      }} />
    </>
  );
}
