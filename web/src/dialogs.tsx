import { createContext, ReactNode, useCallback, useContext, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE = 'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])';

/** Accessible dialog or right-side drawer: labelled, focus moves in and is trapped, Esc closes, focus returns. */
export function Modal({ title, onClose, children, footer, variant = "center", wide = false, closeLabel = "Close" }: {
  title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; variant?: "center" | "drawer"; wide?: boolean; closeLabel?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    const el = ref.current!;
    const first = el.querySelector<HTMLElement>("[data-autofocus]") ?? el.querySelector<HTMLElement>(`.modal-body ${FOCUSABLE}`) ?? el;
    first.focus();
    return () => { if (before && document.contains(before)) before.focus(); };
  }, []);
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
    if (e.key !== "Tab") return;
    const items = [...ref.current!.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((n) => n.offsetParent !== null);
    if (!items.length) return;
    const [a, z] = [items[0], items[items.length - 1]];
    if (e.shiftKey && (document.activeElement === a || document.activeElement === ref.current)) { e.preventDefault(); z.focus(); }
    else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
  };
  return createPortal(
    <div className={`scrim ${variant}`} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal ${variant} ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref} tabIndex={-1} onKeyDown={onKey}>
        <header className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label={closeLabel}>✕</button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>, document.body);
}

export type AskButton = { id: string; label: string; kind?: "primary" | "danger" | "ghost" };
type Ask = { title: string; body?: ReactNode; buttons: AskButton[]; input?: { label: string; value: string; placeholder?: string } };
type Pending = Ask & { resolve: (r: { id: string; value: string }) => void };
type Api = {
  ask: (a: Ask) => Promise<{ id: string; value: string }>;
  confirm: (title: string, body: ReactNode, opts?: { ok?: string; danger?: boolean }) => Promise<boolean>;
  prompt: (title: string, label: string, value?: string, opts?: { ok?: string; placeholder?: string }) => Promise<string | null>;
};
const Ctx = createContext<Api | null>(null);
export const useDialogs = () => useContext(Ctx)!;

export function DialogProvider({ children }: { children: ReactNode }) {
  const [stack, setStack] = useState<Pending[]>([]);
  const ask = useCallback((a: Ask) => new Promise<{ id: string; value: string }>((resolve) => setStack((s) => [...s, { ...a, resolve }])), []);
  const api = useMemo<Api>(() => ({
    ask,
    confirm: async (title, body, o) => (await ask({ title, body, buttons: [{ id: "no", label: "Cancel", kind: "ghost" }, { id: "yes", label: o?.ok ?? "OK", kind: o?.danger ? "danger" : "primary" }] })).id === "yes",
    prompt: async (title, label, value = "", o) => {
      const r = await ask({ title, buttons: [{ id: "no", label: "Cancel", kind: "ghost" }, { id: "yes", label: o?.ok ?? "OK", kind: "primary" }], input: { label, value, placeholder: o?.placeholder } });
      return r.id === "yes" ? r.value : null;
    },
  }), [ask]);
  const top = stack[stack.length - 1];
  const close = (id: string, value: string) => { top.resolve({ id, value }); setStack((s) => s.slice(0, -1)); };
  return (
    <Ctx.Provider value={api}>
      {children}
      {top && <AskDialog key={stack.length} ask={top} onPick={close} />}
    </Ctx.Provider>
  );
}

function AskDialog({ ask, onPick }: { ask: Ask; onPick: (id: string, value: string) => void }) {
  const [value, setValue] = useState(ask.input?.value ?? "");
  const cancel = ask.buttons[0].id;
  const confirmId = ask.buttons[ask.buttons.length - 1].id;
  return (
    <Modal title={ask.title} onClose={() => onPick(cancel, value)}
           footer={ask.buttons.map((b) => (
             <button key={b.id} className={b.kind ?? ""} data-autofocus={b.id === confirmId && !ask.input ? "" : undefined}
                     disabled={b.kind === "primary" && !!ask.input && !value.trim()} onClick={() => onPick(b.id, value)}>{b.label}</button>))}>
      {ask.body && <div className="ask-body">{ask.body}</div>}
      {ask.input && (
        <label>{ask.input.label}
          <input data-autofocus value={value} placeholder={ask.input.placeholder} onChange={(e) => setValue(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && value.trim()) onPick(confirmId, value); }} />
        </label>
      )}
    </Modal>
  );
}
