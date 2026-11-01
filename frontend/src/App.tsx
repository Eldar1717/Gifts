import { Component, Suspense, lazy, type ErrorInfo, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./components/Layout";
import { ToastProvider } from "./context/ToastContext";
import { FullPageLoader } from "./components/ui";
import { initTelegram } from "./lib/telegram";
import { TelegramGate } from "./components/TelegramGate";

const HomePage = lazy(() => import("./pages/Home"));
const MarketPage = lazy(() => import("./pages/Market"));
const ItemDetailPage = lazy(() => import("./pages/ItemDetail"));
const CollectionPage = lazy(() => import("./pages/Collection"));
const FavoritesPage = lazy(() => import("./pages/Favorites"));
const ProfilePage = lazy(() => import("./pages/Profile"));
const OrdersPage = lazy(() => import("./pages/Orders"));
const NotificationsPage = lazy(() => import("./pages/Notifications"));
const CollectionDetailPage = lazy(() => import("./pages/CollectionDetail"));
const SellerPage = lazy(() => import("./pages/Seller"));
const AdminPage = lazy(() => import("./pages/Admin"));
const AboutPage = lazy(() => import("./pages/About"));

initTelegram();

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 20_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        const status = (error as { status?: number }).status;
        if (status && status >= 400 && status < 500) return false;
        return failureCount < 2;
      },
    },
    mutations: { retry: 0 },
  },
});

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("GIFT MARKET crash", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-dvh flex-col items-center justify-center gap-3 px-6 text-center">
          <div className="grid h-14 w-14 place-items-center rounded-2xl bg-danger/15 text-2xl">⚠️</div>
          <p className="text-[16px] font-extrabold">Что-то сломалось</p>
          <p className="max-w-[300px] text-[12.5px] leading-relaxed text-muted">
            Мы записали ошибку. Перезагрузите приложение — если проблема повторится, напишите в поддержку.
          </p>
          <button className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>
            Перезагрузить
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function ScrollReset({ children }: { children: ReactNode }) {
  const location = useLocation();
  return (
    <div key={location.pathname} className="animate-rise">
      {children}
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ToastProvider>
            <TelegramGate>
              <Suspense fallback={<FullPageLoader />}>
                <Routes>
                <Route element={<Layout />}>
                  <Route
                    path="/"
                    element={
                      <ScrollReset>
                        <HomePage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/market"
                    element={
                      <ScrollReset>
                        <MarketPage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/collection"
                    element={
                      <ScrollReset>
                        <CollectionPage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/collections/:slug"
                    element={
                      <ScrollReset>
                        <CollectionDetailPage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/favorites"
                    element={
                      <ScrollReset>
                        <FavoritesPage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/profile"
                    element={
                      <ScrollReset>
                        <ProfilePage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/orders"
                    element={
                      <ScrollReset>
                        <OrdersPage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/notifications"
                    element={
                      <ScrollReset>
                        <NotificationsPage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/gift/:id"
                    element={
                      <ScrollReset>
                        <ItemDetailPage mode="item" />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/listing/:id"
                    element={
                      <ScrollReset>
                        <ItemDetailPage mode="listing" />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/seller/:id"
                    element={
                      <ScrollReset>
                        <SellerPage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/admin"
                    element={
                      <ScrollReset>
                        <AdminPage />
                      </ScrollReset>
                    }
                  />
                  <Route
                    path="/about"
                    element={
                      <ScrollReset>
                        <AboutPage />
                      </ScrollReset>
                    }
                  />
                  <Route path="/market/" element={<Navigate to="/market" replace />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Route>
                </Routes>
              </Suspense>
            </TelegramGate>
          </ToastProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
