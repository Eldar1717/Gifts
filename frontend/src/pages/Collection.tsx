import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Layers, Loader2, PackageOpen, Tag, TrendingUp, Wallet } from "lucide-react";
import { useInvalidateMarket, useOwnedCollection, useConfig } from "../hooks/useApi";
import { api, errorMessage } from "../lib/api";
import type { OwnershipCard } from "../lib/types";
import { EmptyState, ErrorState, Price, Segmented, Sheet, Skeleton, Spinner, StarIcon } from "../components/ui";
import { OwnedGiftCard } from "../components/GiftCard";
import { formatDate, formatNumber, splitAmount } from "../lib/format";
import { hapticNotification, selectionHaptic } from "../lib/telegram";
import { useToast } from "../context/ToastContext";

type Filter = "all" | "listed" | "idle";

export default function CollectionPage() {
  const { data, isLoading, isError, error, refetch } = useOwnedCollection();
  const { data: config } = useConfig();
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<OwnershipCard | null>(null);

  const items = useMemo(() => {
    const list = data ?? [];
    if (filter === "listed") return list.filter((item) => item.listing?.status === "active" || item.listing?.status === "reserved");
    if (filter === "idle") return list.filter((item) => !item.listing);
    return list;
  }, [data, filter]);

  const listedCount = (data ?? []).filter((item) => item.listing).length;
  const totalValue = (data ?? []).reduce((sum, item) => sum + (item.estimated_value_stars ?? 0), 0);

  return (
    <div className="space-y-4 pt-1">
      <div>
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em]">Моя коллекция</h1>
        <p className="mt-0.5 text-[12px] text-muted">
          {formatNumber(data?.length ?? 0)} предметов · оценка {formatNumber(totalValue)} ★ · на продаже {listedCount}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-2xl border border-line bg-white/[0.03] p-3">
          <p className="text-[9.5px] font-bold uppercase tracking-[0.12em] text-muted-2">Оценка коллекции</p>
          <p className="mt-1 flex items-center gap-1 text-[18px] font-extrabold tabular">
            <StarIcon size={15} /> {formatNumber(totalValue)}
          </p>
          <p className="mt-0.5 text-[10px] text-muted-2">по минимальным ценам маркета</p>
        </div>
        <div className="rounded-2xl border border-line bg-white/[0.03] p-3">
          <p className="text-[9.5px] font-bold uppercase tracking-[0.12em] text-muted-2">Активных лотов</p>
          <p className="mt-1 text-[18px] font-extrabold tabular">{listedCount}</p>
          <Link to="/orders" className="mt-0.5 inline-flex items-center gap-1 text-[10px] font-bold text-violet-soft">
            История сделок <ArrowUpRight size={10} />
          </Link>
        </div>
      </div>

      <Segmented
        value={filter}
        onChange={setFilter}
        options={[
          { value: "all", label: "Все" },
          { value: "idle", label: "Свободны" },
          { value: "listed", label: "На продаже" },
        ]}
      />

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="overflow-hidden rounded-[22px] border border-line bg-surface">
              <Skeleton className="aspect-square rounded-none" />
              <div className="space-y-2 p-3">
                <Skeleton className="h-3.5 w-2/3" />
                <Skeleton className="h-3 w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : isError ? (
        <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          title={filter === "all" ? "Коллекция пока пуста" : "Здесь пусто"}
          description={
            filter === "all"
              ? "Купите первый подарок на маркете — он появится здесь с серийным номером и историей."
              : "Измените фильтр, чтобы увидеть остальные предметы."
          }
          icon={<PackageOpen size={22} />}
          action={
            <Link to="/market" className="btn btn-primary btn-sm">
              Перейти в маркет
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {items.map((item, index) => (
            <OwnedGiftCard key={item.id} ownership={item} index={index} onSelect={setSelected} />
          ))}
        </div>
      )}

      <div className="rounded-2xl border border-line bg-white/[0.025] p-3 text-[11px] leading-relaxed text-muted">
        <p className="mb-1 flex items-center gap-1.5 font-bold uppercase tracking-[0.1em] text-muted-2">
          <Wallet size={12} /> Как продать
        </p>
        Нажмите на предмет и укажите цену в Stars. Остальные коллекционеры увидят объявление в маркете, а вы получите
        уведомление о продаже. Комиссия платформы — {config?.commission_percent ?? 10}%, остальное зачисляется на
        внутренний баланс продавца.
      </div>

      <SellSheet ownership={selected} onClose={() => setSelected(null)} />

      <Link
        to="/market?kind=resale"
        className="flex items-center justify-between rounded-2xl border border-line bg-gradient-to-r from-violet/12 to-transparent p-3.5"
      >
        <div>
          <p className="text-[13px] font-bold">Найти редкие предметы</p>
          <p className="text-[11px] text-muted">Перепродажа от коллекционеров</p>
        </div>
        <TrendingUp size={18} className="text-violet-soft" />
      </Link>
    </div>
  );
}

