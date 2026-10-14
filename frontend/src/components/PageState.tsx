import type { UseQueryResult } from "@tanstack/react-query";

type PageStateProps = {
  query: UseQueryResult<unknown, Error>;
  loadingText?: string;
  children: React.ReactNode;
};

export function PageState({ query, loadingText = "Loading…", children }: PageStateProps) {
  if (query.isLoading) {
    return (
      <div className="page-state page-state--loading">
        <div className="page-state__skeleton">
          <div className="skeleton-stats">
            <div className="skeleton-block" />
            <div className="skeleton-block" />
            <div className="skeleton-block" />
            <div className="skeleton-block" />
          </div>
          <div className="skeleton-panel">
            <div className="skeleton-block skeleton-block--wide" />
            <div className="skeleton-table">
              <div className="skeleton-row" />
              <div className="skeleton-row" />
              <div className="skeleton-row" />
            </div>
          </div>
        </div>
        <p className="page-state__text">{loadingText}</p>
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="page-state page-state--error">
        <div className="page-state__error-box">
          <p className="page-state__error-title">Something went wrong</p>
          <p className="page-state__error-msg">{query.error?.message || "Could not load data"}</p>
          <button
            type="button"
            className="btn"
            onClick={() => void query.refetch()}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!query.data) {
    return (
      <div className="page-state page-state--empty">
        <p className="empty">No data available</p>
      </div>
    );
  }

  return <>{children}</>;
}
