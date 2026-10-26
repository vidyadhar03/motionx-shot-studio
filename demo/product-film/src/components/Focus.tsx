import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C, F, T} from '../theme';
import {EASE_IN_OUT, held, tween, type Rect} from '../lib/anim';
import {destRect, toFrame, type Geom} from './Panel';

type Side = 'right' | 'left' | 'top' | 'bottom';

/**
 * An amber outline drawn around a region of a real screenshot (given in screenshot pixels), optionally dimming the rest of
 * the panel and carrying a short label. It annotates the UI; it never replaces or mimics it.
 */
export const Focus: React.FC<{
  geom: Geom;
  rect: Rect;
  start: number;
  end: number;
  pad?: number;
  radius?: number;
  dim?: boolean;
  label?: string;
  side?: Side;
  labelOffset?: number;
  labelAlong?: number; // shift along the side (px)
}> = ({geom, rect, start, end, pad = 7, radius = 10, dim = false, label, side = 'right', labelOffset = 26, labelAlong = 0}) => {
  const frame = useCurrentFrame();
  const vis = held(frame, start, end, 6, 10);
  if (vis <= 0) return null;
  const r = toFrame(geom, rect);
  const box = {x: r.x - pad, y: r.y - pad, w: r.w + pad * 2, h: r.h + pad * 2};
  const draw = tween(frame, start, 16, 0, 1, EASE_IN_OUT);
  const perim = 2 * (box.w + box.h);
  const panel = destRect(geom);
  const labelIn = tween(frame, start + 8, 14);

  const labelStyle: React.CSSProperties = {position: 'absolute', whiteSpace: 'nowrap'};
  if (side === 'right') Object.assign(labelStyle, {left: box.x + box.w + labelOffset, top: box.y + box.h / 2 + labelAlong, transform: 'translateY(-50%)'});
  if (side === 'left') Object.assign(labelStyle, {right: 1920 - box.x + labelOffset, top: box.y + box.h / 2 + labelAlong, transform: 'translateY(-50%)'});
  if (side === 'top') Object.assign(labelStyle, {left: box.x + labelAlong, bottom: 1080 - box.y + labelOffset});
  if (side === 'bottom') Object.assign(labelStyle, {left: box.x + labelAlong, top: box.y + box.h + labelOffset});

  return (
    <div style={{position: 'absolute', inset: 0, opacity: vis, pointerEvents: 'none'}}>
      {dim ? (
        <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0}}>
          <path
            fillRule="evenodd"
            fill={C.bg}
            opacity={0.5 * draw}
            d={`M${panel.x},${panel.y}h${panel.w}v${panel.h}h${-panel.w}z ${roundedRectPath(box, radius)}`}
          />
        </svg>
      ) : null}
      <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}}>
        <rect
          x={box.x}
          y={box.y}
          width={box.w}
          height={box.h}
          rx={radius}
          fill="none"
          stroke={C.amber}
          strokeOpacity={0.18}
          strokeWidth={9}
          strokeDasharray={perim}
          strokeDashoffset={perim * (1 - draw)}
        />
        <rect
          x={box.x}
          y={box.y}
          width={box.w}
          height={box.h}
          rx={radius}
          fill="none"
          stroke={C.amber}
          strokeWidth={2.5}
          strokeDasharray={perim}
          strokeDashoffset={perim * (1 - draw)}
        />
      </svg>
      {label ? (
        <div style={{...labelStyle, overflow: 'hidden', padding: 4}}>
          <div
            style={{
              transform: `translateY(${(1 - labelIn) * 110}%)`,
              opacity: labelIn,
              fontFamily: F.sans,
              fontSize: T.tag,
              fontWeight: 500,
              color: C.text,
              background: 'rgba(17,18,21,0.94)',
              border: `1px solid rgba(232,176,74,0.45)`,
              borderRadius: 999,
              padding: '9px 18px 10px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              boxShadow: '0 10px 30px rgba(0,0,0,0.45)',
            }}
          >
            <span style={{width: 8, height: 8, borderRadius: 8, background: C.amber, display: 'inline-block'}} />
            {label}
          </div>
        </div>
      ) : null}
    </div>
  );
};

const roundedRectPath = (b: Rect, r: number) => {
  const {x, y, w, h} = b;
  return `M${x + r},${y}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${-(w - 2 * r)}a${r},${r} 0 0 1 ${-r},${-r}v${-(h - 2 * r)}a${r},${r} 0 0 1 ${r},${-r}z`;
};
