import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BadgeCheck, ChevronRight, Flame, Sparkles, Star, TrendingUp, Users } from "lucide-react";
import { useHome, useMe } from "../hooks/useApi";
import { CardSkeleton, Counter, EmptyState, ErrorState, Price, RarityBadge, SectionHeader, Skeleton, SmartImage, StarIcon } from "../components/ui";
import { FeatureGiftCard, ItemGiftCard, MarketGiftCard } from "../components/GiftCard";
import { errorMessage } from "../lib/api";
import { formatCompact, formatDate, rarityColor, relativeTime } from "../lib/format";
import { haptic } from "../lib/telegram";

export default function HomePage() {
  const { data, isLoading, isError, error, refetch } = useHome();
  const { data: me } = useMe();
  const navigate = useNavigate();

  if (isLoading) {
    return (
      <div className="space-y-6 pt-2">
        <Skeleton className="h-[132px] rounded-3xl" />
        <div className="flex gap-3 overflow-hidden">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-[300px] w-[248px] shrink-0 rounded-3xl" />
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  }

  const hasCatalogue = data.featured.length + data.trending.length + data.new_arrivals.length > 0;

  return (
    <div className="space-y-7 pt-1">
      {/* Hero ------------------------------------------------------------ */}
      <section className="animate-rise">
        <div className="relative overflow-hidden rounded-[26px] border border-line bg-gradient-to-br from-violet/20 via-surface to-surface p-4">
          <div className="pointer-events-none absolute -right-10 -top-12 h-40 w-40 rounded-full bg-magenta/25 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-16 -left-10 h-40 w-40 rounded-full bg-violet/25 blur-3xl" />
          <p className="text-[10.5px] font-bold uppercase tracking-[0.2em] text-violet-soft">
            {me ? `Привет, ${me.user.display_name.split(" ")[0]}` : "Telegram Stars marketplace"}
          </p>
          <h1 className="mt-1.5 font-display text-[23px] font-extrabold leading-[1.12] tracking-[-0.02em]">
            Коллекционные
            <br />
            подарки нового поколения
          </h1>
          <p className="mt-2 max-w-[280px] text-[12px] leading-relaxed text-muted">
            Покупайте предметы ограниченного тиража за Telegram Stars, собирайте коллекции и перепродавайте с
            прозрачной комиссией.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <button className="btn btn-primary btn-sm" onClick={() => { haptic("medium"); navigate("/market"); }}>
              Открыть маркет <ArrowRight size={14} />
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => { haptic("soft"); navigate("/collection"); }}>
              Моя коллекция
            </button>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2">
            <div className="rounded-2xl border border-line bg-black/25 px-3 py-2">
              <p className="text-[9.5px] font-bold uppercase tracking-[0.12em] text-muted-2">Оборот маркета</p>
              <p className="mt-0.5 flex items-center gap-1 text-[15px] font-extrabold tabular">
                <StarIcon size={13} /> <Counter value={data.stats.total_volume_stars} />
              </p>
            </div>
            <div className="rounded-2xl border border-line bg-black/25 px-3 py-2">
              <p className="text-[9.5px] font-bold uppercase tracking-[0.12em] text-muted-2">Сделок за 24 ч</p>
              <p className="mt-0.5 text-[15px] font-extrabold tabular">{data.stats.sales_24h}</p>
            </div>
          </div>
        </div>
      </section>

      {!hasCatalogue && (
        <EmptyState
          title="Каталог пока пуст"
          description="Администратор ещё не опубликовал коллекции. Как только появятся подарки, они будут здесь."
          icon={<Sparkles size={22} />}
        />
      )}

      {/* Featured -------------------------------------------------------- */}
      {data.featured.length > 0 && (
        <section>
          <SectionHeader
            title="Популярные подарки"
            subtitle="Выбор коллекционеров"
            action="Весь каталог"
            onAction={() => navigate("/market")}
          />
          <div className="no-scrollbar -mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto px-4 pb-1">
            {data.featured.map((item) => (
              <FeatureGiftCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}

      {/* Stats ----------------------------------------------------------- */}
      <section className="grid grid-cols-4 gap-2">
        {[
          { icon: <Flame size={14} />, value: data.stats.active_listings, label: "лотов" },
          { icon: <TrendingUp size={14} />, value: data.stats.sales_24h, label: "сделок" },
          { icon: <Users size={14} />, value: data.stats.collectors, label: "юзеров" },
          { icon: <Star size={14} />, value: formatCompact(data.stats.total_volume_stars), label: "оборот ★" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-2xl border border-line bg-white/[0.03] px-2 py-2.5 text-center"
          >
            <span className="mx-auto mb-1 grid h-7 w-7 place-items-center rounded-full bg-violet/12 text-violet-soft">
              {stat.icon}
            </span>
            <p className="text-[14px] font-extrabold tabular leading-none">{stat.value}</p>
            <p className="mt-1 text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted-2">{stat.label}</p>
          </div>
        ))}
      </section>

      {/* Trending -------------------------------------------------------- */}
      {data.trending.length > 0 && (
        <section>
          <SectionHeader
            title="В тренде"
            subtitle="Самое популярное на маркете сейчас"
            action="Смотреть"
            onAction={() => navigate("/market?sort=popular")}
          />
          <div className="grid grid-cols-2 gap-3">
            {data.trending.slice(0, 4).map((card, index) => (
              <MarketGiftCard key={card.key} card={card} index={index} />
            ))}
          </div>
        </section>
      )}

      {/* New arrivals ---------------------------------------------------- */}
      {data.new_arrivals.length > 0 && (
        <section>
          <SectionHeader title="Новые поступления" subtitle="Свежие предметы в каталоге" />
          <div className="no-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4 pb-1">
            {data.new_arrivals.slice(0, 8).map((item, index) => (
              <div key={item.id} className="w-[150px] shrink-0">
                <ItemGiftCard item={item} index={index} />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Rare collections ------------------------------------------------ */}
      {data.rare_collections.length > 0 && (
        <section>
          <SectionHeader
            title="Редкие коллекции"
            subtitle="Ограниченные серии платформы"
            action="Все коллекции"
            onAction={() => navigate("/market?kind=primary")}
          />
          <div className="space-y-2.5">
            {data.rare_collections.map((collection) => (
              <Link
                key={collection.id}
                to={`/collection/${collection.slug}`}
                onClick={() => haptic("light")}
                className="flex items-center gap-3 rounded-2xl border border-line bg-white/[0.03] p-2.5 active:scale-[0.99]"
              >
                <SmartImage
                  src={collection.cover_url}
                  alt={collection.name}
                  className="h-14 w-14 shrink-0 rounded-xl"
                  glow={`${collection.accent}66`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <p className="truncate text-[13.5px] font-bold">{collection.name}</p>
                    <span
                      className="h-1.5 w-1.5 shrink-0 rounded-full"
                      style={{ background: rarityColor(collection.rarity), boxShadow: `0 0 8px ${rarityColor(collection.rarity)}` }}
                    />
                  </div>
                  <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-2">{collection.description}</p>
                  <div className="mt-1 flex items-center gap-2 text-[10.5px] font-semibold text-muted">
                    <RarityBadge rarity={collection.rarity} />
                    <span>{collection.items_count} предметов</span>
                    {collection.floor_price_stars !== null && (
                      <span className="text-mint">от {collection.floor_price_stars} ★</span>
                    )}
                  </div>
                </div>
                <ChevronRight size={16} className="shrink-0 text-muted-2" />
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Recent sales ---------------------------------------------------- */}
      {data.recent_sales.length > 0 && (
        <section>
          <SectionHeader title="Последние продажи" subtitle="Прозрачная история сделок" />
          <div className="space-y-2">
            {data.recent_sales.slice(0, 5).map((sale, index) => (
              <div
                key={`${sale.item_name}-${index}`}
                className="flex items-center gap-3 rounded-2xl border border-line bg-white/[0.025] p-2"
              >
                <SmartImage src={sale.image_url} alt={sale.item_name} className="h-10 w-10 shrink-0 rounded-lg" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12.5px] font-bold">
                    {sale.item_name}
                    {sale.serial_number !== null && <span className="ml-1 text-muted-2">#{sale.serial_number}</span>}
                  </p>
                  <p className="text-[10.5px] text-muted-2">
                    {relativeTime(sale.sold_at)} · {formatDate(sale.sold_at)}
                  </p>
                </div>
                <Price value={sale.price_stars} size="sm" className="text-mint" />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Top sellers ----------------------------------------------------- */}
      {data.top_sellers.length > 0 && (
        <section>
          <SectionHeader title="Популярные продавцы" subtitle="Рейтинг по завершённым сделкам" />
          <div className="no-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4 pb-1">
            {data.top_sellers.map((seller) => (
              <Link
                key={seller.id}
                to={`/seller/${seller.id}`}
                onClick={() => haptic("light")}
                className="flex w-[104px] shrink-0 flex-col items-center gap-1.5 rounded-2xl border border-line bg-white/[0.03] px-2 py-3"
              >
                <div className="relative">
                  <SmartImage
                    src={seller.photo_url}
                    alt={seller.display_name}
                    className="h-12 w-12 rounded-full"
                  />
                  {seller.rating !== null && (
                    <span className="absolute -bottom-1 left-1/2 flex -translate-x-1/2 items-center gap-0.5 rounded-full border border-gold/40 bg-bg px-1.5 text-[9px] font-bold text-gold">
                      <Star size={8} fill="currentColor" /> {seller.rating.toFixed(1)}
                    </span>
                  )}
                </div>
                <p className="mt-1 w-full truncate text-center text-[11.5px] font-bold">{seller.display_name}</p>
                <p className="text-[9.5px] font-semibold uppercase tracking-wide text-muted-2">
                  {seller.username ? `@${seller.username.slice(0, 12)}` : "collector"}
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Recommended ----------------------------------------------------- */}
      {data.recommended.length > 0 && (
        <section>
          <SectionHeader title="Рекомендуем" subtitle="Доступные предложения по цене" />
          <div className="grid grid-cols-2 gap-3">
            {data.recommended.slice(0, 6).map((card, index) => (
              <MarketGiftCard key={card.key} card={card} index={index} />
            ))}
          </div>
        </section>
      )}

      {/* Trust footer ---------------------------------------------------- */}
      <section className="space-y-3 pb-2">
        <div className="rounded-2xl border border-line bg-white/[0.025] p-3.5">
          <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
            <BadgeCheck size={13} className="text-mint" /> Как работает маркет
          </div>
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">
            Все расчёты выполняются на сервере. Подарок переходит покупателю только после подтверждения платежа
            Telegram Stars. Комиссия платформы — 10%, продавец получает 90% на внутренний баланс.
          </p>
          <Link
            to="/about"
            className="mt-2 inline-flex items-center gap-1 text-[11.5px] font-bold text-violet-soft"
          >
            Правила и ограничения <ArrowRight size={12} />
          </Link>
        </div>
        <p className="px-1 text-center text-[10px] leading-relaxed text-muted-2">
          GIFT MARKET — независимый маркетплейс. Внутренние цифровые подарки не являются официальными
          Telegram Collectible Gifts и не выпущены в блокчейне, если в карточке не указано иное.
        </p>
      </section>
    </div>
  );
}
