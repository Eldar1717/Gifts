import { Link } from "react-router-dom";
import { ArrowUpRight, Heart, Users } from "lucide-react";
import type { ItemCard, MarketCard, OwnershipCard } from "../lib/types";
import { RARITY_META, formatNumber } from "../lib/format";
import { Price, RarityBadge, SmartImage } from "./ui";
import { haptic } from "../lib/telegram";

export function GiftArt({
  item,
  serial,
  className = "",
  style,
  eager = false,
  children,
}: {
  item: Pick<ItemCard, "image_url" | "name" | "glow" | "rarity">;
  serial?: number | null;
  className?: string;
  style?: React.CSSProperties;
  eager?: boolean;
  children?: React.ReactNode;
}) {
  const meta = RARITY_META[item.rarity] ?? RARITY_META.common;
  return (
    <div className={`gift-art ${className}`} style={style}>
      <div
        className="gift-glow"
        style={{ background: `radial-gradient(circle, ${item.glow || meta.glow}, transparent 68%)` }}
      />
      <SmartImage src={item.image_url} alt={item.name} glow={item.glow || meta.glow} className="h-full w-full" eager={eager} />
      {serial !== undefined && serial !== null && <span className="serial-badge">#{serial}</span>}
      {children}
    </div>
  );
}

/** Marketplace card (resale listing or primary mint). */
export function MarketGiftCard({ card, index = 0 }: { card: MarketCard; index?: number }) {
  const href =
    card.kind === "resale" && card.listing_id ? `/listing/${card.listing_id}` : `/gift/${card.item.id}`;
  const pressed = () => haptic("light");
  return (
    <Link
      to={href}
      onClick={pressed}
      className="gift-card animate-rise block"
      style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
    >
      <GiftArt item={card.item} serial={card.serial_number} eager={index < 2} />
      <div className="relative space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-[13.5px] font-bold leading-tight">{card.item.name}</p>
          <RarityBadge rarity={card.item.rarity} />
        </div>
        <p className="truncate text-[11px] font-medium text-muted-2">{card.item.collection.name}</p>
        <div className="flex items-center justify-between gap-2 pt-0.5">
          <Price value={card.price_stars} size="sm" />
          {card.kind === "resale" ? (
            <span className="flex items-center gap-1 text-[10.5px] font-semibold text-muted">
              {card.seller?.display_name?.split(" ")[0] ?? "Коллекционер"}
              <ArrowUpRight size={12} />
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10.5px] font-semibold text-violet-soft">
              <Users size={11} /> {card.item.remaining} осталось
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

/** Catalogue card (primary mint from the home page). */
export function ItemGiftCard({ item, index = 0 }: { item: ItemCard; index?: number }) {
  return (
    <Link
      to={`/gift/${item.id}`}
      onClick={() => haptic("light")}
      className="gift-card animate-rise block"
      style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
    >
      <GiftArt item={item} eager={index < 2} />
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-[13.5px] font-bold leading-tight">{item.name}</p>
          <RarityBadge rarity={item.rarity} />
        </div>
        <div className="flex items-center justify-between gap-2">
          <Price value={item.primary_price_stars} size="sm" />
          <span className="text-[10.5px] font-semibold text-muted-2">
            {formatNumber(item.minted_count)}/{formatNumber(item.edition_size)}
          </span>
        </div>
      </div>
    </Link>
  );
}

/** Wide card used in "featured" carousels. */
export function FeatureGiftCard({ item }: { item: ItemCard }) {
  const meta = RARITY_META[item.rarity] ?? RARITY_META.common;
  return (
    <Link
      to={`/gift/${item.id}`}
      onClick={() => haptic("light")}
      className="gift-card relative block w-[248px] shrink-0 snap-start"
      style={{ boxShadow: `0 24px 60px -34px ${meta.glow}` }}
    >
      <div className="relative">
        <GiftArt item={item} style={{ aspectRatio: "4 / 5" }} />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[2] h-24 bg-gradient-to-t from-[#0d0d15] to-transparent" />
        <div className="absolute inset-x-0 bottom-0 z-[3] p-3.5">
          <RarityBadge rarity={item.rarity} />
          <p className="mt-1.5 text-[15px] font-extrabold leading-tight">{item.name}</p>
          <p className="truncate text-[11px] font-medium text-white/55">{item.collection.name}</p>
          <div className="mt-2 flex items-center justify-between">
            <Price value={item.primary_price_stars} size="md" />
            <span className="rounded-full border border-white/10 bg-black/35 px-2 py-[3px] text-[10px] font-bold text-white/70 backdrop-blur-sm">
              {item.remaining} из {item.edition_size}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}

/** A card for an item the current user owns. */
export function OwnedGiftCard({
  ownership,
  index = 0,
  onSelect,
}: {
  ownership: OwnershipCard;
  index?: number;
  onSelect?: (ownership: OwnershipCard) => void;
}) {
  const status = ownership.listing?.status;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => {
        haptic("light");
        onSelect?.(ownership);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") onSelect?.(ownership);
      }}
      className="gift-card animate-rise block cursor-pointer"
      style={{ animationDelay: `${Math.min(index, 8) * 35}ms` }}
    >
      <GiftArt item={ownership.item} serial={ownership.serial_number}>
        {status === "active" && (
          <span className="absolute left-2 top-2 z-[2] rounded-full border border-mint/40 bg-mint/15 px-2 py-[3px] text-[9.5px] font-bold uppercase tracking-wide text-mint backdrop-blur-sm">
            На продаже
          </span>
        )}
        {status === "reserved" && (
          <span className="absolute left-2 top-2 z-[2] rounded-full border border-gold/40 bg-gold/15 px-2 py-[3px] text-[9.5px] font-bold uppercase tracking-wide text-gold backdrop-blur-sm">
            Бронь
          </span>
        )}
      </GiftArt>
      <div className="space-y-1.5 p-3">
        <p className="truncate text-[13.5px] font-bold leading-tight">{ownership.item.name}</p>
        <div className="flex items-center justify-between gap-2">
          <Price value={ownership.listing?.price_stars ?? ownership.estimated_value_stars ?? 0} size="sm" />
          <RarityBadge rarity={ownership.item.rarity} />
        </div>
      </div>
    </div>
  );
}

export function FavoriteButton({
  active,
  onClick,
  className = "",
}: {
  active: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      aria-label={active ? "Убрать из избранного" : "В избранное"}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        haptic("light");
        onClick();
      }}
      className={`grid h-9 w-9 place-items-center rounded-full border backdrop-blur-md transition ${
        active
          ? "border-rose/50 bg-rose/20 text-rose"
          : "border-white/15 bg-black/40 text-white/70 active:scale-90"
      } ${className}`}
    >
      <Heart size={15} fill={active ? "currentColor" : "none"} />
    </button>
  );
}
