import React, { useEffect } from "react";

// Simple top-right toast stack. App owns the list; each toast auto-dismisses
// after `timeout` ms (default 4s) unless timeout is 0 (sticky, e.g. "Scanning…").
function ToastItem({ t, onDismiss }) {
  useEffect(() => {
    if (!t.timeout) return;
    const h = setTimeout(() => onDismiss(t.id), t.timeout);
    return () => clearTimeout(h);
  }, [t.id, t.timeout, onDismiss]);

  return (
    <div className={`toast ${t.kind || ""}`} onClick={() => onDismiss(t.id)} role="status">
      {t.title && <div className="toast-title">{t.title}</div>}
      <div className="toast-msg">{t.message}</div>
    </div>
  );
}

export default function Toast({ toasts, onDismiss }) {
  if (!toasts || !toasts.length) return null;
  return (
    <div className="toast-wrap">
      {toasts.map((t) => <ToastItem key={t.id} t={t} onDismiss={onDismiss} />)}
    </div>
  );
}
