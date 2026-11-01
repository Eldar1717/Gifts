import type { OrderStatus, Rarity } from "./types";

export const RARITY_META: Record<Rarity, { label: string; color: string; glow: string; weight: number }> = {
  common: { label: "Common", color: "#9aa3b2", glow: "rgba(154,163,178,0.55)", weight: 1 },
  uncommon: { label: "Uncommon", color: "#4ade80", glow: "rgba(74,222,128,0.55)", weight: 2 },
  rare: { label: "Rare", color: "#38bdf8", glow: "rgba(56,189,248,0.6)", weight: 3 },
  epic: { label: "Epic", color: "#a855f7", glow: "rgba(168,85,247,0.65)", weight: 4 },
  legendary: { label: "Legendary", color: "#f5b544", glow: "rgba(245,181,68,0.7)", weight: 5 },
};

export const RARITY_ORDER: Rarity[] = ["common", "uncommon", "rare", "epic", "legendary"];

export function rarityLabel(rarity: Rarity): string {
  return RARITY_META[rarity]?.label ?? rarity;
}

export function rarityColor(rarity: Rarity): string {
  return RARITY_META[rarity]?.color ?? "#9aa3b2";
}

export const ORDER_STATUS_META: Record<OrderStatus, { label: string; color: string; bg: string }> = {
  pending_payment: { label: "Ожидает оплаты", color: "#fbbf24", bg: "rgba(251,191,36,0.14)" },
  paid: { label: "Оплачен", color: "#38bdf8", bg: "rgba(56,189,248,0.14)" },
  fulfilled: { label: "Выполнен", color: "#34d399", bg: "rgba(52,211,153,0.14)" },
  failed: { label: "Ошибка", color: "#f43f5e", bg: "rgba(244,63,94,0.14)" },
  cancelled: { label: "Отменён", color: "#94a3b8", bg: "rgba(148,163,184,0.14)" },
  expired: { label: "Истёк", color: "#94a3b8", bg: "rgba(148,163,184,0.14)" },
  refund_pending: { label: "Возврат в обработке", color: "#fb923c", bg: "rgba(251,146,60,0.14)" },
  refunded: { label: "Возвращён", color: "#a78bfa", bg: "rgba(167,139,250,0.14)" },
};

const nf = new Intl.NumberFormat("ru-RU");

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "0";
  return nf.format(value);
}

export function formatStars(value: number | null | undefined): string {
  return `${formatNumber(value ?? 0)} ★`;
}

export function formatCompact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(".0", "")}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1).replace(".0", "")}K`;
  return String(value);
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "—";
  const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  const options: Intl.DateTimeFormatOptions = withTime
    ? { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "short", year: "numeric" };
  return new Intl.DateTimeFormat("ru-RU", options).format(date);
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (Number.isNaN(diff)) return "—";
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} дн назад`;
  return formatDate(value);
}

export function splitAmount(amount: number, commissionPercent: number): { commission: number; seller: number } {
  const commission = Math.floor((amount * commissionPercent) / 100);
  return { commission, seller: amount - commission };
}

export function pluralize(count: number, forms: [string, string, string]): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return forms[0];
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
  return forms[2];
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "GM";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}
