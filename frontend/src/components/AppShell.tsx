import { useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AuthError, getJson } from "../api/client";
import { isActivePath, NAV_SECTIONS } from "../lib/nav";

type Session = {
  id: string;
  email: string;
  name: string;
  picture_url: string;
  display_timezone_label: string;
};

const LAYOUT_KEY = "portfolio-nav-layout";

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [layout, setLayout] = useState<"sidebar" | "top">(
    () => (localStorage.getItem(LAYOUT_KEY) === "top" ? "top" : "sidebar"),
  );
  const [menuOpen, setMenuOpen] = useState(false);

  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => getJson<Session>("/api/me"),
    retry: false,
  });

  useEffect(() => {
    if (session.error instanceof AuthError) {
      navigate("/auth/login", { replace: true });
    }
  }, [session.error, navigate]);

  function setNavLayout(next: "sidebar" | "top") {
    setLayout(next);
    localStorage.setItem(LAYOUT_KEY, next);
  }

  function titleForPath(): string {
    for (const section of NAV_SECTIONS) {
      for (const item of section.items) {
        if (isActivePath(location.pathname, item.href)) return item.label;
      }
    }
    return "Portfolio";
  }

  const nav = (
    <nav className={layout === "top" ? "topnav-menu" : "nav-scroll"}>
      {NAV_SECTIONS.map((section) => (
        <div key={section.label}>
          {layout === "sidebar" ? <div className="nav-label">{section.label}</div> : null}
          {section.items.map((item) => (
            <NavLink
              key={item.href}
              to={item.href}
              className={({ isActive }) =>
                layout === "top"
                  ? isActive || isActivePath(location.pathname, item.href)
                    ? "is-active"
                    : ""
                  : `nav-link${isActive || isActivePath(location.pathname, item.href) ? " is-active" : ""}`
              }
              onClick={() => setMenuOpen(false)}
            >
              {item.label}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  );

  return (
    <div className={`app-shell${layout === "top" ? " is-top" : ""}`}>
      <div
        className={`drawer-backdrop${menuOpen ? " is-open" : ""}`}
        onClick={() => setMenuOpen(false)}
      />
      <aside className={`sidebar${menuOpen ? " is-open" : ""}`}>
        <Link to="/" className="brand" onClick={() => setMenuOpen(false)}>
          <strong>Portfolio</strong>
          <span>Manager</span>
        </Link>
        {nav}
        <div className="sidebar-foot">
          <div className="layout-toggle">
            <button
              type="button"
              className={layout === "sidebar" ? "is-active" : ""}
              onClick={() => setNavLayout("sidebar")}
            >
              Side
            </button>
            <button
              type="button"
              className={layout === "top" ? "is-active" : ""}
              onClick={() => setNavLayout("top")}
            >
              Top
            </button>
          </div>
        </div>
      </aside>
      <div className="app-main">
        <header className="topnav">
          <Link to="/" className="brand">
            <strong>Portfolio</strong>
            <span>Manager</span>
          </Link>
          {nav}
        </header>
        <header className="topbar">
          <button type="button" className="menu-btn" onClick={() => setMenuOpen(true)}>
            Menu
          </button>
          <h1>{titleForPath()}</h1>
          <div className="user-chip">
            {session.data?.picture_url ? (
              <img src={session.data.picture_url} alt="" />
            ) : null}
            <span>{session.data?.name || session.data?.email}</span>
            <form
              method="post"
              action="/auth/logout"
              onSubmit={(event: FormEvent<HTMLFormElement>) => {
                event.preventDefault();
                void fetch("/auth/logout", {
                  method: "POST",
                  credentials: "include",
                  redirect: "manual",
                }).then(() => navigate("/auth/login"));
              }}
            >
              <button type="submit" className="btn btn--ghost btn--sm">
                Sign out
              </button>
            </form>
          </div>
        </header>
        <div className="page">
          {session.isLoading ? <p className="empty">Loading…</p> : <Outlet />}
        </div>
      </div>
    </div>
  );
}
