import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Ban,
  Check,
  Coins,
  FileClock,
  Flag,
  Gift,
  Layers,
  Plus,
  Receipt,
  Settings2,
  ShieldCheck,
  Users,
} from "lucide-react";
import { api, errorMessage } from "../lib/api";
import { useMe } from "../hooks/useApi";
import type { AdminSettings } from "../lib/types";
import {
  EmptyState,
  ErrorState,
  Price,
  RarityBadge,
  Sheet,
  SmartImage,
  Spinner,
  StarIcon,
} from "../components/ui";
import { formatDate, formatNumber, RARITY_ORDER } from "../lib/format";
import { hapticNotification, selectionHaptic } from "../lib/telegram";
import { useToast } from "../context/ToastContext";

type Tab = "overview" | "users" | "gifts" | "collections" | "orders" | "payouts" | "reports" | "settings" | "audit";

const TABS: Array<{ id: Tab; label: string; icon: typeof Users }> = [
  { id: "overview", label: "Обзор", icon: Activity },
  { id: "users", label: "Люди", icon: Users },
  { id: "gifts", label: "Подарки", icon: Gift },
  { id: "collections", label: "Коллекции", icon: Layers },
  { id: "orders", label: "Заказы", icon: Receipt },
  { id: "payouts", label: "Выплаты", icon: Coins },
  { id: "reports", label: "Жалобы", icon: Flag },
  { id: "settings", label: "Настройки", icon: Settings2 },
  { id: "audit", label: "Аудит", icon: FileClock },
];

export default function AdminPage() {
  const { data: me } = useMe();
  const [tab, setTab] = useState<Tab>("overview");
  const [createOpen, setCreateOpen] = useState<"collection" | "item" | "grant" | null>(null);

  useEffect(() => {
    document.title = "Админ-панель — GIFT MARKET";
  }, []);

  if (!me?.is_admin) {
    return (
      <div className="pt-10">
        <EmptyState title="Доступ закрыт" description="Админ-панель доступна только администраторам платформы." icon={<ShieldCheck size={22} />} />
      </div>
    );
  }

  return (
    <div className="space-y-4 pt-1">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-extrabold tracking-[-0.02em]">Админ-панель</h1>
          <p className="mt-0.5 text-[11.5px] text-muted">
            {me.user.display_name} · {me.admin_role ?? "admin"}
          </p>
        </div>
        <button className="btn btn-soft btn-sm" onClick={() => setCreateOpen("item")}>
          <Plus size={14} /> Подарок
        </button>
      </div>

      <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4">
        {TABS.map((entry) => {
          const Icon = entry.icon;
          return (
            <button
              key={entry.id}
              className={`chip shrink-0 ${tab === entry.id ? "chip-active" : ""}`}
              onClick={() => {
                selectionHaptic();
                setTab(entry.id);
              }}
            >
              <Icon size={12} /> {entry.label}
            </button>
          );
        })}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "users" && <UsersTab />}
      {tab === "gifts" && <GiftsTab onCreate={() => setCreateOpen("item")} onGrant={() => setCreateOpen("grant")} />}
      {tab === "collections" && <CollectionsTab onCreate={() => setCreateOpen("collection")} />}
      {tab === "orders" && <OrdersTab />}
      {tab === "payouts" && <PayoutsTab />}
      {tab === "reports" && <ReportsTab />}
      {tab === "settings" && <SettingsTab />}
      {tab === "audit" && <AuditTab />}

      <Sheet open={createOpen === "collection"} onClose={() => setCreateOpen(null)} title="Новая коллекция">
        <CollectionForm onDone={() => setCreateOpen(null)} />
      </Sheet>
      <Sheet open={createOpen === "item"} onClose={() => setCreateOpen(null)} title="Новый подарок">
        <ItemForm onDone={() => setCreateOpen(null)} />
      </Sheet>
      <Sheet open={createOpen === "grant"} onClose={() => setCreateOpen(null)} title="Выдать подарок пользователю">
        <GrantForm onDone={() => setCreateOpen(null)} />
      </Sheet>
    </div>
  );
}

