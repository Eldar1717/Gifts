import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Calendar, Layers, Sparkles } from "lucide-react";
import { useCollectionDetail } from "../hooks/useCollections";
import { useConfig } from "../hooks/useApi";
import { CardSkeleton, EmptyState, ErrorState, Price, RarityBadge, SmartImage } from "../components/ui";
import { ItemGiftCard } from "../components/GiftCard";
import { errorMessage } from "../lib/api";
import { formatDate, rarityColor, RARITY_ORDER } from "../lib/format";
import { haptic } from "../lib/telegram";

export default function CollectionDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data, isLoading, isError, error, refetch } = useCollectionDetail(slug);
  const { data: config } = useConfig();
  const [rarity, setRarity] = useState<string>("all");

  if (isLoading) {
    return (
      <div className="space-y-4 pt-2">
        <div className="skeleton h-40 rounded-3xl" />
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((index) => (
            <CardSkeleton key={index} />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="pt-6">
        <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        <Link to="/market" className="btn btn-ghost mt-3 w-full">
          В маркет
        </Link>
      </div>
    );
  }

  const { collection, items } = data;
  const filtered = rarity === "all" ? items : items.filter((item) => item.rarity === rarity);
  const available = items.filter((item) => item.remaining > 0);

  return (
    <div className="-mx-4">
      <div className="relative">
        <SmartImage
          src={collection.cover_url}
          alt={collection.name}
          className="h-[210px] w-full rounded-b-[30px]"
          glow={`${collection.accent}66`}
          eager
        />
        <div className="absolute inset-0 bg-gradient-to-t from-bg via-bg/35 to-black/45" />
        <button
          onClick={() => {
            haptic("soft");
            history.back();
          }}
          className="absolute left-4 top-4 grid h-9 w-9 place-items-center rounded-full border border-white/15 bg-black/45 text-white backdrop-blur-md"
          style={{ marginTop: "calc(var(--safe-top) + 4px)" }}
          aria-label="Назад"
        >
          <ArrowLeft size={17} />
        </button>
        <div className="absolute inset-x-0 bottom-0 px-4 pb-4">
          <div className="flex items-center gap-2">
            <RarityBadge rarity={collection.rarity} size="md" />
            {collection.is_featured && (
              <span className="rounded-full border border-violet/40 bg-violet/20 px-2 py-[3px] text-[9.5px] font-bold uppercase tracking-wide text-violet-soft">
                featured
              </span>
            )}
          </div>
          <h1 className="mt-1.5 text-[24px] font-extrabold leading-tight tracking-[-0.02em]">{collection.name}</h1>
        </div>
      </div>

      <div className="space-y-4 px-4 pt-3">
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "Предметов", value: String(collection.items_count) },
            { label: "Выпущено", value: String(collection.items_sold) },
            {
              label: "Floor",
              value: collection.floor_price_stars ? `${collection.floor_price_stars} ★` : "—",
            },
          ].map((stat) => (
            <div key={stat.label} className="rounded-2xl border border-line bg-white/[0.03] px-2 py-2.5 text-center">
              <p className="text-[14px] font-extrabold tabular">{stat.value}</p>
              <p className="mt-0.5 text-[9px] font-bold uppercase tracking-[0.08em] text-muted-2">{stat.label}</p>
            </div>
          ))}
        </div>

        {collection.description && (
          <p className="text-[12.5px] leading-relaxed text-ink/80">{collection.description}</p>
        )}

        <div className="flex flex-wrap items-center gap-3 text-[10.5px] font-semibold text-muted-2">
          <span className="flex items-center gap-1">
            <Calendar size={11} /> {collection.released_at ? formatDate(collection.released_at) : "дата не указана"}
          </span>
          {collection.category && (
            <span className="flex items-center gap-1">
              <Layers size={11} /> {collection.category.emoji} {collection.category.name}
            </span>
          )}
          <span className="flex items-center gap-1 text-violet-soft">
            <Sparkles size={11} /> {available.length} доступно
          </span>
        </div>

        <div className="no-scrollbar flex gap-2 overflow-x-auto pb-1">
          <button className={`chip ${rarity === "all" ? "chip-active" : ""}`} onClick={() => setRarity("all")}>
            Все ({items.length})
          </button>
          {RARITY_ORDER.map((value) => {
            const count = items.filter((item) => item.rarity === value).length;
            if (!count) return null;
            return (
              <button
                key={value}
                className={`chip ${rarity === value ? "chip-active" : ""}`}
                onClick={() => setRarity(value)}
                style={rarity === value ? undefined : { color: rarityColor(value) }}
              >
                {value.toUpperCase()} ({count})
              </button>
            );
          })}
        </div>

        {filtered.length === 0 ? (
          <EmptyState title="Нет предметов" description="В этой коллекции пока нет подарков с выбранной редкостью." />
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {filtered.map((item, index) => (
              <ItemGiftCard key={item.id} item={item} index={index} />
            ))}
          </div>
        )}

        <div className="rounded-2xl border border-line bg-white/[0.025] p-3">
          <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">Комиссия и перепродажа</p>
          <p className="text-[11.5px] leading-relaxed text-muted">
            При перепродаже платформа удерживает {config?.commission_percent ?? 10}% от суммы сделки, продавец
            получает {100 - (config?.commission_percent ?? 10)}%. Первичные выпуски продаются по фиксированной цене
            платформы.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <Price value={collection.floor_price_stars ?? 0} size="sm" />
            <span className="text-[10.5px] text-muted-2">минимальная цена на маркете</span>
          </div>
        </div>

        {collection.ton_collection_address && (
          <div className="rounded-2xl border border-line bg-white/[0.02] p-3">
            <p className="text-[10.5px] font-bold uppercase tracking-[0.1em] text-muted-2">Адрес коллекции в TON</p>
            <p className="mt-1 break-all text-[11px] font-semibold text-violet-soft">
              {collection.ton_collection_address}
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-muted-2">
              Наличие адреса не означает, что все предметы коллекции выпущены в блокчейне. GIFT MARKET не заявляет о
              NFT-статусе внутренних подарков без подтверждённой транзакции.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
