import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Panel, type Geom} from '../components/Panel';
import {Headline} from '../components/Type';
import {Wordmark} from '../components/Brand';
import {COPY, CROP, SHOT} from '../content';
import {EASE_IN, settle, tween} from '../lib/anim';
import {T} from '../theme';

// 0–6 s. Identity first, then the Board's first scene rises in at 1:1 so the cards read as the product itself.
export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame > 192) return null;

  const drift = tween(frame, 96, 90, 0, 1, (t) => t); // a slow, linear lift while the frame holds
  const exitP = (i: number) => tween(frame, 164 + i * 3, 16, 0, 1, EASE_IN);

  const header: Geom = {crop: CROP.sceneHeader, x: 150, y: 300 - drift * 6, scale: 1};
  const hIn = settle(frame, 70);
  return (
    <>
      <Wordmark start={8} exit={56} y={420} hairlineAt={2} />
      <Headline lines={[COPY.hook]} start={78} exit={164} x={156} y={150} size={T.h1} />
      <Panel
        src={SHOT.board}
        geom={{...header, y: header.y + (1 - hIn) * 30 + exitP(0) * 30}}
        reveal={{amount: tween(frame, 70, 18)}}
        opacity={1 - exitP(0)}
        shadow={false}
        border={false}
        radius={0}
      />
      {CROP.boardCard.map((crop, i) => {
        const s = settle(frame, 78 + i * 6, 120);
        const g: Geom = {crop, x: 160 + 540 * i, y: 410 + (1 - s) * 90 - drift * 12 + exitP(i + 1) * 60, scale: 1};
        return (
          <Panel
            key={i}
            src={SHOT.board}
            geom={g}
            opacity={tween(frame, 78 + i * 6, 12) * (1 - exitP(i + 1))}
            radius={12}
            border={false}
          />
        );
      })}
    </>
  );
};
