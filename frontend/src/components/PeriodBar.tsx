import { Link, useNavigate } from "react-router-dom";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

type PeriodBarProps = {
  year: number;
  month: number | null;
  yearOptions: number[];
  basePath: string;
};

export function PeriodBar({ year, month, yearOptions, basePath }: PeriodBarProps) {
  const navigate = useNavigate();
  const href = (nextYear: number, nextMonth: number | null) => {
    const params = new URLSearchParams({ year: String(nextYear) });
    if (nextMonth) params.set("month", String(nextMonth));
    return `${basePath}?${params.toString()}`;
  };

  return (
    <div className="toolbar">
      <div className="month-pills">
        <Link to={href(year, null)} className={month === null ? "is-active" : ""}>
          Year
        </Link>
        {MONTHS.map((label, index) => {
          const value = index + 1;
          return (
            <Link
              key={label}
              to={href(year, value)}
              className={month === value ? "is-active" : ""}
            >
              {label}
            </Link>
          );
        })}
      </div>
      <label className="field" style={{ minWidth: "7rem" }}>
        <span className="sr-only">Year</span>
        <select
          value={year}
          onChange={(event) => {
            navigate(href(Number(event.target.value), month));
          }}
        >
          {yearOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
