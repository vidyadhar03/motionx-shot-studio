import {Easing, interpolate, spring} from 'remotion';
import timeline from '../timeline.json';

export const FPS = timeline.fps;

// One motion language for the whole film.
export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1); // entrances: fast start, long settle
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1); // camera moves and morphs
export const EASE_IN = Easing.bezier(0.7, 0, 0.84, 0); // exits

/** Clamped tween of `frame` over [start, start + dur] from `from` to `to`. */
export const tween = (
  frame: number,
  start: number,
  dur: number,
  from = 0,
  to = 1,
  easing: (t: number) => number = EASE_OUT,
) =>
  interpolate(frame, [start, start + Math.max(1, dur)], [from, to], {
    easing,
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

/** Damped spring, 0 → 1 with a restrained (~3%) overshoot. */
export const settle = (frame: number, start: number, stiffness = 140) =>
  spring({frame: frame - start, fps: FPS, config: {damping: 19, stiffness, mass: 1}});

/** 1 while inside [from, to), with eased fades at both ends. */
export const held = (frame: number, from: number, to: number, fadeIn = 12, fadeOut = 12) =>
  Math.min(tween(frame, from, fadeIn, 0, 1), tween(frame, to - fadeOut, fadeOut, 1, 0, EASE_IN));

export const mix = (a: number, b: number, t: number) => a + (b - a) * t;

export type Rect = {x: number; y: number; w: number; h: number};

export const mixRect = (a: Rect, b: Rect, t: number): Rect => ({
  x: mix(a.x, b.x, t),
  y: mix(a.y, b.y, t),
  w: mix(a.w, b.w, t),
  h: mix(a.h, b.h, t),
});
