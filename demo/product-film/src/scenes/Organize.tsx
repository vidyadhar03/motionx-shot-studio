import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Panel, type Geom} from '../components/Panel';
import {Focus} from '../components/Focus';
import {Eyebrow} from '../components/Type';
import {COPY, CROP, SHOT} from '../content';
import {EASE_IN, EASE_IN_OUT, EASE_OUT, mix, settle, tween} from '../lib/anim';
import {C, F} from '../theme';

// 16–26 s. One scene, its shots, and the references the shot plan lists for them.
// The Board group (scene header + cards) is placed in "board space" (screenshot pixels) and moved as one piece.
const ORIGIN = {x: 150, y: 172}; // top-left of the scene header crop

// The shot plan's assets for these shots (scripts/showcase.py SHOTS): shot 1 → harbour; shot 2 → harbour, keeper, lantern.
// Shot 3 was added later and lists none, so it gets no line.
const ASSETS = [
  {label: 'Location', crop: CROP.assetCard[0]},
  {label: 'Character', crop: CROP.assetCard[1]},
  {label: 'Prop', crop: CROP.assetCard[2]},
];
const LINKS: [number, number][] = [
  [0, 0],
  [1, 0],
  [1, 1],
  [1, 2],
];

const PHRASE_AT = [492, 540, 626];

export const Organize: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < 476 || frame > 792) return null;

  const m = tween(frame, 592, 34, 0, 1, EASE_IN_OUT); // board → row
  const s = mix(1, 0.66, m);
  const ox = mix(150, (1920 - 1620 * 0.66) / 2, m);
  const oy = mix(262, 250, m);
  const out = tween(frame, 764, 18, 0, 1, EASE_IN);
  const lift = (start: number) => (1 - settle(frame, start, 120)) * 70;

  const at = (crop: Geom['crop'], dy = 0): Geom => ({crop, x: ox + (crop.x - ORIGIN.x) * s, y: oy + (crop.y - ORIGIN.y) * s + dy, scale: s});

  const assetScale = 0.72;
  const aw = 337 * assetScale;
  const gap = 60;
  const ax0 = (1920 - (3 * aw + 2 * gap)) / 2;
  const ay = 655;
  const assetGeom = (i: number, dy = 0): Geom => ({crop: ASSETS[i].crop, x: ax0 + i * (aw + gap), y: ay + dy, scale: assetScale});

  const cardBottom = (i: number) => {
    const g = at(CROP.boardCard[i]);
    return {x: g.x + (520 * s) / 2, y: g.y + 391 * s};
  };

  return (
    <div style={{position: 'absolute', inset: 0, opacity: 1 - out}}>
      <Eyebrow text="Production" start={484} x={160} y={92} />
      <Phrases />

      <Panel
        src={SHOT.board}
        geom={at(CROP.sceneHeader, lift(482) * 0.5)}
        opacity={tween(frame, 482, 12)}
        reveal={{amount: tween(frame, 482, 18)}}
        shadow={false}
        border={false}
        radius={0}
      />
      {CROP.boardCard.map((crop, i) => (
        <Panel
          key={i}
          src={SHOT.board}
          geom={at(crop, lift(488 + i * 5))}
          opacity={tween(frame, 488 + i * 5, 12)}
          radius={12 * s}
          border={false}
        />
      ))}
      <Focus geom={at(CROP.sceneHeader)} rect={{x: 152, y: 174, w: 1616, h: 86}} start={500} end={536} pad={4} radius={10} />
      {CROP.boardCard.map((crop, i) => (
        <Focus key={i} geom={at(crop)} rect={crop} start={545 + i * 7} end={588} pad={5} radius={16} />
      ))}

      {ASSETS.map((a, i) => {
        const st = 622 + i * 6;
        return (
          <React.Fragment key={i}>
            <Panel src={SHOT.assets} geom={assetGeom(i, lift(st))} opacity={tween(frame, st, 12)} radius={12} border={false} />
            <div
              style={{
                position: 'absolute',
                left: assetGeom(i).x,
                width: aw,
                top: ay + 366 * assetScale + 18,
                textAlign: 'center',
                fontFamily: F.sans,
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                color: C.muted,
                opacity: tween(frame, st + 10, 14),
              }}
            >
              {a.label}
            </div>
          </React.Fragment>
        );
      })}

      <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0}}>
        {LINKS.map(([card, asset], k) => {
          const a = cardBottom(card);
          const g = assetGeom(asset);
          const b = {x: g.x + aw / 2, y: ay - 2};
          const p = tween(frame, 660 + k * 8, 22, 0, 1, EASE_OUT);
          if (p <= 0) return null;
          const d = `M${a.x},${a.y + 4} C${a.x},${a.y + 55} ${b.x},${b.y - 55} ${b.x},${b.y}`;
          return (
            <g key={k}>
              <path d={d} fill="none" stroke={C.amber} strokeWidth={2} strokeOpacity={0.9} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - p} />
              <circle cx={a.x} cy={a.y + 4} r={4} fill={C.amber} opacity={Math.min(1, p * 3)} />
              <circle cx={b.x} cy={b.y} r={4} fill={C.amber} opacity={p >= 1 ? 1 : 0} />
            </g>
          );
        })}
      </svg>
    </div>
  );
};

/** "Every scene. Every shot. Every reference." Each phrase brightens when its picture is in focus. */
const Phrases: React.FC = () => {
  const frame = useCurrentFrame();
  const inP = tween(frame, 486, 26, 0, 1, EASE_OUT);
  return (
    <div style={{position: 'absolute', left: 156, top: 124, overflow: 'hidden', paddingBottom: 10}}>
      <div
        style={{
          transform: `translateY(${(1 - inP) * 105}%)`,
          fontFamily: F.sans,
          fontSize: 72,
          fontWeight: 600,
          letterSpacing: '-0.035em',
          whiteSpace: 'nowrap',
          display: 'flex',
          gap: '0.32em',
        }}
      >
        {COPY.organize.map((p, i) => {
          const on = tween(frame, PHRASE_AT[i], 14);
          return (
            <span key={i} style={{color: i === 2 ? C.amber : C.text, opacity: 0.22 + 0.78 * on}}>
              {p}
            </span>
          );
        })}
      </div>
    </div>
  );
};
