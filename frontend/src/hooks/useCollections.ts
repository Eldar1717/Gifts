import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export function useCollections(params?: { rarity?: string; category?: string; featured?: boolean }) {
  return useQuery({
    queryKey: ["collections", params ?? {}],
    queryFn: () => api.collections(params),
    staleTime: 60_000,
  });
}

export function useCollectionDetail(slug: string | undefined) {
  return useQuery({
    queryKey: ["collection-detail", slug],
    queryFn: () => api.collection(slug as string),
    enabled: Boolean(slug),
    staleTime: 30_000,
  });
}

export function useSeller(id: number | undefined) {
  return useQuery({
    queryKey: ["seller", id],
    queryFn: () => api.seller(id as number),
    enabled: Boolean(id),
    staleTime: 30_000,
  });
}

export function useSellerReviews(id: number | undefined) {
  return useQuery({
    queryKey: ["seller-reviews", id],
    queryFn: () => api.sellerReviews(id as number),
    enabled: Boolean(id),
  });
}

export function useBindTon() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (address: string) => api.bindTon(address),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["me"] });
    },
  });
}
