import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useMemo, useState } from "react";
import { getJson } from "../api/client";
import { ComparisonChart } from "../components/ComparisonChart";
import { EmptyState } from "../components/EmptyState";
import { Segmented } from "../components/Segmented";
import { asNumber, formatBrl, formatPct, formatSignedBrl, formatSignedUsd, formatUsd, parseDecimalInput } from "../lib/format";

type Suggestion = {
  id: string;
  label: string;
  current_value: string;
  current_weight: string;
  target_weight: string;
  ideal_value: string;
  delta: string;
  action: string;
};

type Payload = {
  suggestions: Suggestion[];
  currency: "BRL" | "USD";
};

export function RebalancePage() {
  const [level, setLevel] = useState<"types" | "securities">("types");
  const [mode, setMode] = useState<"buy_only" | "buy_and_sell">("buy_only");
  const [cashInput, setCashInput] = useState("0");
  
  const parsedCash = useMemo(() => {
    const parsed = parseDecimalInput(cashInput);
    return parsed !== null ? parsed : "0";
  }, [cashInput]);
  
  const deferredCash = useDeferredValue(parsedCash);
  
  const meta = useQuery({
    queryKey: ["rebalance-meta"],
    queryFn: () => getJson<{ usd_brl_rate: string }>("/api/allocation/rebalance"),
  });
  const rate = asNumber(meta.data?.usd_brl_rate) || 1;
  
  const query = useQuery({
    queryKey: ["rebalance", level, mode, deferredCash],
    queryFn: () =>
      getJson<Payload>(
        `/api/allocation/rebalance/${level}?mode=${mode}&new_cash=${encodeURIComponent(deferredCash)}`,
      ),
  });

  const usdCash = useMemo(() => {
    const brl = asNumber(parsedCash);
    return rate ? (brl / rate).toFixed(2) : "0.00";
  }, [parsedCash, rate]);

  const formatMoney = level === "securities" ? formatUsd : formatBrl;
  const formatSigned = level === "securities" ? formatSignedUsd : formatSignedBrl;

  return (
    <>
      <p className="page-lead">
        Cash-only scales buys to the amount you can deploy. Full rebalance includes sells.
      </p>
      <div className="toolbar">
        <div className="btn-row">
          <Segmented
            label="Rebalance level"
            value={level}
            onChange={setLevel}
            options={[
              { value: "types", label: "By asset class" },
              { value: "securities", label: "By holding" },
            ]}
          />
          <Segmented
            label="Rebalance mode"
            value={mode}
            onChange={setMode}
            options={[
              { value: "buy_only", label: "Cash only" },
              { value: "buy_and_sell", label: "Full rebalance" },
            ]}
          />
        </div>
        <div className="btn-row">
          <label className="field">
            Cash to deploy (BRL)
            <input
              id="suggestion-cash"
              inputMode="decimal"
              autoComplete="off"
              value={cashInput}
              onChange={(event) => setCashInput(event.target.value)}
              onBlur={() => {
                const parsed = parseDecimalInput(cashInput);
                if (parsed !== null) {
                  setCashInput(parsed);
                }
              }}
            />
          </label>
          <label className="field">
            Cash to deploy (USD)
            <input id="suggestion-cash-usd" value={usdCash} readOnly />
          </label>
        </div>
      </div>
      {(query.data?.suggestions || []).length ? (
        <section className="panel">
          <div className="panel-head"><h2>Current vs target</h2></div>
          <div className="panel-body">
            <ComparisonChart
              rows={(query.data?.suggestions || []).map((item) => ({
                label: item.label,
                current: item.current_weight,
                target: item.target_weight,
              }))}
            />
          </div>
        </section>
      ) : null}
      <section className="panel">
        <div className="table-wrap">
          <table className="data cards-sm">
            <thead>
              <tr>
                <th>{level === "types" ? "Asset class" : "Holding"}</th>
                <th className="num">Current</th>
                <th className="num">Current %</th>
                <th className="num">Target %</th>
                <th className="num">Ideal</th>
                <th>Action</th>
                <th className="num">Adjustment</th>
              </tr>
            </thead>
            <tbody>
              {!(query.data?.suggestions || []).length ? (
                <tr><td colSpan={7}><EmptyState title="No suggestions" body="Set target weights on asset classes or holdings first." /></td></tr>
              ) : null}
              {(query.data?.suggestions || []).map((item) => (
                <tr key={item.id}>
                  <td className="card-primary" data-label={level === "types" ? "Asset class" : "Holding"}>{item.label}</td>
                  <td className="num hide-on-mobile" data-label="Current">{formatMoney(item.current_value)}</td>
                  <td className="num hide-on-mobile" data-label="Current %">{formatPct(item.current_weight)}</td>
                  <td className="num hide-on-mobile" data-label="Target %">{formatPct(item.target_weight)}</td>
                  <td className="num hide-on-mobile" data-label="Ideal">{formatMoney(item.ideal_value)}</td>
                  <td data-label="Action">
                    <span className="badge badge--action">{item.action === "buy" ? "BUY ▲" : item.action === "sell" ? "SELL ▼" : item.action.toUpperCase()}</span>
                  </td>
                  <td className="num" data-label="Adjustment">{formatSigned(item.delta)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
