import { useEffect, useState } from "react";
import { Bell, BellOff, Check, CheckCheck } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../lib/api";
import { useNotifications } from "../hooks/useApi";
import { EmptyState, ErrorState, RowSkeleton, Spinner } from "../components/ui";
import { relativeTime } from "../lib/format";
import { haptic } from "../lib/telegram";
import { useToast } from "../context/ToastContext";

const TYPE_ICON: Record<string, string> = {
  purchase: "🛍️",
  sale: "💰",
  listing_created: "🏷️",
  listing_cancelled: "🚫",
  payment_status: "💳",
  seller_credit: "✨",
  payout: "🏦",
  offer: "🤝",
  system: "📣",
  admin: "🛡️",
};

export default function NotificationsPage() {
  const { data, isLoading, isError, error, refetch } = useNotifications();
  const client = useQueryClient();
  const toast = useToast();
  const [marking, setMarking] = useState(false);

  useEffect(() => {
    const unread = (data?.items ?? []).filter((item) => !item.is_read).map((item) => item.id);
    if (!unread.length) return;
    const timer = window.setTimeout(async () => {
      try {
        await api.readNotifications(unread);
        client.invalidateQueries({ queryKey: ["me"] });
        client.invalidateQueries({ queryKey: ["notifications"] });
      } catch {
        /* non-critical */
      }
    }, 1400);
    return () => window.clearTimeout(timer);
  }, [data, client]);

  const markAll = async () => {
    setMarking(true);
    try {
      await api.readNotifications();
      toast.success("Все уведомления прочитаны");
      client.invalidateQueries({ queryKey: ["notifications"] });
      client.invalidateQueries({ queryKey: ["me"] });
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setMarking(false);
    }
  };

  const items = data?.items ?? [];
  const unread = items.filter((item) => !item.is_read).length;

  return (
    <div className="space-y-4 pt-1">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-extrabold tracking-[-0.02em]">Уведомления</h1>
          <p className="mt-0.5 text-[12px] text-muted">{unread > 0 ? `${unread} непрочитанных` : "Всё прочитано"}</p>
        </div>
        {items.length > 0 && (
          <button
            className="flex items-center gap-1 text-[11.5px] font-bold text-violet-soft"
            onClick={() => {
              haptic("soft");
              markAll();
            }}
            disabled={marking}
          >
            {marking ? <Spinner size={13} /> : <CheckCheck size={14} />} Прочитать всё
          </button>
        )}
      </div>

      {isLoading ? (
        <RowSkeleton count={5} />
      ) : isError ? (
        <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          title="Пока тихо"
          description="Здесь появятся уведомления о покупках, продажах, выплатах и системных событиях."
          icon={<BellOff size={22} />}
        />
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.id}
              className={`rounded-2xl border p-3 ${
                item.is_read ? "border-line bg-white/[0.02]" : "border-violet/30 bg-violet/[0.07]"
              }`}
            >
              <div className="flex items-start gap-2.5">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-white/[0.06] text-[14px]">
                  {TYPE_ICON[item.type] ?? <Bell size={14} />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-1.5 text-[13px] font-bold">
                    {item.title}
                    {!item.is_read && <span className="h-1.5 w-1.5 rounded-full bg-violet" />}
                  </p>
                  {item.body && <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted">{item.body}</p>}
                  <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-muted-2">
                    {relativeTime(item.created_at)}
                  </p>
                </div>
                {item.is_read && <Check size={13} className="mt-1 shrink-0 text-muted-2" />}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
