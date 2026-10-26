import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C, F, T} from '../theme';
import {EASE_IN, EASE_OUT, held, tween} from '../lib/anim';

/** Amber accent for part of a headline. */
export const Amber: React.FC<{children: React.ReactNode}> = ({children}) => <span style={{color: C.amber}}>{children}</span>;

/**
 * Headline whose lines rise into place behind a mask, one after another, and leave the same way (upward).
 * `exit` is the frame the exit begins; omit it to hold until the parent sequence ends.
 */
export const Headline: React.FC<{
  lines: React.ReactNode[];
  start: number;
  exit?: number;
  x: number;
  y: number;
  size?: number;
  weight?: number;
  color?: string;
  stagger?: number;
  align?: 'left' | 'center';
  width?: number;
  lineHeight?: number;
  family?: string;
  tracking?: string;
}> = ({lines, start, exit, x, y, size = T.h1, weight = 600, color = C.text, stagger = 5, align = 'left', width = 1680, lineHeight = 1.06, family = F.sans, tracking = '-0.035em'}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: align === 'center' ? x - width / 2 : x,
        top: y,
        width,
        textAlign: align,
        fontFamily: family,
        fontSize: size,
        fontWeight: weight,
        letterSpacing: tracking,
        lineHeight,
        color,
      }}
    >
      {lines.map((line, i) => {
        const inP = tween(frame, start + i * stagger, 26, 0, 1, EASE_OUT);
        const outP = exit === undefined ? 0 : tween(frame, exit + i * 3, 14, 0, 1, EASE_IN);
        const ty = (1 - inP) * 105 - outP * 105;
        return (
          // Padding gives descenders room inside the mask; the negative margin keeps the line spacing honest.
          <div key={i} style={{overflow: 'hidden', paddingBottom: size * 0.14, marginBottom: -size * 0.14}}>
            <div style={{transform: `translateY(${ty}%)`, opacity: inP * (1 - outP * 0.6), whiteSpace: 'nowrap'}}>{line}</div>
          </div>
        );
      })}
    </div>
  );
};

/** Small amber section label with a hairline, above a headline. */
export const Eyebrow: React.FC<{text: string; start: number; exit?: number; x: number; y: number}> = ({text, start, exit, x, y}) => {
  const frame = useCurrentFrame();
  const p = tween(frame, start, 22);
  const out = exit === undefined ? 0 : tween(frame, exit, 12, 0, 1, EASE_IN);
  return (
    <div style={{position: 'absolute', left: x, top: y, display: 'flex', alignItems: 'center', gap: 16, opacity: p * (1 - out)}}>
      <div style={{width: 40 * p, height: 2, background: C.amber}} />
      <div
        style={{
          fontFamily: F.sans,
          fontSize: T.eyebrow,
          fontWeight: 600,
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          color: C.amber,
          transform: `translateX(${(1 - p) * -12}px)`,
        }}
      >
        {text}
      </div>
    </div>
  );
};

/** Supporting line: muted, smaller, fades up. */
export const Caption: React.FC<{
  children: React.ReactNode;
  start: number;
  exit?: number;
  x: number;
  y: number;
  size?: number;
  color?: string;
  width?: number;
  align?: 'left' | 'center' | 'right';
}> = ({children, start, exit, x, y, size = T.sub, color = C.muted, width = 900, align = 'left'}) => {
  const frame = useCurrentFrame();
  const p = tween(frame, start, 22);
  const out = exit === undefined ? 0 : tween(frame, exit, 12, 0, 1, EASE_IN);
  const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
  return (
    <div
      style={{
        position: 'absolute',
        left,
        top: y,
        width,
        textAlign: align,
        fontFamily: F.sans,
        fontSize: size,
        fontWeight: 400,
        lineHeight: 1.35,
        letterSpacing: '-0.01em',
        color,
        opacity: p * (1 - out),
        transform: `translateY(${(1 - p) * 14}px)`,
      }}
    >
      {children}
    </div>
  );
};

/** Small honest tag (e.g. "Simulated conversation") pinned near a panel. */
export const Tag: React.FC<{text: string; start: number; exit?: number; x: number; y: number; align?: 'left' | 'right'}> = ({text, start, exit, x, y, align = 'left'}) => {
  const frame = useCurrentFrame();
  const vis = exit === undefined ? tween(frame, start, 16) : held(frame, start, exit, 16, 10);
  return (
    <div
      style={{
        position: 'absolute',
        top: y,
        ...(align === 'left' ? {left: x} : {right: 1920 - x}),
        opacity: vis,
        fontFamily: F.sans,
        fontSize: T.tag,
        fontWeight: 500,
        color: '#b9bcc4',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{width: 7, height: 7, borderRadius: 7, border: `1.5px solid ${C.amber}`, display: 'inline-block'}} />
      {text}
    </div>
  );
};

/** Persistent honesty line, lower left, for every frame that shows the showcase workspace. */
export const Disclosure: React.FC<{from: number; to: number; text: string}> = ({from, to, text}) => {
  const frame = useCurrentFrame();
  const vis = held(frame, from, to, 18, 14);
  if (vis <= 0) return null;
  return (
    <div
      style={{
        position: 'absolute',
        left: 120,
        bottom: 46,
        opacity: vis * 0.95,
        fontFamily: F.sans,
        fontSize: T.tag,
        fontWeight: 500,
        letterSpacing: '0.005em',
        color: '#9da1a9',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
      }}
    >
      <span style={{width: 7, height: 7, borderRadius: 7, background: C.amber, display: 'inline-block', opacity: 0.85}} />
      {text}
    </div>
  );
};

/** Charcoal ground with a faint warm lamp-glow low in the frame. Static, so it never competes with the UI. */
export const Background: React.FC = () => (
  <div style={{position: 'absolute', inset: 0, background: C.bg}}>
    <div
      style={{
        position: 'absolute',
        inset: 0,
        background:
          'radial-gradient(1200px 700px at 72% 108%, rgba(232,176,74,0.075), rgba(232,176,74,0) 70%), radial-gradient(900px 600px at 8% -10%, rgba(255,255,255,0.03), rgba(255,255,255,0) 70%)',
      }}
    />
  </div>
);
