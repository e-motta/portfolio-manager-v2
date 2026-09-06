import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { deleteJson, getJson, sendForm } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Modal } from "../components/Modal";
import { formatBrl, formatDateTime, formatPct } from "../lib/format";

type Investment = {
  id: string;
  institution: string;
  name: string;
  current_value: string;
  asset_type_id: string;
  asset_type_name: string | null;
  updated_at: string;
  source_label: string;
};

type Payload = {
  investments: Investment[];
  institution_summaries: Array<{
    institution: string;
    position_count: number;
    total_value: string;
    weight: string;
  }>;
  asset_types: Array<{ id: string; name: string }>;
  total_current: string;
  investment_count: number;
};

export function OtherInvestmentsPage() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["other-investments"],
    queryFn: () => getJson<Payload>("/api/portfolio/investments"),
  });
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ institution: "", name: "", asset_type_id: "", current_value: "" });
  const [pending, setPending] = useState<Investment | null>(null);

  const create = useMutation({
    mutationFn: (data: Record<string, string>) => sendForm("/api/portfolio/investments", data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["other-investments"] });
      setOpen(false);
    },
  });
  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, string> }) =>
      sendForm(`/api/portfolio/investments/${id}`, data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["other-investments"] });
      setEditing(null);
    },
  });

  async function remove() {
    if (!pending) return;
    await deleteJson(`/api/portfolio/investments/${pending.id}`);
    setPending(null);
    void client.invalidateQueries({ queryKey: ["other-investments"] });
  }

  if (query.isLoading) return <p className="empty">Loading investments…</p>;
  const data = query.data!;

  return (
    <>
      <div className="toolbar">
        <p className="page-lead" style={{ margin: 0 }}>
          Positions outside listed securities, grouped by bank or institution.
        </p>
        <button type="button" className="btn" onClick={() => setOpen(true)}>
          Add investment
        </button>
      </div>
      <dl className="stats">
        <div className="stat">
          <dt>Total</dt>
          <dd>{formatBrl(data.total_current)}</dd>
        </div>
        <div className="stat">
          <dt>Positions</dt>
          <dd>{data.investment_count}</dd>
        </div>
      </dl>
      <section className="panel">
        <div className="panel-head"><h2>By bank / institution</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Institution</th>
                <th className="num">Positions</th>
                <th className="num">Value</th>
                <th className="num">Weight</th>
              </tr>
            </thead>
            <tbody>
              {data.institution_summaries.map((row) => (
                <tr key={row.institution}>
                  <td>{row.institution}</td>
                  <td className="num">{row.position_count}</td>
                  <td className="num">{formatBrl(row.total_value)}</td>
                  <td className="num">{formatPct(row.weight)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <div className="panel-head"><h2>Positions</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Institution</th>
                <th>Name</th>
                <th>Class</th>
                <th className="num">Value</th>
                <th>Updated</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.investments.map((item) => {
                const isEditing = editing === item.id;
                return (
                  <tr key={item.id}>
                    <td>
                      {isEditing ? (
                        <input className="compact wide" value={draft.institution} onChange={(e) => setDraft({ ...draft, institution: e.target.value })} />
                      ) : item.institution}
                    </td>
                    <td>
                      {isEditing ? (
                        <input className="compact wide" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                      ) : item.name}
                    </td>
                    <td>
                      {isEditing ? (
                        <select className="compact wide" value={draft.asset_type_id} onChange={(e) => setDraft({ ...draft, asset_type_id: e.target.value })}>
                          {data.asset_types.map((type) => (
                            <option key={type.id} value={type.id}>{type.name}</option>
                          ))}
                        </select>
                      ) : item.asset_type_name}
                    </td>
                    <td className="num">
                      {isEditing ? (
                        <input className="compact" value={draft.current_value} onChange={(e) => setDraft({ ...draft, current_value: e.target.value })} />
                      ) : formatBrl(item.current_value)}
                    </td>
                    <td>{formatDateTime(item.updated_at)}</td>
                    <td className="num">
                      <div className="inline-edit">
                        {isEditing ? (
                          <>
                            <button type="button" className="btn btn--sm" onClick={() => update.mutate({ id: item.id, data: draft })}>Save</button>
                            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>Cancel</button>
                          </>
                        ) : (
                          <>
                            <button type="button" className="btn btn--ghost btn--sm" onClick={() => {
                              setEditing(item.id);
                              setDraft({
                                institution: item.institution,
                                name: item.name,
                                asset_type_id: item.asset_type_id,
                                current_value: item.current_value,
                              });
                            }}>Edit</button>
                            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPending(item)}>Delete</button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <Modal open={open} title="Add investment" onClose={() => setOpen(false)} footer={<button form="add-inv" className="btn" type="submit">Save</button>}>
        <form id="add-inv" className="form-grid" onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          create.mutate({
            asset_type_id: String(form.get("asset_type_id") || ""),
            institution: String(form.get("institution") || ""),
            name: String(form.get("name") || ""),
            current_value: String(form.get("current_value") || ""),
          });
        }}>
          <label className="field">Institution<input name="institution" required /></label>
          <label className="field">Name<input name="name" required /></label>
          <label className="field">
            Asset class
            <select name="asset_type_id" required>
              {data.asset_types.map((type) => <option key={type.id} value={type.id}>{type.name}</option>)}
            </select>
          </label>
          <label className="field">Current value (BRL)<input name="current_value" required /></label>
        </form>
      </Modal>
      <ConfirmDialog
        open={Boolean(pending)}
        title="Delete investment"
        message={`Delete ${pending?.name}?`}
        onClose={() => setPending(null)}
        onConfirm={() => void remove()}
      />
    </>
  );
}
