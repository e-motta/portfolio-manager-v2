import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { getJson } from "../api/client";
import { FinanceTabs } from "../components/FinanceTabs";
import { MonthChart } from "../components/MonthChart";
import { PeriodBar } from "../components/PeriodBar";
import { QueryFlash } from "../components/QueryFlash";
import { formatBrl, plClass } from "../lib/format";
import { useFinancePeriod } from "../lib/finance";

type Summary = {
  year: number;
  selected_month: number;
  year_options: number[];
  month_income: string;
  month_expenses: string;
  month_balance: string;
  year_income: string;
  year_expenses: string;
  year_balance: string;
  monthly_chart: { points: Array<{ month: number; label: string; income: number; expense: number; balance: number }> };
  summary_cards: Array<{
    id: string;
    title: string;
    subtitle: string;
    total_amount: string;
    manage_href: string;
    manage_label: string;
    lines: Array<{ label: string; amount: string; paid?: boolean }>;
  }>;
};

export function FinanceSummaryPage() {
  const { month, query } = useFinancePeriod();
  const navigate = useNavigate();
  const dataQuery = useQuery({
    queryKey: ["finance-summary", query],
    queryFn: () => getJson<Summary>(`/api/finance/summary?${query}`),
  });
  if (dataQuery.isLoading) return <p className="empty">Loading finance summary…</p>;
  const data = dataQuery.data!;
  const yearView = month == null;
  const income = yearView ? data.year_income : data.month_income;
  const expenses = yearView ? data.year_expenses : data.month_expenses;
  const balance = yearView ? data.year_balance : data.month_balance;

  return (
    <>
      <FinanceTabs />
      <QueryFlash />
      <PeriodBar year={data.year} month={month} yearOptions={data.year_options} basePath="/finance/summary" />
      <dl className="stats">
        <div className="stat is-positive">
          <dt>Income</dt>
          <dd>{formatBrl(income)}</dd>
          {yearView ? <div className="meta">Full year</div> : <div className="meta">YTD {formatBrl(data.year_income)}</div>}
        </div>
        <div className="stat is-negative">
          <dt>Expenses</dt>
          <dd>{formatBrl(expenses)}</dd>
          {yearView ? <div className="meta">Full year</div> : <div className="meta">YTD {formatBrl(data.year_expenses)}</div>}
        </div>
        <div className={`stat ${plClass(balance)}`}>
          <dt>Balance</dt>
          <dd>{formatBrl(balance)}</dd>
          {yearView ? <div className="meta">Full year</div> : <div className="meta">YTD {formatBrl(data.year_balance)}</div>}
        </div>
      </dl>
      <section className="panel">
        <div className="panel-head"><h2>Monthly trend</h2></div>
        <div className="panel-body">
          <MonthChart
            points={data.monthly_chart.points}
            selectedMonth={month}
            variant="summary"
            onSelect={(next) => navigate(`/finance/summary?year=${data.year}&month=${next}`)}
          />
        </div>
      </section>
      <div className="cards">
        {data.summary_cards.map((card) => (
          <article key={card.id} className="summary-card">
            <h3>{card.title}</h3>
            <p>{card.subtitle}</p>
            <div className={`total ${plClass(card.total_amount)}`}>{formatBrl(card.total_amount)}</div>
            {card.lines.map((line) => (
              <div key={line.label} className="summary-line">
                <span>{line.label}{line.paid === false ? " · unpaid" : ""}</span>
                <span>{formatBrl(line.amount)}</span>
              </div>
            ))}
            <div style={{ marginTop: "0.8rem" }}>
              <Link className="btn btn--ghost btn--sm" to={card.manage_href}>{card.manage_label}</Link>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
