import { useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AuthError, getJson } from "../api/client";
import { isActivePath, NAV_SECTIONS, type NavItem } from "../lib/nav";

type Session = {
  id: string;
  email: string;
  name: string;
  picture_url: string;
  display_timezone_label: string;
};

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
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

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  function titleForPath(): string {
    for (const section of NAV_SECTIONS) {
      for (const item of section.items) {
        if (isActivePath(location.pathname, item.href)) return item.label;
      }
    }
    return "Portfolio";
  }

  function signOut(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void fetch("/auth/logout", {
      method: "POST",
      credentials: "include",
      redirect: "manual",
    }).then(() => navigate("/auth/login"));
  }

  return (
    <div className="app-shell">
      <div
        className={`drawer-backdrop${menuOpen ? " is-open" : ""}`}
        onClick={() => setMenuOpen(false)}
      />
      <aside className={`sidebar${menuOpen ? " is-open" : ""}`} id="app-sidebar">
        <Link to="/" className="brand" onClick={() => setMenuOpen(false)}>
          <strong>Portfolio</strong>
          <span>Manager</span>
        </Link>
        <nav className="nav-scroll" aria-label="Main">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="nav-group">
              <div className="nav-label">{section.label}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.href}
                  to={item.href}
                  className={({ isActive }) =>
                    `nav-link${isActive || isActivePath(location.pathname, item.href) ? " is-active" : ""}`
                  }
                  onClick={() => setMenuOpen(false)}
                >
                  <NavIcon name={item.icon} />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="sidebar-user">
            {session.data?.picture_url ? (
              <img src={session.data.picture_url} alt="" />
            ) : (
              <span className="sidebar-user__initial" aria-hidden="true">
                {(session.data?.name || session.data?.email || "?").slice(0, 1).toUpperCase()}
              </span>
            )}
            <div className="sidebar-user__meta">
              <strong>{session.data?.name || "Signed in"}</strong>
              <span>{session.data?.email}</span>
            </div>
          </div>
          <form method="post" action="/auth/logout" onSubmit={signOut}>
            <button type="submit" className="sidebar-signout">
              Sign out
            </button>
          </form>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <button
            type="button"
            className="menu-btn"
            aria-expanded={menuOpen}
            aria-controls="app-sidebar"
            onClick={() => setMenuOpen(true)}
          >
            <span className="sr-only">Open menu</span>
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" strokeWidth="1.8" />
            </svg>
          </button>
          <h1>{titleForPath()}</h1>
          <div className="user-chip">
            {session.data?.picture_url ? <img src={session.data.picture_url} alt="" /> : null}
            <span>{session.data?.name || session.data?.email}</span>
          </div>
        </header>
        <div className="page">
          {session.isLoading ? <p className="empty">Loading…</p> : <Outlet />}
        </div>
      </div>
    </div>
  );
}

function NavIcon({ name }: { name: NavItem["icon"] }) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    "aria-hidden": true as const,
  };
  if (name === "home") {
    return <svg {...common}><path d="M4 11l8-7 8 7v8a2 2 0 0 1-2 2h-4v-6H10v6H6a2 2 0 0 1-2-2z" /></svg>;
  }
  if (name === "holdings") {
    return <svg {...common}><path d="M4 19V9l8-5 8 5v10H4zM4 19l8-5 8 5" /></svg>;
  }
  if (name === "other") {
    return <svg {...common}><path d="M6 8h12l1 11H5L6 8zM9 8V7a3 3 0 0 1 6 0v1" /></svg>;
  }
  if (name === "classes") {
    return <svg {...common}><path d="M12 4l8 4-8 4-8-4 8-4zM4 12l8 4 8-4M4 16l8 4 8-4" /></svg>;
  }
  if (name === "rebalance") {
    return <svg {...common}><path d="M7 4v16M17 4v16M4 8h6M14 16h6" /></svg>;
  }
  if (name === "summary") {
    return <svg {...common}><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M8 3v4M16 3v4M4 10h16" /></svg>;
  }
  if (name === "income") {
    return <svg {...common}><path d="M12 19V5M7 10l5-5 5 5" /></svg>;
  }
  if (name === "expenses") {
    return <svg {...common}><path d="M12 5v14M7 14l5 5 5-5" /></svg>;
  }
  if (name === "transfers") {
    return <svg {...common}><path d="M7 7h13l-3-3M17 17H4l3 3M7 7v3M17 17v-3" /></svg>;
  }
  if (name === "invest") {
    return <svg {...common}><path d="M4 19h16M7 19V9h3v10M14 19V5h3v14" /></svg>;
  }
  if (name === "history") {
    return <svg {...common}><circle cx="12" cy="12" r="8" /><path d="M12 8v5l3 2" /></svg>;
  }
  if (name === "backup") {
    return <svg {...common}><path d="M7 18a5 5 0 1 1 1.5-9.8A6 6 0 0 1 21 13a4 4 0 0 1-1 7H7z" /></svg>;
  }
  return <svg {...common}><path d="M3 10h18M5 10v8m14-8v8M3 18h18M12 4l9 6H3z" /></svg>;
}
