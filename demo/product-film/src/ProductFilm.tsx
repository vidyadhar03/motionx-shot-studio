import React from 'react';
import {AbsoluteFill, Audio, staticFile} from 'remotion';
import timeline from './timeline.json';
import {DISCLOSE} from './content';
import {Background, Disclosure} from './components/Type';
import {Hook} from './scenes/Hook';
import {Story} from './scenes/Story';
import {Organize} from './scenes/Organize';
import {Direct} from './scenes/Direct';
import {Memory} from './scenes/Memory';
import {EndCard, Export, Tech} from './scenes/Finish';

// Scenes use absolute frame numbers (see timeline.json and STORYBOARD.md) so picture and sound cues share one clock.
export const ProductFilm: React.FC<{withAudio: boolean}> = ({withAudio}) => (
  <AbsoluteFill style={{backgroundColor: '#0a0b0d', overflow: 'hidden'}}>
    <Background />
    <Hook />
    <Story />
    <Organize />
    <Direct />
    <Memory />
    <Export />
    <Tech />
    <EndCard />
    <Disclosure from={timeline.disclosure.from} to={timeline.disclosure.to} text={DISCLOSE.global} />
    {withAudio ? <Audio src={staticFile('audio/score.wav')} /> : null}
  </AbsoluteFill>
);
