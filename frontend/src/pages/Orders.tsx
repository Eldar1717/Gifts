import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Receipt,
  RefreshCcw,
  ShoppingBag,
  Star,
  Store,
} from "lucide-react";
import { api, errorMessage } from "../lib/api";
import { useOrders } from "../hooks/useApi";
import type { Order } from "../lib/types";
import {
  EmptyState,
  ErrorState,
  Price,
  RowSkeleton,
  Segmented,
  Sheet,
  SmartImage,
  Spinner,
} from "../components/ui";
import { ORDER_STATUS_META, formatDate } from "../lib/format";
import { haptic, hapticNotification, selectionHaptic } from "../lib/telegram";
import { useToast } from "../context/ToastContext";

export default function OrdersPage() {
  const [role, setRole] = useState<"buyer" | "seller">("buyer");
  const { data, isLoading, isError, error, refetch } = useOrders(role);
  const [selected, setSelected] = useState<Order | null>(null);

  return (
    <div className="space-y-4 pt-1">
      <div>
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em]">История сделок</h1>
        <p className="mt-0.5 text-[12px] text-muted">Покупки, продажи, статусы платежей и чеки</p>
      </div>

      <Segmented
        value={role}
        onChange={(value) => {
          selectionHaptic();
          setRole(value);
        }}
        options={[
          { value: "buyer", label: "Покупки" },
          { value: "seller", label: "Продажи" },
        ]}
      />

      {isLoading ? (
        <RowSkeleton count={4} />
      ) : isError ? (
        <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
      ) : !data?.items.length ? (
        <EmptyState
          title={role === "buyer" ? "Покупок пока нет" : "Продаж пока нет"}
          description={
            role === "buyer"
              ? "Найдите подарок на маркете — все покупки и чеки сохранятся здесь."
              : "Выставите предмет из коллекции на продажу, и сделки появятся в этом списке."
          }
          icon={role === "buyer" ? <ShoppingBag size={22} /> : <Store size={22} />}
          action={
            <Link to={role === "buyer" ? "/market" : "/collection"} className="btn btn-primary btn-sm">
              {role === "buyer" ? "Открыть маркет" : "Моя коллекция"}
            </Link>
          }
        />
      ) : (
        <div className="space-y-2.5">
          {data.items.map((order) => {
            const meta = ORDER_STATUS_META[order.status];
            return (
              <button
                key={order.id}
                onClick={() => {
                  haptic("light");
                  setSelected(order);
                }}
                className="flex w-full items-center gap-3 rounded-2xl border border-line bg-white/[0.03] p-2.5 text-left active:scale-[0.995]"
              >
                <SmartImage src={order.item.image_url} alt={order.item.name} className="h-14 w-14 shrink-0 rounded-xl" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-bold">{order.item.name}</p>
                  <p className="text-[10.5px] text-muted-2">
                    {order.order_number} · {formatDate(order.created_at, true)}
                  </p>
                  <span
                    className="status-pill mt-1"
                    style={{ color: meta.color, background: meta.bg, borderColor: `${meta.color}40` }}
                  >
                    {order.status === "fulfilled" && role === "buyer" ? "Получено" : meta.label}
                  </span>
                </div>
                <div className="text-right">
                  <Price value={order.amount_stars} size="sm" />
                  <p className="mt-0.5 flex items-center justify-end gap-0.5 text-[10px] font-semibold text-muted-2">
                    {role === "buyer" ? <ArrowDownLeft size={10} /> : <ArrowUpRight size={10} />}
                    {role === "buyer" ? "покупка" : `+${order.seller_amount_stars} ★`}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      )}

      <OrderSheet order={selected} onClose={() => setSelected(null)} role={role} />
    </div>
  );
}

function OrderSheet({ order, onClose, role }: { order: Order | null; onClose: () => void; role: "buyer" | "seller" }) {
  const client = useQueryClient();
  const toast = useToast();
  const [detail, setDetail] = useState<{ payment: { telegram_payment_charge_id: string | null; status: string } | null } | null>(null);
  const [loading, setLoading] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [reviewed, setReviewed] = useState(false);

  useEffect(() => {
    if (!order) return;
    setReviewed(order.reviewed);
    setDetail(null);
    api
      .order(order.id)
      .then((data) => setDetail(data))
      .catch(() => setDetail(null));
  }, [order]);

  if (!order) return null;
  const meta = ORDER_STATUS_META[order.status];

  const refund = async () => {
    setLoading(true);
    try {
      await api.refundOrder(order.id);
      toast.success("Возврат отправлен в Telegram");
      hapticNotification("success");
      client.invalidateQueries({ queryKey: ["orders"] });
      client.invalidateQueries({ queryKey: ["me"] });
      onClose();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const sendReview = async () => {
    setLoading(true);
    try {
      await api.review({ order_id: order.id, rating, comment });
      toast.success("Спасибо за отзыв!");
      setReviewed(true);
      client.invalidateQueries({ queryKey: ["orders"] });
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet open={Boolean(order)} onClose={onClose} title="Детали сделки">
      <div className="space-y-3 pb-2">
        <div className="flex items-center gap-3 rounded-2xl border border-line bg-white/[0.03] p-2.5">
          <SmartImage src={order.item.image_url} alt={order.item.name} className="h-16 w-16 rounded-xl" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13.5px] font-bold">{order.item.name}</p>
            <p className="text-[11px] text-muted">{order.item.collection.name}</p>
            {order.serial_number !== null && (
              <p className="text-[10.5px] font-semibold text-violet-soft">Экземпляр #{order.serial_number}</p>
            )}
          </div>
          <Price value={order.amount_stars} size="md" />
        </div>

        <div className="space-y-1.5 rounded-2xl border border-line bg-white/[0.02] p-3 text-[12px]">
          <InfoRow label="Номер заказа" value={order.order_number} />
          <InfoRow label="Статус" value={meta.label} color={meta.color} />
          <InfoRow label="Тип" value={order.order_type === "resale" ? "Перепродажа" : "Первичный выпуск"} />
          <InfoRow label="Создан" value={formatDate(order.created_at, true)} />
          {order.paid_at && <InfoRow label="Оплачен" value={formatDate(order.paid_at, true)} />}
          {order.fulfilled_at && <InfoRow label="Передан" value={formatDate(order.fulfilled_at, true)} />}
          {order.order_type === "resale" && (
            <>
              <InfoRow label="Комиссия платформы" value={`${order.commission_stars} ★`} />
              <InfoRow
                label={role === "buyer" ? "Продавец получил" : "Ваше начисление"}
                value={`${order.seller_amount_stars} ★`}
                color="#34d399"
              />
            </>
          )}
          <InfoRow label="Покупатель" value={order.buyer?.display_name ?? "—"} />
          {detail?.payment?.telegram_payment_charge_id && (
            <div className="flex items-start justify-between gap-3">
              <span className="text-muted">Чек Telegram</span>
              <span className="max-w-[190px] break-all text-right text-[10.5px] font-semibold text-muted">
                {detail.payment.telegram_payment_charge_id}
              </span>
            </div>
          )}
        </div>

        {order.failure_reason && (
          <p className="rounded-xl border border-danger/25 bg-danger/[0.08] p-2.5 text-[11.5px] font-semibold leading-relaxed text-rose">
            {order.failure_reason}
          </p>
        )}

        {role === "buyer" && order.can_review && !reviewed && (
          <div className="rounded-2xl border border-line bg-white/[0.02] p-3">
            <p className="text-[12px] font-bold">Оцените продавца</p>
            <div className="mt-2 flex gap-1.5">
              {[1, 2, 3, 4, 5].map((value) => (
                <button
                  key={value}
                  onClick={() => {
                    selectionHaptic();
                    setRating(value);
                  }}
                  aria-label={`${value} звёзд`}
                >
                  <Star
                    size={24}
                    className={value <= rating ? "text-gold" : "text-white/15"}
                    fill={value <= rating ? "currentColor" : "none"}
                  />
                </button>
              ))}
            </div>
            <textarea
              className="field mt-2"
              placeholder="Короткий отзыв (необязательно)"
              value={comment}
              onChange={(event) => setComment(event.target.value.slice(0, 500))}
            />
            <button className="btn btn-primary btn-sm mt-2 w-full" onClick={sendReview} disabled={loading}>
              {loading ? <Spinner size={14} /> : <Star size={14} />} Отправить отзыв
            </button>
          </div>
        )}

        {role === "buyer" && order.status === "paid" && (
          <button className="btn btn-ghost w-full" onClick={refund} disabled={loading}>
            {loading ? <Spinner size={15} /> : <RefreshCcw size={15} />} Запросить возврат Stars
          </button>
        )}

        <Link
          to={`/gift/${order.item.id}`}
          onClick={onClose}
          className="btn btn-ghost w-full"
        >
          <Receipt size={15} /> Открыть карточку подарка
        </Link>
      </div>
    </Sheet>
  );
}

function InfoRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-muted">{label}</span>
      <span className="text-right font-semibold" style={color ? { color } : undefined}>
        {value}
      </span>
    </div>
  );
}
