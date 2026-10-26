import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Panel, type Geom} from '../components/Panel';
import {Focus} from '../components/Focus';
import {Caption, Eyebrow, Headline} from '../components/Type';
import {COPY, CROP, SHOT} from '../content';
import {EASE_IN, EASE_IN_OUT, mix, mixRect, settle, tween} from '../lib/anim';
import {T} from '../theme';

// 6–16 s. Idea → (same place) script → story review and its approval.
const START_SCALE = 1.25;
const IDEA_Y = Math.round((1080 - CROP.startIdea.h * START_SCALE) / 2);
const SCRIPT_Y = Math.round((1080 - CROP.startScript.h * START_SCALE) / 2);

export const Story: React.FC = () => {
  const frame = useCurrentFrame();
  if (frame < 180 || frame > 482) return null;

  // Start panel: one crop that grows from the idea form to the script form as the tab switches.
  const sw = tween(frame, 276, 26, 0, 1, EASE_IN_OUT);
  const crop = mixRect(CROP.startIdea, CROP.startScript, sw);
  const startIn = settle(frame, 192);
  const startOut = tween(frame, 356, 18, 0, 1, EASE_IN);
  const startGeom: Geom = {
    crop,
    x: 750 - startOut * 80,
    y: mix(IDEA_Y, SCRIPT_Y, sw) + (1 - startIn) * 60,
    scale: START_SCALE,
  };
  const startSettled: Geom = {...startGeom, y: mix(IDEA_Y, SCRIPT_Y, sw)};

  // Story drawer: beats with their provenance, then the approval box.
  const beatsIn = settle(frame, 366);
  const apprIn = settle(frame, 420);
  const out = tween(frame, 460, 16, 0, 1, EASE_IN);
  const beats: Geom = {crop: CROP.beats, x: 1013 - out * 80, y: 196 + (1 - beatsIn) * 70, scale: 1.3};
  const appr: Geom = {crop: CROP.approval, x: 1013 - out * 80, y: 690 + (1 - apprIn) * 70, scale: 1.15};

  return (
    <>
      <Eyebrow text="Story first" start={194} exit={458} x={120} y={338} />
      <Headline lines={COPY.idea} start={196} exit={268} x={116} y={384} />
      <Headline lines={COPY.script} start={294} exit={358} x={116} y={384} />
      <Caption start={310} exit={356} x={120} y={500}>
        {COPY.scriptNote}
      </Caption>
      <Headline lines={COPY.story} start={366} exit={456} x={116} y={384} size={T.h1} />
      <Caption start={432} exit={456} x={120} y={600}>
        {COPY.storyNote}
      </Caption>

      <Panel
        src={SHOT.idea}
        src2={SHOT.script}
        mix2={tween(frame, 276, 6)}
        geom={startGeom}
        opacity={tween(frame, 192, 12) * (1 - startOut)}
        reveal={{amount: tween(frame, 192, 20), from: 'bottom'}}
      />
      <Focus geom={startSettled} rect={CROP.ideaText} start={226} end={274} pad={4} radius={8} />
      <Focus geom={{...startSettled, crop: CROP.startScript, y: SCRIPT_Y}} rect={CROP.scriptTab} start={300} end={352} pad={5} radius={10} />

      <Panel src={SHOT.story} geom={beats} opacity={tween(frame, 366, 12) * (1 - out)} reveal={{amount: tween(frame, 366, 20)}} />
      <Focus
        geom={{...beats, y: 196}}
        rect={CROP.addedByDirector}
        start={400}
        end={458}
        pad={5}
        radius={14}
        label="Every addition is marked"
        side="right"
      />
      <Panel src={SHOT.story} geom={appr} opacity={tween(frame, 420, 12) * (1 - out)} reveal={{amount: tween(frame, 420, 18)}} />
      <Focus geom={{...appr, y: 690}} rect={CROP.approvalButtons} start={436} end={458} pad={6} radius={12} />
    </>
  );
};
