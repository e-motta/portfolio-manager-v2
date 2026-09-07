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

export function formatBrl(value: unknown): string {
  const amount = asNumber(value);
  const absolute = Math.abs(amount).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return amount < 0 ? `-R$\u00a0${absolute}` : `R$\u00a0${absolute}`;
}

export function formatCompactBrl(value: unknown): string {
  const amount = asNumber(value);
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(amount);
  if (abs >= 1_000_000) return `${sign}R$\u00a0${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `${sign}R$\u00a0${(abs / 1000).toFixed(0)}k`;
  return formatBrl(amount);
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
  const absolute = Math.abs(amount).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (amount > 0) return `+R$\u00a0${absolute}`;
  if (amount < 0) return `-R$\u00a0${absolute}`;
  return `R$\u00a0${absolute}`;
}

export function formatPct(value: unknown, digits = 1): string {
  const amount = asOptionalNumber(value);
  if (amount === null) return "—";
  return `${(amount * 100).toFixed(digits)}%`;
}

export function formatPctPoints(value: unknown, digits = 1): string {
  const amount = asOptionalNumber(value);
  if (amount === null) return "—";
  const text = `${amount.toFixed(digits)}%`;
  if (amount > 0) return `+${text}`;
  return text;
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
