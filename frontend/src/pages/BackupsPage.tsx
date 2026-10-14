import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getJson, sendForm } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState } from "../components/EmptyState";
import { QueryFlash } from "../components/QueryFlash";
import { showToast } from "../components/inputs";
import { formatDateTime } from "../lib/format";

type BackupsPayload = {
  google_configured: boolean;
  drive_connected: boolean;
};

type Backup = { file_id: string; name: string; created_at: string; size_bytes: number };

type BackupList = {
  backups: Backup[];
  drive_error: string | null;
};

export function BackupsPage() {
  const client = useQueryClient();
  const [pendingRestore, setPendingRestore] = useState<Backup | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Backup | null>(null);
  const [loading, setLoading] = useState<string | null>(null);

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
    onSuccess: () => {
      showToast("Backup created");
      void client.invalidateQueries({ queryKey: ["backups-list"] });
    },
    onError: (error) => {
      showToast(`Error creating backup: ${error instanceof Error ? error.message : "Unknown error"}`);
    },
  });

  async function handleRestore() {
    if (!pendingRestore) return;
    setLoading(pendingRestore.file_id);
    try {
      await sendForm(`/api/backups/${pendingRestore.file_id}/restore`, {});
      showToast("Backup restored successfully");
      void client.invalidateQueries();
    } catch (error) {
      showToast(`Error restoring backup: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setLoading(null);
      setPendingRestore(null);
    }
  }

  async function handleDelete() {
    if (!pendingDelete) return;
    setLoading(pendingDelete.file_id);
    try {
      await sendForm(`/api/backups/${pendingDelete.file_id}/delete`, {});
      showToast("Backup deleted");
      void client.invalidateQueries({ queryKey: ["backups-list"] });
    } catch (error) {
      showToast(`Error deleting backup: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setLoading(null);
      setPendingDelete(null);
    }
  }

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
          <button
            type="button"
            className="btn"
            disabled={create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Creating…" : "Create backup"}
          </button>
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
            <table className="data cards-sm">
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
                    <td className="card-primary" data-label="File">{file.name}</td>
                    <td data-label="Created">{formatDateTime(file.created_at)}</td>
                    <td className="num card-actions">
                      <div className="inline-edit">
                        <button
                          type="button"
                          className="btn btn--sm"
                          disabled={loading === file.file_id}
                          onClick={() => setPendingRestore(file)}
                        >
                          Restore
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          disabled={loading === file.file_id}
                          onClick={() => setPendingDelete(file)}
                        >
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

      <ConfirmDialog
        open={Boolean(pendingRestore)}
        title="Restore backup"
        message={pendingRestore
          ? `Restore "${pendingRestore.name}" from ${formatDateTime(pendingRestore.created_at)}? This will overwrite all current portfolio and finance data.`
          : ""}
        confirmLabel="Restore"
        danger={false}
        onConfirm={() => void handleRestore()}
        onClose={() => setPendingRestore(null)}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete backup"
        message={pendingDelete
          ? `Delete "${pendingDelete.name}" from ${formatDateTime(pendingDelete.created_at)}? This cannot be undone.`
          : ""}
        confirmLabel="Delete"
        danger={true}
        onConfirm={() => void handleDelete()}
        onClose={() => setPendingDelete(null)}
      />
    </>
  );
}
