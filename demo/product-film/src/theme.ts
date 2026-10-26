import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {loadFont as loadNewsreader} from '@remotion/google-fonts/Newsreader';

const inter = loadInter('normal', {weights: ['400', '500', '600', '700'], subsets: ['latin']});
const newsreader = loadNewsreader('normal', {weights: ['400', '500'], subsets: ['latin']});

// The app's own palette (web/src/styles.css), so the film and the screenshots share one light.
export const C = {
  bg: '#0a0b0d',
  bgLift: '#111215',
  panel: '#16171a',
  line: 'rgba(255,255,255,0.09)',
  text: '#ececef',
  muted: '#8e929b',
  dim: '#5d616a',
  amber: '#e8b04a',
  amberSoft: 'rgba(232,176,74,0.14)',
  ok: '#4cc38a',
};

export const F = {
  sans: inter.fontFamily,
  serif: newsreader.fontFamily,
};

// Type scale (px at 1080p). Smallest on-screen copy is 22px so it survives a half-size preview.
export const T = {
  display: 112,
  h1: 84,
  h2: 64,
  sub: 34,
  tag: 22,
  eyebrow: 20,
};
