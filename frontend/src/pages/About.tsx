import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowLeft, BadgeCheck, Banknote, Info, Scale, ShieldCheck, Sparkles } from "lucide-react";
import { useConfig } from "../hooks/useApi";
import { haptic, openTelegramLink } from "../lib/telegram";

const SUPPORT_URL = (import.meta.env.VITE_SUPPORT_URL as string | undefined) || "https://t.me/";

export default function AboutPage() {
  const { data: config } = useConfig();
  const [open, setOpen] = useState<string | null>("market");

  const sections = [
    {
      id: "market",
      title: "Как работает маркетплейс",
      body: [
        "GIFT MARKET — платформа, на которой коллекционеры покупают цифровые подарки ограниченного тиража, хранят их в личном инвентаре и перепродают другим пользователям.",
        "Первичные выпуски продаёт платформа по фиксированной цене. На вторичном рынке цену устанавливает владелец предмета, а платформа удерживает комиссию с каждой успешной сделки.",
        "Все суммы, комиссии и начисления рассчитываются исключительно на сервере. Приложение никогда не передаёт цену в платёжный запрос — сумма берётся из базы данных.",
      ],
    },
    {
      id: "commission",
      title: "Комиссия и распределение средств",
      body: [
        `Текущая комиссия платформы: ${config?.commission_percent ?? 10}%. Продавец получает ${config?.seller_share_percent ?? 90}% от суммы сделки.`,
        `Пример: при продаже за 500 Telegram Stars платформа удерживает ${Math.floor((500 * (config?.commission_percent ?? 10)) / 100)} Stars, продавцу начисляется ${500 - Math.floor((500 * (config?.commission_percent ?? 10)) / 100)} Stars.`,
        "Комиссия округляется вниз до целой звезды; остаток всегда достаётся продавцу. Комиссия настраивается администратором в панели управления, изменения фиксируются в журнале аудита.",
      ],
    },
    {
      id: "balance",
      title: "Внутренний баланс продавца",
      body: [
        "После продажи доход продавца попадает в раздел «Ожидают» внутреннего баланса и становится «Доступным» после периода удержания (сейчас " +
          `${config?.hold_hours ?? 72} ч), чтобы покрыть возможные возвраты и споры.`,
        "Внутренний баланс — это учётная запись в базе данных, а не банковский счёт, кошелёк Telegram Stars или криптокошелёк. Приложение не выполняет автоматический вывод Stars или TON.",
        "Выплата оформляется заявкой: администратор проверяет её, согласует способ выплаты и фиксирует результат. До момента реального перевода средств заявка не является гарантией выплаты. Порядок выплат, налоги и требования к верификации определяются владельцем платформы в соответствии с применимым законодательством.",
      ],
    },
    {
      id: "nft",
      title: "Подарки, NFT и TON",
      body: [
        "Внутренние подарки GIFT MARKET — это цифровые предметы, которые существуют только в базе данных платформы. Они не выпущены в блокчейне и не являются NFT, если в карточке предмета прямо не указано иное.",
        "Официальные Telegram Collectible Gifts — отдельная категория, которая выпускается Telegram. Платформа не выдаёт внутренние предметы за официальные подарки Telegram и не заявляет о правах на них.",
        "TON-адрес, указанный в карточке коллекции, подтверждает только существование адреса в сети. Он не доказывает, что конкретные предметы отчеканены в блокчейне: для этого требуется подтверждённая транзакция минта.",
      ],
    },
    {
      id: "payments",
      title: "Платежи и возвраты",
      body: [
        "Цифровые товары внутри Telegram Mini App оплачиваются Telegram Stars (валюта XTR).",
        "Покупатель получает подарок только после подтверждённого платежа от Telegram (`successful_payment`). Ответ приложения о «закрытии счёта» не является подтверждением оплаты.",
        "Если после оплаты доставка невозможна (например, предмет уже продан), backend инициирует возврат Stars через Telegram. Если автоматический возврат не проходит, заказ помечается как требующий ручной обработки.",
        "Оплаченный, но не исполненный заказ можно вернуть в истории сделок. Исполненные заказы возвращаются только через поддержку после возврата предмета.",
      ],
    },
    {
      id: "security",
      title: "Безопасность и данные",
      body: [
        "Каждый запрос к API авторизуется подписью Telegram initData; подпись проверяется на сервере с учётом времени жизни сессии.",
        "Покупка выполняется в одной транзакции: проверка платежа, передача права собственности, запись комиссии и начисление продавцу. Повторная обработка платежных уведомлений идемпотентна — повторный webhook не создаёт второе начисление.",
        "Платформа хранит только публичные данные профиля Telegram (имя, username, аватар) и историю операций. Секретные ключи и seed-фразы не запрашиваются.",
      ],
    },
    {
      id: "support",
      title: "Поддержка и правила",
      body: [
        "Спорные ситуации, жалобы на объявления и вопросы по выплатам рассматриваются через поддержку. Жалобы из карточки подарка попадают в панель модерации.",
        "Владелец платформы обязан опубликовать собственные правила использования, политику конфиденциальности, условия возвратов и ограничения по регионам и возрасту, а также соблюдать требования Telegram и местного законодательства.",
      ],
    },
  ];

  return (
    <div className="space-y-4 pt-1">
      <button onClick={() => { haptic("soft"); history.back(); }} className="flex items-center gap-1 text-[12px] font-bold text-muted">
        <ArrowLeft size={14} /> Назад
      </button>

      <div className="relative overflow-hidden rounded-[26px] border border-line bg-gradient-to-br from-violet/18 via-surface to-surface p-4">
        <div className="pointer-events-none absolute -right-10 -top-12 h-36 w-36 rounded-full bg-magenta/20 blur-3xl" />
        <div className="flex items-center gap-2">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-violet to-magenta">
            <Sparkles size={18} className="text-white" />
          </span>
          <div>
            <p className="text-[16px] font-extrabold leading-none">GIFT MARKET</p>
            <p className="mt-1 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-muted-2">
              digital collectibles · v1.0.0
            </p>
          </div>
        </div>
        <p className="mt-3 text-[12px] leading-relaxed text-muted">
          Маркетплейс цифровых коллекционных подарков в Telegram. Ниже — честное описание того, как устроены деньги,
          право собственности и границы возможностей платформы.
        </p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {[
            { icon: <BadgeCheck size={11} />, label: `комиссия ${config?.commission_percent ?? 10}%` },
            { icon: <ShieldCheck size={11} />, label: "проверка initData" },
            { icon: <Banknote size={11} />, label: "выплаты вручную" },
          ].map((chip) => (
            <span
              key={chip.label}
              className="inline-flex items-center gap-1 rounded-full border border-line bg-white/[0.05] px-2 py-1 text-[10px] font-semibold text-muted"
            >
              {chip.icon} {chip.label}
            </span>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-gold/25 bg-gold/[0.07] p-3">
        <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.1em] text-gold">
          <AlertTriangle size={13} /> Важное ограничение
        </p>
        <p className="mt-1 text-[11.5px] leading-relaxed text-gold/85">
          Внутренние предметы платформы не являются официальными Telegram Collectible Gifts и не выпущены в
          блокчейне. Внутренний баланс не является кошельком: автоматический вывод Stars или TON не поддерживается.
        </p>
      </div>

      <div className="space-y-2">
        {sections.map((section) => {
          const isOpen = open === section.id;
          return (
            <div key={section.id} className="overflow-hidden rounded-2xl border border-line bg-white/[0.02]">
              <button
                className="flex w-full items-center justify-between px-3.5 py-3 text-left"
                onClick={() => {
                  haptic("soft");
                  setOpen(isOpen ? null : section.id);
                }}
              >
                <span className="text-[12.5px] font-bold">{section.title}</span>
                <span className={`text-muted-2 transition-transform ${isOpen ? "rotate-180" : ""}`}>▾</span>
              </button>
              {isOpen && (
                <div className="space-y-2 px-3.5 pb-3.5">
                  {section.body.map((paragraph, index) => (
                    <p key={index} className="text-[11.5px] leading-relaxed text-muted">
                      {paragraph}
                    </p>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="space-y-2 pb-2">
        <button
          className="btn btn-ghost w-full"
          onClick={() => openTelegramLink(SUPPORT_URL)}
        >
          <Scale size={15} /> Связаться с поддержкой
        </button>
        <Link to="/market" className="btn btn-primary w-full">
          <Info size={15} /> Перейти в маркет
        </Link>
        <p className="px-2 text-center text-[10px] leading-relaxed text-muted-2">
          Нажимая кнопки, вы соглашаетесь с правилами платформы. Актуальные правила, политика конфиденциальности и
          порядок выплат публикуются владельцем сервиса.
        </p>
      </div>
    </div>
  );
}
