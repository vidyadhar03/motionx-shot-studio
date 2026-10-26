import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Panel, type Geom} from '../components/Panel';
import {Focus} from '../components/Focus';
import {Caption, Eyebrow, Headline, Tag} from '../components/Type';
import {Wordmark} from '../components/Brand';
import {COPY, CROP, DISCLOSE, END_CARD_LINK, SHOT} from '../content';
import {EASE_IN, EASE_IN_OUT, EASE_OUT, settle, tween} from '../lib/anim';
import {C, F, T} from '../theme';

// 46–49.5 s. Export: the selected takes and their manifest.
export const Export: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < 1376 || frame > 1500) return null;
  const out = tween(frame, 1476, 14, 0, 1, EASE_IN);
  const sc = 1.1;
  const s = settle(frame, 1386);
  const geom: Geom = {crop: CROP.exportDialog, x: 1800 - 679 * sc, y: (1080 - 600 * sc) / 2, scale: sc};
  return (
    <div style={{position: 'absolute', inset: 0, opacity: 1 - out}}>
      <Eyebrow text="Export" start={1386} x={120} y={338} />
      <Headline lines={COPY.export} start={1388} x={116} y={384} size={80} />
      <Tag text={DISCLOSE.export} start={1446} x={120} y={600} />
      <Panel src={SHOT.export} geom={{...geom, y: geom.y + (1 - s) * 60}} opacity={tween(frame, 1386, 12)} reveal={{amount: tween(frame, 1386, 20)}} />
      <Focus geom={geom} rect={CROP.exportRows} start={1414} end={1444} pad={4} radius={14} dim />
      <Focus geom={geom} rect={CROP.exportZip} start={1446} end={1476} pad={6} radius={12} />
    </div>
  );
};

// 49.5–52.5 s. How a generation actually runs. Accurate and simplified: the app and ComfyUI are local, inference is hosted.
type NodeDef = {x: number; title: string; sub: string; start: number};
const NODE_W = 380;
const NODE_H = 132;
const NODE_Y = 560;
const NODES: NodeDef[] = [
  {x: 150, title: 'MotionX', sub: 'Shot Studio app', start: 1494},
  {x: 770, title: 'Comfy workflows', sub: 'local ComfyUI', start: 1502},
  {x: 1390, title: 'Hosted generation', sub: 'image & video inference', start: 1510},
];

