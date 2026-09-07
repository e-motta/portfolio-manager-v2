import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { deleteJson, getJson, sendForm } from "../api/client";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DonutChart } from "../components/DonutChart";
import { EmptyState } from "../components/EmptyState";
import { FileDrop } from "../components/FileDrop";
import { Modal } from "../components/Modal";
import { Segmented } from "../components/Segmented";
import {
  asNumber,
  formatBrl,
  formatDate,
  formatDateTime,
  formatPct,
  formatPctPoints,
  formatQty,
  formatSignedBrl,
  formatSignedUsd,
  formatUsd,
  plClass,
  todayIso,
} from "../lib/format";

type Lot = {
  id: string;
  symbol: string;
  name: string;
  position: string;
  purchase_date: string;
  purchase_price_usd: string;
  usd_brl_rate: string;
  provisional_fx: boolean;
  source: string;
  cost_basis_usd: string;
};

type Dividend = {
  id: string;
  symbol: string;
  pay_date: string;
  gross_amount_usd: string;
  withholding_tax_usd: string;
  net_amount_usd: string;
  source: string;
};

type Holding = {
  symbol: string;
  name: string;
  total_position: string;
  avg_purchase_price_usd: string;
  current_price_usd: string;
  current_value_brl: string;
  current_weight: string;
  target_pct: string;
  pl_usd: string;
  pl_brl: string;
  has_provisional_fx: boolean;
};

type ReturnRow = {
  symbol: string;
  name: string;
  unrealized_pl_usd: string;
  dividend_net_usd: string;
  total_return_usd: string;
  total_return_brl: string;
  total_return_pct_usd: string | null;
  total_return_pct_brl: string | null;
};

type ImportPreview = {
  error?: string;
  rows?: Array<Record<string, unknown>>;
  import_token?: string;
  new_count?: number;
  existing_count?: number;
  has_trades?: boolean;
  has_dividends?: boolean;
};

type Payload = {
  consolidated: Holding[];
  security_returns: ReturnRow[];
  lots: Lot[];
  dividends: Dividend[];
  total_brl: string;
  total_current_usd: string;
  total_pl_usd: string;
  total_pl_brl: string;
  unrealized_pl_usd: string;
  dividend_net_usd: string;
  lot_count: number;
  symbol_count: number;
  last_prices_at: string | null;
  provisional_fx_count: number;
  target_total_display: string;
  target_total_balanced: boolean;
  today: string;
};

