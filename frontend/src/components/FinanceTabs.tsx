import { NavLink, useSearchParams } from "react-router-dom";

const TABS = [
  { href: "/finance/summary", label: "Summary" },
  { href: "/finance/income", label: "Income" },
  { href: "/finance/expenses", label: "Expenses" },
  { href: "/finance/transfers", label: "Transfers" },
  { href: "/finance/investments", label: "Investments" },
];

export function FinanceTabs() {
  const [params] = useSearchParams();
  const qs = params.toString();
  const suffix = qs ? `?${qs}` : "";

  return (
    <nav className="subnav" aria-label="Finance">
      {TABS.map((tab) => (
        <NavLink
          key={tab.href}
          to={`${tab.href}${suffix}`}
          className={({ isActive }) => (isActive ? "is-active" : "")}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
