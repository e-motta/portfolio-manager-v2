import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { deleteJson, getJson, sendForm } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { Modal } from "../components/Modal";
import { formatPct } from "../lib/format";

type AssetTypeRow = {
  asset_type: {
    id: string;
    name: string;
    target_pct: string | null;
    is_exchange_traded: boolean;
  };
  asset_count: number;
  has_target: boolean;
};

type Payload = {
  asset_types: AssetTypeRow[];
  target_total: string;
  weighted_count: number;
};

export function AssetClassesPage() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["asset-classes"],
    queryFn: () => getJson<Payload>("/api/allocation/classes"),
  });
  const [open, setOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<AssetTypeRow | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name: "", target_pct: "" });

  const create = useMutation({
    mutationFn: (data: Record<string, string>) => sendForm("/api/allocation/classes", data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["asset-classes"] });
      setOpen(false);
    },
  });

  const update = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, string> }) =>
      sendForm(`/api/allocation/classes/${id}`, data),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["asset-classes"] });
      setEditing(null);
    },
  });

  async function remove() {
    if (!pendingDelete) return;
    await deleteJson(`/api/allocation/classes/${pendingDelete.asset_type.id}`);
    setPendingDelete(null);
    void client.invalidateQueries({ queryKey: ["asset-classes"] });
  }

  if (query.isLoading) return <p className="empty">Loading asset classes…</p>;
  const data = query.data!;
  const total = Number(data.target_total) * 100;

  return (
    <>
      <div className="toolbar">
        <p className="page-lead" style={{ margin: 0 }}>
          Target weights across the full portfolio. Listed securities cannot be removed.
        </p>
        <button type="button" className="btn" onClick={() => setOpen(true)}>
          Add class
        </button>
      </div>
      <p>
        {data.weighted_count === 0
          ? "No target weights set"
          : Math.abs(total - 100) < 0.05
            ? <span className="badge badge--ok">Targets = 100%</span>
            : <span className="badge badge--warn">Targets = {total.toFixed(1)}%</span>}
      </p>
      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Class</th>
                <th className="num">Assets</th>
                <th className="num">Target</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!data.asset_types.length ? (
                <tr><td colSpan={4}><EmptyState title="No asset classes" /></td></tr>
              ) : null}
              {data.asset_types.map((row) => {
                const isEditing = editing === row.asset_type.id;
                return (
                  <tr key={row.asset_type.id}>
                    <td>
                      {isEditing ? (
                        <input
                          className="compact wide"
                          value={draft.name}
                          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                        />
                      ) : (
                        row.asset_type.name
                      )}
                    </td>
                    <td className="num">{row.asset_count}</td>
                    <td className="num">
                      {isEditing ? (
                        <input
                          className="compact"
                          value={draft.target_pct}
                          placeholder="—"
                          onChange={(event) => setDraft({ ...draft, target_pct: event.target.value })}
                        />
                      ) : row.has_target ? (
                        formatPct(row.asset_type.target_pct)
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="num">
                      <div className="inline-edit">
                        {isEditing ? (
                          <>
                            <button
                              type="button"
                              className="btn btn--sm"
                              onClick={() =>
                                update.mutate({
                                  id: row.asset_type.id,
                                  data: { name: draft.name, target_pct: draft.target_pct },
                                })
                              }
                            >
                              Save
                            </button>
                            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm"
                              onClick={() => {
                                setEditing(row.asset_type.id);
                                setDraft({
                                  name: row.asset_type.name,
                                  target_pct: row.has_target
                                    ? (Number(row.asset_type.target_pct) * 100).toFixed(1)
                                    : "",
                                });
                              }}
                            >
                              Edit
                            </button>
                            {row.asset_type.is_exchange_traded ? null : (
                              <button
                                type="button"
                                className="btn btn--ghost btn--sm"
                                onClick={() => setPendingDelete(row)}
                              >
                                Delete
                              </button>
                            )}
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
      <Modal
        open={open}
        title="Add asset class"
        onClose={() => setOpen(false)}
        footer={
          <button
            type="submit"
            form="add-class"
            className="btn"
          >
            Save
          </button>
        }
      >
        <form
          id="add-class"
          className="form-grid"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            create.mutate({
              name: String(form.get("name") || ""),
              target_pct: String(form.get("target_pct") || ""),
            });
          }}
        >
          <label className="field">
            Name
            <input name="name" required />
          </label>
          <label className="field">
            Target %
            <input name="target_pct" placeholder="Optional" />
          </label>
        </form>
      </Modal>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete class"
        message={`Delete ${pendingDelete?.asset_type.name}? Positions in this class will be removed.`}
        onClose={() => setPendingDelete(null)}
        onConfirm={() => void remove()}
      />
    </>
  );
}
