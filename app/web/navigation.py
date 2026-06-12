from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    label: str
    href: str
    prefix: str
    section: str | None = None


NAV_SECTIONS = [
    ("Overview", [NavItem("Dashboard", "/", "/")]),
    (
        "Portfolio",
        [
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
    ("History", [NavItem("Snapshots", "/history", "/history")]),
]

LEGACY_REDIRECTS = {
    "/securities": "/portfolio/holdings",
    "/investments": "/portfolio/investments",
    "/types": "/allocation/classes",
    "/suggestions": "/allocation/rebalance",
    "/snapshots": "/history",
}
