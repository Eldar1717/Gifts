import { type ReactNode } from "react";
import { ExternalLink, Send, ShieldCheck, Sparkles } from "lucide-react";
import { useMeta } from "../hooks/useApi";
import { isTelegram, openTelegramLink } from "../lib/telegram";
import { FullPageLoader } from "./ui";

/**
 * The Mini App must be opened from Telegram (initData is required for every
 * authenticated action). In local development the backend reports `dev_mode`
 * and the gate stays open so the UI can be previewed in a normal browser.
 */
export function TelegramGate({ children }: { children: ReactNode }) {
  const { data: meta, isLoading, isError } = useMeta();

  if (isLoading) return <FullPageLoader />;
  if (isError) return <>{children}</>;
  if (isTelegram || meta?.dev_mode || !meta?.bot_configured) return <>{children}</>;

  const botUrl = meta?.bot_username
    ? `https://t.me/${meta.bot_username}${meta.webapp_url ? "?startapp" : ""}`
    : "";

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 grid h-20 w-20 place-items-center rounded-[26px] bg-gradient-to-br from-violet to-magenta shadow-[0_24px_60px_-20px_rgba(124,92,255,0.95)]">
        <Sparkles size={32} className="text-white" />
      </div>
      <h1 className="font-display text-[20px] font-extrabold">GIFT MARKET</h1>
      <p className="mt-2 max-w-[320px] text-[13px] leading-relaxed text-muted">
        Это Telegram Mini App. Откройте приложение через бота — авторизация и оплата Stars работают только внутри
        Telegram.
      </p>
      <div className="mt-4 flex w-full max-w-[320px] flex-col gap-2">
        {botUrl && (
          <button className="btn btn-primary w-full" onClick={() => openTelegramLink(botUrl)}>
            <Send size={16} /> Открыть бота
          </button>
        )}
        <a
          className="btn btn-ghost w-full"
          href="https://web.telegram.org/"
          target="_blank"
          rel="noreferrer noopener"
        >
          <ExternalLink size={15} /> Telegram Web
        </a>
      </div>
      <p className="mt-4 flex items-center gap-1.5 text-[10.5px] text-muted-2">
        <ShieldCheck size={12} /> Авторизация проверяется подписью Telegram initData
      </p>
    </div>
  );
}
