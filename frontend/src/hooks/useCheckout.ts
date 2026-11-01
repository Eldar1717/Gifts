import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../lib/api";
import { openInvoice } from "../lib/telegram";
import type { InvoiceResponse, OrderDetail } from "../lib/types";
import { useInvalidateMarket } from "./useApi";

export type CheckoutPhase =
  | "idle"
  | "creating"
  | "ready"
  | "paying"
  | "confirming"
  | "done"
  | "error";

interface CheckoutState {
  phase: CheckoutPhase;
  invoice: InvoiceResponse | null;
  order: OrderDetail | null;
  error: string;
}

const INITIAL: CheckoutState = { phase: "idle", invoice: null, order: null, error: "" };

/**
 * Checkout pipeline.
 *
 * 1. Ask the backend for an invoice — the amount always comes from the server.
 * 2. Open the Telegram Stars invoice.
 * 3. Poll the order until the webhook has confirmed the payment (the frontend
 *    callback is never trusted: ownership changes only after `successful_payment`).
 */
export function useCheckout() {
  const [state, setState] = useState<CheckoutState>(INITIAL);
  const invalidate = useInvalidateMarket();
  const timer = useRef<number | null>(null);
  const cancelled = useRef(false);

  const clearTimer = () => {
    if (timer.current) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  };

  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
      clearTimer();
    };
  }, []);

  const poll = useCallback(
    async (orderId: number, attempt = 0) => {
      if (cancelled.current) return;
      if (attempt > 22) {
        setState((current) => ({
          ...current,
          phase: "error",
          error: "Платёж ещё обрабатывается. Проверьте статус заказа в профиле через минуту.",
        }));
        invalidate();
        return;
      }
      try {
        const order = await api.order(orderId);
        if (cancelled.current) return;
        if (order.status === "fulfilled") {
          setState((current) => ({ ...current, phase: "done", order }));
          invalidate();
          return;
        }
        if (order.status === "refunded") {
          setState((current) => ({
            ...current,
            phase: "error",
            order,
            error: "Платёж подтверждён, но доставка не удалась. Telegram Stars возвращены автоматически.",
          }));
          invalidate();
          return;
        }
        if (order.status === "refund_pending") {
          setState((current) => ({
            ...current,
            phase: "error",
            order,
            error: "Возврат обрабатывается вручную. Мы свяжемся с вами в Telegram.",
          }));
          return;
        }
        timer.current = window.setTimeout(() => poll(orderId, attempt + 1), attempt < 6 ? 1200 : 2500);
      } catch {
        timer.current = window.setTimeout(() => poll(orderId, attempt + 1), 2500);
      }
    },
    [invalidate],
  );

  const start = useCallback(
    async (target: { listing_id?: number; item_id?: number }) => {
      clearTimer();
      setState({ ...INITIAL, phase: "creating" });
      try {
        const invoice = await api.invoice(target);
        setState({ phase: "ready", invoice, order: null, error: "" });
        return invoice;
      } catch (error) {
        setState({ ...INITIAL, phase: "error", error: errorMessage(error) });
        return null;
      }
    },
    [],
  );

  const pay = useCallback(
    async (options: { allowDevSimulation?: boolean } = {}) => {
      const invoice = state.invoice;
      if (!invoice) return;
      setState((current) => ({ ...current, phase: "paying", error: "" }));

      if (!invoice.invoice_url) {
        if (options.allowDevSimulation) {
          try {
            const result = await api.devPay(invoice.order_id);
            if (result.status === "fulfilled") {
              setState((current) => ({ ...current, phase: "done" }));
              invalidate();
              return;
            }
            setState((current) => ({
              ...current,
              phase: "error",
              error: result.error || "Платёж не удался в демо-режиме.",
            }));
            return;
          } catch (error) {
            setState((current) => ({ ...current, phase: "error", error: errorMessage(error) }));
            return;
          }
        }
        setState((current) => ({
          ...current,
          phase: "error",
          error: "Оплата недоступна: платёжная система Telegram не настроена.",
        }));
        return;
      }

      const status = await openInvoice(invoice.invoice_url);
      if (status === "paid") {
        setState((current) => ({ ...current, phase: "confirming" }));
        poll(invoice.order_id);
        return;
      }
      if (status === "cancelled" || status === "failed") {
        setState((current) => ({
          ...current,
          phase: "error",
          error: status === "failed" ? "Платёж не прошёл. Попробуйте ещё раз." : "Оплата отменена.",
        }));
        return;
      }
      if (status === "pending") {
        setState((current) => ({ ...current, phase: "confirming" }));
        poll(invoice.order_id);
        return;
      }
      setState((current) => ({
        ...current,
        phase: "error",
        error: "Не удалось открыть счёт Telegram. Откройте приложение внутри Telegram.",
      }));
    },
    [state.invoice, poll, invalidate],
  );

  const reset = useCallback(() => {
    clearTimer();
    setState(INITIAL);
  }, []);

  return { ...state, start, pay, reset, setState };
}
