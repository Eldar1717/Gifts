import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  BadgeCheck,
  Banknote,
  Bell,
  ChevronRight,
  CircleHelp,
  Gavel,
  Handshake,
  Info,
  Lock,
  LogOut,
  Receipt,
  Settings2,
  ShieldCheck,
  Sparkles,
  Star,
  Wallet,
} from "lucide-react";
import { api, errorMessage, setDevTelegramId } from "../lib/api";
import { useConfig, useMe, useMeta, useOffers, usePayouts, useTransactions } from "../hooks/useApi";
import type { Offer } from "../lib/types";
import {
  Avatar,
  EmptyState,
  ErrorState,
  FullPageLoader,
  Price,
  Sheet,
  Spinner,
  StarIcon,
} from "../components/ui";
import { formatDate, formatNumber, relativeTime } from "../lib/format";
import { haptic, hapticNotification, isTelegram, openTelegramLink, selectionHaptic } from "../lib/telegram";
import { useToast } from "../context/ToastContext";

export default function ProfilePage() {
  const { data: me, isLoading, isError, error, refetch } = useMe();
  const { data: meta } = useMeta();
  const { data: payouts } = usePayouts();
  const { data: transactions } = useTransactions();
  const { data: incomingOffers } = useOffers("incoming");
  const client = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [payoutOpen, setPayoutOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [offersOpen, setOffersOpen] = useState(false);

  useEffect(() => {
    document.title = "Профиль — GIFT MARKET";
  }, []);

  if (isLoading) return <FullPageLoader label="Загружаем профиль" />;
  if (isError || !me) {
    return <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />;
  }

  const { user, stats, balance, settings } = me;
  const toggle = async (key: keyof typeof settings) => {
    selectionHaptic();
    try {
      await api.updateSettings({ [key]: !settings[key] } as never);
      client.invalidateQueries({ queryKey: ["me"] });
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  return (
    <div className="space-y-4 pt-1">
      {/* Header ------------------------------------------------------- */}
      <div className="relative overflow-hidden rounded-[26px] border border-line bg-gradient-to-br from-violet/18 via-surface to-surface p-4">
        <div className="pointer-events-none absolute -right-8 -top-10 h-32 w-32 rounded-full bg-magenta/20 blur-3xl" />
        <div className="flex items-center gap-3">
          <Avatar name={user.display_name} src={user.photo_url} size={58} ring />
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1 truncate text-[17px] font-extrabold">
              {user.display_name}
              {me.is_admin && <BadgeCheck size={15} className="text-violet-soft" />}
            </p>
            <p className="truncate text-[11.5px] font-semibold text-muted">
              {user.username ? `@${user.username}` : `ID ${user.telegram_id}`}
            </p>
            <div className="mt-1 flex items-center gap-2">
              {stats.rating !== null ? (
                <span className="flex items-center gap-1 rounded-full border border-gold/30 bg-gold/10 px-2 py-[2px] text-[10px] font-bold text-gold">
                  <Star size={9} fill="currentColor" /> {stats.rating.toFixed(1)} · {stats.rating_count}
                </span>
              ) : (
                <span className="rounded-full border border-line bg-white/5 px-2 py-[2px] text-[10px] font-semibold text-muted">
                  новый коллекционер
                </span>
              )}
              <span className="text-[10px] text-muted-2">с {formatDate(user.created_at)}</span>
            </div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-4 gap-2">
          {[
            { label: "подарков", value: stats.gifts_owned },
            { label: "лотов", value: stats.listings_active },
            { label: "продаж", value: stats.sales_count },
            { label: "покупок", value: stats.purchases_count },
          ].map((item) => (
            <div key={item.label} className="rounded-xl border border-line bg-black/25 px-1 py-2 text-center">
              <p className="text-[15px] font-extrabold tabular leading-none">{item.value}</p>
              <p className="mt-0.5 text-[9px] font-semibold uppercase tracking-wide text-muted-2">{item.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Balance ------------------------------------------------------ */}
      <div className="rounded-[22px] border border-line bg-white/[0.03] p-3.5">
        <div className="flex items-start justify-between">
          <div>
            <p className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-2">
              <Wallet size={12} /> Баланс продавца
            </p>
            <p className="mt-1 flex items-center gap-1.5 text-[26px] font-extrabold leading-none tabular">
              <StarIcon size={20} /> {formatNumber(balance.available_stars + balance.pending_stars)}
            </p>
          </div>
          <button onClick={() => { haptic("soft"); setPayoutOpen(true); }} className="btn btn-soft btn-sm">
            <Banknote size={14} /> Выплата
          </button>
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2">
          <div className="rounded-xl bg-black/25 px-2.5 py-2">
            <p className="text-[9px] font-bold uppercase tracking-wide text-muted-2">Ожидают</p>
            <p className="mt-0.5 text-[12.5px] font-extrabold tabular">{formatNumber(balance.pending_stars)} ★</p>
          </div>
          <div className="rounded-xl bg-black/25 px-2.5 py-2">
            <p className="text-[9px] font-bold uppercase tracking-wide text-muted-2">Доступно</p>
            <p className="mt-0.5 text-[12.5px] font-extrabold tabular text-mint">
              {formatNumber(balance.available_stars)} ★
            </p>
          </div>
          <div className="rounded-xl bg-black/25 px-2.5 py-2">
            <p className="text-[9px] font-bold uppercase tracking-wide text-muted-2">Выплачено</p>
            <p className="mt-0.5 text-[12.5px] font-extrabold tabular">{formatNumber(balance.withdrawn_stars)} ★</p>
          </div>
        </div>
        <p className="mt-2 text-[10.5px] leading-relaxed text-muted-2">
          Внутренний баланс — не кошелёк. Выплаты выполняются вручную после проверки; удержание{" "}
          {balance.hold_hours} ч с момента продажи.
        </p>
      </div>

      {/* Revenue stats ------------------------------------------------ */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-2xl border border-line bg-white/[0.03] p-3">
          <p className="flex items-center gap-1 text-[9.5px] font-bold uppercase tracking-[0.1em] text-muted-2">
            <ArrowUpRight size={11} className="text-mint" /> Продано
          </p>
          <p className="mt-1 text-[16px] font-extrabold tabular">{formatNumber(stats.gross_sales_stars)} ★</p>
          <p className="text-[10px] text-muted-2">оборот по вашим лотам</p>
        </div>
        <div className="rounded-2xl border border-line bg-white/[0.03] p-3">
          <p className="flex items-center gap-1 text-[9.5px] font-bold uppercase tracking-[0.1em] text-muted-2">
            <ArrowDownLeft size={11} className="text-violet-soft" /> Куплено
          </p>
          <p className="mt-1 text-[16px] font-extrabold tabular">{formatNumber(stats.gross_purchases_stars)} ★</p>
          <p className="text-[10px] text-muted-2">всего потрачено на подарки</p>
        </div>
      </div>

      {/* Quick actions ------------------------------------------------ */}
      <div className="space-y-2">
        <MenuRow icon={<Receipt size={16} />} label="История сделок" hint="покупки и продажи" onClick={() => navigate("/orders")} />
        <MenuRow
          icon={<Handshake size={16} />}
          label="Предложения"
          hint={incomingOffers?.length ? `${incomingOffers.length} входящих` : "нет входящих"}
          onClick={() => setOffersOpen(true)}
        />
        <MenuRow icon={<Wallet size={16} />} label="Финансовый журнал" hint="начисления и комиссии" onClick={() => setHistoryOpen(true)} />
        <MenuRow
          icon={<Gavel size={16} />}
          label="Мои заявки на выплату"
          hint={payouts?.length ? `${payouts.length} заявок` : "нет заявок"}
          onClick={() => setPayoutOpen(true)}
        />
        {me.is_admin && (
          <MenuRow
            icon={<ShieldCheck size={16} />}
            label="Админ-панель"
            hint={me.admin_role ?? "admin"}
            onClick={() => navigate("/admin")}
            accent
          />
        )}
      </div>

      {/* Privacy settings -------------------------------------------- */}
      <div className="rounded-[22px] border border-line bg-white/[0.03] p-3.5">
        <p className="mb-2 flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-2">
          <Settings2 size={12} /> Приватность и уведомления
        </p>
        <div className="space-y-1">
          <ToggleRow label="Показывать коллекцию" hint="другие видят ваши подарки" value={settings.show_collection} onChange={() => toggle("show_collection")} />
          <ToggleRow label="Принимать предложения" hint="покупка по вашей цене" value={settings.allow_offers} onChange={() => toggle("allow_offers")} />
          <ToggleRow label="Уведомления о продажах" hint="Telegram и в приложении" value={settings.notify_sales} onChange={() => toggle("notify_sales")} />
          <ToggleRow label="Маркетинговые сообщения" hint="новости и подборки" value={settings.notify_market} onChange={() => toggle("notify_market")} />
        </div>
      </div>

      {/* TON wallet --------------------------------------------------- */}
      <TonWalletCard address={me.ton_address} enabled={Boolean(meta?.ton_enabled)} onSaved={() => client.invalidateQueries({ queryKey: ["me"] })} />

      {/* Demo switcher ------------------------------------------------ */}
      {meta?.dev_mode && !isTelegram && <DemoIdentityCard />}

      {/* Footer info -------------------------------------------------- */}
      <div className="space-y-2 pb-2">
        <Link to="/about" className="flex items-center justify-between rounded-2xl border border-line bg-white/[0.02] px-3.5 py-3">
          <span className="flex items-center gap-2 text-[12.5px] font-semibold">
            <CircleHelp size={15} className="text-muted" /> Правила, выплаты и ограничения
          </span>
          <ChevronRight size={15} className="text-muted-2" />
        </Link>
        <div className="flex items-center justify-between rounded-2xl border border-line bg-white/[0.02] px-3.5 py-3">
          <span className="flex items-center gap-2 text-[12.5px] font-semibold">
            <Bell size={15} className="text-muted" /> Версия приложения
          </span>
          <span className="text-[11px] font-bold text-muted-2">1.0.0</span>
        </div>
        <p className="px-1 text-center text-[10px] leading-relaxed text-muted-2">
          GIFT MARKET · цифровые коллекционные подарки. Внутренние предметы платформы не являются официальными
          Telegram Collectible Gifts и не выпущены в блокчейне.
        </p>
      </div>

      {/* Sheets ------------------------------------------------------- */}
      <Sheet open={historyOpen} onClose={() => setHistoryOpen(false)} title="Финансовый журнал">
        <div className="space-y-2 pb-2">
          {!transactions?.items.length ? (
            <EmptyState title="Операций пока нет" description="Здесь появятся начисления за продажи, комиссии и выплаты." />
          ) : (
            transactions.items.map((transaction) => (
              <div key={transaction.id} className="flex items-center justify-between rounded-xl border border-line bg-white/[0.02] px-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-[11.5px] font-semibold">{transaction.description || transaction.type}</p>
                  <p className="text-[10px] text-muted-2">
                    {relativeTime(transaction.created_at)} · {transaction.bucket}
                  </p>
                </div>
                <span
                  className={`shrink-0 text-[12.5px] font-extrabold tabular ${
                    transaction.amount_stars > 0 ? "text-mint" : "text-rose"
                  }`}
                >
                  {transaction.amount_stars > 0 ? "+" : ""}
                  {transaction.amount_stars} ★
                </span>
              </div>
            ))
          )}
          <p className="pt-1 text-[10.5px] leading-relaxed text-muted-2">
            Журнал неизменяем: каждая операция имеет уникальный идентификатор и связана с заказом или выплатой.
          </p>
        </div>
      </Sheet>

      <PayoutSheet open={payoutOpen} onClose={() => setPayoutOpen(false)} onDone={() => client.invalidateQueries({ queryKey: ["me"] })} />

      <Sheet open={offersOpen} onClose={() => setOffersOpen(false)} title="Входящие предложения">
        <OffersList offers={incomingOffers ?? []} onAction={() => client.invalidateQueries({ queryKey: ["offers"] })} />
      </Sheet>
    </div>
  );
}

function MenuRow({
  icon,
  label,
  hint,
  onClick,
  accent,
}: {
  icon: React.ReactNode;
  label: string;
  hint?: string;
  onClick: () => void;
  accent?: boolean;
}) {
  return (
    <button
      onClick={() => {
        haptic("soft");
        onClick();
      }}
      className={`flex w-full items-center gap-3 rounded-2xl border px-3.5 py-3 text-left active:scale-[0.995] ${
        accent ? "border-violet/35 bg-violet/[0.1]" : "border-line bg-white/[0.02]"
      }`}
    >
      <span className={`grid h-8 w-8 place-items-center rounded-xl ${accent ? "bg-violet/25 text-violet-soft" : "bg-white/[0.06] text-muted"}`}>
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-bold">{label}</span>
        {hint && <span className="block truncate text-[10.5px] text-muted-2">{hint}</span>}
      </span>
      <ChevronRight size={15} className="shrink-0 text-muted-2" />
    </button>
  );
}

function ToggleRow({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: boolean;
  onChange: () => void;
}) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <div className="min-w-0 pr-3">
        <p className="text-[12.5px] font-semibold">{label}</p>
        <p className="text-[10px] text-muted-2">{hint}</p>
      </div>
      <button
        role="switch"
        aria-checked={value}
        aria-label={label}
        onClick={onChange}
        className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${
          value ? "bg-violet" : "bg-white/12"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
            value ? "translate-x-[18px]" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}

function PayoutSheet({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { data: me } = useMe();
  const { data: config } = useConfig();
  const { data: payouts } = usePayouts();
  const toast = useToast();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("stars_manual");
  const [destination, setDestination] = useState("");
  const [loading, setLoading] = useState(false);
  const client = useQueryClient();

  const available = me?.balance.available_stars ?? 0;
  // The server validates the same limit; the value is only used for the hint.
  const minimum = config?.min_payout_stars ?? 100;

  const submit = async () => {
    setLoading(true);
    try {
      await api.requestPayout({ amount_stars: Number(amount), method, destination });
      toast.success("Заявка создана. Выплата выполняется вручную.");
      hapticNotification("success");
      setAmount("");
      onDone();
      client.invalidateQueries({ queryKey: ["payouts"] });
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="Выплата продавцу">
      <div className="space-y-3 pb-2">
        <div className="rounded-2xl border border-gold/25 bg-gold/[0.07] p-3 text-[11.5px] leading-relaxed text-gold/90">
          <p className="mb-1 flex items-center gap-1.5 font-bold uppercase tracking-wide">
            <Info size={12} /> Важно
          </p>
          {me?.balance.payout_note ||
            "Внутренний баланс не является банковским или криптовалютным кошельком. Заявка не означает автоматический вывод Stars: выплата согласуется и выполняется вручную."}
        </div>

        <div className="flex items-center justify-between rounded-2xl border border-line bg-white/[0.02] px-3 py-2.5">
          <span className="text-[12px] text-muted">Доступно к выплате</span>
          <span className="text-[14px] font-extrabold text-mint">{formatNumber(available)} ★</span>
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">Сумма</label>
          <input
            className="field"
            inputMode="numeric"
            placeholder={`минимум ${minimum}`}
            value={amount}
            onChange={(event) => setAmount(event.target.value.replace(/\D/g, "").slice(0, 7))}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">Способ</label>
          <div className="flex flex-wrap gap-2">
            {[
              { value: "stars_manual", label: "Stars (вручную)" },
              { value: "bank_manual", label: "Банк (вручную)" },
              { value: "ton_manual", label: "TON (вручную)" },
            ].map((option) => (
              <button
                key={option.value}
                className={`chip ${method === option.value ? "chip-active" : ""}`}
                onClick={() => {
                  selectionHaptic();
                  setMethod(option.value);
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">
            Реквизиты / контакт
          </label>
          <input
            className="field"
            placeholder="@username, счёт или адрес TON"
            value={destination}
            onChange={(event) => setDestination(event.target.value.slice(0, 160))}
          />
        </div>

        <button className="btn btn-primary w-full" onClick={submit} disabled={loading || !amount || Number(amount) < minimum}>
          {loading ? <Spinner size={16} /> : <Banknote size={15} />} Создать заявку
        </button>

        {Boolean(payouts?.length) && (
          <div className="space-y-1.5 pt-1">
            <p className="text-[11px] font-bold uppercase tracking-[0.1em] text-muted-2">История заявок</p>
            {payouts!.map((payout) => (
              <div key={payout.id} className="flex items-center justify-between rounded-xl border border-line bg-white/[0.02] px-3 py-2">
                <div>
                  <p className="text-[12px] font-bold">{payout.amount_stars} ★</p>
                  <p className="text-[10px] text-muted-2">{formatDate(payout.created_at, true)}</p>
                </div>
                <span
                  className="status-pill"
                  style={{
                    color:
                      payout.status === "paid"
                        ? "#34d399"
                        : payout.status === "rejected"
                          ? "#f43f5e"
                          : payout.status === "approved"
                            ? "#38bdf8"
                            : "#fbbf24",
                    background: "rgba(255,255,255,0.06)",
                  }}
                >
                  {payout.status === "requested"
                    ? "заявка"
                    : payout.status === "approved"
                      ? "подтверждена"
                      : payout.status === "paid"
                        ? "выплачено"
                        : "отклонена"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Sheet>
  );
}

function OffersList({ offers, onAction }: { offers: Offer[]; onAction: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState<number | null>(null);

  const act = async (offer: Offer, accept: boolean) => {
    setBusy(offer.id);
    try {
      if (accept) {
        const result = await api.acceptOffer(offer.id);
        toast.success(`Предложение принято: создан лот за ${offer.price_stars} ★`);
        hapticNotification("success");
        window.location.href = `/listing/${result.listing_id}`;
      } else {
        await api.declineOffer(offer.id);
        toast.info("Предложение отклонено");
      }
      onAction();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  if (!offers.length) {
    return (
      <EmptyState
        title="Входящих предложений нет"
        description="Покупатели могут предложить цену за предмет из вашей коллекции, если вы разрешили предложения."
        icon={<Handshake size={22} />}
      />
    );
  }

  return (
    <div className="space-y-2 pb-2">
      {offers.map((offer) => (
        <div key={offer.id} className="rounded-2xl border border-line bg-white/[0.02] p-2.5">
          <div className="flex items-center gap-2.5">
            <img src={offer.image_url} alt={offer.item_name} className="h-12 w-12 rounded-xl object-cover" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12.5px] font-bold">{offer.item_name}</p>
              <p className="text-[10.5px] text-muted-2">
                {offer.buyer.display_name} · {relativeTime(offer.created_at)}
              </p>
            </div>
            <Price value={offer.price_stars} size="sm" />
          </div>
          {offer.message && <p className="mt-1.5 rounded-lg bg-white/[0.03] px-2 py-1.5 text-[11px] text-muted">«{offer.message}»</p>}
          {offer.status === "pending" ? (
            <div className="mt-2 flex gap-2">
              <button className="btn btn-ghost btn-sm flex-1" onClick={() => act(offer, false)} disabled={busy === offer.id}>
                Отклонить
              </button>
              <button className="btn btn-primary btn-sm flex-1" onClick={() => act(offer, true)} disabled={busy === offer.id}>
                {busy === offer.id ? <Spinner size={13} /> : null} Принять
              </button>
            </div>
          ) : (
            <p className="mt-1.5 text-[10.5px] font-bold uppercase tracking-wide text-muted-2">
              {offer.status === "accepted" ? "принято" : "отклонено"}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

function TonWalletCard({ address, enabled, onSaved }: { address: string; enabled: boolean; onSaved: () => void }) {
  const [value, setValue] = useState(address);
  const [saving, setSaving] = useState(false);
  const toast = useToast();

  const save = async () => {
    setSaving(true);
    try {
      await api.bindTon(value.trim());
      toast.success(value.trim() ? "Адрес TON сохранён" : "Адрес удалён");
      onSaved();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-[22px] border border-line bg-white/[0.03] p-3.5">
      <p className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-2">
        <Sparkles size={12} /> TON-кошелёк
      </p>
      <p className="mb-2 text-[10.5px] leading-relaxed text-muted-2">
        Публичный адрес для будущих выплат и проверки внешних NFT. Приватные ключи и seed-фразы приложение не
        запрашивает и не хранит.
      </p>
      <div className="flex gap-2">
        <input
          className="field"
          placeholder="EQ… / UQ…"
          value={value}
          onChange={(event) => setValue(event.target.value.slice(0, 80))}
        />
        <button className="btn btn-ghost btn-sm shrink-0 px-3" onClick={save} disabled={saving}>
          {saving ? <Spinner size={14} /> : "Сохранить"}
        </button>
      </div>
      {!enabled && (
        <p className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-2">
          <Info size={10} /> Проверка адреса недоступна: TON API не настроен администратором.
        </p>
      )}
    </div>
  );
}

function DemoIdentityCard() {
  const { data: me } = useMe();
  const [value, setValue] = useState("");
  const toast = useToast();
  const client = useQueryClient();

  const switchUser = () => {
    const id = value.replace(/\D/g, "");
    setDevTelegramId(id || null);
    toast.success(id ? `Тестовый пользователь ${id}` : "Вернулись к демо-пользователю");
    client.invalidateQueries();
    window.setTimeout(() => window.location.reload(), 350);
  };

  return (
    <div className="rounded-[22px] border border-gold/25 bg-gold/[0.06] p-3.5">
      <p className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-gold">
        <Lock size={12} /> Локальный тестовый доступ
      </p>
      <p className="mt-1 text-[10.5px] leading-relaxed text-gold/80">
        Backend запущен с DEV_AUTH=true вне Telegram. Можно переключиться на другого тестового Telegram ID, чтобы
        проверить покупку и продажу с двух аккаунтов. В продакшене этот режим запрещён.
      </p>
      <div className="mt-2 flex gap-2">
        <input
          className="field h-11"
          placeholder="Telegram ID, напр. 900000002"
          value={value}
          onChange={(event) => setValue(event.target.value.slice(0, 16))}
        />
        <button className="btn btn-ghost btn-sm shrink-0 px-3" onClick={switchUser}>
          Сменить
        </button>
      </div>
      <p className="mt-1.5 text-[10px] text-gold/70">Текущий аккаунт: {me?.user.telegram_id}</p>
      <button
        onClick={() => openTelegramLink("https://t.me/")}
        className="mt-2 flex items-center gap-1 text-[10px] font-semibold text-gold/70"
      >
        <LogOut size={10} /> В Telegram доступ закрыт без initData
      </button>
    </div>
  );
}

