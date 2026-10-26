import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {C, F} from './theme';
import {SHEET_FRAMES} from './sheet';

// Key frames pulled from the rendered MP4 (scripts/contact-sheet.mjs), laid out with timecodes for review.
export const SHEET = {cols: 4, thumbW: 576, thumbH: 324, gap: 24, label: 46, header: 96};
export const sheetSize = () => {
  const rows = Math.ceil(SHEET_FRAMES.length / SHEET.cols);
  return {
    width: SHEET.cols * SHEET.thumbW + (SHEET.cols + 1) * SHEET.gap,
    height: SHEET.header + rows * (SHEET.thumbH + SHEET.label) + rows * SHEET.gap,
  };
};

const tc = (f: number) => `${String(Math.floor(f / 30)).padStart(2, '0')}:${String(f % 30).padStart(2, '0')}`;

export const ContactSheet: React.FC = () => (
  <AbsoluteFill style={{background: C.bg, fontFamily: F.sans}}>
    <div style={{position: 'absolute', left: SHEET.gap, top: 30, fontSize: 30, fontWeight: 600, color: C.text}}>
      MotionX Shot Studio · product film <span style={{color: C.muted, fontWeight: 400}}>· key frames (seconds:frames @ 30 fps)</span>
    </div>
    {SHEET_FRAMES.map(([frame, label], i) => {
      const col = i % SHEET.cols;
      const row = Math.floor(i / SHEET.cols);
      const x = SHEET.gap + col * (SHEET.thumbW + SHEET.gap);
      const y = SHEET.header + row * (SHEET.thumbH + SHEET.label + SHEET.gap);
      return (
        <div key={frame} style={{position: 'absolute', left: x, top: y, width: SHEET.thumbW}}>
          <Img
            src={staticFile(`contact/f${String(frame).padStart(4, '0')}.png`)}
            style={{width: SHEET.thumbW, height: SHEET.thumbH, display: 'block', boxShadow: `0 0 0 1px ${C.line}`}}
          />
          <div style={{marginTop: 10, fontSize: 20, color: C.muted, display: 'flex', gap: 12}}>
            <span style={{color: C.amber, fontVariantNumeric: 'tabular-nums'}}>{tc(frame)}</span>
            <span>{label}</span>
          </div>
        </div>
      );
    })}
  </AbsoluteFill>
);
