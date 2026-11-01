import { type ReactNode, useEffect, useRef, useState } from "react";
import { AlertTriangle, Inbox, Loader2, RefreshCw, Sparkles, X } from "lucide-react";
import type { Rarity } from "../lib/types";
import { RARITY_META, initials, rarityLabel } from "../lib/format";
import { haptic } from "../lib/telegram";

/* ------------------------------------------------------------------ Stars */
export function StarIcon({ size = 14, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <defs>
        <linearGradient id="starGradient" x1="4" y1="2" x2="20" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFE08A" />
          <stop offset="0.55" stopColor="#F7C948" />
          <stop offset="1" stopColor="#E9A23B" />
        </linearGradient>
      </defs>
      <path
        d="M12 2.6l2.72 5.86 6.28.83-4.63 4.45 1.2 6.36L12 16.98l-5.57 3.12 1.2-6.36L3 9.29l6.28-.83L12 2.6z"
        fill="url(#starGradient)"
        stroke="rgba(255,255,255,0.45)"
        strokeWidth="0.7"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Price({
  value,
  size = "md",
  className = "",
}: {
  value: number;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}) {
  const map = { sm: "text-[13px]", md: "text-[15px]", lg: "text-[19px]", xl: "text-[28px]" };
  const icon = { sm: 12, md: 14, lg: 17, xl: 24 };
  return (
    <span className={`price-tag ${map[size]} ${className}`}>
      <span>{new Intl.NumberFormat("ru-RU").format(value)}</span>
      <StarIcon size={icon[size]} />
    </span>
  );
}

/* ---------------------------------------------------------------- Rarity */
export function RarityBadge({ rarity, size = "sm" }: { rarity: Rarity; size?: "sm" | "md" }) {
  const meta = RARITY_META[rarity] ?? RARITY_META.common;
  return (
    <span
      className={`rarity-text inline-flex items-center rounded-full ${
        size === "sm" ? "px-2 py-[3px] text-[9.5px]" : "px-2.5 py-1 text-[11px]"
      }`}
      style={{
        color: meta.color,
        background: `${meta.color}1f`,
        border: `1px solid ${meta.color}40`,
      }}
    >
      {rarityLabel(rarity)}
    </span>
  );
}

export function RarityDot({ rarity }: { rarity: Rarity }) {
  const meta = RARITY_META[rarity] ?? RARITY_META.common;
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: meta.color }}>
      <span className="h-[6px] w-[6px] rounded-full" style={{ background: meta.color, boxShadow: `0 0 8px ${meta.color}` }} />
      {rarityLabel(rarity)}
    </span>
  );
}

