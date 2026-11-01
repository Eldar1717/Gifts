/**
 * GIFT MARKET API client.
 *
 * - Authenticates with Telegram `initData` (`Authorization: tma <initData>`).
 * - Never sends prices: the server derives every amount from its own data.
 * - Normalises errors into `ApiError` with a human readable Russian message.
 */

import { initData } from "./telegram";
import type {
  AdminAuditRow,
  AdminItemRow,
  AdminOrderRow,
  AdminOverview,
  AdminPayoutRow,
  AdminReportRow,
  AdminSettings,
  AdminUserRow,
  Balance,
  Category,
  CollectionPublic,
  HomeResponse,
  InvoiceResponse,
  ItemCard,
  ItemDetail,
  Listing,
  MarketCard,
  MarketplaceConfig,
  Me,
  Meta,
  NotificationItem,
  Offer,
  Order,
  OrderDetail,
  OwnershipCard,
  OwnershipDetail,
  Page,
  Payout,
  Review,
  SellerProfile,
  Transaction,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "/api";

export class ApiError extends Error {
  status: number;
  detail: string;
  authRequired: boolean;

  constructor(status: number, detail: string, authRequired = false) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.authRequired = authRequired;
  }
}

function devTelegramId(): string | null {
  try {
    return localStorage.getItem("gm_dev_telegram_id");
  } catch {
    return null;
  }
}

export function setDevTelegramId(id: string | null): void {
  try {
    if (id) localStorage.setItem("gm_dev_telegram_id", id);
    else localStorage.removeItem("gm_dev_telegram_id");
  } catch {
    /* ignore */
  }
}

function headers(extra?: HeadersInit): Headers {
  const result = new Headers(extra);
  result.set("Accept", "application/json");
  if (initData) result.set("Authorization", `tma ${initData}`);
  const devId = devTelegramId();
  if (devId) result.set("X-Dev-Telegram-Id", devId);
  return result;
}

type QueryValue = string | number | boolean | null | undefined | Array<string | number>;

function withQuery(path: string, params?: Record<string, QueryValue>): string {
  if (!params) return path;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      value.forEach((entry) => search.append(key, String(entry)));
    } else {
      search.append(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; params?: Record<string, QueryValue>; signal?: AbortSignal } = {},
): Promise<T> {
  const url = `${API_BASE}${withQuery(path, options.params)}`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "GET",
      headers: headers(options.body ? { "Content-Type": "application/json" } : undefined),
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
      credentials: "omit",
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "Нет соединения с сервером. Проверьте интернет и попробуйте снова.");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const data = payload as { detail?: unknown; auth_required?: boolean } | null;
    let message = "Что-то пошло не так. Попробуйте ещё раз.";
    const detail = data?.detail;
    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item) => {
          const entry = item as { loc?: Array<string | number>; msg?: string };
          const field = entry.loc?.slice(1).join(".");
          return field ? `${field}: ${entry.msg}` : entry.msg;
        })
        .filter(Boolean)
        .join("; ");
    }
    if (response.status === 429) {
      message = "Слишком много запросов. Подождите немного и повторите.";
    }
    if (response.status >= 500) {
      message = "Сервер временно недоступен. Попробуйте позже.";
    }
    throw new ApiError(response.status, message, Boolean(data?.auth_required));
  }

  return payload as T;
}

