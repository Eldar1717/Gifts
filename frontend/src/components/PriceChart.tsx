import { useMemo } from "react";
import type { PricePoint } from "../lib/types";
import { formatDate } from "../lib/format";

/** Minimal area chart for price / sales history (no chart library needed). */
export function PriceChart({
  points,
  height = 108,
  accent = "#a78bfa",
  emptyLabel = "Пока нет данных об изменении цены",
}: {
  points: PricePoint[];
  height?: number;
  accent?: string;
  emptyLabel?: string;
}) {
  const series = useMemo(() => [...points].reverse().slice(-24), [points]);

  if (series.length < 2) {
    return (
      <div
        className="grid place-items-center rounded-2xl border border-dashed border-line bg-white/[0.02] text-[12px] text-muted-2"
        style={{ height }}
      >
        {emptyLabel}
      </div>
    );
  }

  const width = 320;
  const padding = 8;
  const prices = series.map((point) => point.price_stars);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;

  const coords = series.map((point, index) => {
    const x = padding + (index / (series.length - 1)) * (width - padding * 2);
    const y = height - padding - ((point.price_stars - min) / range) * (height - padding * 2);
    return { x, y, point };
  });

  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const area = `${line} L${coords[coords.length - 1].x.toFixed(1)},${height - padding} L${coords[0].x.toFixed(
    1,
  )},${height - padding} Z`;

  const last = coords[coords.length - 1];
  const first = coords[0];
  const delta = series[series.length - 1].price_stars - series[0].price_stars;
  const deltaPercent = series[0].price_stars ? Math.round((delta / series[0].price_stars) * 100) : 0;

  return (
    <div className="rounded-2xl border border-line bg-white/[0.025] p-3">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-2">Динамика цены</span>
        <span
          className="text-[11.5px] font-bold"
          style={{ color: delta >= 0 ? "#34d399" : "#fb7185" }}
        >
          {delta >= 0 ? "+" : ""}
          {deltaPercent}%
        </span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} className="spark" preserveAspectRatio="none">
        <defs>
          <linearGradient id="sparkGradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={accent} stopOpacity="0.55" />
            <stop offset="100%" stopColor={accent} stopOpacity="1" />
          </linearGradient>
          <linearGradient id="sparkArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity="0.32" />
            <stop offset="100%" stopColor={accent} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#sparkArea)" />
        <path d={line} className="line" />
        <circle cx={first.x} cy={first.y} r="2.6" fill={accent} opacity="0.55" />
        <circle cx={last.x} cy={last.y} r="3.4" fill="#fff" stroke={accent} strokeWidth="2.2" />
      </svg>
      <div className="mt-1 flex justify-between text-[10.5px] text-muted-2">
        <span>{formatDate(series[0].created_at)}</span>
        <span>{series[series.length - 1].price_stars} ★</span>
        <span>{formatDate(series[series.length - 1].created_at)}</span>
      </div>
    </div>
  );
}
