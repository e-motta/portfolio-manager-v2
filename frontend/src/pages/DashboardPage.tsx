import { useQuery } from "@tanstack/react-query";
import { getJson } from "../api/client";
import { DonutChart } from "../components/DonutChart";
import { asNumber, formatBrl, formatPct, formatPctPoints, plClass } from "../lib/format";

type Dashboard = {
  rows: Array<{
    asset_type: { id: string; name: string; is_exchange_traded: boolean };
    current_value: string;
    current_weight: string;
    current_weight_allocation: string | null;
    target_weight: string | null;
    target_weight_allocation: string | null;
    drift: string | null;
    drift_value: string | null;
    has_target: boolean;
  }>;
  total_value: string;
  allocation_sleeve_value: string;
  allocation_target_sum: string;
  overweight: number;
  underweight: number;
};

export function DashboardPage() {
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => getJson<Dashboard>("/api/dashboard"),
  });

  if (query.isLoading) return <p className="empty">Loading portfolio…</p>;
  if (query.error) return <p className="empty">Could not load dashboard.</p>;
  const data = query.data!;
  const total = asNumber(data.total_value);
  const sleeve = asNumber(data.allocation_sleeve_value);
  const targetSum = asNumber(data.allocation_target_sum);
  const slices = data.rows
    .filter((row) => asNumber(row.current_value) > 0)
    .map((row) => ({ label: row.asset_type.name, value: asNumber(row.current_value) }));

  return (
    <>
      <p className="page-lead">
        Weights as % of total portfolio and % of the allocation sleeve · BRL
      </p>
      <dl className="stats">
        <div className="stat">
          <dt>Total value</dt>
          <dd>{formatBrl(data.total_value)}</dd>
        </div>
        <div className="stat">
          <dt>Allocation sleeve</dt>
          <dd>{formatBrl(data.allocation_sleeve_value)}</dd>
          <div className="meta">{total > 0 ? `${((sleeve / total) * 100).toFixed(1)}% of total` : "—"}</div>
        </div>
        <div className={`stat ${data.overweight ? "is-negative" : ""}`}>
          <dt>Overweight</dt>
          <dd>{data.overweight}</dd>
        </div>
        <div className={`stat ${data.underweight ? "is-positive" : ""}`}>
          <dt>Underweight</dt>
          <dd>{data.underweight}</dd>
        </div>
      </dl>
      <section className="panel">
        <div className="panel-head">
          <h2>Asset allocation</h2>
        </div>
        {targetSum > 0 && targetSum !== 1 ? (
          <p className="panel-body preview-note">
            Asset class targets sum to {(targetSum * 100).toFixed(1)}%
          </p>
        ) : null}
        <div className="panel-body">
          {slices.length ? (
            <DonutChart slices={slices} centerLabel="Portfolio" centerValue={formatBrl(data.total_value)} />
          ) : (
            <p className="empty">No positions yet. Add securities or other investments to see allocation.</p>
          )}
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Asset class</th>
                <th className="num">Market value</th>
                <th>Sleeve</th>
                <th className="num">Current total</th>
                <th className="num">Current sleeve</th>
                <th className="num">Target total</th>
                <th className="num">Target sleeve</th>
                <th className="num">Drift %</th>
                <th className="num">Drift R$</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => {
                const currentAlloc = asNumber(row.current_weight_allocation) * 100;
                const targetAlloc = asNumber(row.target_weight_allocation) * 100;
                const driftPct = asNumber(row.drift) * 100;
                return (
                  <tr key={row.asset_type.id} className={row.has_target ? "" : "row-untracked"}>
                    <td>
                      <div>{row.asset_type.name}</div>
                      <div className="cell-sub">
                        {row.asset_type.is_exchange_traded
                          ? "From securities"
                          : row.has_target
                            ? ""
                            : "Outside allocation"}
                      </div>
                    </td>
                    <td className="num">{formatBrl(row.current_value)}</td>
                    <td>
                      {row.has_target ? (
                        <div className="alloc-track" title={`Current ${currentAlloc.toFixed(1)}% · Target ${targetAlloc.toFixed(1)}%`}>
                          <div className="alloc-fill" style={{ width: `${Math.min(currentAlloc, targetAlloc)}%` }} />
                          {currentAlloc > targetAlloc ? (
                            <div className="alloc-fill excess" style={{ left: `${targetAlloc}%`, width: `${currentAlloc - targetAlloc}%` }} />
                          ) : (
                            <div className="alloc-fill gap" style={{ left: `${currentAlloc}%`, width: `${Math.max(0, targetAlloc - currentAlloc)}%` }} />
                          )}
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="num">{formatPct(row.current_weight)}</td>
                    <td className="num">{row.current_weight_allocation == null ? "—" : formatPct(row.current_weight_allocation)}</td>
                    <td className="num">{row.target_weight == null ? "—" : formatPct(row.target_weight)}</td>
                    <td className="num">{row.target_weight_allocation == null ? "—" : formatPct(row.target_weight_allocation)}</td>
                    <td className={`num ${plClass(driftPct)}`}>{row.drift == null ? "—" : formatPctPoints(driftPct)}</td>
                    <td className={`num ${plClass(row.drift_value)}`}>{row.drift_value == null ? "—" : formatBrl(row.drift_value)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
