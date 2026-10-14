export function asNumber(value: unknown): number {
  if (value === null || value === undefined || value === "") return 0;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function asOptionalNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

const brlFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const brlCompactFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
});

export function formatBrl(value: unknown): string {
  const amount = asNumber(value);
  return brlFormatter.format(amount);
}

export function formatCompactBrl(value: unknown): string {
  const amount = asNumber(value);
  const abs = Math.abs(amount);
  if (abs >= 10_000) {
    return brlCompactFormatter.format(amount);
  }
  return formatBrl(amount);
}

export function parseDecimalInput(text: string): string | null {
  if (!text || typeof text !== "string") return null;
  let cleaned = text.trim();
  cleaned = cleaned.replace(/^R\$\s*/i, "");
  cleaned = cleaned.replace(/^\$\s*/, "");
  cleaned = cleaned.replace(/[^\d.,-]/g, "");
  if (!cleaned) return null;
  const hasComma = cleaned.includes(",");
  const hasDot = cleaned.includes(".");
  if (hasComma && hasDot) {
    const lastComma = cleaned.lastIndexOf(",");
    const lastDot = cleaned.lastIndexOf(".");
    if (lastComma > lastDot) {
      cleaned = cleaned.replace(/\./g, "").replace(",", ".");
    } else {
      cleaned = cleaned.replace(/,/g, "");
    }
  } else if (hasComma) {
    const parts = cleaned.split(",");
    if (parts.length === 2 && parts[1].length <= 2) {
      cleaned = cleaned.replace(",", ".");
    } else {
      cleaned = cleaned.replace(/,/g, "");
    }
  }
  const n = parseFloat(cleaned);
  if (!Number.isFinite(n)) return null;
  return n.toFixed(2);
}

export function formatUsd(value: unknown): string {
  const amount = asNumber(value);
  const absolute = Math.abs(amount).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return amount < 0 ? `-$${absolute}` : `$${absolute}`;
}

export function formatSignedUsd(value: unknown): string {
  const amount = asNumber(value);
  const absolute = Math.abs(amount).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (amount > 0) return `+$${absolute}`;
  if (amount < 0) return `-$${absolute}`;
  return `$${absolute}`;
}

export function formatSignedBrl(value: unknown): string {
  const amount = asNumber(value);
  const formatted = brlFormatter.format(Math.abs(amount));
  if (amount > 0) return `+${formatted}`;
  if (amount < 0) return `-${formatted}`;
  return formatted;
}

export function formatPct(value: unknown, digits = 1): string {
  const amount = asOptionalNumber(value);
  if (amount === null) return "—";
  const pct = amount * 100;
  const formatted = new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(pct);
  return `${formatted}%`;
}

export function formatPctPoints(value: unknown, digits = 1): string {
  const amount = asOptionalNumber(value);
  if (amount === null) return "—";
  const formatted = new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(amount);
  if (amount > 0) return `+${formatted}%`;
  return `${formatted}%`;
}

export function formatQty(value: unknown, digits = 4): string {
  const amount = asNumber(value);
  return amount.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  });
}

export function formatDate(value: unknown): string {
  if (!value) return "—";
  const text = String(value);
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return text;
  return `${match[3]}/${match[2]}/${match[1]}`;
}

export function formatDateTime(value: unknown, zoneLabel = "BRT"): string {
  if (!value) return "—";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  const formatted = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  }).format(date);
  return `${formatted} ${zoneLabel}`;
}

export function plClass(value: unknown): string {
  const amount = asNumber(value);
  if (amount > 0) return "is-positive";
  if (amount < 0) return "is-negative";
  return "is-neutral";
}

export function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}
