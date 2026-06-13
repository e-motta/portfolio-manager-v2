const financeChartInstances = new Map();

const FINANCE_CHART_COLORS = {
  income: { default: "#059669", selected: "#047857" },
  expense: { default: "#dc2626", selected: "#991b1b" },
  balance: {
    positive: { default: "#059669", selected: "#047857" },
    negative: { default: "#dc2626", selected: "#991b1b" },
    zero: "#e5e7eb",
  },
};

function formatSignedBrl(value) {
  const amount = Number(value);
  const formatted = Math.abs(amount).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (amount > 0) {
    return `+R$ ${formatted}`;
  }
  if (amount < 0) {
    return `-R$ ${formatted}`;
  }
  return `R$ ${formatted}`;
}

function chartBarValue(point, variant) {
  if (variant === "income") {
    return Math.max(point.value, 0);
  }
  return Math.abs(point.value);
}

function chartBarColor(point, config) {
  const selected = point.month === config.selectedMonth;
  if (config.variant === "income") {
    const palette = FINANCE_CHART_COLORS.income;
    return selected ? palette.selected : palette.default;
  }
  if (config.variant === "expense") {
    const palette = FINANCE_CHART_COLORS.expense;
    return selected ? palette.selected : palette.default;
  }
  if (point.value > 0) {
    const palette = FINANCE_CHART_COLORS.balance.positive;
    return selected ? palette.selected : palette.default;
  }
  if (point.value < 0) {
    const palette = FINANCE_CHART_COLORS.balance.negative;
    return selected ? palette.selected : palette.default;
  }
  return FINANCE_CHART_COLORS.balance.zero;
}

function buildHitboxSeries(config, maxValue) {
  return {
    id: "hitbox",
    type: "custom",
    data: config.points.map((point) => ({
      month: point.month,
      rawValue: point.value,
    })),
    renderItem(params, api) {
      const categoryIndex = params.dataIndex;
      const bandWidth = api.size([1, 0])[0];
      const top = api.coord([categoryIndex, maxValue]);
      const bottom = api.coord([categoryIndex, 0]);
      const width = bandWidth * 0.92;
      const height = bottom[1] - top[1];
      const x = top[0] - width / 2;

      return {
        type: "rect",
        shape: {
          x,
          y: top[1],
          width,
          height,
        },
        style: {
          fill: "transparent",
        },
        emphasis: {
          style: {
            fill: "transparent",
          },
        },
      };
    },
    tooltip: { show: false },
    cursor: "pointer",
    z: 10,
  };
}

function buildFinanceChartOption(config) {
  const labels = config.points.map((point) => point.label);
  const seriesData = config.points.map((point) => ({
    value: chartBarValue(point, config.variant),
    rawValue: point.value,
    month: point.month,
    itemStyle: {
      color: chartBarColor(point, config),
      borderRadius: [6, 6, 2, 2],
    },
  }));
  const maxValue = Math.max(...seriesData.map((point) => point.value), 1);

  return {
    aria: {
      enabled: true,
      label: { description: config.ariaLabel },
    },
    animationDuration: 350,
    grid: {
      left: 12,
      right: 12,
      top: 16,
      bottom: 8,
      containLabel: true,
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter(params) {
        const item =
          params.find((entry) => entry.seriesId === "values") ?? params[0];
        if (!item) {
          return "";
        }
        const rawValue = item.data.rawValue ?? item.data.value;
        return `${item.axisValue}<br>${formatSignedBrl(rawValue)}`;
      },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisTick: { alignWithLabel: true },
      axisLine: { lineStyle: { color: "#d1d5db" } },
      axisLabel: {
        color: "#6b7280",
        fontSize: 11,
        fontWeight: 600,
      },
    },
    yAxis: {
      type: "value",
      show: false,
      min: 0,
    },
    series: [
      {
        id: "values",
        type: "bar",
        data: seriesData,
        barMaxWidth: 32,
      },
      buildHitboxSeries(config, maxValue),
    ],
  };
}

function destroyFinanceCharts(root = document) {
  root.querySelectorAll(".finance-echart").forEach((element) => {
    const chart = financeChartInstances.get(element);
    if (chart) {
      chart.dispose();
      financeChartInstances.delete(element);
    }
  });
}

function navigateToFinanceMonth(config, month) {
  if (!month) {
    return;
  }
  window.location.assign(`${config.linkBase}?year=${config.year}&month=${month}`);
}

function bindFinanceChartInteractions(chart, config) {
  chart.on("click", "series", (params) => {
    if (params.seriesId !== "hitbox") {
      return;
    }
    navigateToFinanceMonth(config, params.data?.month);
  });
}

function initFinanceCharts(root = document) {
  if (typeof echarts === "undefined") {
    return;
  }

  root.querySelectorAll(".finance-echart").forEach((element) => {
    if (financeChartInstances.has(element)) {
      return;
    }

    let config;
    try {
      config = JSON.parse(element.dataset.chart || "{}");
    } catch (_) {
      return;
    }

    const chart = echarts.init(element);
    chart.setOption(buildFinanceChartOption(config));
    bindFinanceChartInteractions(chart, config);

    financeChartInstances.set(element, chart);
  });
}

function resizeFinanceCharts() {
  financeChartInstances.forEach((chart) => chart.resize());
}

document.addEventListener("DOMContentLoaded", () => initFinanceCharts());
window.addEventListener("resize", resizeFinanceCharts);
document.body.addEventListener("htmx:beforeSwap", (event) => {
  destroyFinanceCharts(event.detail.target);
});
document.body.addEventListener("htmx:afterSwap", (event) => {
  initFinanceCharts(event.detail.target);
});
