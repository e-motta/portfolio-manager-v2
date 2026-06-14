from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    label: str
    href: str
    prefix: str
    section: str | None = None


NAV_SECTIONS = [
    (
        "Portfolio",
        [
            NavItem("Dashboard", "/", "/", "Portfolio"),
            NavItem("Securities", "/portfolio/holdings", "/portfolio/holdings", "Portfolio"),
            NavItem("Other", "/portfolio/investments", "/portfolio/investments", "Portfolio"),
        ],
    ),
    (
        "Allocation",
        [
            NavItem("Asset Classes", "/allocation/classes", "/allocation/classes", "Allocation"),
            NavItem("Rebalancing", "/allocation/rebalance", "/allocation/rebalance", "Allocation"),
        ],
    ),
    (
        "Finance",
        [
            NavItem("Dashboard", "/finance/summary", "/finance/summary", "Finance"),
            NavItem("Income", "/finance/income", "/finance/income", "Finance"),
            NavItem("Expenses", "/finance/expenses", "/finance/expenses", "Finance"),
            NavItem("Transfers", "/finance/transfers", "/finance/transfers", "Finance"),
            NavItem("Investments", "/finance/investments", "/finance/investments", "Finance"),
        ],
    ),
    (
        "Data & sync",
        [
            NavItem("Snapshots", "/history", "/history"),
            NavItem("Backups", "/backups", "/backups"),
            NavItem("Open Finance", "/open-finance", "/open-finance"),
        ],
    ),
]

LEGACY_REDIRECTS = {
    "/securities": "/portfolio/holdings",
    "/investments": "/portfolio/investments",
    "/types": "/allocation/classes",
    "/suggestions": "/allocation/rebalance",
    "/snapshots": "/history",
}
