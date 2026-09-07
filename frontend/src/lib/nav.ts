export type NavItem = {
  label: string;
  href: string;
};

export type NavSection = {
  label: string;
  items: NavItem[];
};

export const NAV_SECTIONS: NavSection[] = [
  {
    label: "Portfolio",
    items: [
      { label: "Dashboard", href: "/" },
      { label: "Securities", href: "/portfolio/holdings" },
      { label: "Other", href: "/portfolio/investments" },
    ],
  },
  {
    label: "Allocation",
    items: [
      { label: "Asset classes", href: "/allocation/classes" },
      { label: "Rebalancing", href: "/allocation/rebalance" },
    ],
  },
  {
    label: "Finance",
    items: [
      { label: "Dashboard", href: "/finance/summary" },
      { label: "Income", href: "/finance/income" },
      { label: "Expenses", href: "/finance/expenses" },
      { label: "Transfers", href: "/finance/transfers" },
      { label: "Investments", href: "/finance/investments" },
    ],
  },
  {
    label: "Data & sync",
    items: [
      { label: "Snapshots", href: "/history" },
      { label: "Backups", href: "/backups" },
      { label: "Open Finance", href: "/open-finance" },
    ],
  },
];

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
