import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Me } from "../lib/types";

const STALE = 30_000;

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: 10 * 60_000, retry: 1 });
}

export function useConfig() {
  return useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: 60_000 });
}

export function useHome() {
  return useQuery({ queryKey: ["home"], queryFn: api.home, staleTime: STALE });
}

export function useMe(options: { enabled?: boolean } = {}) {
  return useQuery<Me>({
    queryKey: ["me"],
    queryFn: api.me,
    staleTime: 15_000,
    retry: 1,
    enabled: options.enabled ?? true,
  });
}

export function useMarket(params: Record<string, string | number | boolean | string[] | undefined>) {
  return useQuery({
    queryKey: ["market", params],
    queryFn: () => api.market(params),
    staleTime: STALE,
    placeholderData: (previous) => previous,
  });
}

export function useItem(id: number | null) {
  return useQuery({
    queryKey: ["item", id],
    queryFn: () => api.item(id as number),
    enabled: id !== null,
    staleTime: 10_000,
  });
}

export function useListingDetail(id: number | null) {
  return useQuery({
    queryKey: ["listing-detail", id],
    queryFn: () => api.listing(id as number),
    enabled: id !== null,
    staleTime: 10_000,
  });
}

export function useOwnedCollection() {
  return useQuery({ queryKey: ["owned"], queryFn: api.collection_owned, staleTime: 10_000 });
}

export function useFavorites() {
  return useQuery({ queryKey: ["favorites"], queryFn: api.favorites, staleTime: 10_000 });
}

export function useNotifications() {
  return useQuery({ queryKey: ["notifications"], queryFn: () => api.notifications(), staleTime: 10_000 });
}

export function useOrders(role: "buyer" | "seller" = "buyer") {
  return useQuery({
    queryKey: ["orders", role],
    queryFn: () => api.orders(role),
    staleTime: 10_000,
  });
}

export function useTransactions() {
  return useQuery({ queryKey: ["transactions"], queryFn: () => api.transactions(), staleTime: 10_000 });
}

export function usePayouts() {
  return useQuery({ queryKey: ["payouts"], queryFn: api.payouts, staleTime: 10_000 });
}

export function useOffers(direction: "incoming" | "outgoing" = "incoming") {
  return useQuery({
    queryKey: ["offers", direction],
    queryFn: () => api.offers(direction),
    staleTime: 10_000,
  });
}

/** Invalidate every query touched by a trading action. */
export function useInvalidateMarket() {
  const client = useQueryClient();
  const keys: QueryKey[] = [
    ["home"],
    ["market"],
    ["owned"],
    ["favorites"],
    ["me"],
    ["orders"],
    ["item"],
    ["listing-detail"],
    ["notifications"],
    ["listings"],
    ["config"],
  ];
  return () => keys.forEach((key) => client.invalidateQueries({ queryKey: key }));
}

export function useToggleFavorite() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (itemId: number) => api.toggleFavorite(itemId),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["favorites"] });
      client.invalidateQueries({ queryKey: ["item"] });
    },
  });
}
