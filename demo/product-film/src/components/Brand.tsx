import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C, F, T} from '../theme';
import {COPY} from '../content';
import {EASE_IN, EASE_IN_OUT, EASE_OUT, tween} from '../lib/anim';

/** "MotionX Shot Studio" set like the app header (white + amber), revealed behind a mask, with an amber hairline. */
export const Wordmark: React.FC<{start: number; exit?: number; y: number; size?: number; hairlineAt?: number}> = ({
  start,
  exit,
  y,
  size = T.display,
  hairlineAt,
}) => {
  const frame = useCurrentFrame();
  const inP = tween(frame, start, 30, 0, 1, EASE_OUT);
  const outP = exit === undefined ? 0 : tween(frame, exit, 16, 0, 1, EASE_IN);
  const lineStart = hairlineAt ?? start - 6;
  const line = tween(frame, lineStart, 30, 0, 1, EASE_IN_OUT) * (1 - tween(frame, (exit ?? 1e9) - 2, 14, 0, 1, EASE_IN_OUT));
  return (
    <>
      <div style={{position: 'absolute', left: 0, right: 0, top: y, display: 'flex', justifyContent: 'center'}}>
        <div style={{overflow: 'hidden', paddingBottom: size * 0.16}}>
          <div
            style={{
              transform: `translateY(${(1 - inP) * 140 - outP * 140}%)`,
              fontFamily: F.sans,
              fontSize: size,
              fontWeight: 700,
              letterSpacing: '-0.045em',
              lineHeight: 1,
              color: C.text,
              whiteSpace: 'nowrap',
            }}
          >
            {COPY.wordmark[0]} <span style={{color: C.amber, fontWeight: 600}}>{COPY.wordmark[1]}</span>
          </div>
        </div>
      </div>
      <div
        style={{
          position: 'absolute',
          top: y + size * 1.38,
          left: 960 - 210 * line,
          width: 420 * line,
          height: 2,
          background: `linear-gradient(90deg, rgba(232,176,74,0), ${C.amber} 30%, ${C.amber} 70%, rgba(232,176,74,0))`,
        }}
      />
    </>
  );
};
