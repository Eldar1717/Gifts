import { Link } from "react-router-dom";
import { Heart, Sparkles } from "lucide-react";
import { useFavorites } from "../hooks/useApi";
import { CardSkeleton, EmptyState, ErrorState } from "../components/ui";
import { MarketGiftCard } from "../components/GiftCard";
import { errorMessage } from "../lib/api";

export default function FavoritesPage() {
  const { data, isLoading, isError, error, refetch } = useFavorites();

  return (
    <div className="space-y-4 pt-1">
      <div>
        <h1 className="text-[22px] font-extrabold tracking-[-0.02em]">Избранное</h1>
        <p className="mt-0.5 text-[12px] text-muted">
          {data?.length ? `${data.length} подарков в списке` : "Отмечайте подарки, чтобы следить за ценой"}
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <CardSkeleton key={index} />
          ))}
        </div>
      ) : isError ? (
        <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="Избранное пусто"
          description="Нажмите на сердечко в карточке подарка — он появится здесь, и вы сможете вернуться к нему позже."
          icon={<Heart size={22} />}
          action={
            <Link to="/market" className="btn btn-primary btn-sm">
              <Sparkles size={14} /> Открыть маркет
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {data.map((card, index) => (
            <MarketGiftCard key={card.key} card={card} index={index} />
          ))}
        </div>
      )}
    </div>
  );
}