export const Tech: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < 1480 || frame > 1590) return null;
  const out = tween(frame, 1564, 14, 0, 1, EASE_IN);
  const mid = NODE_Y + NODE_H / 2;
  const arrows = [
    {x1: NODES[0].x + NODE_W, x2: NODES[1].x, label: ['Comfy SDK', 'local proxy'], start: 1508},
    {x1: NODES[1].x + NODE_W, x2: NODES[2].x, label: ['Partner', 'Nodes'], start: 1516},
  ];
  const pulse = tween(frame, 1528, 30, 0, 1, EASE_IN_OUT);
  const pulseX = NODES[0].x + NODE_W - 20 + pulse * (NODES[2].x + 20 - (NODES[0].x + NODE_W - 20));
  const gem = tween(frame, 1522, 18);
  const brk = tween(frame, 1530, 20);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: 1 - out}}>
      <Headline lines={[COPY.tech]} start={1490} x={960} y={236} align="center" width={1600} />
      {/* Gemini, separately: it powers the Director chat, not image or video generation. */}
      <div
        style={{
          position: 'absolute',
          left: NODES[0].x,
          width: NODE_W,
          top: 412,
          display: 'flex',
          justifyContent: 'center',
          opacity: gem,
          transform: `translateY(${(1 - gem) * 12}px)`,
        }}
      >
        <div
          style={{
            fontFamily: F.sans,
            fontSize: 24,
            fontWeight: 500,
            color: C.text,
            border: `1px solid ${C.line}`,
            background: C.bgLift,
            borderRadius: 999,
            padding: '10px 22px',
          }}
        >
          <span style={{color: C.amber, fontWeight: 600}}>Gemini</span> · the Director
        </div>
      </div>
      <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0}}>
        <line x1={NODES[0].x + NODE_W / 2} x2={NODES[0].x + NODE_W / 2} y1={468} y2={468 + 92 * gem} stroke={C.muted} strokeWidth={2} strokeDasharray="5 7" />
        {arrows.map((a, i) => {
          const p = tween(frame, a.start, 18, 0, 1, EASE_OUT);
          const x2 = a.x1 + (a.x2 - a.x1) * p;
          return (
            <g key={i}>
              <line x1={a.x1} x2={x2} y1={mid} y2={mid} stroke={C.amber} strokeWidth={2.5} />
              {p > 0.98 ? <path d={`M${a.x2 - 12},${mid - 8} L${a.x2},${mid} L${a.x2 - 12},${mid + 8}`} fill="none" stroke={C.amber} strokeWidth={2.5} /> : null}
            </g>
          );
        })}
        {pulse > 0 && pulse < 1 ? <circle cx={pulseX} cy={mid} r={7} fill={C.amber} /> : null}
        {/* Where things run. */}
        <path
          d={`M${NODES[0].x},${NODE_Y + NODE_H + 40} v14 H${NODES[1].x + NODE_W} v-14`}
          fill="none"
          stroke={C.muted}
          strokeWidth={1.5}
          opacity={brk}
        />
        <path d={`M${NODES[2].x},${NODE_Y + NODE_H + 40} v14 H${NODES[2].x + NODE_W} v-14`} fill="none" stroke={C.muted} strokeWidth={1.5} opacity={brk} />
      </svg>
      {arrows.map((a, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: a.x1,
            width: a.x2 - a.x1,
            top: mid - 64,
            textAlign: 'center',
            fontFamily: F.sans,
            fontSize: 20,
            lineHeight: 1.25,
            fontWeight: 500,
            color: C.muted,
            opacity: tween(frame, a.start + 10, 14),
            whiteSpace: 'nowrap',
          }}
        >
          {a.label[0]}
          <br />
          {a.label[1]}
        </div>
      ))}
      {NODES.map((n, i) => {
        const s = settle(frame, n.start);
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: n.x,
              top: NODE_Y + (1 - s) * 40,
              width: NODE_W,
              height: NODE_H,
              borderRadius: 18,
              background: C.panel,
              boxShadow: `inset 0 0 0 1px ${i === 0 ? 'rgba(232,176,74,0.55)' : C.line}, 0 24px 60px rgba(0,0,0,0.45)`,
              opacity: tween(frame, n.start, 12),
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              paddingLeft: 32,
              fontFamily: F.sans,
            }}
          >
            <div style={{fontSize: 34, fontWeight: 600, letterSpacing: '-0.02em', color: C.text}}>{n.title}</div>
            <div style={{fontSize: 22, color: C.muted, marginTop: 6}}>{n.sub}</div>
          </div>
        );
      })}
      {[
        {x: NODES[0].x, w: NODES[1].x + NODE_W - NODES[0].x, text: 'On your machine'},
        {x: NODES[2].x, w: NODE_W, text: 'Hosted'},
      ].map((b, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: b.x,
            width: b.w,
            top: NODE_Y + NODE_H + 70,
            textAlign: 'center',
            fontFamily: F.sans,
            fontSize: 22,
            fontWeight: 600,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: C.muted,
            opacity: brk,
          }}
        >
          {b.text}
        </div>
      ))}
    </div>
  );
};

// 52.5–55 s. Wordmark and the promise; everything is still for the final second.
export const EndCard: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < 1574) return null;
  return (
    <>
      <Wordmark start={1580} y={398} hairlineAt={1588} />
      <Caption start={1596} x={960} y={588} width={1400} align="center" size={50} color="#d9d9dd">
        <span style={{fontFamily: F.serif, letterSpacing: '-0.005em'}}>{COPY.closing}</span>
      </Caption>
      {END_CARD_LINK ? (
        <Caption start={1606} x={960} y={676} width={1400} align="center" size={T.tag} color={C.muted}>
          {END_CARD_LINK}
        </Caption>
      ) : null}
    </>
  );
};
