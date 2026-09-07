import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getJson, sendForm } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { QueryFlash } from "../components/QueryFlash";
import { formatDateTime } from "../lib/format";

type BackupsPayload = {
  google_configured: boolean;
  drive_connected: boolean;
};

type BackupList = {
  backups: Array<{ file_id: string; name: string; created_at: string; size_bytes: number }>;
  drive_error: string | null;
};

export function BackupsPage() {
  const client = useQueryClient();
  const page = useQuery({
    queryKey: ["backups"],
    queryFn: () => getJson<BackupsPayload>("/api/backups"),
  });
  const list = useQuery({
    queryKey: ["backups-list"],
    queryFn: () => getJson<BackupList>("/api/backups/partials/list"),
    enabled: Boolean(page.data?.drive_connected),
    retry: false,
  });

  const create = useMutation({
    mutationFn: () => sendForm("/api/backups/create", {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["backups-list"] }),
  });

  if (page.isLoading) return <p className="empty">Loading backups…</p>;
  const data = page.data!;

  return (
    <>
      <p className="page-lead">JSON backups of portfolio and finance data, stored in Google Drive.</p>
      <QueryFlash />
      {!data.google_configured ? (
        <div className="connect-card">
          <h2>Google Drive is not set up</h2>
          <p>Ask an administrator to configure Google sign-in for this environment before connecting Drive backups.</p>
        </div>
      ) : !data.drive_connected ? (
        <div className="connect-card">
          <h2>Connect Google Drive</h2>
          <p>Store encrypted JSON backups of this portfolio in your Drive so you can restore later.</p>
          <a className="btn" href="/api/backups/google/connect">Connect Google Drive</a>
        </div>
      ) : (
        <div className="toolbar">
          <button type="button" className="btn" onClick={() => create.mutate()}>Create backup</button>
        </div>
      )}
      {list.data?.drive_error ? (
        <p className="login-error">
          {list.data.drive_error} <a href="/api/backups/google/connect">Reconnect Google Drive</a>
        </p>
      ) : null}
      {list.data?.backups?.length ? (
        <section className="panel">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Created</th>
                  <th className="num">Actions</th>
                </tr>
              </thead>
              <tbody>
                {list.data.backups.map((file) => (
                  <tr key={file.file_id}>
                    <td>{file.name}</td>
                    <td>{formatDateTime(file.created_at)}</td>
                    <td className="num">
                      <div className="inline-edit">
                        <button type="button" className="btn btn--sm" onClick={() => void sendForm(`/api/backups/${file.file_id}/restore`, {}).then(() => client.invalidateQueries())}>
                          Restore
                        </button>
                        <button type="button" className="btn btn--ghost btn--sm" onClick={() => void sendForm(`/api/backups/${file.file_id}/delete`, {}).then(() => client.invalidateQueries({ queryKey: ["backups-list"] }))}>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : data.drive_connected && !list.isLoading ? (
        <EmptyState title="No backups yet" body="Create a backup to copy the current portfolio into Drive." />
      ) : null}
    </>
  );
}
