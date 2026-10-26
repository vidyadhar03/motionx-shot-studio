import React from 'react';
import {Img, staticFile} from 'remotion';
import {C} from '../theme';
import type {Rect} from '../lib/anim';

/** Where a screenshot region lands: `crop` in screenshot pixels, drawn with its top-left at (x, y) and scaled by `scale`. */
export type Geom = {crop: Rect; x: number; y: number; scale: number};

export const destRect = (g: Geom): Rect => ({x: g.x, y: g.y, w: g.crop.w * g.scale, h: g.crop.h * g.scale});

/** Map a rectangle given in screenshot pixels to frame pixels for a panel. */
export const toFrame = (g: Geom, r: Rect): Rect => ({
  x: g.x + (r.x - g.crop.x) * g.scale,
  y: g.y + (r.y - g.crop.y) * g.scale,
  w: r.w * g.scale,
  h: r.h * g.scale,
});

/** Move a geometry by an offset (used for entrance/exit motion) without changing its crop. */
export const shift = (g: Geom, dx: number, dy: number): Geom => ({...g, x: g.x + dx, y: g.y + dy});

const SCREEN = (name: string) => staticFile(`screens/${name}`);

type Reveal = {amount: number; from?: 'bottom' | 'top' | 'left' | 'right'};

/**
 * A precisely cropped region of a real screenshot. Nothing is redrawn: the pixels are the app's own.
 * `src2` + `mix2` cross-dissolve to a second screenshot through the same crop (used for matched tab switches).
 */
export const Panel: React.FC<{
  src: string;
  geom: Geom;
  src2?: string;
  mix2?: number;
  opacity?: number;
  reveal?: Reveal;
  radius?: number;
  shadow?: boolean;
  border?: boolean;
  dimmed?: number; // 0..1, darkens the panel when it is not the subject
  zIndex?: number;
}> = ({src, geom, src2, mix2 = 0, opacity = 1, reveal, radius = 14, shadow = true, border = true, dimmed = 0, zIndex}) => {
  const d = destRect(geom);
  const amt = reveal ? Math.max(0, Math.min(1, reveal.amount)) : 1;
  const hide = (1 - amt) * 100;
  const from = reveal?.from ?? 'bottom';
  // The panel grows out of the named edge: 'bottom' rises, 'left' wipes rightward, and so on.
  const inset = {
    bottom: `${hide}% 0 0 0`,
    top: `0 0 ${hide}% 0`,
    left: `0 ${hide}% 0 0`,
    right: `0 0 0 ${hide}%`,
  }[from];
  const clip = amt < 1 ? `inset(${inset} round ${radius}px)` : undefined;
  const img = (name: string, o: number) => (
    <Img
      src={SCREEN(name)}
      style={{
        position: 'absolute',
        left: -geom.crop.x * geom.scale,
        top: -geom.crop.y * geom.scale,
        width: 1920 * geom.scale,
        height: 1080 * geom.scale,
        maxWidth: 'none',
        opacity: o,
      }}
    />
  );
  if (opacity <= 0.001) return null;
  return (
    <>
      {shadow ? (
        <div
          style={{
            position: 'absolute',
            left: d.x,
            top: d.y,
            width: d.w,
            height: d.h,
            borderRadius: radius,
            boxShadow: '0 30px 80px rgba(0,0,0,0.55), 0 8px 24px rgba(0,0,0,0.35)',
            opacity: opacity * amt ** 4,
            zIndex,
          }}
        />
      ) : null}
      <div
        style={{
          position: 'absolute',
          left: d.x,
          top: d.y,
          width: d.w,
          height: d.h,
          borderRadius: radius,
          overflow: 'hidden',
          opacity,
          clipPath: clip,
          background: C.bg,
          zIndex,
        }}
      >
        {img(src, 1)}
        {src2 && mix2 > 0 ? img(src2, mix2) : null}
        {dimmed > 0 ? <div style={{position: 'absolute', inset: 0, background: C.bg, opacity: dimmed * 0.62}} /> : null}
        {border ? (
          <div
            style={{position: 'absolute', inset: 0, borderRadius: radius, boxShadow: `inset 0 0 0 1px ${C.line}`}}
          />
        ) : null}
      </div>
    </>
  );
};
