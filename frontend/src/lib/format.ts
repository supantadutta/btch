export const fmtUsd = (v: number | string, dp = 2) =>
  Number(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });

export const fmtNum = (v: number | string, dp = 2) =>
  Number(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });

export const fmtPct = (v: number | string, dp = 2) => `${Number(v).toFixed(dp)}%`;

export const signClass = (v: number | string) =>
  Number(v) > 0 ? "text-up" : Number(v) < 0 ? "text-down" : "text-text-dim";

export const signed = (v: number | string, dp = 2) => {
  const n = Number(v);
  return `${n > 0 ? "+" : ""}${fmtUsd(n, dp)}`;
};
