import type { Dict } from "../i18n/ar";
import type { Lang } from "../i18n";

// Dates from the API are UTC ISO strings; shown in the browser's timezone. Arabic keeps Latin digits.

export type Format = ReturnType<typeof makeFormat>;

export function makeFormat(lang: Lang, t: Dict) {
  const locale = lang === "ar" ? "ar-u-nu-latn" : "en-US";
  const dateLocale = lang === "ar" ? "ar-u-nu-latn" : "en-GB";
  const num = new Intl.NumberFormat(locale);
  const dateTime = new Intl.DateTimeFormat(dateLocale, {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const date = new Intl.DateTimeFormat(dateLocale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const time = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" });
  const shortDay = new Intl.DateTimeFormat(dateLocale, {
    month: "short",
    day: "numeric",
  });
  const rel = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });

  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 365 * 24 * 3600],
    ["month", 30 * 24 * 3600],
    ["day", 24 * 3600],
    ["hour", 3600],
    ["minute", 60],
  ];

  const moneyFormats = new Map<string, Intl.NumberFormat>();
  const moneyFormat = (currency: string) => {
    let fmt = moneyFormats.get(currency);
    if (!fmt) {
      try {
        fmt = new Intl.NumberFormat(locale, { style: "currency", currency });
      } catch {
        // not an ISO currency code: fall back to dollars
        fmt = new Intl.NumberFormat(locale, { style: "currency", currency: "USD" });
      }
      moneyFormats.set(currency, fmt);
    }
    return fmt;
  };
  const cents2 = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const whole = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  // Lebanon writes "$25" (not "US$") and "4,000,000 ل.ل." / "LBP"; the mark keeps "$25"
  // in order inside Arabic text.
  const dollars = (v: number) => `\u200E$${Number.isInteger(v) ? whole.format(v) : cents2.format(v)}`;
  const lira = (v: number) => `${whole.format(v)} ${lang === "ar" ? "ل.ل." : "LBP"}`;

  return {
    /** Wallet amounts (US cents) → "$12.50" */
    usd: (cents: number) => `\u200E$${cents2.format(cents / 100)}`,
    /** A product price in the shop's currency → "$49.90", "AED 49.90" */
    money: (amount: number | string, currency: string) => {
      const v = typeof amount === "string" ? Number(amount) : amount;
      if (!Number.isFinite(v)) return String(amount);
      if (currency === "USD") return dollars(v);
      if (currency === "LBP") return lira(v);
      return moneyFormat(currency).format(v);
    },
    /** 1250000 → "1,250,000" */
    num: (n: number | string | null | undefined) => {
      if (n === null || n === undefined || n === "") return "";
      const v = typeof n === "string" ? Number(n) : n;
      return Number.isFinite(v) ? num.format(v) : String(n);
    },
    dateTime: (iso: string) => dateTime.format(new Date(iso)),
    date: (iso: string) => date.format(new Date(iso)),
    /** Time only if today, else short date + time. */
    smart: (iso: string) => {
      const d = new Date(iso);
      const now = new Date();
      if (d.toDateString() === now.toDateString()) return time.format(d);
      return `${shortDay.format(d)}${lang === "ar" ? "،" : ","} ${time.format(d)}`;
    },
    time: (iso: string) => time.format(new Date(iso)),
    /** "3 minutes ago" */
    ago: (iso: string, now = Date.now()) => {
      const secs = (new Date(iso).getTime() - now) / 1000;
      for (const [unit, size] of units) {
        if (Math.abs(secs) >= size) return rel.format(Math.round(secs / size), unit);
      }
      return t.time.justNow;
    },
    /** Elapsed time without "ago": "14 minutes" / "2 hours" */
    duration: (iso: string, now = Date.now()) => {
      const mins = Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000));
      const fmt = (value: number, unit: "minute" | "hour" | "day") =>
        new Intl.NumberFormat(locale, { style: "unit", unit, unitDisplay: "long" }).format(value);
      if (mins < 60) return fmt(Math.max(1, mins), "minute");
      if (mins < 60 * 24) return fmt(Math.floor(mins / 60), "hour");
      return fmt(Math.floor(mins / 1440), "day");
    },
  };
}

/** Display name for a customer: name, username, or "Customer 0001" from the channel's ID. */
export function customerName(username: string | null | undefined, igsid: string, t: Dict, f: Format, name?: string | null): string {
  if (name) return name;
  if (username) return username;
  return `${t.common.customer} ${toLocaleDigits(igsid.slice(-4), f)}`;
}

function toLocaleDigits(digits: string, f: Format): string {
  return digits.replace(/\d/g, (d) => f.num(Number(d)));
}

export function formatBytesMB(bytes: number): string {
  return String(Math.round((bytes / 1024 / 1024) * 10) / 10);
}
