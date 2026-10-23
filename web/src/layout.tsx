import { createContext, ReactNode, useContext, useEffect } from "react";
import { createPortal } from "react-dom";

// The right-hand slot is shared: a section's inspector (shot Direction/Proposal/Details, asset detail) or the director.
// Sections render their inspector into `sideEl` through a portal and say whether they want the slot at all.
type L = { sideEl: HTMLElement | null; setWant: (v: boolean) => void; narrow: boolean; ctxOpen: boolean; setCtxOpen: (v: boolean) => void };
export const LayoutCtx = createContext<L>({ sideEl: null, setWant: () => {}, narrow: false, ctxOpen: false, setCtxOpen: () => {} });
export const useLayout = () => useContext(LayoutCtx);

export function useSide(wanted: boolean) {
  const { setWant } = useLayout();
  useEffect(() => { setWant(wanted); return () => setWant(false); }, [wanted, setWant]);
}
export function SidePortal({ children }: { children: ReactNode }) {
  const { sideEl } = useLayout();
  return sideEl ? createPortal(children, sideEl) : null;
}
