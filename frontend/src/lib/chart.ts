import { asNumber } from "./format";

export const CHART_PALETTE = [
  "#4a90a4", // teal
  "#7b68b6", // purple
  "#c9a227", // ochre
  "#5e81ac", // blue
  "#d08770", // rose/salmon
  "#6a8a82", // slate
  "#8b9a6b", // olive
  "#5c6bc0", // indigo
  "#b0a090", // sand
  "#45b7d1", // cyan
];

export const EXPENSE_CATEGORY_GROUPS: Record<string, string> = {
  Bills: "#5e81ac",
  "Alimentação fora": "#c9a227",
  Supermercado: "#c9a227",
  Suplementos: "#8b9a6b",
  Corrida: "#8b9a6b",
  "Academia e treino": "#8b9a6b",
  "Assinaturas digitais": "#7b68b6",
  Telecom: "#7b68b6",
  Seguros: "#5e81ac",
  "Contabilidade / PJ": "#5e81ac",
  Saúde: "#d08770",
  Casa: "#6a8a82",
  Transporte: "#4a90a4",
  "Compras online": "#b0a090",
  "Bar e lazer": "#45b7d1",
  Presentes: "#45b7d1",
  Outros: "#b0a090",
};

export const CATEGORY_GROUP_COLORS: Record<string, string> = {
  Bills: "#5e81ac",
  Alimentação: "#c9a227",
  Esporte: "#8b9a6b",
  Assinaturas: "#7b68b6",
  Vida: "#d08770",
  Outros: "#b0a090",
};

export function formatAxis(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(abs >= 10_000 ? 0 : 1)}k`;
  return `${sign}${Math.round(abs)}`;
}

export function niceMax(value: number): number {
  const abs = Math.max(Math.abs(value), 1);
  const exp = 10 ** Math.floor(Math.log10(abs));
  return Math.ceil(abs / exp) * exp;
}

export function sliceColor(index: number): string {
  return CHART_PALETTE[index % CHART_PALETTE.length];
}

export function numeric(value: unknown): number {
  return asNumber(value);
}
