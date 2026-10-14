import { useState } from "react";
import { formatBrl } from "../lib/format";
import { EXPENSE_CATEGORY_GROUPS, CATEGORY_GROUP_COLORS } from "../lib/chart";

export type RankedBarItem = {
  label: string;
  slug: string;
  value: number;
  count: number;
};

type RankedBarsProps = {
  items: RankedBarItem[];
  topN?: number;
  showGroupLegend?: boolean;
};

export function RankedBars({ items, topN = 8, showGroupLegend = true }: RankedBarsProps) {
  const [showAll, setShowAll] = useState(false);

  const sorted = [...items].sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
  const total = sorted.reduce((sum, item) => sum + Math.abs(item.value), 0);
  const maxValue = sorted.length > 0 ? Math.abs(sorted[0].value) : 1;

  const visibleItems = showAll ? sorted : sorted.slice(0, topN);
  const hiddenCount = sorted.length - topN;
  const hiddenTotal = sorted.slice(topN).reduce((sum, item) => sum + Math.abs(item.value), 0);

  function getCategoryColor(category: string): string {
    return EXPENSE_CATEGORY_GROUPS[category] || "#b0a090";
  }

  const groups = showGroupLegend ? Object.entries(CATEGORY_GROUP_COLORS) : [];

  return (
    <div
      className="ranked-bars"
      role="list"
      aria-label={`Expense categories ranked by amount, showing ${visibleItems.length} of ${sorted.length}`}
    >
      {showGroupLegend && groups.length > 0 ? (
        <div className="ranked-bars-legend" aria-hidden="true">
          {groups.map(([name, color]) => (
            <span key={name} className="ranked-bars-legend-item">
              <i style={{ background: color }} />
              {name}
            </span>
          ))}
        </div>
      ) : null}

      <div className="ranked-bars-list">
        {visibleItems.map((item, index) => {
          const absValue = Math.abs(item.value);
          const pct = total > 0 ? (absValue / total) * 100 : 0;
          const barWidth = maxValue > 0 ? (absValue / maxValue) * 100 : 0;
          const color = getCategoryColor(item.label);
          const pctFormatted = pct.toFixed(1).replace(".", ",");

          return (
            <a
              key={item.slug}
              href={`#category-${item.slug}`}
              className="ranked-bar-row"
              role="listitem"
              aria-label={`${index + 1}. ${item.label}: ${formatBrl(-absValue)}, ${pctFormatted}% of total, ${item.count} transactions`}
            >
              <span className="ranked-bar-label">{item.label}</span>
              <span className="ranked-bar-track" aria-hidden="true">
                <span
                  className="ranked-bar-fill"
                  style={{ width: `${barWidth}%`, background: color }}
                />
              </span>
              <span className="ranked-bar-amount">{formatBrl(-absValue)}</span>
              <span className="ranked-bar-pct">{pctFormatted}%</span>
              <span className="ranked-bar-count">{item.count}</span>
            </a>
          );
        })}
      </div>

      {hiddenCount > 0 && !showAll ? (
        <button
          type="button"
          className="ranked-bars-more"
          onClick={() => setShowAll(true)}
          aria-expanded="false"
        >
          +{hiddenCount} more ({formatBrl(-hiddenTotal)})
        </button>
      ) : null}

      {showAll && hiddenCount > 0 ? (
        <button
          type="button"
          className="ranked-bars-more"
          onClick={() => setShowAll(false)}
          aria-expanded="true"
        >
          Show less
        </button>
      ) : null}
    </div>
  );
}
