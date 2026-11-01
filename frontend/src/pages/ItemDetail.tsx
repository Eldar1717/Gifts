import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BadgeCheck,
  CheckCircle2,
  ChevronRight,
  Clock,
  ExternalLink,
  Flag,
  Heart,
  History,
  Info,
  Layers,
  Share2,
  ShieldCheck,
  Sparkles,
  Star,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { api, errorMessage } from "../lib/api";
import { useConfig, useItem, useListingDetail, useMeta, useToggleFavorite } from "../hooks/useApi";
import { useCheckout } from "../hooks/useCheckout";
import type { ItemDetail } from "../lib/types";
import {
  Avatar,
  EmptyState,
  ErrorState,
  FullPageLoader,
  Price,
  RarityBadge,
  Sheet,
  SmartImage,
  Spinner,
  StarIcon,
} from "../components/ui";
import { GiftArt } from "../components/GiftCard";
import { PriceChart } from "../components/PriceChart";
import { formatDate, rarityColor, relativeTime, splitAmount } from "../lib/format";
import { haptic, hapticNotification, openTelegramLink, selectionHaptic, webApp } from "../lib/telegram";
import { useToast } from "../context/ToastContext";

type Tab = "about" | "price" | "owners" | "sales";

export default function ItemDetailPage({ mode }: { mode: "item" | "listing" }) {
  const { id } = useParams<{ id: string }>();
  const numericId = id ? Number(id) : null;
  const itemQuery = useItem(mode === "item" ? numericId : null);
  const listingQuery = useListingDetail(mode === "listing" ? numericId : null);
  const query = mode === "item" ? itemQuery : listingQuery;
  const { data, isLoading, isError, error, refetch } = query;
  const { data: meta } = useMeta();
  const { data: config } = useConfig();
  const favorite = useToggleFavorite();
  const toast = useToast();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("about");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const checkout = useCheckout();

  useEffect(() => {
    if (!data) return;
    document.title = `${data.item.name} — GIFT MARKET`;
    return () => {
      document.title = "GIFT MARKET — коллекционные подарки";
    };
  }, [data]);

  useEffect(() => {
    const backButton = webApp?.BackButton;
    if (!backButton) return;
    const handler = () => navigate(-1);
    backButton.show();
    backButton.onClick(handler);
    return () => {
      backButton.offClick(handler);
      backButton.hide();
    };
  }, [navigate]);

  const commission = config?.commission_percent ?? 10;
  const split = useMemo(
    () => (data ? splitAmount(data.price_stars, data.kind === "resale" ? commission : 100) : null),
    [data, commission],
  );

  if (isLoading) return <FullPageLoader label="Открываем карточку" />;
  if (isError || !data) {
    return (
      <div className="pt-6">
        <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        <button className="btn btn-ghost mt-3 w-full" onClick={() => navigate("/market")}>
          Вернуться в маркет
        </button>
      </div>
    );
  }

  const isResale = data.kind === "resale";
  const share = async () => {
    haptic("soft");
    const url = `${window.location.origin}/gift/${data.item.id}`;
    const text = `${data.item.name} · ${data.price_stars} Stars на GIFT MARKET`;
    const shareUrl = meta?.bot_username
      ? `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`
      : `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
    openTelegramLink(shareUrl);
  };

  const openCheckout = () => {
    haptic("medium");
    setSheetOpen(true);
    if (checkout.phase === "idle" || checkout.phase === "error") {
      checkout.start(isResale && data.listing_id ? { listing_id: data.listing_id } : { item_id: data.item.id });
    }
  };

  const closeSheet = () => {
    if (checkout.phase === "paying" || checkout.phase === "confirming") return;
    setSheetOpen(false);
    if (checkout.phase === "done") {
      checkout.reset();
      navigate("/collection");
    } else if (checkout.phase === "error") {
      checkout.reset();
    }
  };

  const handleFavorite = () => {
    favorite.mutate(data.item.id, {
      onSuccess: (result) => {
        toast.success(result.favorite ? "Добавлено в избранное" : "Убрано из избранного");
        hapticNotification("success");
      },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };

  const buyLabel = isResale ? "Купить сейчас" : data.remaining > 0 ? "Купить за Stars" : "Тираж распродан";
  const canBuy = data.can_buy && (isResale || data.remaining > 0);

  return (
    <div className="-mx-4">
      {/* Art ---------------------------------------------------------- */}
      <div className="relative">
        <GiftArt
          item={data.item}
          style={{ aspectRatio: "1 / 1", borderBottomLeftRadius: 32, borderBottomRightRadius: 32 }}
          eager
        >
          <div className="pointer-events-none absolute inset-0 z-[2] bg-gradient-to-t from-bg via-transparent to-black/40" />
        </GiftArt>

        <div
          className="absolute left-0 right-0 top-0 z-[3] flex items-center justify-between px-4"
          style={{ paddingTop: "calc(var(--safe-top) + 10px)" }}
        >
          <button
            onClick={() => {
              haptic("soft");
              navigate(-1);
            }}
            className="grid h-9 w-9 place-items-center rounded-full border border-white/15 bg-black/45 text-white backdrop-blur-md"
            aria-label="Назад"
          >
            <ArrowLeft size={17} />
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={share}
              className="grid h-9 w-9 place-items-center rounded-full border border-white/15 bg-black/45 text-white backdrop-blur-md"
              aria-label="Поделиться"
            >
              <Share2 size={15} />
            </button>
            <button
              onClick={handleFavorite}
              className={`grid h-9 w-9 place-items-center rounded-full border backdrop-blur-md ${
                data.favorite
                  ? "border-rose/50 bg-rose/25 text-rose"
                  : "border-white/15 bg-black/45 text-white"
              }`}
              aria-label="Избранное"
            >
              <Heart size={15} fill={data.favorite ? "currentColor" : "none"} />
            </button>
          </div>
        </div>

        <div className="absolute bottom-3 left-4 right-4 z-[3] flex items-end justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <RarityBadge rarity={data.item.rarity} size="md" />
            {data.serial_number !== null && (
              <span className="rounded-full border border-white/15 bg-black/45 px-2 py-[3px] text-[10.5px] font-bold text-white/85 backdrop-blur-md">
                Серийный #{data.serial_number}
              </span>
            )}
            {data.kind === "resale" ? (
              <span className="rounded-full border border-mint/40 bg-mint/15 px-2 py-[3px] text-[10px] font-bold uppercase tracking-wide text-mint">
                перепродажа
              </span>
            ) : (
              <span className="rounded-full border border-violet/40 bg-violet/20 px-2 py-[3px] text-[10px] font-bold uppercase tracking-wide text-violet-soft">
                новый выпуск
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Title & price ------------------------------------------------ */}
      <div className="-mt-1 space-y-4 px-4 pt-3">
        <div>
          <Link
            to={`/collection/${data.item.collection.slug}`}
            className="inline-flex items-center gap-1 text-[11.5px] font-bold uppercase tracking-[0.12em]"
            style={{ color: data.item.collection.accent }}
          >
            <Layers size={12} /> {data.item.collection.name}
          </Link>
          <h1 className="mt-1 text-[24px] font-extrabold leading-[1.15] tracking-[-0.02em]">{data.item.name}</h1>
          <div className="mt-2 flex items-center gap-3">
            <Price value={data.price_stars} size="xl" />
            {isResale && split && (
              <span className="rounded-lg border border-line bg-white/[0.04] px-2 py-1 text-[10.5px] font-semibold text-muted">
                продавцу <span className="text-mint">{split.seller} ★</span> · комиссия {commission}%
              </span>
            )}
          </div>
        </div>

        {/* Seller / edition ------------------------------------------ */}
        {isResale && data.seller ? (
          <Link
            to={`/seller/${data.seller.id}`}
            className="flex items-center gap-3 rounded-2xl border border-line bg-white/[0.03] p-3 active:scale-[0.99]"
          >
            <Avatar name={data.seller.display_name} src={data.seller.photo_url} size={40} />
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-1 truncate text-[13px] font-bold">
                {data.seller.display_name}
                <BadgeCheck size={13} className="text-violet-soft" />
              </p>
              <p className="flex items-center gap-1.5 text-[11px] text-muted">
                {data.seller.rating !== null ? (
                  <>
                    <Star size={10} fill="currentColor" className="text-gold" /> {data.seller.rating.toFixed(1)} рейтинг
                  </>
                ) : (
                  "Новый продавец"
                )}
                {data.listed_at && ` · ${relativeTime(data.listed_at)}`}
              </p>
            </div>
            <ChevronRight size={16} className="text-muted-2" />
          </Link>
        ) : (
          <div className="rounded-2xl border border-line bg-white/[0.03] p-3">
            <div className="flex items-center justify-between text-[11.5px] font-semibold text-muted">
              <span>Выпущено {data.minted_count} из {data.edition_size}</span>
              <span className="text-violet-soft">осталось {data.remaining}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className="h-full rounded-full bg-gradient-to-r from-violet to-magenta"
                style={{ width: `${Math.min(100, (data.minted_count / Math.max(1, data.edition_size)) * 100)}%` }}
              />
            </div>
          </div>
        )}

        {data.owned_by_me && (
          <div className="flex items-center gap-2 rounded-2xl border border-mint/30 bg-mint/[0.08] px-3 py-2.5 text-[12px] font-semibold text-mint">
            <CheckCircle2 size={15} /> Этот подарок уже есть в вашей коллекции
          </div>
        )}

        {/* Tabs ------------------------------------------------------ */}
        <div className="no-scrollbar sticky top-[58px] z-20 -mx-4 flex gap-2 overflow-x-auto bg-bg/90 px-4 py-2 backdrop-blur-xl">
          {(
            [
              { id: "about", label: "Описание" },
              { id: "price", label: "История цены" },
              { id: "owners", label: "Владельцы" },
              { id: "sales", label: "Продажи" },
            ] as Array<{ id: Tab; label: string }>
          ).map((entry) => (
            <button
              key={entry.id}
              onClick={() => {
                selectionHaptic();
                setTab(entry.id);
              }}
              className={`chip ${tab === entry.id ? "chip-active" : ""}`}
            >
              {entry.label}
            </button>
          ))}
        </div>

        {tab === "about" && <AboutTab data={data} />}
        {tab === "price" && (
          <div className="space-y-3">
            <PriceChart points={data.price_history} accent={data.item.collection.accent || "#a78bfa"} />
            <div className="space-y-2">
              {data.price_history.length === 0 && (
                <EmptyState title="История пуста" description="Цена появится, когда подарок выставят на продажу." />
              )}
              {data.price_history.map((point, index) => (
                <div
                  key={`${point.created_at}-${index}`}
                  className="flex items-center justify-between rounded-xl border border-line bg-white/[0.02] px-3 py-2"
                >
                  <span className="flex items-center gap-2 text-[12px] font-semibold">
                    <TrendingUp size={13} className="text-violet-soft" />
                    {priceEventLabel(point.event)}
                  </span>
                  <div className="text-right">
                    <p className="text-[12.5px] font-bold tabular">{point.price_stars} ★</p>
                    <p className="text-[10px] text-muted-2">{formatDate(point.created_at, true)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {tab === "owners" && (
          <div className="space-y-2">
            {data.owners_history.length === 0 ? (
              <EmptyState title="Пока без перепродаж" description="Предмет ещё не менял владельца." icon={<History size={20} />} />
            ) : (
              data.owners_history.map((entry, index) => (
                <div key={index} className="flex items-start gap-3 rounded-2xl border border-line bg-white/[0.02] p-2.5">
                  <Avatar name={entry.to.display_name} src={entry.to.photo_url} size={34} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12.5px] font-bold">
                      {entry.event === "mint" ? "Первичный выпуск" : `Перешёл к ${entry.to.display_name}`}
                    </p>
                    <p className="text-[10.5px] text-muted-2">
                      {formatDate(entry.created_at, true)}
                      {entry.from && ` · от ${entry.from.display_name}`}
                    </p>
                  </div>
                  {entry.price_stars > 0 && <Price value={entry.price_stars} size="sm" />}
                </div>
              ))
            )}
          </div>
        )}
        {tab === "sales" && (
          <div className="space-y-2">
            {data.recent_sales.length === 0 ? (
              <EmptyState title="Продаж пока нет" description="Станьте первым владельцем этого подарка." icon={<Sparkles size={20} />} />
            ) : (
              data.recent_sales.map((sale, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between rounded-xl border border-line bg-white/[0.02] px-3 py-2.5"
                >
                  <span className="flex items-center gap-2 text-[12px] font-semibold text-muted">
                    <Clock size={13} /> {formatDate(sale.created_at, true)}
                  </span>
                  <Price value={sale.price_stars} size="sm" className="text-mint" />
                </div>
              ))
            )}
          </div>
        )}

        <div className="h-16" />
        <div className="flex items-center justify-between pb-2 pt-1 text-[11px] text-muted-2">
          <span>Просмотров: {data.views ?? 0}</span>
          <button onClick={() => setReportOpen(true)} className="flex items-center gap-1 font-semibold active:opacity-70">
            <Flag size={12} /> Пожаловаться
          </button>
        </div>
      </div>

      {/* Sticky purchase bar ------------------------------------------ */}
      <div
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg/92 px-4 pt-2.5 backdrop-blur-xl"
        style={{ paddingBottom: "calc(var(--nav-height) + var(--safe-bottom) + 10px)" }}
      >
        <div className="mx-auto flex max-w-[520px] items-center gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-muted-2">
              {isResale ? "Цена продавца" : "Цена платформы"}
            </p>
            <Price value={data.price_stars} size="lg" />
          </div>
          {data.owned_by_me ? (
            <Link to="/collection" className="btn btn-ghost ml-auto flex-1">
              <Wallet size={16} /> В коллекции
            </Link>
          ) : (
            <button className="btn btn-primary ml-auto flex-1" disabled={!canBuy} onClick={openCheckout}>
              {canBuy ? buyLabel : "Недоступно"}
            </button>
          )}
        </div>
      </div>

      {/* Checkout sheet ----------------------------------------------- */}
      <Sheet
        open={sheetOpen}
        onClose={closeSheet}
        title={checkout.phase === "done" ? "Покупка завершена" : "Оформление покупки"}
        dismissible={checkout.phase !== "paying" && checkout.phase !== "confirming"}
      >
        <CheckoutSheet
          checkout={checkout}
          data={data}
          commission={commission}
          devMode={Boolean(meta?.dev_mode)}
          onPay={() => checkout.pay({ allowDevSimulation: Boolean(meta?.dev_mode) })}
          onClose={closeSheet}
        />
      </Sheet>

      {/* Report sheet -------------------------------------------------- */}
      <Sheet open={reportOpen} onClose={() => setReportOpen(false)} title="Жалоба на объявление">
        <ReportForm
          targetType={isResale ? "listing" : "gift"}
          targetId={isResale && data.listing_id ? data.listing_id : data.item.id}
          onDone={() => setReportOpen(false)}
        />
      </Sheet>
    </div>
  );
}

/* ---------------------------------------------------------------- pieces */
function AboutTab({ data }: { data: ItemDetail }) {
  return (
    <div className="space-y-3">
      <p className="text-[13px] leading-relaxed text-ink/85">
        {data.description || "Описание скоро появится."}
      </p>
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: "Коллекция", value: data.item.collection.name },
          { label: "Редкость", value: data.item.rarity.toUpperCase(), color: rarityColor(data.item.rarity) },
          { label: "Тираж", value: `${data.edition_size}` },
          { label: "Выпущено", value: `${data.minted_count}` },
          {
            label: "Источник",
            value:
              data.item.source === "internal"
                ? "GIFT MARKET"
                : data.item.source === "telegram_official"
                  ? "Telegram"
                  : "Внешний NFT",
          },
          { label: "Перепродажа", value: data.item.is_tradeable ? "Разрешена" : "Запрещена" },
        ].map((row) => (
          <div key={row.label} className="rounded-xl border border-line bg-white/[0.02] px-3 py-2">
            <p className="text-[9.5px] font-bold uppercase tracking-[0.1em] text-muted-2">{row.label}</p>
            <p className="mt-0.5 truncate text-[12.5px] font-bold" style={row.color ? { color: row.color } : undefined}>
              {row.value}
            </p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border border-line bg-white/[0.02] p-3">
        <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
          <ShieldCheck size={13} className="text-mint" /> Безопасность сделки
        </p>
        <ul className="space-y-1.5 text-[11.5px] leading-relaxed text-muted">
          <li className="flex gap-1.5">
            <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-mint" />
            Счёт выставляется на сервере: цену нельзя изменить из приложения.
          </li>
          <li className="flex gap-1.5">
            <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-mint" />
            Подарок переходит покупателю только после подтверждённого платежа Telegram Stars.
          </li>
          <li className="flex gap-1.5">
            <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-mint" />
            Предмет закрепляется за покупателем в одной транзакции с записью в финансовый журнал.
          </li>
        </ul>
      </div>

      <div className="rounded-2xl border border-line bg-white/[0.02] p-3">
        <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
          <Info size={13} /> О происхождении
        </p>
        <p className="text-[11.5px] leading-relaxed text-muted">
          {data.item.source === "internal" &&
            "Это внутренний цифровой предмет GIFT MARKET: он существует только в базе платформы и не выпущен в блокчейне. Он не является официальным Telegram Collectible Gift или NFT."}
          {data.item.source === "telegram_official" &&
            "Предмет относится к официальным коллекционным подаркам Telegram. Условия и подтверждение владения определяются Telegram."}
          {data.item.source === "external_nft" &&
            "Предмет может быть связан с внешним NFT. Проверка владения выполняется по данным блокчейна, а не по данным приложения."}
        </p>
        {data.collection.ton_collection_address && (
          <p className="mt-2 flex items-center gap-1 break-all text-[11px] font-semibold text-violet-soft">
            <ExternalLink size={11} /> {data.collection.ton_collection_address}
          </p>
        )}
      </div>
    </div>
  );
}

function CheckoutSheet({
  checkout,
  data,
  commission,
  devMode,
  onPay,
  onClose,
}: {
  checkout: ReturnType<typeof useCheckout>;
  data: ItemDetail;
  commission: number;
  devMode: boolean;
  onPay: () => void;
  onClose: () => void;
}) {
  const split = splitAmount(data.price_stars, data.kind === "resale" ? commission : 100);

  if (checkout.phase === "done") {
    return (
      <div className="pb-2 text-center">
        <div className="mx-auto mb-3 grid h-16 w-16 place-items-center rounded-full bg-mint/15">
          <CheckCircle2 size={30} className="text-mint" />
        </div>
        <p className="text-[16px] font-extrabold">Подарок в вашей коллекции</p>
        <p className="mx-auto mt-1.5 max-w-[300px] text-[12.5px] leading-relaxed text-muted">
          Платёж подтверждён Telegram. Предмет закреплён за вами, чек доступен в истории заказов.
        </p>
        <button className="btn btn-primary mt-4 w-full" onClick={onClose}>
          Перейти в коллекцию
        </button>
      </div>
    );
  }

  if (checkout.phase === "creating") {
    return (
      <div className="flex flex-col items-center gap-3 py-10">
        <Spinner size={26} className="text-violet-soft" />
        <p className="text-[13px] font-semibold text-muted">Создаём счёт в Telegram Stars…</p>
      </div>
    );
  }

  if (checkout.phase === "paying" || checkout.phase === "confirming") {
    return (
      <div className="flex flex-col items-center gap-3 py-10">
        <Spinner size={26} className="text-violet-soft" />
        <p className="text-[13px] font-semibold text-muted">
          {checkout.phase === "paying" ? "Открываем счёт Telegram…" : "Ожидаем подтверждение платежа…"}
        </p>
        <p className="max-w-[290px] text-center text-[11px] leading-relaxed text-muted-2">
          Право собственности передаётся только после подтверждения от Telegram. Не закрывайте приложение.
        </p>
      </div>
    );
  }

  if (checkout.phase === "error") {
    return (
      <div className="pb-2">
        <div className="rounded-2xl border border-danger/30 bg-danger/[0.08] p-3 text-[12.5px] font-semibold leading-relaxed text-rose">
          {checkout.error}
        </div>
        <div className="mt-3 flex gap-2">
          <button className="btn btn-ghost flex-1" onClick={onClose}>
            Закрыть
          </button>
          <button
            className="btn btn-primary flex-1"
            onClick={() => {
              checkout.reset();
              checkout.start(
                data.kind === "resale" && data.listing_id
                  ? { listing_id: data.listing_id }
                  : { item_id: data.item.id },
              );
            }}
          >
            Повторить
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3 pb-2">
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-white/[0.03] p-2.5">
        <SmartImage src={data.item.image_url} alt={data.item.name} className="h-14 w-14 rounded-xl" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-bold">{data.item.name}</p>
          <p className="text-[11px] text-muted">{data.item.collection.name}</p>
          {data.serial_number !== null && (
            <p className="text-[10.5px] font-semibold text-violet-soft">Серийный №{data.serial_number}</p>
          )}
        </div>
        <Price value={data.price_stars} size="md" />
      </div>

      <div className="space-y-1.5 rounded-2xl border border-line bg-white/[0.02] p-3 text-[12px]">
        <Row label="Сумма к оплате" value={`${data.price_stars} ★`} strong />
        {data.kind === "resale" ? (
          <>
            <Row label={`Комиссия платформы (${commission}%)`} value={`${split.commission} ★`} muted />
            <Row label="Получит продавец" value={`${split.seller} ★`} muted />
          </>
        ) : (
          <Row label="Тип" value="Первичный выпуск платформы" muted />
        )}
        <Row label="Валюта" value="Telegram Stars (XTR)" muted />
      </div>

      <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-muted-2">
        <ShieldCheck size={13} className="mt-0.5 shrink-0 text-mint" />
        Оплата проходит в Telegram. Цифровые товары в Telegram оплачиваются Stars; возврат возможен, пока заказ не
        исполнен.
      </p>

      {devMode && (
        <div className="rounded-xl border border-gold/30 bg-gold/[0.08] p-2.5 text-[11px] font-semibold leading-relaxed text-gold/90">
          Демо-режим: Telegram-бот не подключён, оплата будет симулирована на backend и создаст реальные записи в
          базе (сделку, владельца, записи финансового журнала).
        </div>
      )}

      <button className="btn btn-primary w-full" onClick={onPay}>
        <StarIcon size={16} /> {devMode && !checkout.invoice?.invoice_url ? "Симулировать оплату" : "Оплатить в Telegram"}
      </button>
      <button className="btn btn-ghost w-full" onClick={onClose}>
        Отмена
      </button>
    </div>
  );
}

function Row({ label, value, muted, strong }: { label: string; value: string; muted?: boolean; strong?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className={muted ? "text-muted" : "text-ink"}>{label}</span>
      <span className={`tabular ${strong ? "text-[14px] font-extrabold" : "font-semibold"}`}>{value}</span>
    </div>
  );
}

function ReportForm({
  targetType,
  targetId,
  onDone,
}: {
  targetType: string;
  targetId: number;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("Подозрение на мошенничество");
  const [details, setDetails] = useState("");
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  const submit = async () => {
    setLoading(true);
    try {
      await api.report({ target_type: targetType, target_id: targetId, reason, details });
      toast.success("Жалоба отправлена модераторам");
      onDone();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3 pb-2">
      <div className="flex flex-wrap gap-2">
        {["Подозрение на мошенничество", "Неверное описание", "Запрещённый контент", "Спам"].map((option) => (
          <button
            key={option}
            className={`chip ${reason === option ? "chip-active" : ""}`}
            onClick={() => {
              selectionHaptic();
              setReason(option);
            }}
          >
            {option}
          </button>
        ))}
      </div>
      <textarea
        className="field"
        placeholder="Опишите проблему (необязательно)"
        value={details}
        onChange={(event) => setDetails(event.target.value.slice(0, 1000))}
      />
      <button className="btn btn-primary w-full" onClick={submit} disabled={loading}>
        {loading ? <Spinner size={16} /> : <Flag size={15} />} Отправить жалобу
      </button>
    </div>
  );
}

function priceEventLabel(event: string): string {
  switch (event) {
    case "listed":
      return "Выставлен на продажу";
    case "price_changed":
      return "Изменена цена";
    case "sold":
      return "Продан";
    case "cancelled":
      return "Снят с продажи";
    case "mint":
      return "Первичный выпуск";
    default:
      return event;
  }
}