/* ---------------------------------------------------------------- Avatar */
export function Avatar({
  name,
  src,
  size = 36,
  ring = false,
}: {
  name: string;
  src?: string;
  size?: number;
  ring?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const style = {
    width: size,
    height: size,
    boxShadow: ring ? "0 0 0 2px rgba(124,92,255,0.55), 0 8px 20px -10px rgba(124,92,255,0.9)" : undefined,
  };
  if (src && !failed) {
    return (
      <img
        src={src}
        alt={name}
        style={style}
        className="shrink-0 rounded-full object-cover"
        onError={() => setFailed(true)}
        loading="lazy"
      />
    );
  }
  return (
    <div
      style={style}
      className="grid shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet/80 to-magenta/60 text-[11px] font-extrabold text-white"
    >
      {initials(name)}
    </div>
  );
}

/* ------------------------------------------------------------- SmartImage */
export function SmartImage({
  src,
  alt,
  className = "",
  glow,
  eager = false,
}: {
  src: string;
  alt: string;
  className?: string;
  glow?: string;
  eager?: boolean;
}) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  return (
    <div className={`relative overflow-hidden ${className}`} style={{ background: "rgba(255,255,255,0.03)" }}>
      {glow && (
        <div
          className="pointer-events-none absolute inset-0 z-0"
          style={{ background: `radial-gradient(circle at 50% 55%, ${glow}, transparent 62%)`, opacity: 0.5 }}
        />
      )}
      {state !== "ready" && <div className="skeleton absolute inset-0 rounded-none" />}
      {state === "error" ? (
        <div className="relative z-[1] grid h-full w-full place-items-center text-muted-2">
          <Sparkles size={28} />
        </div>
      ) : (
        <img
          src={src}
          alt={alt}
          loading={eager ? "eager" : "lazy"}
          decoding="async"
          onLoad={() => setState("ready")}
          onError={() => setState("error")}
          className={`relative z-[1] h-full w-full object-cover transition-opacity duration-500 ${
            state === "ready" ? "opacity-100" : "opacity-0"
          }`}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Sheet */
export function Sheet({
  open,
  onClose,
  title,
  children,
  dismissible = true,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  dismissible?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  if (!open) return null;
  return (
    <>
      <div
        className="sheet-backdrop"
        onClick={() => {
          if (dismissible) {
            haptic("soft");
            onClose();
          }
        }}
      />
      <div className="sheet-panel" role="dialog" aria-modal="true">
        <div className="sheet-grabber" />
        <div className="mb-3 flex items-start justify-between gap-3">
          {title ? <h2 className="text-[17px] font-extrabold">{title}</h2> : <span />}
          {dismissible && (
            <button
              onClick={() => {
                haptic("soft");
                onClose();
              }}
              className="grid h-8 w-8 place-items-center rounded-full bg-white/5 text-muted"
              aria-label="Закрыть"
            >
              <X size={16} />
            </button>
          )}
        </div>
        {children}
      </div>
    </>
  );
}

/* -------------------------------------------------------------- Skeletons */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function CardSkeleton() {
  return (
    <div className="overflow-hidden rounded-[22px] border border-line bg-surface">
      <Skeleton className="aspect-square rounded-none" />
      <div className="space-y-2 p-3">
        <Skeleton className="h-3.5 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  );
}

export function RowSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-3">
          <Skeleton className="h-14 w-14 rounded-xl" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/2" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-8 w-16" />
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------ Empty/Error */
export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-3xl border border-dashed border-line bg-white/[0.02] px-6 py-12 text-center">
      <div className="mb-3 grid h-14 w-14 place-items-center rounded-2xl bg-violet/10 text-violet-soft">
        {icon ?? <Inbox size={24} />}
      </div>
      <p className="text-[15px] font-bold">{title}</p>
      {description && <p className="mt-1.5 max-w-[280px] text-[13px] leading-relaxed text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-3xl border border-danger/25 bg-danger/[0.06] p-5 text-center">
      <AlertTriangle className="mx-auto mb-2 text-danger" size={22} />
      <p className="text-[13.5px] font-semibold text-ink">{message}</p>
      {onRetry && (
        <button className="btn btn-ghost btn-sm mt-3" onClick={onRetry}>
          <RefreshCw size={14} /> Повторить
        </button>
      )}
    </div>
  );
}

export function Spinner({ size = 18, className = "" }: { size?: number; className?: string }) {
  return <Loader2 size={size} className={`animate-spin ${className}`} />;
}

export function FullPageLoader({ label = "Загружаем GIFT MARKET" }: { label?: string }) {
  return (
    <div className="flex min-h-[60dvh] flex-col items-center justify-center gap-4">
      <div className="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-violet to-magenta shadow-[0_18px_40px_-16px_rgba(124,92,255,0.9)]">
        <Sparkles className="text-white" size={24} />
      </div>
      <p className="text-[13px] font-semibold text-muted">{label}…</p>
    </div>
  );
}

/* ------------------------------------------------------------- Section UI */
export function SectionHeader({
  title,
  action,
  subtitle,
  onAction,
}: {
  title: string;
  subtitle?: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3 px-0.5">
      <div>
        <h2 className="text-[17px] font-extrabold tracking-[-0.02em]">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[11.5px] font-medium text-muted">{subtitle}</p>}
      </div>
      {action && (
        <button onClick={onAction} className="text-[12.5px] font-bold text-violet-soft active:opacity-70">
          {action}
        </button>
      )}
    </div>
  );
}

export function StatTile({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-2xl border border-line bg-white/[0.03] px-3 py-2.5">
      <p className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-2">{label}</p>
      <p className="mt-1 text-[16px] font-extrabold tabular" style={accent ? { color: accent } : undefined}>
        {value}
      </p>
      {hint && <p className="mt-0.5 text-[10.5px] text-muted-2">{hint}</p>}
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="segment">
      {options.map((option) => (
        <button
          key={option.value}
          data-active={option.value === value}
          onClick={() => {
            haptic("soft");
            onChange(option.value);
          }}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Counter({ value, duration = 900 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(0);
  useEffect(() => {
    const start = performance.now();
    const from = ref.current;
    let raf = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = Math.round(from + (value - from) * eased);
      setDisplay(next);
      if (progress < 1) raf = requestAnimationFrame(tick);
      else ref.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return <>{new Intl.NumberFormat("ru-RU").format(display)}</>;
}
