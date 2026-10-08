import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const fmtNum = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "-"
    : v.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const fmtCompact = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "-"
    : Math.abs(v) < 100000
      ? fmtNum(v, Number.isInteger(v) ? 0 : 2)
      : new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 2 }).format(v);

export const fmtPct = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "-" : `${v.toFixed(digits)}%`;

export const fmtDate = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "-";

export const label = (v: string | null | undefined) =>
  v ? v.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : "-";

export const DOMAINS = ["customer", "account", "balance", "transaction", "aml", "kyc", "sanctions", "audit"] as const;
export const DOMAIN_LABEL: Record<string, string> = {
  customer: "Customers",
  account: "Accounts",
  balance: "Balances",
  transaction: "Transactions",
  aml: "AML",
  kyc: "KYC",
  sanctions: "Sanctions",
  audit: "Audit",
};

export const COLORS = {
  primary: "#0070AD",
  secondary: "#004C7F",
  success: "#28A745",
  warning: "#FFC107",
  danger: "#DC3545",
  palette: ["#0070AD", "#004C7F", "#28A745", "#FFC107", "#DC3545", "#5BA4CF", "#7A8B99", "#9B59B6"],
};
