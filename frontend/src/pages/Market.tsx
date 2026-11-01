import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ArrowDownUp, Check, Filter, Search, SlidersHorizontal, Sparkles, X } from "lucide-react";
import { api, errorMessage } from "../lib/api";
import { useCollections } from "../hooks/useCollections";
import { RARITY_META, RARITY_ORDER } from "../lib/format";
import type { MarketCard, Rarity } from "../lib/types";
import { CardSkeleton, EmptyState, ErrorState, Sheet, Spinner } from "../components/ui";
import { MarketGiftCard } from "../components/GiftCard";
import { haptic, selectionHaptic } from "../lib/telegram";

type Kind = "all" | "primary" | "resale";
type Sort = "recent" | "price_asc" | "price_desc" | "popular" | "rarity";

const SORT_LABELS: Record<Sort, string> = {
  recent: "Сначала новые",
  price_asc: "Цена: по возрастанию",
  price_desc: "Цена: по убыванию",
  popular: "Популярные",
  rarity: "По редкости",
};

const PAGE_SIZE = 20;

export default function MarketPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [debounced, setDebounced] = useState(search);
  const [kind, setKind] = useState<Kind>((params.get("kind") as Kind) || "all");
  const [sort, setSort] = useState<Sort>((params.get("sort") as Sort) || "recent");
  const [rarities, setRarities] = useState<Rarity[]>([]);
  const [collection, setCollection] = useState<string>(params.get("collection") ?? "");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const sentinel = useRef<HTMLDivElement | null>(null);
  const { data: collections } = useCollections();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 320);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const next = new URLSearchParams(params);
    if (debounced) next.set("q", debounced);
    else next.delete("q");
    if (kind !== "all") next.set("kind", kind);
    else next.delete("kind");
    if (sort !== "recent") next.set("sort", sort);
    else next.delete("sort");
    if (collection) next.set("collection", collection);
    else next.delete("collection");
    setParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, kind, sort, collection]);

  const query = useInfiniteQuery({
    queryKey: ["market", "infinite", { q: debounced, kind, sort, rarities, collection, minPrice, maxPrice }],
    initialPageParam: 1,
    queryFn: ({ pageParam }) =>
      api.market({
        q: debounced || undefined,
        kind,
        sort,
        rarity: rarities,
        collection: collection || undefined,
        min_price: minPrice ? Number(minPrice) : undefined,
        max_price: maxPrice ? Number(maxPrice) : undefined,
        page: pageParam,
        page_size: PAGE_SIZE,
      }),
    getNextPageParam: (lastPage) => (lastPage.page < lastPage.pages ? lastPage.page + 1 : undefined),
    staleTime: 20_000,
  });

  const cards: MarketCard[] = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );
  const total = query.data?.pages[0]?.total ?? 0;

  const activeFilters =
    rarities.length + (collection ? 1 : 0) + (minPrice ? 1 : 0) + (maxPrice ? 1 : 0) + (kind !== "all" ? 1 : 0);

  const resetFilters = useCallback(() => {
    setRarities([]);
    setCollection("");
    setMinPrice("");
    setMaxPrice("");
    setKind("all");
    haptic("medium");
  }, []);

  useEffect(() => {
    const node = sentinel.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && query.hasNextPage && !query.isFetchingNextPage) {
          query.fetchNextPage();
        }
      },
      { rootMargin: "320px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [query]);

  useEffect(() => {
    document.title = "Маркет — GIFT MARKET";
    return () => {
      document.title = "GIFT MARKET — коллекционные подарки";
    };
  }, []);

  return (
    <div className="space-y-4 pt-1">
      <div>
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em]">Маркет</h1>
        <p className="mt-0.5 text-[12px] text-muted">
          {total > 0 ? `${total} предложений от платформы и коллекционеров` : "Каталог коллекционных подарков"}
        </p>
      </div>

      <div className="sticky top-[58px] z-20 -mx-4 bg-bg/85 px-4 py-2 backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-2" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Подарок или коллекция"
              className="field pl-10 pr-9"
              inputMode="search"
              aria-label="Поиск по маркету"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-2"
                aria-label="Очистить"
              >
                <X size={15} />
              </button>
            )}
          </div>
          <button
            onClick={() => {
              haptic("soft");
              setSortOpen(true);
            }}
            className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-line bg-white/[0.045] text-muted"
            aria-label="Сортировка"
          >
            <ArrowDownUp size={17} />
          </button>
          <button
            onClick={() => {
              haptic("soft");
              setFiltersOpen(true);
            }}
            className={`relative grid h-12 w-12 shrink-0 place-items-center rounded-2xl border ${
              activeFilters
                ? "border-violet/50 bg-violet/15 text-violet-soft"
                : "border-line bg-white/[0.045] text-muted"
            }`}
            aria-label="Фильтры"
          >
            <SlidersHorizontal size={17} />
            {activeFilters > 0 && (
              <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-violet px-1 text-[9px] font-extrabold text-white">
                {activeFilters}
              </span>
            )}
          </button>
        </div>

        <div className="no-scrollbar -mx-4 mt-2 flex gap-2 overflow-x-auto px-4">
          {(
            [
              { value: "all", label: "Все" },
              { value: "primary", label: "Новые" },
              { value: "resale", label: "Перепродажа" },
            ] as Array<{ value: Kind; label: string }>
          ).map((option) => (
            <button
              key={option.value}
              className={`chip ${kind === option.value ? "chip-active" : ""}`}
              onClick={() => {
                selectionHaptic();
                setKind(option.value);
              }}
            >
              {option.value === "primary" && <Sparkles size={12} />}
              {option.label}
            </button>
          ))}
          <span className="my-2 w-px shrink-0 bg-line" />
          {RARITY_ORDER.map((rarity) => {
            const active = rarities.includes(rarity);
            return (
              <button
                key={rarity}
                className="chip shrink-0"
                style={
                  active
                    ? {
                        color: "#fff",
                        background: `${RARITY_META[rarity].color}33`,
                        borderColor: `${RARITY_META[rarity].color}80`,
                      }
                    : undefined
                }
                onClick={() => {
                  selectionHaptic();
                  setRarities((current) =>
                    current.includes(rarity) ? current.filter((item) => item !== rarity) : [...current, rarity],
                  );
                }}
              >
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: RARITY_META[rarity].color }}
                />
                {RARITY_META[rarity].label}
              </button>
            );
          })}
        </div>
      </div>

      {activeFilters > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-[11.5px] font-semibold text-muted">
            {SORT_LABELS[sort]} · {total} результатов
          </p>
          <button onClick={resetFilters} className="flex items-center gap-1 text-[11.5px] font-bold text-violet-soft">
            <X size={12} /> Сбросить
          </button>
        </div>
      )}

      {query.isLoading ? (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <CardSkeleton key={index} />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error)} onRetry={() => query.refetch()} />
      ) : cards.length === 0 ? (
        <EmptyState
          title="Ничего не найдено"
          description="Попробуйте изменить фильтры или ценовой диапазон — возможно, подходящий подарок уже скоро появится."
          icon={<Filter size={22} />}
          action={
            activeFilters > 0 ? (
              <button className="btn btn-ghost btn-sm" onClick={resetFilters}>
                Сбросить фильтры
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            {cards.map((card, index) => (
              <MarketGiftCard key={card.key} card={card} index={index} />
            ))}
          </div>
          <div ref={sentinel} className="h-2" />
          {query.hasNextPage && (
            <button
              className="btn btn-ghost w-full"
              onClick={() => query.fetchNextPage()}
              disabled={query.isFetchingNextPage}
            >
              {query.isFetchingNextPage ? <Spinner size={16} /> : null}
              {query.isFetchingNextPage ? "Загружаем…" : "Показать ещё"}
            </button>
          )}
          {!query.hasNextPage && cards.length > 6 && (
            <p className="pb-2 text-center text-[11px] text-muted-2">Вы посмотрели все предложения</p>
          )}
        </>
      )}

      {/* Sort sheet ------------------------------------------------------ */}
      <Sheet open={sortOpen} onClose={() => setSortOpen(false)} title="Сортировка">
        <div className="space-y-1.5 pb-2">
          {(Object.keys(SORT_LABELS) as Sort[]).map((key) => (
            <button
              key={key}
              onClick={() => {
                selectionHaptic();
                setSort(key);
                setSortOpen(false);
              }}
              className={`flex w-full items-center justify-between rounded-xl px-3.5 py-3 text-[14px] font-semibold ${
                sort === key ? "bg-violet/15 text-violet-soft" : "bg-white/[0.03] text-ink"
              }`}
            >
              {SORT_LABELS[key]}
              {sort === key && <Check size={16} />}
            </button>
          ))}
        </div>
      </Sheet>

      {/* Filters sheet --------------------------------------------------- */}
      <Sheet open={filtersOpen} onClose={() => setFiltersOpen(false)} title="Фильтры">
        <div className="space-y-4 pb-2">
          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">Коллекция</p>
            <div className="flex flex-wrap gap-2">
              <button
                className={`chip ${!collection ? "chip-active" : ""}`}
                onClick={() => {
                  selectionHaptic();
                  setCollection("");
                }}
              >
                Все коллекции
              </button>
              {(collections ?? []).map((item) => (
                <button
                  key={item.slug}
                  className={`chip ${collection === item.slug ? "chip-active" : ""}`}
                  onClick={() => {
                    selectionHaptic();
                    setCollection(collection === item.slug ? "" : item.slug);
                  }}
                >
                  {item.name}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">
              Цена, Telegram Stars
            </p>
            <div className="flex items-center gap-2">
              <input
                className="field"
                inputMode="numeric"
                placeholder="от"
                value={minPrice}
                onChange={(event) => setMinPrice(event.target.value.replace(/\D/g, "").slice(0, 7))}
              />
              <span className="text-muted-2">—</span>
              <input
                className="field"
                inputMode="numeric"
                placeholder="до"
                value={maxPrice}
                onChange={(event) => setMaxPrice(event.target.value.replace(/\D/g, "").slice(0, 7))}
              />
            </div>
          </div>

          <div>
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">Редкость</p>
            <div className="flex flex-wrap gap-2">
              {RARITY_ORDER.map((rarity) => {
                const active = rarities.includes(rarity);
                return (
                  <button
                    key={rarity}
                    className="chip"
                    style={
                      active
                        ? {
                            color: "#fff",
                            background: `${RARITY_META[rarity].color}33`,
                            borderColor: `${RARITY_META[rarity].color}80`,
                          }
                        : undefined
                    }
                    onClick={() => {
                      selectionHaptic();
                      setRarities((current) =>
                        current.includes(rarity)
                          ? current.filter((item) => item !== rarity)
                          : [...current, rarity],
                      );
                    }}
                  >
                    {RARITY_META[rarity].label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button className="btn btn-ghost flex-1" onClick={resetFilters}>
              Сбросить
            </button>
            <button className="btn btn-primary flex-1" onClick={() => setFiltersOpen(false)}>
              Применить
            </button>
          </div>
        </div>
      </Sheet>
    </div>
  );
}
