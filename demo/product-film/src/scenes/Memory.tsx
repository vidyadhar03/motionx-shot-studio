import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Panel, type Geom} from '../components/Panel';
import {Focus} from '../components/Focus';
import {Caption, Eyebrow, Headline, Tag} from '../components/Type';
import {COPY, CROP, DISCLOSE, SHOT} from '../content';
import {EASE_IN, settle, tween} from '../lib/anim';
import {C} from '../theme';

// 39–46 s. The memory dialog cut into its three scopes, stacked; the controls do the talking.
const SCALE = 1.1;
const X = 1800 - 730 * SCALE;
const ITEMS = [CROP.memAll, CROP.memFilm, CROP.memShots];

export const Memory: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < 1166 || frame > 1392) return null;
  const out = tween(frame, 1364, 18, 0, 1, EASE_IN);
  const total = ITEMS.reduce((a, c) => a + c.h * SCALE, 0) + 2 * 20;
  let y = (1080 - total) / 2;
  const geoms: Geom[] = ITEMS.map((crop) => {
    const g = {crop, x: X, y, scale: SCALE};
    y += crop.h * SCALE + 20;
    return g;
  });
  return (
    <div style={{position: 'absolute', inset: 0, opacity: 1 - out}}>
      <Eyebrow text="Director memory" start={1176} x={120} y={338} />
      <Headline lines={COPY.memory} start={1178} x={116} y={384} size={80} />
      <Caption start={1228} exit={1286} x={120} y={584} color={C.text}>
        Guesses stay tentative until you confirm.
      </Caption>
      <Caption start={1292} x={120} y={584} color={C.text}>
        {COPY.memoryNote}
      </Caption>
      <Tag text={DISCLOSE.memory} start={1200} x={120} y={660} />
      {geoms.map((g, i) => {
        const st = 1180 + i * 8;
        const s = settle(frame, st);
        return <Panel key={i} src={SHOT.memory} geom={{...g, x: g.x + (1 - s) * 70}} opacity={tween(frame, st, 12)} reveal={{amount: tween(frame, st, 18), from: 'right'}} radius={12} />;
      })}
      <Focus geom={geoms[1]} rect={CROP.memTentative} start={1226} end={1286} pad={6} radius={10} />
      <Focus geom={geoms[0]} rect={CROP.memCorrect} start={1290} end={1362} pad={7} radius={10} />
    </div>
  );
};
