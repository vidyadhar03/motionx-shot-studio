import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Panel, type Geom} from '../components/Panel';
import {Focus} from '../components/Focus';
import {Caption, Eyebrow, Headline, Tag} from '../components/Type';
import {COPY, CROP, DISCLOSE, SHOT} from '../content';
import {EASE_IN, EASE_IN_OUT, mix, mixRect, settle, tween} from '../lib/anim';
import {T} from '../theme';

// 26–39 s. A request in the director chat → the chat scrolls into its own proposal → compare and choose.
export const Direct: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < 776 || frame > 1182) return null;
  return (
    <>
      <Eyebrow text="Direction" start={784} exit={994} x={120} y={338} />
      {frame < 1016 ? <Chat /> : null}
      {frame >= 1000 ? <Compare /> : null}
    </>
  );
};

const CHAT_SCALE = 1.45;
const CHAT_X = 1800 - 424 * CHAT_SCALE;

const Chat: React.FC = () => {
  const frame = useCurrentFrame();
  // One continuous crop of the director column: the request and the director's status lines, then it scrolls down to
  // the proposal card that the same turn produced.
  const sc = tween(frame, 885, 32, 0, 1, EASE_IN_OUT);
  const crop = mixRect(CROP.chatTop, CROP.chatProposal, sc);
  const hTop = CROP.chatTop.h * CHAT_SCALE;
  const hProp = CROP.chatProposal.h * CHAT_SCALE;
  const out = tween(frame, 994, 18, 0, 1, EASE_IN);
  const inS = settle(frame, 786);
  const geom: Geom = {
    crop,
    x: CHAT_X + out * 80,
    y: mix((1080 - hTop) / 2, (1080 - hProp) / 2, sc) + (1 - inS) * 40,
    scale: CHAT_SCALE,
  };
  const settled: Geom = {crop: CROP.chatProposal, x: CHAT_X, y: (1080 - hProp) / 2, scale: CHAT_SCALE};
  // The conversation appears turn by turn: the request, then "Reading the shot.", then "Setting the move…".
  const typed = tween(frame, 788, 14, 0, 0.34) + tween(frame, 816, 12, 0, 0.32) + tween(frame, 838, 12, 0, 0.34);
  return (
    <>
      <Headline lines={COPY.direct} start={788} exit={880} x={116} y={384} />
      <Headline lines={COPY.review} start={894} exit={994} x={116} y={384} />
      <Caption start={950} exit={994} x={120} y={600}>
        {COPY.approveNote}
      </Caption>
      <Tag text={DISCLOSE.chat} start={796} exit={1000} x={CHAT_X} y={geom.y - 46} />
      <Panel
        src={SHOT.proposal}
        geom={geom}
        opacity={tween(frame, 786, 10) * (1 - out)}
        reveal={{amount: Math.max(typed, sc), from: 'top'}}
      />
      <Focus geom={settled} rect={CROP.camLight} start={922} end={946} pad={6} radius={10} />
      <Focus geom={settled} rect={CROP.approveBtn} start={948} end={994} pad={6} radius={14} />
    </>
  );
};

const Compare: React.FC = () => {
  const frame = useCurrentFrame();
  const out = tween(frame, 1160, 18, 0, 1, EASE_IN);
  const sc = 0.9;
  const w = 917 * sc;
  const gap = 30;
  const x0 = (1920 - (2 * w + gap)) / 2;
  const y = 236;
  const take = (i: number): Geom => {
    const s = settle(frame, 1012 + i * 8);
    return {crop: CROP.compareTake[i], x: x0 + i * (w + gap) + (1 - s) * (i === 0 ? -70 : 70), y, scale: sc};
  };
  const takeSettled = (i: number): Geom => ({crop: CROP.compareTake[i], x: x0 + i * (w + gap), y, scale: sc});
  const fbIn = settle(frame, 1040);
  const fb: Geom = {crop: CROP.stairsFeedback, x: x0 + 34, y: y + 76 + (1 - fbIn) * 30, scale: 1.35};
  const stripIn = settle(frame, 1100);
  const strip: Geom = {crop: CROP.takeStrip, x: (1920 - 410 * 1.5) / 2, y: 820 + (1 - stripIn) * 40, scale: 1.5};
  const chosen = tween(frame, 1078, 18);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: 1 - out}}>
      <Eyebrow text="Review" start={1010} x={120} y={68} />
      <Headline lines={[COPY.compare]} start={1012} x={116} y={104} size={T.h2} />
      {[0, 1].map((i) => (
        <Panel key={i} src={SHOT.compare} geom={take(i)} opacity={tween(frame, 1012 + i * 8, 12)} dimmed={i === 0 ? chosen * 0.55 : 0} />
      ))}
      <Panel src={SHOT.feedback} geom={fb} opacity={tween(frame, 1040, 10) * (1 - chosen * 0.35)} radius={12} border={false} />
      <Focus geom={takeSettled(1)} rect={CROP.take2Selected} start={1078} end={1158} pad={6} radius={10} />
      <Panel src={SHOT.feedback} geom={strip} opacity={tween(frame, 1100, 12)} radius={12} />
      <Tag text={DISCLOSE.takes} start={1030} x={1800} y={1006} align="right" />
    </div>
  );
};
