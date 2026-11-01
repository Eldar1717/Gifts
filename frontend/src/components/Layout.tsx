import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Bell, Compass, Heart, Home, Sparkles, User, Wallet } from "lucide-react";
import { useConfig, useMe, useMeta } from "../hooks/useApi";
import { Avatar, StarIcon } from "./ui";
import { formatCompact } from "../lib/format";
import { haptic, isTelegram } from "../lib/telegram";

const NAV = [
  { to: "/", label: "Главная", icon: Home, end: true },
  { to: "/market", label: "Маркет", icon: Compass },
  { to: "/collection", label: "Коллекция", icon: Wallet },
  { to: "/favorites", label: "Избранное", icon: Heart },
  { to: "/profile", label: "Профиль", icon: User },
];

export function Layout() {
  const { data: me } = useMe();
  const { data: meta } = useMeta();
  const { data: config } = useConfig();
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [location.pathname]);

  const showDemoBanner = Boolean(meta?.dev_mode) && !isTelegram;
  const maintenance = config?.maintenance_mode;

  return (
    <div className="min-h-dvh">
      <header
        className={`sticky top-0 z-30 transition-all duration-300 ${
          scrolled ? "border-b border-line bg-bg/85 backdrop-blur-xl" : "bg-transparent"
        }`}
        style={{ paddingTop: "calc(var(--safe-top) + 6px)" }}
      >
        <div className="container-app flex items-center gap-3 pb-2.5 pt-1.5">
          <Link to="/" className="flex min-w-0 items-center gap-2.5" onClick={() => haptic("soft")}>
            <span className="grid h-9 w-9 place-items-center rounded-[13px] bg-gradient-to-br from-violet to-magenta shadow-[0_10px_24px_-12px_rgba(124,92,255,0.95)]">
              <Sparkles size={17} className="text-white" />
            </span>
            <span className="min-w-0">
              <span className="block truncate font-display text-[13.5px] font-extrabold uppercase leading-none tracking-[0.14em] text-ink">
                Gift Market
              </span>
              <span className="mt-0.5 block truncate text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-2">
                digital collectibles
              </span>
            </span>
          </Link>

          <div className="ml-auto flex items-center gap-2">
            {me && (
              <Link
                to="/profile"
                onClick={() => haptic("soft")}
                className="flex h-9 items-center gap-1.5 rounded-full border border-line bg-white/[0.04] pl-2.5 pr-3"
              >
                <StarIcon size={14} />
                <span className="text-[12.5px] font-extrabold tabular">
                  {formatCompact(me.balance.available_stars + me.balance.pending_stars)}
                </span>
              </Link>
            )}
            <Link
              to="/notifications"
              onClick={() => haptic("soft")}
              className="relative grid h-9 w-9 place-items-center rounded-full border border-line bg-white/[0.04] text-muted"
              aria-label="Уведомления"
            >
              <Bell size={16} />
              {Boolean(me?.unread_notifications) && (
                <span className="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-rose px-1 text-[9px] font-extrabold text-white">
                  {me!.unread_notifications > 9 ? "9+" : me!.unread_notifications}
                </span>
              )}
            </Link>
            <Link to="/profile" onClick={() => haptic("soft")} aria-label="Профиль">
              <Avatar name={me?.user.display_name ?? "Гость"} src={me?.user.photo_url} size={34} ring />
            </Link>
          </div>
        </div>

        {showDemoBanner && (
          <div className="container-app pb-2">
            <button
              onClick={() => navigate("/about")}
              className="flex w-full items-center gap-2 rounded-xl border border-gold/25 bg-gold/[0.08] px-3 py-1.5 text-left text-[10.5px] font-semibold leading-snug text-gold/90"
            >
              <span className="rounded bg-gold/20 px-1.5 py-0.5 text-[9px] font-extrabold uppercase">demo</span>
              Telegram не обнаружен — открыт локальный демо-режим. Платежи симулируются на backend.
            </button>
          </div>
        )}

        {maintenance && (
          <div className="container-app pb-2">
            <div className="rounded-xl border border-danger/30 bg-danger/10 px-3 py-1.5 text-[10.5px] font-semibold text-rose">
              {config?.maintenance_message || "Маркетплейс на техническом обслуживании"}
            </div>
          </div>
        )}
      </header>

      <main className="container-app page-bottom-space pt-1">
        <Outlet />
      </main>

      <nav className="nav-shell">
        <div className="nav-inner">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => haptic("soft")}
                className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
              >
                <Icon size={19} strokeWidth={2.1} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
