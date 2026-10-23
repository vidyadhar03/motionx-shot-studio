import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";

export function useMedia(q: string) {
  const [m, setM] = useState(() => matchMedia(q).matches);
  useEffect(() => { const mq = matchMedia(q); const h = () => setM(mq.matches); mq.addEventListener("change", h); return () => mq.removeEventListener("change", h); }, [q]);
  return m;
}

// The right-hand slot is shared: the director chat, or a section's own panel (shot controls, asset detail).
// A section renders its panel into `sideEl` through a portal and says whether it wants the slot (`want`), whether it
// REPLACES the chat while shown (`replace`: manual shot controls), and whether the whole slot should step aside (`hide`:
// Compare gives the videos the room).
type L = {
  sideEl: HTMLElement | null; setWant: (v: boolean) => void; setReplace: (v: boolean) => void; setHide: (v: boolean) => void;
  narrow: boolean; ctxOpen: boolean; setCtxOpen: (v: boolean) => void;
};
export const LayoutCtx = createContext<L>({ sideEl: null, setWant: () => {}, setReplace: () => {}, setHide: () => {}, narrow: false, ctxOpen: false, setCtxOpen: () => {} });
export const useLayout = () => useContext(LayoutCtx);

export function useSide(wanted: boolean, opts: { replace?: boolean; hide?: boolean } = {}) {
  const { setWant, setReplace, setHide } = useLayout();
  const replace = !!opts.replace, hide = !!opts.hide;
  useEffect(() => { setWant(wanted); setReplace(replace); setHide(hide); return () => { setWant(false); setReplace(false); setHide(false); }; }, [wanted, replace, hide, setWant, setReplace, setHide]);
}
export function SidePortal({ children }: { children: ReactNode }) {
  const { sideEl } = useLayout();
  return sideEl ? createPortal(children, sideEl) : null;
}
