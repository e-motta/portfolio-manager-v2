import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { getJson } from "../api/client";
import { ComparisonChart } from "../components/ComparisonChart";
import { EmptyState } from "../components/EmptyState";
import { Segmented } from "../components/Segmented";
import { asNumber, formatBrl, formatSignedBrl, formatSignedUsd, formatUsd } from "../lib/format";

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
  const [cash, setCash] = useState("0");
  const meta = useQuery({
    queryKey: ["rebalance-meta"],
    queryFn: () => getJson<{ usd_brl_rate: string }>("/api/allocation/rebalance"),
  });
  const rate = asNumber(meta.data?.usd_brl_rate) || 1;
  const cashValue = cash;
  const query = useQuery({
    queryKey: ["rebalance", level, mode, cashValue],
    queryFn: () =>
      getJson<Payload>(
        `/api/allocation/rebalance/${level}?mode=${mode}&new_cash=${encodeURIComponent(cashValue || "0")}`,
      ),
  });

  const usdCash = useMemo(() => {
    const brl = asNumber(cash);
    return rate ? (brl / rate).toFixed(2) : "0.00";
  }, [cash, rate]);

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
            <input id="suggestion-cash" value={cash} onChange={(event) => setCash(event.target.value)} />
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
          <table className="data">
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
                  <td>{item.label}</td>
                  <td className="num">{formatMoney(item.current_value)}</td>
                  <td className="num">{(asNumber(item.current_weight) * 100).toFixed(1)}%</td>
                  <td className="num">{(asNumber(item.target_weight) * 100).toFixed(1)}%</td>
                  <td className="num">{formatMoney(item.ideal_value)}</td>
                  <td>
                    <span className={`badge badge--${item.action}`}>{item.action}</span>
                  </td>
                  <td className="num">{formatSigned(item.delta)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
