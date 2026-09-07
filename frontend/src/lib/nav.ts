export type NavItem = {
  label: string;
  href: string;
  icon: "home" | "holdings" | "other" | "classes" | "rebalance" | "summary" | "income" | "expenses" | "transfers" | "invest" | "history" | "backup" | "bank";
};

export type NavSection = {
  label: string;
  items: NavItem[];
};

export const NAV_SECTIONS: NavSection[] = [
  {
    label: "Portfolio",
    items: [
      { label: "Dashboard", href: "/", icon: "home" },
      { label: "Securities", href: "/portfolio/holdings", icon: "holdings" },
      { label: "Other investments", href: "/portfolio/investments", icon: "other" },
    ],
  },
  {
    label: "Allocation",
    items: [
      { label: "Asset classes", href: "/allocation/classes", icon: "classes" },
      { label: "Rebalancing", href: "/allocation/rebalance", icon: "rebalance" },
    ],
  },
  {
    label: "Finance",
    items: [
      { label: "Summary", href: "/finance/summary", icon: "summary" },
      { label: "Income", href: "/finance/income", icon: "income" },
      { label: "Expenses", href: "/finance/expenses", icon: "expenses" },
      { label: "Transfers", href: "/finance/transfers", icon: "transfers" },
      { label: "Investments", href: "/finance/investments", icon: "invest" },
    ],
  },
  {
    label: "Data & sync",
    items: [
      { label: "Snapshots", href: "/history", icon: "history" },
      { label: "Backups", href: "/backups", icon: "backup" },
      { label: "Open Finance", href: "/open-finance", icon: "bank" },
    ],
  },
];

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