export function HoldingsPage() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["holdings"],
    queryFn: () => getJson<Payload>("/api/portfolio/holdings"),
  });
  const [tradeOpen, setTradeOpen] = useState(false);
  const [divOpen, setDivOpen] = useState(false);
  const [importKind, setImportKind] = useState<"lots" | "dividends" | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [editingTarget, setEditingTarget] = useState<string | null>(null);
  const [targetDraft, setTargetDraft] = useState("");
  const [editingLot, setEditingLot] = useState<string | null>(null);
  const [lotDraft, setLotDraft] = useState({ purchase_date: "", position: "", purchase_price_usd: "", usd_brl_rate: "" });
  const [editingDiv, setEditingDiv] = useState<string | null>(null);
  const [divDraft, setDivDraft] = useState({ pay_date: "", gross_amount_usd: "", withholding_tax_usd: "" });
  const [pendingLot, setPendingLot] = useState<Lot | null>(null);
  const [pendingDiv, setPendingDiv] = useState<Dividend | null>(null);
  const [section, setSection] = useState<"positions" | "performance" | "lots" | "dividends">("positions");

  const refreshPrices = useMutation({
    mutationFn: () => sendForm("/api/prices/refresh", {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["holdings"] }),
  });
  const refreshPtax = useMutation({
    mutationFn: () => sendForm("/api/portfolio/holdings/ptax/refresh", {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["holdings"] }),
  });
  const createTrade = useMutation({
    mutationFn: (data: Record<string, string>) => sendForm("/api/portfolio/holdings/lots", data),
    onSuccess: () => {
      setTradeOpen(false);
      void client.invalidateQueries({ queryKey: ["holdings"] });
    },
  });
  const createDiv = useMutation({
    mutationFn: (data: Record<string, string>) => sendForm("/api/portfolio/holdings/dividends", data),
    onSuccess: () => {
      setDivOpen(false);
      void client.invalidateQueries({ queryKey: ["holdings"] });
    },
  });

  const symbols = useMemo(
    () => Array.from(new Set((query.data?.consolidated || []).map((item) => item.symbol))),
    [query.data],
  );

  async function uploadStatement(file: File) {
    const path =
      importKind === "dividends"
        ? "/api/portfolio/holdings/dividends/import/preview"
        : "/api/portfolio/holdings/import/preview";
    const body = new FormData();
    body.append("statement", file);
    const response = await fetch(path, { method: "POST", body, credentials: "include" });
    const payload = (await response.json()) as ImportPreview;
    setPreview(payload);
    const rows = payload.rows || [];
    setSelected(
      rows
        .filter((row) => !row.already_exists)
        .map((row) => String(row.lot_key || row.dividend_key)),
    );
  }

  async function confirmImport() {
    const path =
      importKind === "dividends"
        ? "/api/portfolio/holdings/dividends/import/confirm"
        : "/api/portfolio/holdings/import/confirm";
    const key = importKind === "dividends" ? "dividends" : "lots";
    await sendForm(path, {
      import_token: String(preview?.import_token || ""),
      [key]: selected,
    });
    setImportKind(null);
    setPreview(null);
    void client.invalidateQueries({ queryKey: ["holdings"] });
  }

  if (query.isLoading) return <p className="empty">Loading securities and market data…</p>;
  if (!query.data) return <p className="empty">Could not load holdings.</p>;
  const data = query.data;

  return (
    <>
      <div className="toolbar">
        <p className="page-lead" style={{ margin: 0 }} id="securities-subtitle">
          {data.symbol_count} tickers · {data.lot_count} lots
          {data.last_prices_at ? ` · Prices ${formatDateTime(data.last_prices_at)}` : ""}
        </p>
        <div className="btn-row">
          <button type="button" className="btn" onClick={() => setTradeOpen(true)}>Add trade</button>
          <button type="button" className="btn btn--ghost" onClick={() => setDivOpen(true)}>Add dividend</button>
          <button type="button" className="btn btn--ghost" onClick={() => refreshPrices.mutate()}>Refresh prices</button>
          {data.provisional_fx_count > 0 ? (
            <button type="button" className="btn btn--ghost" onClick={() => refreshPtax.mutate()}>
              Update PTAX rates
            </button>
          ) : null}
          <button type="button" className="btn btn--ghost" onClick={() => { setImportKind("lots"); setPreview(null); }}>
            Import IB lots
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => { setImportKind("dividends"); setPreview(null); }}>
            Preview dividends
          </button>
        </div>
      </div>
      <dl className="stats">
        <div className="stat"><dt>Market value</dt><dd>{formatBrl(data.total_brl)}</dd></div>
        <div className="stat"><dt>Value (USD)</dt><dd>{formatUsd(data.total_current_usd)}</dd></div>
        <div className={`stat ${plClass(data.total_pl_usd)}`}><dt>Total return</dt><dd>{formatSignedUsd(data.total_pl_usd)}</dd></div>
        <div className="stat"><dt>Dividends net (USD)</dt><dd>{formatUsd(data.dividend_net_usd)}</dd></div>
      </dl>
      <p>
        {Number(data.target_total_display) === 0 ? (
          <span className="badge badge--warn">No target weights set</span>
        ) : data.target_total_balanced ? (
          <span className="badge badge--ok">Targets = 100%</span>
        ) : (
          <span className="badge badge--warn">Targets = {data.target_total_display}%</span>
        )}
      </p>
      <div className="toolbar">
        <Segmented
          label="Holdings sections"
          value={section}
          onChange={setSection}
          options={[
            { value: "positions", label: "Positions" },
            { value: "performance", label: "Performance" },
            { value: "lots", label: "Tax lots" },
            { value: "dividends", label: "Dividends" },
          ]}
        />
      </div>
      {section === "positions" ? (
      <section className="panel">
        <div className="panel-head"><h2>Positions by ticker</h2></div>
        {data.consolidated.length ? (
          <div className="panel-body">
            <DonutChart
              slices={data.consolidated.map((item) => ({ label: item.symbol, value: asNumber(item.current_value_brl) }))}
              centerLabel="Securities"
            />
          </div>
        ) : (
          <EmptyState title="No securities yet" body="Add a trade or import an Interactive Brokers statement." />
        )}
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Ticker</th>
                <th className="num">Qty</th>
                <th className="num">Avg cost</th>
                <th className="num">Last</th>
                <th className="num">Value</th>
                <th className="num">Weight</th>
                <th className="num">Target</th>
                <th className="num">P/L</th>
              </tr>
            </thead>
            <tbody>
              {data.consolidated.map((item) => (
                <tr key={item.symbol}>
                  <td>
                    <div>{item.symbol}</div>
                    <div className="cell-sub">{item.name}</div>
                  </td>
                  <td className="num">{formatQty(item.total_position)}</td>
                  <td className="num">{formatUsd(item.avg_purchase_price_usd)}</td>
                  <td className="num">{formatUsd(item.current_price_usd)}</td>
                  <td className="num">{formatBrl(item.current_value_brl)}</td>
                  <td className="num">{formatPct(item.current_weight)}</td>
                  <td className="num">
                    {editingTarget === item.symbol ? (
                      <span className="inline-edit">
                        <input className="compact" value={targetDraft} onChange={(e) => setTargetDraft(e.target.value)} />
                        <button type="button" className="btn btn--sm" onClick={async () => {
                          await sendForm(`/api/portfolio/holdings/symbols/${item.symbol}`, { target_pct: targetDraft });
                          setEditingTarget(null);
                          void client.invalidateQueries({ queryKey: ["holdings"] });
                        }}>Save</button>
                      </span>
                    ) : (
                      <button type="button" className="btn btn--ghost btn--sm" onClick={() => {
                        setEditingTarget(item.symbol);
                        setTargetDraft((Number(item.target_pct) * 100).toFixed(1));
                      }}>{formatPct(item.target_pct)}</button>
                    )}
                  </td>
                  <td className={`num ${plClass(item.pl_usd)}`}>{formatSignedUsd(item.pl_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      ) : null}
      {section === "performance" ? (
      <section className="panel">
        <div className="panel-head"><h2>Performance by ticker</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Ticker</th>
                <th className="num">Unrealized</th>
                <th className="num">Dividends net (USD)</th>
                <th className="num">Total return (USD)</th>
                <th className="num">Total return (BRL)</th>
                <th className="num">%</th>
              </tr>
            </thead>
            <tbody>
              {!data.security_returns.length ? (
                <tr><td colSpan={6}><EmptyState title="No performance data yet" /></td></tr>
              ) : null}
              {data.security_returns.map((item) => (
                <tr key={item.symbol}>
                  <td>{item.symbol}</td>
                  <td className={`num ${plClass(item.unrealized_pl_usd)}`}>{formatSignedUsd(item.unrealized_pl_usd)}</td>
                  <td className="num">{formatUsd(item.dividend_net_usd)}</td>
                  <td className={`num ${plClass(item.total_return_usd)}`}>{formatSignedUsd(item.total_return_usd)}</td>
                  <td className={`num ${plClass(item.total_return_brl)}`}>{formatSignedBrl(item.total_return_brl)}</td>
                  <td className={`num ${plClass(item.total_return_pct_usd)}`}>{formatPctPoints(item.total_return_pct_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      ) : null}
      {section === "lots" ? (
      <section className="panel">
        <div className="panel-head"><h2>Tax lots</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Trade date</th>
                <th className="num">Qty</th>
                <th className="num">Price</th>
                <th className="num">FX</th>
                <th>Source</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!data.lots.length ? (
                <tr><td colSpan={7}><EmptyState title="No tax lots yet" /></td></tr>
              ) : null}
              {data.lots.map((lot) => {
                const isEditing = editingLot === lot.id;
                return (
                  <tr key={lot.id}>
                    <td>{lot.symbol}</td>
                    <td>{isEditing ? <input className="compact wide" type="date" value={lotDraft.purchase_date} onChange={(e) => setLotDraft({ ...lotDraft, purchase_date: e.target.value })} /> : formatDate(lot.purchase_date)}</td>
                    <td className="num">{isEditing ? <input className="compact" value={lotDraft.position} onChange={(e) => setLotDraft({ ...lotDraft, position: e.target.value })} /> : formatQty(lot.position)}</td>
                    <td className="num">{isEditing ? <input className="compact" value={lotDraft.purchase_price_usd} onChange={(e) => setLotDraft({ ...lotDraft, purchase_price_usd: e.target.value })} /> : formatUsd(lot.purchase_price_usd)}</td>
                    <td className="num">
                      {isEditing ? <input className="compact" value={lotDraft.usd_brl_rate} onChange={(e) => setLotDraft({ ...lotDraft, usd_brl_rate: e.target.value })} /> : lot.usd_brl_rate}
                      {lot.provisional_fx ? <span className="badge badge--warn">est.</span> : null}
                    </td>
                    <td>{lot.source}</td>
                    <td className="num">
                      {isEditing ? (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--sm" onClick={async () => {
                            await sendForm(`/api/portfolio/holdings/lots/${lot.id}`, lotDraft);
                            setEditingLot(null);
                            void client.invalidateQueries({ queryKey: ["holdings"] });
                          }}>Save</button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditingLot(null)}>Cancel</button>
                        </div>
                      ) : (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => {
                            setEditingLot(lot.id);
                            setLotDraft({
                              purchase_date: lot.purchase_date,
                              position: lot.position,
                              purchase_price_usd: lot.purchase_price_usd,
                              usd_brl_rate: lot.usd_brl_rate,
                            });
                          }}>Edit</button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPendingLot(lot)}>Delete</button>
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
      ) : null}
      {section === "dividends" ? (
      <section className="panel">
        <div className="panel-head"><h2>Dividends</h2></div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Pay date</th>
                <th className="num">Gross</th>
                <th className="num">Withholding</th>
                <th className="num">Net</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!data.dividends.length ? (
                <tr><td colSpan={6}><EmptyState title="No dividends recorded" /></td></tr>
              ) : null}
              {data.dividends.map((item) => {
                const isEditing = editingDiv === item.id;
                return (
                  <tr key={item.id}>
                    <td>{item.symbol}</td>
                    <td>{isEditing ? <input className="compact wide" type="date" value={divDraft.pay_date} onChange={(e) => setDivDraft({ ...divDraft, pay_date: e.target.value })} /> : formatDate(item.pay_date)}</td>
                    <td className="num">{isEditing ? <input className="compact" value={divDraft.gross_amount_usd} onChange={(e) => setDivDraft({ ...divDraft, gross_amount_usd: e.target.value })} /> : formatUsd(item.gross_amount_usd)}</td>
                    <td className="num">{isEditing ? <input className="compact" value={divDraft.withholding_tax_usd} onChange={(e) => setDivDraft({ ...divDraft, withholding_tax_usd: e.target.value })} /> : formatUsd(item.withholding_tax_usd)}</td>
                    <td className="num">{formatUsd(item.net_amount_usd)}</td>
                    <td className="num">
                      {isEditing ? (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--sm" onClick={async () => {
                            await sendForm(`/api/portfolio/holdings/dividends/${item.id}`, divDraft);
                            setEditingDiv(null);
                            void client.invalidateQueries({ queryKey: ["holdings"] });
                          }}>Save</button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditingDiv(null)}>Cancel</button>
                        </div>
                      ) : (
                        <div className="inline-edit">
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => {
                            setEditingDiv(item.id);
                            setDivDraft({
                              pay_date: item.pay_date,
                              gross_amount_usd: item.gross_amount_usd,
                              withholding_tax_usd: item.withholding_tax_usd,
                            });
                          }}>Edit</button>
                          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setPendingDiv(item)}>Delete</button>
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
      ) : null}
      <Modal open={tradeOpen} title="Add trade" onClose={() => setTradeOpen(false)} footer={<button form="add-trade" className="btn" type="submit">Save</button>}>
        <form id="add-trade" className="form-grid" onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          createTrade.mutate(Object.fromEntries(form.entries()) as Record<string, string>);
        }}>
          <label className="field">Symbol<input name="symbol" required /></label>
          <label className="field">Trade date<input name="purchase_date" type="date" defaultValue={data.today || todayIso()} required /></label>
          <label className="field">Quantity<input name="position" required /></label>
          <label className="field">Price (USD)<input name="purchase_price_usd" required /></label>
          <label className="field">USD/BRL (optional)<input name="usd_brl_rate" /></label>
        </form>
      </Modal>
      <Modal open={divOpen} title="Add dividend" onClose={() => setDivOpen(false)} footer={<button form="add-div" className="btn" type="submit">Save</button>}>
        <form id="add-div" className="form-grid" onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          createDiv.mutate(Object.fromEntries(form.entries()) as Record<string, string>);
        }}>
          <label className="field">
            Symbol
            <input name="symbol" list="holding-symbols" required />
          </label>
          <datalist id="holding-symbols">
            {symbols.map((symbol) => <option key={symbol} value={symbol} />)}
          </datalist>
          <label className="field">Pay date<input name="pay_date" type="date" defaultValue={data.today || todayIso()} required /></label>
          <label className="field">Gross (USD)<input name="gross_amount_usd" required /></label>
          <label className="field">Withholding (USD)<input name="withholding_tax_usd" defaultValue="0" /></label>
        </form>
      </Modal>
      <Modal
        open={importKind !== null}
        title={importKind === "dividends" ? "Import dividends" : "Import tax lots"}
        wide
        onClose={() => setImportKind(null)}
        footer={preview?.import_token && (preview.rows || []).length ? (
          <button type="button" className="btn" onClick={() => void confirmImport()}>
            {importKind === "dividends" ? "Add selected dividends" : "Add selected tax lots"}
          </button>
        ) : null}
      >
        <FileDrop
          accept=".csv,text/csv"
          label="Interactive Brokers statement"
          hint="CSV from Activity / Trades or Dividends"
          onFile={(file) => void uploadStatement(file)}
        />
        {preview?.error ? <p className="login-error">{preview.error}</p> : null}
        {preview && !preview.error && importKind === "lots" && preview.has_trades === false ? (
          <p>No trades found in this statement</p>
        ) : null}
        {preview?.rows?.length ? (
          <div className="table-wrap" style={{ marginTop: "1rem" }}>
            <table className="data">
              <thead>
                <tr>
                  <th>
                    <input
                      type="checkbox"
                      checked={selected.length > 0}
                      onChange={(event) => {
                        if (event.target.checked) {
                          setSelected((preview.rows || []).filter((row) => !row.already_exists).map((row) => String(row.lot_key || row.dividend_key)));
                        } else setSelected([]);
                      }}
                    />
                  </th>
                  <th>Ticker</th>
                  <th>{importKind === "dividends" ? "Pay date" : "Trade date"}</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {(preview.rows || []).map((row) => {
                  const key = String(row.lot_key || row.dividend_key);
                  return (
                    <tr key={key}>
                      <td>
                        <input
                          type="checkbox"
                          disabled={Boolean(row.already_exists)}
                          checked={selected.includes(key)}
                          onChange={(event) => {
                            setSelected((current) => event.target.checked ? [...current, key] : current.filter((item) => item !== key));
                          }}
                        />
                      </td>
                      <td>{String(row.symbol)}</td>
                      <td>{formatDate(row.trade_date || row.pay_date)}</td>
                      <td>{row.already_exists ? "In portfolio · already imported" : "New"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </Modal>
      <ConfirmDialog open={Boolean(pendingLot)} title="Delete lot" message={`Delete ${pendingLot?.symbol} lot?`} onClose={() => setPendingLot(null)} onConfirm={async () => {
        if (pendingLot) await deleteJson(`/api/portfolio/holdings/lots/${pendingLot.id}`);
        setPendingLot(null);
        void client.invalidateQueries({ queryKey: ["holdings"] });
      }} />
      <ConfirmDialog open={Boolean(pendingDiv)} title="Delete dividend" message={`Delete ${pendingDiv?.symbol} dividend?`} onClose={() => setPendingDiv(null)} onConfirm={async () => {
        if (pendingDiv) await deleteJson(`/api/portfolio/holdings/dividends/${pendingDiv.id}`);
        setPendingDiv(null);
        void client.invalidateQueries({ queryKey: ["holdings"] });
      }} />
    </>
  );
}
