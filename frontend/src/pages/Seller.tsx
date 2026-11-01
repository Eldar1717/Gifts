import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Star } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";
import { useSeller, useSellerReviews } from "../hooks/useCollections";
import { useConfig } from "../hooks/useApi";
import type { OwnershipCard } from "../lib/types";
import {
  Avatar,
  EmptyState,
  ErrorState,
  Price,
  RarityBadge,
  Segmented,
  Sheet,
  SmartImage,
  Spinner,
  StarIcon,
} from "../components/ui";
import { MarketGiftCard } from "../components/GiftCard";
import { formatDate, formatNumber, rarityColor, splitAmount } from "../lib/format";
import { haptic, hapticNotification, selectionHaptic } from "../lib/telegram";
import { useToast } from "../context/ToastContext";

type Tab = "listings" | "collection" | "reviews";

export default function SellerPage() {
  const { id } = useParams<{ id: string }>();
  const sellerId = Number(id);
  const seller = useSeller(Number.isFinite(sellerId) ? sellerId : undefined);
  const reviews = useSellerReviews(Number.isFinite(sellerId) ? sellerId : undefined);
  const listings = useQuery({
    queryKey: ["seller-listings", sellerId],
    queryFn: () => api.sellerListings(sellerId),
    enabled: Number.isFinite(sellerId),
  });
  const collection = useQuery({
    queryKey: ["seller-collection", sellerId],
    queryFn: () => api.sellerCollection(sellerId),
    enabled: Number.isFinite(sellerId),
    retry: false,
  });
  const [tab, setTab] = useState<Tab>("listings");
  const [offerTarget, setOfferTarget] = useState<OwnershipCard | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    document.title = "Профиль продавца — GIFT MARKET";
  }, []);

  if (seller.isLoading) {
    return <div className="pt-10 text-center text-[13px] text-muted">Загружаем профиль…</div>;
  }
  if (seller.isError || !seller.data) {
    return (
      <div className="pt-6">
        <ErrorState message={errorMessage(seller.error)} onRetry={() => seller.refetch()} />
      </div>
    );
  }

  const { user, stats, collection_visible } = seller.data;

  return (
    <div className="space-y-4 pt-1">
      <button
        onClick={() => {
          haptic("soft");
          navigate(-1);
        }}
        className="flex items-center gap-1 text-[12px] font-bold text-muted"
      >
        <ArrowLeft size={14} /> Назад
      </button>

      <div className="relative overflow-hidden rounded-[26px] border border-line bg-gradient-to-br from-violet/15 via-surface to-surface p-4">
        <div className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-magenta/20 blur-3xl" />
        <div className="flex items-center gap-3">
          <Avatar name={user.display_name} src={user.photo_url} size={56} ring />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[17px] font-extrabold">{user.display_name}</p>
            <p className="truncate text-[11.5px] font-semibold text-muted">
              {user.username ? `@${user.username}` : "коллекционер"}
            </p>
            <div className="mt-1 flex items-center gap-2">
              {user.rating !== null ? (
                <span className="flex items-center gap-1 rounded-full border border-gold/30 bg-gold/10 px-2 py-[2px] text-[10px] font-bold text-gold">
                  <Star size={9} fill="currentColor" /> {user.rating.toFixed(1)} · {stats.rating_count}
                </span>
              ) : (
                <span className="rounded-full border border-line bg-white/5 px-2 py-[2px] text-[10px] text-muted">
                  без отзывов
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-4 gap-2">
          {[
            { label: "подарков", value: stats.gifts_owned },
            { label: "лотов", value: stats.listings_active },
            { label: "продаж", value: stats.sales_count },
            { label: "покупок", value: stats.purchases_count },
          ].map((stat) => (
            <div key={stat.label} className="rounded-xl border border-line bg-black/25 px-1 py-2 text-center">
              <p className="text-[15px] font-extrabold tabular leading-none">{formatNumber(stat.value)}</p>
              <p className="mt-0.5 text-[9px] font-semibold uppercase tracking-wide text-muted-2">{stat.label}</p>
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] text-muted">
          <span>Оборот продаж</span>
          <Price value={stats.gross_sales_stars} size="sm" />
        </div>
      </div>

      <Segmented
        value={tab}
        onChange={(value) => {
          selectionHaptic();
          setTab(value);
        }}
        options={[
          { value: "listings", label: "Лоты" },
          { value: "collection", label: "Коллекция" },
          { value: "reviews", label: "Отзывы" },
        ]}
      />

      {tab === "listings" &&
        (listings.isLoading ? (
          <div className="py-8 text-center text-[12px] text-muted">Загружаем лоты…</div>
        ) : !listings.data?.length ? (
          <EmptyState title="Нет активных лотов" description="У продавца сейчас нет активных объявлений." />
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {listings.data.map((card, index) => (
              <MarketGiftCard key={card.key} card={card} index={index} />
            ))}
          </div>
        ))}

      {tab === "collection" &&
        (collection.isLoading ? (
          <div className="py-8 text-center text-[12px] text-muted">Загружаем коллекцию…</div>
        ) : collection.isError ? (
          <EmptyState
            title="Коллекция скрыта"
            description={collection_visible ? "Не удалось открыть коллекцию." : "Коллекционер отключил отображение подарков в настройках приватности."}
          />
        ) : !collection.data?.length ? (
          <EmptyState title="Коллекция пуста" />
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {collection.data.map((ownership) => (
              <button
                key={ownership.id}
                onClick={() => {
                  if (ownership.listing) return;
                  haptic("soft");
                  setOfferTarget(ownership);
                }}
                className="gift-card text-left"
              >
                <div className="gift-art">
                  <SmartImage
                    src={ownership.item.image_url}
                    alt={ownership.item.name}
                    glow={ownership.item.glow}
                    className="h-full w-full"
                  />
                  {ownership.serial_number !== null && (
                    <span className="serial-badge">#{ownership.serial_number}</span>
                  )}
                </div>
                <div className="space-y-1.5 p-3">
                  <p className="truncate text-[13px] font-bold">{ownership.item.name}</p>
                  <div className="flex items-center justify-between">
                    <Price value={ownership.estimated_value_stars ?? 0} size="sm" />
                    <RarityBadge rarity={ownership.item.rarity} />
                  </div>
                  <p className="text-[10px] font-semibold text-violet-soft">
                    {ownership.listing ? `На продаже за ${ownership.listing.price_stars} ★` : "Предложить цену →"}
                  </p>
                </div>
              </button>
            ))}
          </div>
        ))}

      {tab === "reviews" &&
        (reviews.isLoading ? (
          <div className="py-8 text-center text-[12px] text-muted">Загружаем отзывы…</div>
        ) : !reviews.data?.items.length ? (
          <EmptyState title="Отзывов пока нет" description="Отзывы оставляют покупатели после завершённых сделок." />
        ) : (
          <div className="space-y-2">
            {reviews.data.items.map((review) => (
              <div key={review.id} className="rounded-2xl border border-line bg-white/[0.02] p-3">
                <div className="flex items-center gap-2">
                  <Avatar name={review.author.display_name} src={review.author.photo_url} size={28} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] font-bold">{review.author.display_name}</p>
                    <p className="text-[10px] text-muted-2">{formatDate(review.created_at, true)}</p>
                  </div>
                  <span className="flex items-center gap-0.5 text-gold">
                    {Array.from({ length: review.rating }).map((_, index) => (
                      <Star key={index} size={11} fill="currentColor" />
                    ))}
                  </span>
                </div>
                {review.comment && <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">«{review.comment}»</p>}
              </div>
            ))}
          </div>
        ))}

      <OfferSheet ownership={offerTarget} onClose={() => setOfferTarget(null)} />

      <p className="pb-2 text-center text-[10px] leading-relaxed text-muted-2">
        Рейтинг формируется только по завершённым сделкам. GIFT MARKET не гарантирует качество описаний продавцов.
      </p>
    </div>
  );
}

function OfferSheet({ ownership, onClose }: { ownership: OwnershipCard | null; onClose: () => void }) {
  const { data: config } = useConfig();
  const toast = useToast();
  const [price, setPrice] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const commission = config?.commission_percent ?? 10;
  const split = splitAmount(Number(price || 0), commission);

  const submit = async () => {
    if (!ownership) return;
    setLoading(true);
    try {
      await api.offer({ ownership_id: ownership.id, price_stars: Number(price), message });
      hapticNotification("success");
      toast.success("Предложение отправлено продавцу");
      setPrice("");
      setMessage("");
      onClose();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet open={Boolean(ownership)} onClose={onClose} title="Предложить цену">
      {ownership && (
        <div className="space-y-3 pb-2">
          <div className="flex items-center gap-3 rounded-2xl border border-line bg-white/[0.03] p-2.5">
            <SmartImage src={ownership.item.image_url} alt={ownership.item.name} className="h-14 w-14 rounded-xl" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-bold">{ownership.item.name}</p>
              <p className="text-[11px] text-muted">
                {ownership.item.collection.name}
                {ownership.serial_number !== null && ` · #${ownership.serial_number}`}
              </p>
              <p className="text-[10.5px] font-semibold" style={{ color: rarityColor(ownership.item.rarity) }}>
                {ownership.item.rarity.toUpperCase()}
              </p>
            </div>
            <Price value={ownership.estimated_value_stars ?? 0} size="sm" />
          </div>

          <div className="relative">
            <input
              className="field pr-12 text-[17px] font-extrabold"
              inputMode="numeric"
              placeholder="Ваша цена в Stars"
              value={price}
              onChange={(event) => setPrice(event.target.value.replace(/\D/g, "").slice(0, 7))}
            />
            <StarIcon size={18} className="absolute right-4 top-1/2 -translate-y-1/2" />
          </div>

          {Number(price) > 0 && (
            <p className="text-[11px] text-muted">
              При продаже продавец получит <span className="font-bold text-mint">{split.seller} ★</span> (комиссия{" "}
              {commission}%).
            </p>
          )}

          <textarea
            className="field"
            placeholder="Сообщение продавцу (необязательно)"
            value={message}
            onChange={(event) => setMessage(event.target.value.slice(0, 280))}
          />

          <button className="btn btn-primary w-full" onClick={submit} disabled={loading || !Number(price)}>
            {loading ? <Spinner size={16} /> : null} Отправить предложение
          </button>
          <p className="text-[10.5px] leading-relaxed text-muted-2">
            Предложение не является сделкой. Если продавец примет его, создаётся лот по вашей цене, и вы сможете
            оплатить его через Telegram Stars.
          </p>
        </div>
      )}
    </Sheet>
  );
}
