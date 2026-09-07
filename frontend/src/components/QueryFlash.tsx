import { useSearchParams } from "react-router-dom";

function messageFromParams(params: URLSearchParams): { tone: "ok" | "error" | "warn"; text: string } | null {
  const error = params.get("error");
  if (error) return { tone: "error", text: error };

  const parts: string[] = [];
  const imported = params.get("imported");
  const expenses = params.get("expenses");
  const transfers = params.get("transfers");
  const investments = params.get("investments");
  const updated = params.get("updated");
  if (imported != null && imported !== "") {
    const n = Number(imported);
    parts.push(n === 1 ? "1 item imported" : `${imported} items imported`);
  }
  if (expenses) parts.push(`${expenses} expense${expenses === "1" ? "" : "s"}`);
  if (transfers) parts.push(`${transfers} transfer${transfers === "1" ? "" : "s"}`);
  if (investments) parts.push(`${investments} investment${investments === "1" ? "" : "s"}`);
  if (updated) parts.push(`${updated} updated`);
  if (params.get("connected")) parts.push("Connected.");
  if (params.get("disconnected")) parts.push("Disconnected.");
  if (params.get("saved")) parts.push("Saved.");
  if (params.get("restored")) parts.push("Restored.");
  if (params.get("deleted")) parts.push("Deleted.");
  if (!parts.length) return null;
  return { tone: "ok", text: parts.join(" · ") };
}

export function QueryFlash() {
  const [params, setParams] = useSearchParams();
  const notice = messageFromParams(params);
  if (!notice) return null;
  return (
    <div className={`alert alert--${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>
      <div className="alert-body">{notice.text}</div>
      <button
        type="button"
        className="alert-dismiss"
        aria-label="Dismiss"
        onClick={() => {
          const next = new URLSearchParams(params);
          for (const key of [
            "imported",
            "expenses",
            "transfers",
            "investments",
            "updated",
            "connected",
            "disconnected",
            "saved",
            "restored",
            "deleted",
            "error",
          ]) {
            next.delete(key);
          }
          setParams(next, { replace: true });
        }}
      >
        ×
      </button>
    </div>
  );
}