export const api = {
  // --- public ------------------------------------------------------------
  meta: () => request<Meta>("/meta"),
  config: () => request<MarketplaceConfig>("/config"),
  home: () => request<HomeResponse>("/home"),
  categories: () => request<Category[]>("/categories"),
  collections: (params?: { rarity?: string; category?: string; featured?: boolean }) =>
    request<CollectionPublic[]>("/collections", { params }),
  collection: (slug: string) =>
    request<{ collection: CollectionPublic; items: ItemCard[] }>(
      `/collections/${encodeURIComponent(slug)}`,
    ),
  market: (params: Record<string, QueryValue>) => request<Page<MarketCard>>("/market", { params }),
  item: (id: number) => request<ItemDetail>(`/items/${id}`),
  listing: (id: number) => request<ItemDetail>(`/market/listings/${id}`),
  seller: (id: number) => request<SellerProfile>(`/sellers/${id}`),
  sellerReviews: (id: number) => request<Page<Review>>(`/sellers/${id}/reviews`),
  sellerListings: (id: number) => request<MarketCard[]>(`/sellers/${id}/listings`),
  sellerCollection: (id: number) => request<OwnershipCard[]>(`/sellers/${id}/collection`),

  // --- account -----------------------------------------------------------
  me: () => request<Me>("/me"),
  updateSettings: (body: Partial<Me["settings"]>) =>
    request<Me["settings"]>("/me/settings", { method: "PATCH", body }),
  bindTon: (address: string) => request<Record<string, unknown>>("/me/ton", { method: "POST", body: { address } }),
  balance: () => request<Balance>("/me/balance"),
  transactions: (page = 1) =>
    request<Page<Transaction>>("/me/transactions", { params: { page, page_size: 30 } }),
  collection_owned: () => request<OwnershipCard[]>("/me/collection"),
  ownership: (id: number) => request<OwnershipDetail>(`/me/collection/${id}`),
  myListings: () => request<Listing[]>("/me/listings"),
  favorites: () => request<MarketCard[]>("/favorites"),
  toggleFavorite: (itemId: number) =>
    request<{ item_id: number; favorite: boolean }>(`/favorites/${itemId}`, { method: "POST" }),
  notifications: (unreadOnly = false) =>
    request<Page<NotificationItem>>("/notifications", { params: { unread_only: unreadOnly } }),
  readNotifications: (ids?: number[]) =>
    request<{ updated: number; unread: number }>("/notifications/read", { method: "POST", body: ids ?? null }),
  payouts: () => request<Payout[]>("/me/payouts"),
  requestPayout: (body: { amount_stars: number; method: string; destination: string }) =>
    request<Payout>("/me/payouts", { method: "POST", body }),
  offers: (direction: "incoming" | "outgoing" = "incoming") =>
    request<Offer[]>("/me/offers", { params: { direction } }),

  // --- marketplace -------------------------------------------------------
  createListing: (body: { ownership_id: number; price_stars: number }) =>
    request<{ listing: Listing; commission_percent: number; seller_receives_stars: number }>("/listings", {
      method: "POST",
      body,
    }),
  updateListing: (id: number, price: number) =>
    request<Listing>(`/listings/${id}`, { method: "PATCH", body: { price_stars: price } }),
  cancelListing: (id: number) => request<{ ok: boolean }>(`/listings/${id}`, { method: "DELETE" }),
  invoice: (body: { listing_id?: number; item_id?: number }) =>
    request<InvoiceResponse>("/checkout/invoice", { method: "POST", body }),
  devPay: (orderId: number) =>
    request<{ order_id: number; status: string; refunded: boolean; error: string }>("/checkout/dev-pay", {
      method: "POST",
      body: { order_id: orderId },
    }),
  orders: (role: "buyer" | "seller" = "buyer", page = 1) =>
    request<Page<Order>>("/orders", { params: { role, page, page_size: 20 } }),
  order: (id: number) => request<OrderDetail>(`/orders/${id}`),
  refundOrder: (id: number) => request<{ status: string }>(`/orders/${id}/refund`, { method: "POST" }),
  review: (body: { order_id: number; rating: number; comment: string }) =>
    request<Review>("/reviews", { method: "POST", body }),
  offer: (body: { ownership_id: number; price_stars: number; message?: string }) =>
    request<Offer>("/offers", { method: "POST", body }),
  acceptOffer: (id: number) => request<{ ok: boolean; listing_id: number }>(`/offers/${id}/accept`, { method: "POST" }),
  declineOffer: (id: number) => request<{ ok: boolean }>(`/offers/${id}/decline`, { method: "POST" }),
  report: (body: { target_type: string; target_id: number; reason: string; details?: string }) =>
    request<{ ok: boolean }>("/reports", { method: "POST", body }),

  // --- admin -------------------------------------------------------------
  admin: {
    overview: () => request<AdminOverview>("/admin/overview"),
    users: (params?: { q?: string; blocked?: boolean; page?: number }) =>
      request<Page<AdminUserRow>>("/admin/users", { params }),
    updateUser: (id: number, body: Record<string, unknown>) =>
      request<{ message: string }>(`/admin/users/${id}`, { method: "PATCH", body }),
    adjustBalance: (id: number, body: { user_id: number; amount_stars: number; reason: string }) =>
      request<{ message: string }>(`/admin/users/${id}/balance`, { method: "POST", body }),
    notifyUser: (id: number, title: string, body: string) =>
      request<{ message: string }>(`/admin/users/${id}/notify`, {
        method: "POST",
        params: { title, body },
      }),
    categories: () =>
      request<Array<{ id: number; slug: string; name: string; emoji: string; sort_order: number; is_active: boolean; collections: number }>>(
        "/admin/categories",
      ),
    createCategory: (body: Record<string, unknown>) =>
      request<{ id: number }>("/admin/categories", { method: "POST", body }),
    updateCategory: (id: number, body: Record<string, unknown>) =>
      request<{ ok: boolean }>(`/admin/categories/${id}`, { method: "PATCH", body }),
    collections: () => request<Array<CollectionPublic & { items_total: number }>>("/admin/collections"),
    createCollection: (body: Record<string, unknown>) =>
      request<{ id: number }>("/admin/collections", { method: "POST", body }),
    updateCollection: (id: number, body: Record<string, unknown>) =>
      request<{ ok: boolean }>(`/admin/collections/${id}`, { method: "PATCH", body }),
    verifyTon: (id: number, address: string) =>
      request<{ ok: boolean }>(`/admin/collections/${id}/verify-ton`, {
        method: "POST",
        params: { address },
      }),
    items: (params?: { q?: string; page?: number }) => request<Page<AdminItemRow>>("/admin/items", { params }),
    createItem: (body: Record<string, unknown>) => request<{ id: number }>("/admin/items", { method: "POST", body }),
    updateItem: (id: number, body: Record<string, unknown>) =>
      request<{ ok: boolean }>(`/admin/items/${id}`, { method: "PATCH", body }),
    grant: (body: { user_id: number; item_id: number; quantity: number; reason: string }) =>
      request<{ message: string }>("/admin/gifts/grant", { method: "POST", body }),
    orders: (params?: { status?: string; page?: number }) =>
      request<Page<AdminOrderRow>>("/admin/orders", { params }),
    refundOrder: (id: number, reason: string) =>
      request<{ refund_id: number; status: string }>(`/admin/orders/${id}/refund`, {
        method: "POST",
        params: { reason },
      }),
    listings: (params?: { status?: string; page?: number }) =>
      request<Page<{ id: number; seller: UserShortLike; price_stars: number; status: string }>>("/admin/listings", {
        params,
      }),
    cancelListing: (id: number) =>
      request<{ message: string }>(`/admin/listings/${id}/cancel`, { method: "POST" }),
    transactions: (params?: { type?: string; bucket?: string; page?: number }) =>
      request<Page<Transaction & { user: UserShortLike | null }>>("/admin/transactions", { params }),
    payouts: (params?: { status?: string; page?: number }) =>
      request<Page<AdminPayoutRow>>("/admin/payouts", { params }),
    decidePayout: (id: number, body: { status: string; admin_note: string; external_reference: string }) =>
      request<{ message: string }>(`/admin/payouts/${id}`, { method: "POST", body }),
    reports: (params?: { status?: string; page?: number }) =>
      request<Page<AdminReportRow>>("/admin/reports", { params }),
    resolveReport: (id: number, body: { status: string; resolution: string }) =>
      request<{ message: string }>(`/admin/reports/${id}`, { method: "POST", body }),
    settings: () => request<AdminSettings>("/admin/settings"),
    updateSettings: (body: Record<string, unknown>) =>
      request<AdminSettings>("/admin/settings", { method: "PATCH", body }),
    audit: (params?: { action?: string; page?: number }) =>
      request<Page<AdminAuditRow>>("/admin/audit-logs", { params }),
    telegramStatus: () => request<Record<string, unknown>>("/admin/telegram/status"),
    setupWebhook: () => request<{ ok: boolean; url: string }>("/admin/telegram/setup-webhook", { method: "POST" }),
  },
};

type UserShortLike = { id: number; display_name: string; username: string; photo_url: string; rating: number | null };

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return "Неизвестная ошибка";
}
