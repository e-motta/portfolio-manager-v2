import { asNumber } from "./format";

export const CHART_PALETTE = [
  "#21543c",
  "#9c4320",
  "#3d6e8c",
  "#8a5a12",
  "#6a7f6c",
  "#5c4a7a",
  "#2d6a4c",
  "#b06a3c",
];

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