function SellSheet({ ownership, onClose }: { ownership: OwnershipCard | null; onClose: () => void }) {
  const { data: config } = useConfig();
  const invalidate = useInvalidateMarket();
  const toast = useToast();
  const [price, setPrice] = useState("");
  const [saving, setSaving] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const commission = config?.commission_percent ?? 10;
  const minPrice = config?.min_listing_price ?? 10;
  const maxPrice = config?.max_listing_price ?? 100000;
  const numericPrice = Number(price || 0);
  const split = splitAmount(numericPrice, commission);
  const listing = ownership?.listing ?? null;

  const close = () => {
    setPrice("");
    onClose();
  };

  const createListing = async () => {
    if (!ownership) return;
    if (numericPrice < minPrice) {
      toast.error(`Минимальная цена — ${minPrice} Stars`);
      return;
    }
    if (numericPrice > maxPrice) {
      toast.error(`Максимальная цена — ${maxPrice} Stars`);
      return;
    }
    setSaving(true);
    try {
      await api.createListing({ ownership_id: ownership.id, price_stars: numericPrice });
      hapticNotification("success");
      toast.success("Объявление опубликовано");
      invalidate();
      close();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const cancel = async () => {
    if (!listing) return;
    setCancelling(true);
    try {
      await api.cancelListing(listing.id);
      toast.success("Объявление снято");
      invalidate();
      close();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setCancelling(false);
    }
  };

  return (
    <Sheet open={Boolean(ownership)} onClose={close} title={listing ? "Управление объявлением" : "Выставить на продажу"}>
      {ownership && (
        <div className="space-y-3 pb-2">
          <div className="flex items-center gap-3 rounded-2xl border border-line bg-white/[0.03] p-2.5">
            <img
              src={ownership.item.image_url}
              alt={ownership.item.name}
              className="h-14 w-14 rounded-xl object-cover"
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-bold">{ownership.item.name}</p>
              <p className="text-[11px] text-muted">
                {ownership.item.collection.name}
                {ownership.serial_number !== null && ` · #${ownership.serial_number}`}
              </p>
              <p className="text-[10.5px] text-muted-2">получен {formatDate(ownership.acquired_at)}</p>
            </div>
            <Price value={ownership.estimated_value_stars ?? ownership.item.primary_price_stars} size="sm" />
          </div>

          {listing ? (
            <>
              <div className="rounded-2xl border border-mint/25 bg-mint/[0.07] p-3">
                <p className="text-[11px] font-bold uppercase tracking-[0.1em] text-mint">Лот активен</p>
                <p className="mt-1 flex items-center gap-1 text-[15px] font-extrabold">
                  <StarIcon size={14} /> {listing.price_stars} Stars
                </p>
                <p className="mt-0.5 text-[11px] text-muted">
                  Размещено {formatDate(listing.listed_at)}
                  {listing.status === "reserved" && " · сейчас оформляет покупатель"}
                </p>
              </div>
              <div className="rounded-2xl border border-line bg-white/[0.02] p-3 text-[12px]">
                <div className="flex justify-between">
                  <span className="text-muted">Вы получите</span>
                  <span className="font-bold text-mint">
                    {splitAmount(listing.price_stars, commission).seller} ★
                  </span>
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="text-muted">Комиссия платформы</span>
                  <span className="font-semibold">{splitAmount(listing.price_stars, commission).commission} ★</span>
                </div>
              </div>
              <button className="btn btn-danger w-full" onClick={cancel} disabled={cancelling || listing.status === "reserved"}>
                {cancelling ? <Spinner size={16} /> : <Tag size={15} />} Снять с продажи
              </button>
            </>
          ) : (
            <>
              <div>
                <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">
                  Цена в Telegram Stars
                </label>
                <div className="relative">
                  <input
                    className="field pr-12 text-[17px] font-extrabold"
                    inputMode="numeric"
                    placeholder={String(minPrice)}
                    value={price}
                    onChange={(event) => setPrice(event.target.value.replace(/\D/g, "").slice(0, 7))}
                    autoFocus
                  />
                  <StarIcon size={18} className="absolute right-4 top-1/2 -translate-y-1/2" />
                </div>
                <div className="mt-2 flex gap-1.5">
                  {[1, 1.5, 2, 3].map((multiplier) => {
                    const suggested =
                      Math.round(((ownership.estimated_value_stars ?? ownership.item.primary_price_stars) * multiplier) / 10) * 10;
                    return (
                      <button
                        key={multiplier}
                        className="chip flex-1 justify-center"
                        onClick={() => {
                          selectionHaptic();
                          setPrice(String(suggested));
                        }}
                      >
                        {suggested} ★
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-2xl border border-line bg-white/[0.02] p-3 text-[12px]">
                <div className="flex justify-between">
                  <span className="text-muted">Получите на баланс</span>
                  <span className="font-bold text-mint">{split.seller} ★</span>
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="text-muted">Комиссия {commission}%</span>
                  <span className="font-semibold">{split.commission} ★</span>
                </div>
                <div className="mt-1 flex justify-between">
                  <span className="text-muted">Срок удержания</span>
                  <span className="font-semibold">{config?.hold_hours ?? 72} ч</span>
                </div>
              </div>

              <p className="text-[11px] leading-relaxed text-muted-2">
                Оценка основана на минимальной цене похожих предложений. После продажи средства поступят на внутренний
                баланс: сначала в «ожидающие», после периода удержания — в «доступные» для запроса выплаты.
              </p>

              <button className="btn btn-primary w-full" onClick={createListing} disabled={saving || !numericPrice}>
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Tag size={15} />}
                {saving ? "Публикуем…" : "Опубликовать объявление"}
              </button>
            </>
          )}

          <Link
            to="/orders"
            onClick={close}
            className="flex items-center justify-center gap-1 text-[11.5px] font-bold text-violet-soft"
          >
            <Layers size={12} /> Мои лоты и сделки
          </Link>
        </div>
      )}
    </Sheet>
  );
}
