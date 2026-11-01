/**
 * Typed wrapper around the Telegram Mini App SDK.
 *
 * The app must also work in a normal browser (local development, preview),
 * so every call is defensive and no-ops when the SDK is unavailable.
 */

export type HapticStyle = "light" | "medium" | "heavy" | "rigid" | "soft";
export type HapticNotification = "error" | "success" | "warning";

interface TelegramWebAppUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_url?: string;
}

interface TelegramMainButton {
  text: string;
  isVisible: boolean;
  show(): void;
  hide(): void;
  setText(text: string): void;
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
  enable(): void;
  disable(): void;
}

interface TelegramBackButton {
  isVisible: boolean;
  show(): void;
  hide(): void;
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
}

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: { user?: TelegramWebAppUser; start_param?: string };
  version: string;
  platform: string;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  isExpanded: boolean;
  viewportHeight: number;
  ready(): void;
  expand(): void;
  close(): void;
  isVersionAtLeast(version: string): boolean;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  enableClosingConfirmation?(): void;
  openTelegramLink?(url: string): void;
  openLink?(url: string): void;
  showAlert?(message: string, cb?: () => void): void;
  showConfirm?(message: string, cb?: (confirmed: boolean) => void): void;
  HapticFeedback?: {
    impactOccurred(style: HapticStyle): void;
    notificationOccurred(type: HapticNotification): void;
    selectionChanged(): void;
  };
  MainButton: TelegramMainButton;
  BackButton: TelegramBackButton;
  openInvoice?(url: string, callback?: (status: "paid" | "cancelled" | "failed" | "pending") => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export const webApp: TelegramWebApp | undefined = window.Telegram?.WebApp;

export const isTelegram = Boolean(webApp && webApp.initData.length > 0);
export const initData = webApp?.initData ?? "";
export const telegramUser = webApp?.initDataUnsafe?.user;
export const startParam = webApp?.initDataUnsafe?.start_param ?? "";

let initialized = false;

export function initTelegram(): void {
  if (initialized || !webApp) return;
  initialized = true;
  try {
    webApp.ready();
    webApp.expand();
    webApp.setHeaderColor?.("#07070d");
    webApp.setBackgroundColor?.("#07070d");
  } catch {
    /* older clients: ignore */
  }
}

export function haptic(style: HapticStyle = "light"): void {
  try {
    webApp?.HapticFeedback?.impactOccurred(style);
  } catch {
    /* no-op */
  }
}

export function hapticNotification(type: HapticNotification): void {
  try {
    webApp?.HapticFeedback?.notificationOccurred(type);
  } catch {
    /* no-op */
  }
}

export function selectionHaptic(): void {
  try {
    webApp?.HapticFeedback?.selectionChanged();
  } catch {
    /* no-op */
  }
}

export function openTelegramLink(url: string): void {
  if (!url) return;
  try {
    if (webApp?.openTelegramLink) {
      webApp.openTelegramLink(url);
      return;
    }
    if (webApp?.openLink) {
      webApp.openLink(url);
      return;
    }
  } catch {
    /* fall through */
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export function openExternal(url: string): void {
  if (!url) return;
  try {
    if (webApp?.openLink) {
      webApp.openLink(url);
      return;
    }
  } catch {
    /* fall through */
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

export type InvoiceStatus = "paid" | "cancelled" | "failed" | "pending";

/**
 * Opens a Telegram Stars invoice.
 *
 * Returns `null` when the invoice API is unavailable (browser/dev mode) so the
 * caller can fall back to the development payment simulator — never to a fake
 * "success" state.
 */
export function openInvoice(url: string): Promise<InvoiceStatus | null> {
  return new Promise((resolve) => {
    if (!url) {
      resolve(null);
      return;
    }
    if (!webApp?.openInvoice) {
      resolve(null);
      return;
    }
    try {
      webApp.openInvoice(url, (status) => resolve(status));
    } catch {
      resolve(null);
    }
  });
}

export function showConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (webApp?.showConfirm) {
      webApp.showConfirm(message, (confirmed) => resolve(Boolean(confirmed)));
      return;
    }
    resolve(window.confirm(message));
  });
}

export function showAlert(message: string): void {
  if (webApp?.showAlert) {
    webApp.showAlert(message);
    return;
  }
  window.alert(message);
}