/* ------------------------------------------------------------------ tabs */
function OverviewTab() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin-overview"],
    queryFn: api.admin.overview,
    staleTime: 15_000,
  });

  if (isLoading) return <div className="py-10 text-center"><Spinner /></div>;
  if (isError || !data) return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;

  const maxVolume = Math.max(1, ...data.revenue_series.map((point) => point.volume_stars));

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Metric label="Оборот" value={`${formatNumber(data.total_volume_stars)} ★`} hint="завершённые сделки" />
        <Metric label="Доход платформы" value={`${formatNumber(data.platform_revenue_stars)} ★`} hint="журнал комиссий" accent="#34d399" />
        <Metric label="Начислено продавцам" value={`${formatNumber(data.seller_credits_stars)} ★`} hint="всего" />
        <Metric label="Сделок" value={formatNumber(data.orders_fulfilled_count)} hint={`из ${data.orders_count} заказов`} />
        <Metric label="Активные лоты" value={formatNumber(data.active_listings)} hint="на маркете" />
        <Metric label="Пользователи" value={formatNumber(data.users_total)} hint={`${data.active_users_7d} активны за 7 дней`} />
        <Metric label="Ожидает выплат" value={`${formatNumber(data.pending_payouts_stars)} ★`} hint={`${data.pending_payout_requests} заявок`} accent="#fbbf24" />
        <Metric label="Жалобы" value={formatNumber(data.open_reports)} hint="открытые" accent={data.open_reports ? "#f43f5e" : undefined} />
      </div>

      <div className="rounded-2xl border border-line bg-white/[0.025] p-3">
        <p className="mb-2 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-2">Оборот за 14 дней</p>
        <div className="flex h-[92px] items-end gap-1">
          {data.revenue_series.map((point) => (
            <div key={point.date} className="group relative flex-1">
              <div
                className="w-full rounded-t bg-gradient-to-t from-violet/30 to-violet"
                style={{ height: `${Math.max(4, (point.volume_stars / maxVolume) * 88)}px` }}
                title={`${point.date}: ${point.volume_stars} ★ · ${point.orders} сделок`}
              />
            </div>
          ))}
        </div>
        <div className="mt-1.5 flex justify-between text-[9px] text-muted-2">
          <span>{data.revenue_series[0]?.date}</span>
          <span>{data.revenue_series[data.revenue_series.length - 1]?.date}</span>
        </div>
      </div>

      <div className="rounded-2xl border border-line bg-white/[0.025] p-3">
        <p className="mb-2 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-2">Популярные подарки</p>
        {data.top_gifts.length === 0 ? (
          <p className="text-[11.5px] text-muted-2">Пока нет продаж.</p>
        ) : (
          <div className="space-y-1.5">
            {data.top_gifts.map((gift) => (
              <div key={gift.id} className="flex items-center justify-between text-[11.5px]">
                <span className="truncate font-semibold">{gift.name}</span>
                <span className="shrink-0 text-muted">
                  {gift.sales} сделок · {formatNumber(gift.volume_stars)} ★
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-line bg-white/[0.025] p-3">
        <p className="mb-2 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-2">Балансы продавцов</p>
        <div className="grid grid-cols-2 gap-2 text-[11.5px]">
          <div className="rounded-xl bg-black/25 p-2">
            <p className="text-muted-2">В ожидании</p>
            <p className="font-extrabold">{formatNumber(data.seller_pending_stars)} ★</p>
          </div>
          <div className="rounded-xl bg-black/25 p-2">
            <p className="text-muted-2">Доступно</p>
            <p className="font-extrabold text-mint">{formatNumber(data.seller_available_stars)} ★</p>
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <p className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-2">Последние заказы</p>
        {data.recent_orders.map((order) => (
          <div key={order.id} className="flex items-center justify-between rounded-xl border border-line bg-white/[0.02] px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-[11.5px] font-semibold">{order.item_name}</p>
              <p className="text-[9.5px] text-muted-2">
                {order.order_number} · {order.buyer?.display_name} · {formatDate(order.created_at, true)}
              </p>
            </div>
            <span className="shrink-0 text-[11px] font-bold">{order.amount_stars} ★</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function UsersTab() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["admin-users", search, page],
    queryFn: () => api.admin.users({ q: search || undefined, page }),
    staleTime: 10_000,
  });
  const client = useQueryClient();
  const toast = useToast();

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.admin.updateUser(id, body),
    onSuccess: () => {
      toast.success("Пользователь обновлён");
      client.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <div className="space-y-3">
      <input className="field" placeholder="Поиск по @username или Telegram ID" value={search} onChange={(event) => setSearch(event.target.value)} />

      {query.isLoading ? (
        <div className="py-8 text-center"><Spinner /></div>
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error)} onRetry={() => query.refetch()} />
      ) : !query.data?.items.length ? (
        <EmptyState title="Пользователи не найдены" />
      ) : (
        <div className="space-y-2">
          {query.data.items.map((user) => (
            <div key={user.id} className="rounded-2xl border border-line bg-white/[0.02] p-2.5">
              <div className="flex items-center gap-2.5">
                <div className="grid h-9 w-9 place-items-center rounded-full bg-violet/20 text-[10px] font-bold">
                  {user.display_name.slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-bold">
                    {user.display_name} {user.is_admin && <span className="text-violet-soft">· admin</span>}
                  </p>
                  <p className="text-[10px] text-muted-2">
                    ID {user.telegram_id} · подарков {user.gifts_owned} · продаж {user.sales_count}
                  </p>
                  <p className="text-[10px] text-muted-2">
                    баланс: {user.available_stars} ★ доступно / {user.pending_stars} ★ ожидает
                  </p>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <button
                  className={`btn btn-sm ${user.is_blocked ? "btn-primary" : "btn-danger"}`}
                  onClick={() => update.mutate({ id: user.id, body: { is_blocked: !user.is_blocked } })}
                >
                  {user.is_blocked ? <Check size={12} /> : <Ban size={12} />}
                  {user.is_blocked ? "Разблокировать" : "Блокировать"}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => update.mutate({ id: user.id, body: { is_admin: !user.is_admin } })}
                >
                  <ShieldCheck size={12} /> {user.is_admin ? "Снять админа" : "Сделать админом"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {query.data && query.data.pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
            Назад
          </button>
          <span className="text-[11px] text-muted">
            {page} / {query.data.pages}
          </span>
          <button
            className="btn btn-ghost btn-sm"
            disabled={page >= query.data.pages}
            onClick={() => setPage((value) => value + 1)}
          >
            Далее
          </button>
        </div>
      )}
    </div>
  );
}

function GiftsTab({ onCreate, onGrant }: { onCreate: () => void; onGrant: () => void }) {
  const query = useQuery({
    queryKey: ["admin-items", 1],
    queryFn: () => api.admin.items({ page: 1 }),
    staleTime: 15_000,
  });
  const client = useQueryClient();
  const toast = useToast();

  const toggleStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => api.admin.updateItem(id, { status }),
    onSuccess: () => {
      toast.success("Статус обновлён");
      client.invalidateQueries({ queryKey: ["admin-items"] });
      client.invalidateQueries({ queryKey: ["market"] });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <button className="btn btn-primary btn-sm flex-1" onClick={onCreate}>
          <Plus size={13} /> Новый подарок
        </button>
        <button className="btn btn-ghost btn-sm flex-1" onClick={onGrant}>
          <Gift size={13} /> Выдать вручную
        </button>
      </div>

      {query.isLoading ? (
        <div className="py-8 text-center"><Spinner /></div>
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error)} onRetry={() => query.refetch()} />
      ) : !query.data?.items.length ? (
        <EmptyState title="Подарков пока нет" description="Создайте коллекцию и добавьте первый предмет." />
      ) : (
        query.data.items.map((row) => (
          <div key={row.item.id} className="flex gap-2.5 rounded-2xl border border-line bg-white/[0.02] p-2.5">
            <SmartImage src={row.item.image_url} alt={row.item.name} className="h-14 w-14 shrink-0 rounded-xl" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12px] font-bold">{row.item.name}</p>
              <p className="text-[10px] text-muted-2">
                {row.collection_name} · {row.minted_count}/{row.edition_size} · {row.item.primary_price_stars} ★
              </p>
              <div className="mt-1 flex items-center gap-1.5">
                <RarityBadge rarity={row.item.rarity} />
                <span className="rounded-full bg-white/[0.06] px-2 py-[2px] text-[9px] font-bold uppercase text-muted">
                  {row.item.status}
                </span>
              </div>
              <div className="mt-1.5 flex gap-1.5">
                {row.item.status !== "active" && (
                  <button
                    className="btn btn-soft btn-sm"
                    onClick={() => toggleStatus.mutate({ id: row.item.id, status: "active" })}
                  >
                    Опубликовать
                  </button>
                )}
                {row.item.status === "active" && (
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => toggleStatus.mutate({ id: row.item.id, status: "archived" })}
                  >
                    В архив
                  </button>
                )}
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function CollectionsTab({ onCreate }: { onCreate: () => void }) {
  const query = useQuery({ queryKey: ["admin-collections"], queryFn: api.admin.collections, staleTime: 15_000 });
  const client = useQueryClient();
  const toast = useToast();

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => api.admin.updateCollection(id, body),
    onSuccess: () => {
      toast.success("Коллекция обновлена");
      client.invalidateQueries({ queryKey: ["admin-collections"] });
      client.invalidateQueries({ queryKey: ["collections"] });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <div className="space-y-3">
      <button className="btn btn-primary btn-sm w-full" onClick={onCreate}>
        <Plus size={13} /> Новая коллекция
      </button>
      {query.isLoading ? (
        <div className="py-8 text-center"><Spinner /></div>
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error)} onRetry={() => query.refetch()} />
      ) : (
        query.data?.map((collection) => (
          <div key={collection.id} className="rounded-2xl border border-line bg-white/[0.02] p-2.5">
            <div className="flex items-center gap-2.5">
              <SmartImage src={collection.cover_url} alt={collection.name} className="h-12 w-12 rounded-xl" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-bold">{collection.name}</p>
                <p className="text-[10px] text-muted-2">
                  {collection.items_total} подарков · продано {collection.items_sold} · {collection.status}
                </p>
              </div>
              <RarityBadge rarity={collection.rarity} />
            </div>
            <div className="mt-2 flex gap-1.5">
              {collection.status !== "active" ? (
                <button className="btn btn-soft btn-sm" onClick={() => update.mutate({ id: collection.id, body: { status: "active" } })}>
                  Активировать
                </button>
              ) : (
                <button className="btn btn-ghost btn-sm" onClick={() => update.mutate({ id: collection.id, body: { status: "archived" } })}>
                  В архив
                </button>
              )}
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => update.mutate({ id: collection.id, body: { is_featured: !collection.is_featured } })}
              >
                {collection.is_featured ? "Убрать из featured" : "В featured"}
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function OrdersTab() {
  const [status, setStatus] = useState("");
  const query = useQuery({
    queryKey: ["admin-orders", status],
    queryFn: () => api.admin.orders({ status: status || undefined }),
    staleTime: 10_000,
  });
  const toast = useToast();
  const client = useQueryClient();
  const [processing, setProcessing] = useState<number | null>(null);

  const refund = async (id: number) => {
    setProcessing(id);
    try {
      const result = await api.admin.refundOrder(id, "Возврат администратором");
      toast.success(`Возврат: ${result.status}`);
      hapticNotification("success");
      client.invalidateQueries({ queryKey: ["admin-orders"] });
      client.invalidateQueries({ queryKey: ["admin-overview"] });
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setProcessing(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="no-scrollbar flex gap-2 overflow-x-auto">
        {["", "pending_payment", "paid", "fulfilled", "refunded", "refund_pending"].map((value) => (
          <button
            key={value || "all"}
            className={`chip shrink-0 ${status === value ? "chip-active" : ""}`}
            onClick={() => {
              selectionHaptic();
              setStatus(value);
            }}
          >
            {value ? value.replace("_", " ") : "все"}
          </button>
        ))}
      </div>

      {query.isLoading ? (
        <div className="py-8 text-center"><Spinner /></div>
      ) : query.isError ? (
        <ErrorState message={errorMessage(query.error)} onRetry={() => query.refetch()} />
      ) : !query.data?.items.length ? (
        <EmptyState title="Заказов нет" />
      ) : (
        query.data.items.map((order) => (
          <div key={order.id} className="rounded-2xl border border-line bg-white/[0.02] p-2.5">
            <div className="flex items-center gap-2.5">
              <SmartImage src={order.image_url} alt={order.item_name} className="h-11 w-11 rounded-lg" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-bold">{order.item_name}</p>
                <p className="text-[10px] text-muted-2">
                  {order.order_number} · {order.buyer?.display_name} → {order.seller?.display_name ?? "платформа"}
                </p>
                <p className="text-[10px] text-muted-2">{formatDate(order.created_at, true)} · {order.status}</p>
              </div>
              <div className="text-right">
                <p className="text-[12px] font-extrabold">{order.amount_stars} ★</p>
                <p className="text-[9.5px] text-muted-2">fee {order.commission_stars} ★</p>
              </div>
            </div>
            {order.status === "paid" && (
              <button className="btn btn-danger btn-sm mt-2 w-full" disabled={processing === order.id} onClick={() => refund(order.id)}>
                {processing === order.id ? <Spinner size={12} /> : null} Вернуть Stars покупателю
              </button>
            )}
          </div>
        ))
      )}
    </div>
  );
}

function PayoutsTab() {
  const [status, setStatus] = useState("requested");
  const query = useQuery({
    queryKey: ["admin-payouts", status],
    queryFn: () => api.admin.payouts({ status: status || undefined }),
    staleTime: 10_000,
  });
  const toast = useToast();
  const client = useQueryClient();
  const [busy, setBusy] = useState<number | null>(null);

  const decide = async (id: number, decision: string) => {
    setBusy(id);
    try {
      await api.admin.decidePayout(id, {
        status: decision,
        admin_note: decision === "rejected" ? "Отклонено администратором" : "Обработано вручную",
        external_reference: decision === "paid" ? `manual-${Date.now()}` : "",
      });
      toast.success("Заявка обновлена");
      client.invalidateQueries({ queryKey: ["admin-payouts"] });
      client.invalidateQueries({ queryKey: ["me"] });
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {["requested", "approved", "paid", "rejected", ""].map((value) => (
          <button
            key={value || "all"}
            className={`chip ${status === value ? "chip-active" : ""}`}
            onClick={() => {
              selectionHaptic();
              setStatus(value);
            }}
          >
            {value || "все"}
          </button>
        ))}
      </div>

      <div className="rounded-2xl border border-gold/25 bg-gold/[0.06] p-2.5 text-[10.5px] leading-relaxed text-gold/85">
        Выплаты выполняются вручную вне приложения. Комиссия платформы уже удержана при продаже; здесь происходит
        только фиксация решения и суммы.
      </div>

      {query.isLoading ? (
        <div className="py-8 text-center"><Spinner /></div>
      ) : !query.data?.items.length ? (
        <EmptyState title="Заявок нет" description="Когда продавец запросит выплату, она появится здесь." icon={<Coins size={20} />} />
      ) : (
        query.data.items.map((payout) => (
          <div key={payout.id} className="rounded-2xl border border-line bg-white/[0.02] p-2.5">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <p className="truncate text-[12px] font-bold">{payout.user.display_name}</p>
                <p className="text-[10px] text-muted-2">
                  {payout.method} · {payout.destination || "без реквизитов"} · {formatDate(payout.created_at, true)}
                </p>
              </div>
              <Price value={payout.amount_stars} size="sm" />
            </div>
            <p className="mt-1 text-[9.5px] font-bold uppercase tracking-wide text-muted-2">{payout.status}</p>
            {["requested", "approved"].includes(payout.status) && (
              <div className="mt-2 flex gap-1.5">
                {payout.status === "requested" && (
                  <button className="btn btn-soft btn-sm flex-1" disabled={busy === payout.id} onClick={() => decide(payout.id, "approved")}>
                    Подтвердить
                  </button>
                )}
                {payout.status === "approved" && (
                  <button className="btn btn-primary btn-sm flex-1" disabled={busy === payout.id} onClick={() => decide(payout.id, "paid")}>
                    Отметить выплату
                  </button>
                )}
                <button className="btn btn-danger btn-sm flex-1" disabled={busy === payout.id} onClick={() => decide(payout.id, "rejected")}>
                  Отклонить
                </button>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}

function ReportsTab() {
  const query = useQuery({ queryKey: ["admin-reports"], queryFn: () => api.admin.reports(), staleTime: 10_000 });
  const toast = useToast();
  const client = useQueryClient();

  const resolve = async (id: number, status: string) => {
    try {
      await api.admin.resolveReport(id, { status, resolution: "Проверено модератором" });
      toast.success("Жалоба обновлена");
      client.invalidateQueries({ queryKey: ["admin-reports"] });
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };

  if (query.isLoading) return <div className="py-8 text-center"><Spinner /></div>;
  if (!query.data?.items.length) {
    return <EmptyState title="Жалоб нет" description="Здесь появятся обращения пользователей." icon={<Flag size={20} />} />;
  }

  return (
    <div className="space-y-2">
      {query.data.items.map((report) => (
        <div key={report.id} className="rounded-2xl border border-line bg-white/[0.02] p-2.5">
          <div className="flex items-center justify-between">
            <p className="text-[11.5px] font-bold">
              {report.reporter.display_name} → {report.target_type} #{report.target_id}
            </p>
            <span className="status-pill bg-white/[0.06] text-[10px] text-muted">{report.status}</span>
          </div>
          <p className="mt-1 text-[11px] font-semibold text-rose">{report.reason}</p>
          {report.details && <p className="mt-0.5 text-[10.5px] text-muted">{report.details}</p>}
          <p className="mt-1 text-[9.5px] text-muted-2">{formatDate(report.created_at, true)}</p>
          {["open", "reviewing"].includes(report.status) && (
            <div className="mt-2 flex gap-1.5">
              <button className="btn btn-soft btn-sm flex-1" onClick={() => resolve(report.id, "reviewing")}>
                В работу
              </button>
              <button className="btn btn-ghost btn-sm flex-1" onClick={() => resolve(report.id, "resolved")}>
                Решено
              </button>
              <button className="btn btn-danger btn-sm flex-1" onClick={() => resolve(report.id, "dismissed")}>
                Отклонить
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function SettingsTab() {
  const query = useQuery({ queryKey: ["admin-settings"], queryFn: api.admin.settings, staleTime: 10_000 });
  const toast = useToast();
  const client = useQueryClient();
  const [form, setForm] = useState<Partial<AdminSettings>>({});
  const current = useMemo(() => ({ ...query.data, ...form }) as AdminSettings | undefined, [query.data, form]);

  const save = useMutation({
    mutationFn: () => api.admin.updateSettings(form),
    onSuccess: () => {
      toast.success("Настройки сохранены");
      hapticNotification("success");
      setForm({});
      client.invalidateQueries({ queryKey: ["admin-settings"] });
      client.invalidateQueries({ queryKey: ["config"] });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  if (query.isLoading || !current) return <div className="py-8 text-center"><Spinner /></div>;
  if (query.isError) return <ErrorState message={errorMessage(query.error)} onRetry={() => query.refetch()} />;

  const field = (key: keyof AdminSettings, label: string, type: "number" | "text" | "textarea" = "number", hint?: string) => (
    <div>
      <label className="mb-1 block text-[10px] font-bold uppercase tracking-[0.1em] text-muted-2">{label}</label>
      {type === "textarea" ? (
        <textarea
          className="field"
          value={String(current[key] ?? "")}
          onChange={(event) => setForm((prev) => ({ ...prev, [key]: event.target.value }))}
        />
      ) : (
        <input
          className="field"
          type={type === "number" ? "number" : "text"}
          value={String(current[key] ?? "")}
          onChange={(event) =>
            setForm((prev) => ({ ...prev, [key]: type === "number" ? Number(event.target.value) : event.target.value }))
          }
        />
      )}
      {hint && <p className="mt-1 text-[9.5px] text-muted-2">{hint}</p>}
    </div>
  );

  return (
    <div className="space-y-3">
      <div className="rounded-2xl border border-line bg-white/[0.02] p-3">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">Экономика</p>
        <div className="space-y-2.5">
          {field("commission_percent", "Комиссия платформы, %", "number", "0–50%. При 10% продавец получает 90%.")}
          <div className="grid grid-cols-2 gap-2">
            {field("min_listing_price", "Мин. цена лота, ★")}
            {field("max_listing_price", "Макс. цена лота, ★")}
          </div>
          <div className="grid grid-cols-2 gap-2">
            {field("hold_hours", "Удержание, ч")}
            {field("min_payout_stars", "Мин. выплата, ★")}
          </div>
          {field("max_active_listings", "Лимит активных лотов")}
        </div>
      </div>

      <div className="rounded-2xl border border-line bg-white/[0.02] p-3">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">Режим обслуживания</p>
        <button
          className={`mb-2 flex h-9 items-center gap-2 rounded-xl px-3 text-[11.5px] font-bold ${
            current.maintenance_mode ? "bg-danger/20 text-rose" : "bg-white/[0.06] text-muted"
          }`}
          onClick={() => setForm((prev) => ({ ...prev, maintenance_mode: !current.maintenance_mode }))}
        >
          {current.maintenance_mode ? "Включён" : "Выключен"} · нажмите, чтобы переключить
        </button>
        {field("maintenance_message", "Сообщение для пользователей", "text")}
      </div>

      <div className="rounded-2xl border border-line bg-white/[0.02] p-3">
        <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">Политика выплат</p>
        {field("payout_note", "Текст для продавцов", "textarea")}
        {field("terms_url", "Ссылка на правила", "text")}
      </div>

      <button className="btn btn-primary w-full" onClick={() => save.mutate()} disabled={save.isPending || !Object.keys(form).length}>
        {save.isPending ? <Spinner size={15} /> : <Check size={15} />} Сохранить настройки
      </button>
      <p className="text-[10px] text-muted-2">
        Обновлено: {formatDate(current.updated_at, true)}
        {current.updated_by ? ` · ${current.updated_by.display_name}` : ""}
      </p>
    </div>
  );
}

function AuditTab() {
  const query = useQuery({ queryKey: ["admin-audit"], queryFn: () => api.admin.audit(), staleTime: 10_000 });
  if (query.isLoading) return <div className="py-8 text-center"><Spinner /></div>;
  if (!query.data?.items.length) return <EmptyState title="Журнал пуст" description="Действия администраторов будут записаны здесь." />;

  return (
    <div className="space-y-1.5">
      {query.data.items.map((row) => (
        <div key={row.id} className="rounded-xl border border-line bg-white/[0.02] px-3 py-2">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-bold">{row.action}</p>
            <span className="text-[9.5px] text-muted-2">{formatDate(row.created_at, true)}</span>
          </div>
          <p className="text-[9.5px] text-muted-2">
            {row.admin?.display_name ?? "system"} · {row.entity_type} #{row.entity_id ?? "—"}
          </p>
          {row.after && row.after !== "{}" && (
            <p className="mt-0.5 truncate text-[9px] text-muted-2">{row.after}</p>
          )}
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- forms */
function CollectionForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const client = useQueryClient();
  const [form, setForm] = useState({
    slug: "",
    name: "",
    description: "",
    cover_url: "",
    accent: "#7c5cff",
    rarity: "rare",
    status: "draft",
    is_featured: false,
  });
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      await api.admin.createCollection(form);
      toast.success("Коллекция создана");
      client.invalidateQueries({ queryKey: ["admin-collections"] });
      onDone();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2.5 pb-2">
      <input className="field" placeholder="slug (латиница, дефисы)" value={form.slug} onChange={(event) => setForm({ ...form, slug: event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "") })} />
      <input className="field" placeholder="Название" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
      <textarea className="field" placeholder="Описание" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
      <input className="field" placeholder="Обложка: /gifts/aurum-drake.jpg или https://…" value={form.cover_url} onChange={(event) => setForm({ ...form, cover_url: event.target.value })} />
      <div className="flex flex-wrap gap-1.5">
        {RARITY_ORDER.map((value) => (
          <button key={value} className={`chip ${form.rarity === value ? "chip-active" : ""}`} onClick={() => setForm({ ...form, rarity: value })}>
            {value}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5">
        {["draft", "active"].map((value) => (
          <button key={value} className={`chip ${form.status === value ? "chip-active" : ""}`} onClick={() => setForm({ ...form, status: value })}>
            {value === "draft" ? "Черновик" : "Активна"}
          </button>
        ))}
        <button className={`chip ${form.is_featured ? "chip-active" : ""}`} onClick={() => setForm({ ...form, is_featured: !form.is_featured })}>
          featured
        </button>
      </div>
      <button className="btn btn-primary w-full" onClick={submit} disabled={loading || !form.slug || !form.name}>
        {loading ? <Spinner size={15} /> : <Plus size={15} />} Создать коллекцию
      </button>
    </div>
  );
}

function ItemForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const client = useQueryClient();
  const collections = useQuery({ queryKey: ["admin-collections"], queryFn: api.admin.collections });
  const [form, setForm] = useState({
    collection_id: 0,
    name: "",
    description: "",
    image_url: "",
    rarity: "rare",
    edition_size: 100,
    primary_price_stars: 100,
    status: "active",
    source: "internal",
    is_tradeable: true,
    is_featured: false,
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!form.collection_id && collections.data?.length) {
      setForm((prev) => ({ ...prev, collection_id: collections.data![0].id }));
    }
  }, [collections.data, form.collection_id]);

  const submit = async () => {
    setLoading(true);
    try {
      await api.admin.createItem(form);
      toast.success("Подарок создан");
      client.invalidateQueries({ queryKey: ["admin-items"] });
      client.invalidateQueries({ queryKey: ["market"] });
      onDone();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2.5 pb-2">
      <select
        className="field"
        value={form.collection_id}
        onChange={(event) => setForm({ ...form, collection_id: Number(event.target.value) })}
      >
        <option value={0}>Выберите коллекцию</option>
        {collections.data?.map((collection) => (
          <option key={collection.id} value={collection.id}>
            {collection.name}
          </option>
        ))}
      </select>
      <input className="field" placeholder="Название подарка" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
      <textarea className="field" placeholder="Описание" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
      <input className="field" placeholder="Изображение: /gifts/… или https://…" value={form.image_url} onChange={(event) => setForm({ ...form, image_url: event.target.value })} />
      <div className="grid grid-cols-2 gap-2">
        <input className="field" type="number" placeholder="Тираж" value={form.edition_size} onChange={(event) => setForm({ ...form, edition_size: Number(event.target.value) })} />
        <input className="field" type="number" placeholder="Цена, ★" value={form.primary_price_stars} onChange={(event) => setForm({ ...form, primary_price_stars: Number(event.target.value) })} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {RARITY_ORDER.map((value) => (
          <button key={value} className={`chip ${form.rarity === value ? "chip-active" : ""}`} onClick={() => setForm({ ...form, rarity: value })}>
            {value}
          </button>
        ))}
      </div>
      <div className="flex gap-1.5">
        <button className={`chip ${form.is_tradeable ? "chip-active" : ""}`} onClick={() => setForm({ ...form, is_tradeable: !form.is_tradeable })}>
          перепродажа
        </button>
        <button className={`chip ${form.is_featured ? "chip-active" : ""}`} onClick={() => setForm({ ...form, is_featured: !form.is_featured })}>
          featured
        </button>
        <button className={`chip ${form.status === "active" ? "chip-active" : ""}`} onClick={() => setForm({ ...form, status: form.status === "active" ? "draft" : "active" })}>
          {form.status === "active" ? "активен" : "черновик"}
        </button>
      </div>
      <button className="btn btn-primary w-full" onClick={submit} disabled={loading || !form.name || !form.collection_id}>
        {loading ? <Spinner size={15} /> : <Plus size={15} />} Создать подарок
      </button>
      <p className="text-[10px] leading-relaxed text-muted-2">
        Изображения из папки <code>/gifts</code> доступны фронтенду; для Telegram-инвойсов нужен публичный HTTPS URL
        (Cloudflare Pages подойдёт).
      </p>
    </div>
  );
}

function GrantForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const client = useQueryClient();
  const items = useQuery({ queryKey: ["admin-items", 1], queryFn: () => api.admin.items({ page: 1 }) });
  const [form, setForm] = useState({ user_id: 0, item_id: 0, quantity: 1, reason: "" });
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      const result = await api.admin.grant(form);
      toast.success(result.message);
      client.invalidateQueries({ queryKey: ["admin-items"] });
      onDone();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2.5 pb-2">
      <input className="field" placeholder="Telegram ID пользователя" value={form.user_id || ""} onChange={(event) => setForm({ ...form, user_id: Number(event.target.value.replace(/\D/g, "")) })} />
      <select className="field" value={form.item_id} onChange={(event) => setForm({ ...form, item_id: Number(event.target.value) })}>
        <option value={0}>Выберите подарок</option>
        {items.data?.items.map((row) => (
          <option key={row.item.id} value={row.item.id}>
            {row.item.name} ({row.minted_count}/{row.edition_size})
          </option>
        ))}
      </select>
      <input className="field" type="number" min={1} max={50} value={form.quantity} onChange={(event) => setForm({ ...form, quantity: Math.min(50, Math.max(1, Number(event.target.value))) })} />
      <input className="field" placeholder="Причина (для аудита)" value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
      <button className="btn btn-primary w-full" onClick={submit} disabled={loading || !form.user_id || !form.item_id}>
        {loading ? <Spinner size={15} /> : <Gift size={15} />} Выдать
      </button>
      <p className="text-[10px] text-muted-2">Пользователь должен хотя бы раз открыть приложение, чтобы его аккаунт существовал в базе.</p>
    </div>
  );
}

function Metric({ label, value, hint, accent }: { label: string; value: string; hint?: string; accent?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white/[0.03] p-3">
      <p className="text-[9px] font-bold uppercase tracking-[0.1em] text-muted-2">{label}</p>
      <p className="mt-1 flex items-center gap-1 text-[15px] font-extrabold tabular" style={accent ? { color: accent } : undefined}>
        {value.includes("★") && <StarIcon size={12} />}
        {value.replace(" ★", "")}
      </p>
      {hint && <p className="mt-0.5 text-[9px] text-muted-2">{hint}</p>}
    </div>
  );
}
