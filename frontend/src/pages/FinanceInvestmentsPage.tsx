import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { deleteJson, getJson, sendForm } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Modal } from "../components/Modal";
import { MonthChart } from "../components/MonthChart";
import { PeriodBar } from "../components/PeriodBar";
import { formatBrl } from "../lib/format";
import { useFinancePeriod } from "../lib/finance";

type Entry = { id: string; month: number; broker: string; amount: string };
type Payload = {
  year: number;
  filter_month: number | null;
  selected_month: number;
  form_default_month: number;
  year_options: number[];
  month_labels: string[];
  investment_brokers: Array<[string, string]>;
  entries: Entry[];
  annual_target: string;
  ytd_invested: string;
  month_invested: string;
  year_invested: string;
  monthly_chart: { points: Array<{ month: number; label: string; value: number }> };
  broker_lines: Array<{ broker: string; label: string; amount: string }>;
};

export function FinanceInvestmentsPage() {
  const { query } = useFinancePeriod();
  const navigate = useNavigate();
  const client = useQueryClient();
  const dataQuery = useQuery({
    queryKey: ["finance-investments", query],
    queryFn: () => getJson<Payload>(`/api/finance/investments?${query}`),
  });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ month: "", broker: "", amount: "" });
  const [pending, setPending] = useState<Entry | null>(null);
  const create = useMutation({
    mutationFn: (data: Record<string, string>) => sendForm("/api/finance/investments", data),
    onSuccess: () => {
      setOpen(false);
      void client.invalidateQueries({ queryKey: ["finance-investments"] });
    },
  });

  if (dataQuery.isLoading) return <p className="empty">Loading contributions…</p>;
  const data = dataQuery.data!;
  const brokers = data.investment_brokers || [];

  return (
    <>
      <PeriodBar year={data.year} month={data.filter_month} yearOptions={data.year_options} basePath="/finance/investments" />
      <dl className="stats">
        <div className="stat"><dt>Annual target</dt><dd>{formatBrl(data.annual_target)}</dd></div>
        <div className="stat"><dt>YTD invested</dt><dd>{formatBrl(data.ytd_invested)}</dd></div>
        <div className="stat"><dt>This month</dt><dd>{formatBrl(data.month_invested)}</dd></div>
        <div className="stat"><dt>Year invested</dt><dd>{formatBrl(data.year_invested)}</dd></div>
      </dl>
      <div className="toolbar">
        <div className="btn-row">
          {data.broker_lines.map((line) => (
            <span key={line.broker} className="badge badge--src">{line.label} {formatBrl(line.amount)}</span>
          ))}
        </div>
        <button type="button" className="btn" onClick={() => setOpen(true)}>Add contribution</button>
      </div>
      <section className="panel">
        <div className="panel-body">
          <MonthChart points={data.monthly_chart.points} selectedMonth={data.filter_month ?? data.selected_month} onSelect={(next) => navigate(`/finance/investments?year=${data.year}&month=${next}`)} />
        </div>
      </section>
      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                {data.filter_month == null ? <th>Month</th> : null}
                <th>Broker</th>
                <th className="num">Amount</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.entries.map((entry) => {
                const isEditing = editing === entry.id;
                const label = brokers.find((item) => item[0] === entry.broker)?.[1] || entry.broker;
                return (
                  <tr key={entry.id}>
                    {data.filter_month == null ? <td>{isEditing ? <select className="compact" value={draft.month} onChange={(e) => setDraft({ ...draft, month: e.target.value })}>{data.month_labels.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}</select> : data.month_labels[entry.month - 1]}</td> : null}
                    <td>{isEditing ? <select className="compact wide" value={draft.broker} onChange={(e) => setDraft({ ...draft, broker: e.target.value })}>{brokers.map((item) => <option key={item[0]} value={item[0]}>{item[1]}</option>)}</select> : label}</td>
                    <td className="num">{isEditing ? <input className="compact" value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} /> : formatBrl(entry.amount)}</td>
                    <td className="num">
                      {isEditing ? (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--sm" onClick={async () => {
                            await sendForm(`/api/finance/investments/${entry.id}`, draft);
                            setEditing(null);
                            void client.invalidateQueries({ queryKey: ["finance-investments"] });
                          }}>Save</button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>Cancel</button>
                        </div>
                      ) : (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => {
                            setEditing(entry.id);
                            setDraft({ month: String(entry.month), broker: entry.broker, amount: entry.amount });
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
      <Modal open={open} title="Add contribution" onClose={() => setOpen(false)} footer={<button form="add-fin-inv" className="btn" type="submit">Save</button>}>
        <form id="add-fin-inv" className="form-grid" onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          create.mutate({
            year: String(data.year),
            month: String(form.get("month") || data.form_default_month),
            broker: String(form.get("broker") || ""),
            amount: String(form.get("amount") || ""),
          });
        }}>
          <label className="field">Month<select name="month" defaultValue={data.form_default_month}>{data.month_labels.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}</select></label>
          <label className="field">Broker<select name="broker">{brokers.map((item) => <option key={item[0]} value={item[0]}>{item[1]}</option>)}</select></label>
          <label className="field">Amount<input name="amount" required /></label>
        </form>
      </Modal>
      <ConfirmDialog open={Boolean(pending)} title="Delete contribution" message="Delete this contribution?" onClose={() => setPending(null)} onConfirm={async () => {
        if (pending) await deleteJson(`/api/finance/investments/${pending.id}`);
        setPending(null);
        void client.invalidateQueries({ queryKey: ["finance-investments"] });
      }} />
    </>
  );
}
