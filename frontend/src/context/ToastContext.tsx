import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { hapticNotification } from "../lib/telegram";

type ToastKind = "success" | "error" | "info";

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  show: (message: string, kind?: ToastKind) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);

  const show = useCallback((message: string, kind: ToastKind = "info") => {
    if (!message) return;
    counter.current += 1;
    const id = counter.current;
    setToasts((current) => [...current.slice(-2), { id, kind, message }]);
    hapticNotification(kind === "error" ? "error" : kind === "success" ? "success" : "warning");
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id));
    }, kind === "error" ? 5200 : 3200);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      show,
      success: (message: string) => show(message, "success"),
      error: (message: string) => show(message, "error"),
      info: (message: string) => show(message, "info"),
    }),
    [show],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-shell">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.kind}`} role="status">
            {toast.kind === "success" && <CheckCircle2 size={17} className="text-mint" />}
            {toast.kind === "error" && <AlertCircle size={17} className="text-danger" />}
            {toast.kind === "info" && <Info size={17} className="text-violet-soft" />}
            <span className="text-ink">{toast.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
