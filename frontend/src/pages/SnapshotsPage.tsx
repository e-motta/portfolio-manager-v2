import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { deleteJson, getJson, sendForm } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { formatBrl, formatDate, formatDateTime, formatPct } from "../lib/format";

type SnapshotList = {
  today: string;
  snapshots: Array<{ id: string; snapshot_date: string; total_value: string; created_at: string }>;
  asset_class_names: string[];
  history_rows: Array<{
    snapshot: { id: string; snapshot_date: string; total_value: string };
    values_by_name: Record<string, string>;
    weights_by_name: Record<string, string>;
  }>;
};

export function SnapshotsPage() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["snapshots"],
    queryFn: () => getJson<SnapshotList>("/api/history"),
  });
  const [date, setDate] = useState("");
  const [pending, setPending] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => sendForm("/api/history", { snapshot_date: date || query.data?.today || "" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["snapshots"] }),
  });

  if (query.isLoading) return <p className="empty">Loading history…</p>;
  const data = query.data!;

  return (
    <>
      <div className="toolbar">
        <p className="page-lead" style={{ margin: 0 }}>
          Capture a point-in-time copy of allocation, holdings, and other investments.
        </p>
        <form className="btn-row" onSubmit={(event: FormEvent) => { event.preventDefault(); create.mutate(); }}>
          <input type="date" value={date || data.today} onChange={(event) => setDate(event.target.value)} />
          <button className="btn" type="submit">Capture</button>
        </form>
      </div>
      <section className="panel">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Date</th>
                <th className="num">Total</th>
                {data.asset_class_names.map((name) => <th key={name} className="num">{name}</th>)}
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.history_rows.map((row) => (
                <tr key={row.snapshot.id}>
                  <td><Link to={`/history/${row.snapshot.id}`}>{formatDate(row.snapshot.snapshot_date)}</Link></td>
                  <td className="num">{formatBrl(row.snapshot.total_value)}</td>
                  {data.asset_class_names.map((name) => (
                    <td key={name} className="num">{formatPct(row.weights_by_name[name])}</td>
                  ))}
                  <td className="num">
                    <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPending(row.snapshot.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <ConfirmDialog
        open={Boolean(pending)}
        title="Delete snapshot"
        message="Delete this snapshot?"
        onClose={() => setPending(null)}
        onConfirm={async () => {
          if (pending) await deleteJson(`/api/history/${pending}`);
          setPending(null);
          void client.invalidateQueries({ queryKey: ["snapshots"] });
        }}
      />
    </>
  );
}

type Detail = {
  snapshot: { snapshot_date: string; total_value: string; created_at: string };
  asset_classes: Array<{ name: string; current_value: string; current_weight: string; target_weight: string | null }>;
  investments: Array<{ institution: string; name: string; asset_type_name: string; current_value: string }>;
  holdings: Array<{ symbol: string; name: string; total_position: string; current_value_brl: string }>;
};

export function SnapshotDetailPage({ snapshotId }: { snapshotId: string }) {
  const query = useQuery({
    queryKey: ["snapshot", snapshotId],
    queryFn: () => getJson<Detail>(`/api/history/${snapshotId}`),
  });
  if (query.isLoading) return <p className="empty">Loading snapshot…</p>;
  if (!query.data) return <p className="empty">Snapshot not found.</p>;
  const data = query.data;

  return (
    <>
      <p className="page-lead">
        Captured {formatDateTime(data.snapshot.created_at)} · {formatBrl(data.snapshot.total_value)}
      </p>
      <section className="panel">
        <div className="panel-head"><h2>Asset classes</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Class</th><th className="num">Value</th><th className="num">Weight</th><th className="num">Target</th></tr></thead>
            <tbody>
              {data.asset_classes.map((row) => (
                <tr key={row.name}>
                  <td>{row.name}</td>
                  <td className="num">{formatBrl(row.current_value)}</td>
                  <td className="num">{formatPct(row.current_weight)}</td>
                  <td className="num">{row.target_weight == null ? "—" : formatPct(row.target_weight)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <div className="panel-head"><h2>Holdings</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Ticker</th><th>Name</th><th className="num">Qty</th><th className="num">Value</th></tr></thead>
            <tbody>
              {data.holdings.map((row) => (
                <tr key={row.symbol}>
                  <td>{row.symbol}</td>
                  <td>{row.name}</td>
                  <td className="num">{row.total_position}</td>
                  <td className="num">{formatBrl(row.current_value_brl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <div className="panel-head"><h2>Other investments</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead><tr><th>Institution</th><th>Name</th><th>Class</th><th className="num">Value</th></tr></thead>
            <tbody>
              {data.investments.map((row) => (
                <tr key={`${row.institution}-${row.name}`}>
                  <td>{row.institution}</td>
                  <td>{row.name}</td>
                  <td>{row.asset_type_name}</td>
                  <td className="num">{formatBrl(row.current_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
