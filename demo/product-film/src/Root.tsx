import React from 'react';
import {Composition} from 'remotion';
import timeline from './timeline.json';
import {ProductFilm} from './ProductFilm';
import {ContactSheet, sheetSize} from './ContactSheet';

const Film: React.FC = () => (
  <Composition
    id="ProductFilm"
    component={ProductFilm}
    durationInFrames={timeline.durationInFrames}
    fps={timeline.fps}
    width={timeline.width}
    height={timeline.height}
    defaultProps={{withAudio: true}}
  />
);

export const Root: React.FC = () => (
  <>
    <Film />
    <Composition id="ContactSheet" component={ContactSheet} durationInFrames={1} fps={30} {...sheetSize()} />
  </>
);
