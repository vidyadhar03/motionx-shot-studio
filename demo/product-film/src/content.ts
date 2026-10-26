// Everything a non-animator might want to change: copy, the honesty lines, screenshot crops and the closing link.
// Crops are in screenshot pixels (all screenshots are 1920×1080, demo/showcase/screens).
import type {Rect} from './lib/anim';

export const COPY = {
  wordmark: ['MotionX', 'Shot Studio'] as const,
  hook: 'Your film. One workspace.',
  idea: ['Start with', 'an idea.'],
  script: ['Or your script.'],
  scriptNote: 'Stored exactly as you paste it.',
  story: ['Shape the story', 'before the shots.'],
  storyNote: 'The shot plan comes after your approval.',
  organize: ['Every scene.', 'Every shot.', 'Every reference.'],
  direct: ['Give direction.'],
  review: ['Review before', 'generation.'],
  approveNote: 'Nothing runs until you approve.',
  compare: 'Compare. Choose. Keep your takes.',
  memory: ['Your preferences,', 'remembered.'],
  memoryNote: 'Review, correct or forget.',
  export: ['Selected takes.', 'Ready for your edit.'],
  tech: 'Built on ComfyUI.',
  closing: 'Your idea. Your direction.',
};

// Honesty layer. The showcase uses sample art, fake-adapter placeholder clips and a scripted director.
export const DISCLOSE = {
  global: 'Illustrative workspace · sample media and simulated conversations',
  chat: 'Simulated conversation',
  takes: 'Sample takes · an illustrative lighting change, not model output',
  memory: 'Editable preference memory · not model training',
  export: 'Takes + manifest.json · not an assembled film',
};

/**
 * Closing link. No public repository URL is verified for this project (the local repo has no remote), so the
 * end card shows no link. Set this to a verified URL to show it under the closing line.
 */
export const END_CARD_LINK: string | null = null;

export const SHOT = {
  board: '01-board.png',
  idea: '02-start-from-idea.png',
  script: '03-start-from-script.png',
  story: '04b-story-review.png',
  assets: '06-assets.png',
  feedback: '07-director-feedback.png',
  proposal: '08-proposal.png',
  compare: '09-compare.png',
  memory: '10-memory.png',
  export: '11-export.png',
};

const r = (x: number, y: number, w: number, h: number): Rect => ({x, y, w, h});

export const CROP = {
  // 01-board
  sceneHeader: r(150, 172, 1620, 92),
  boardCard: [r(160, 273, 520, 391), r(700, 273, 520, 391), r(1240, 273, 520, 391)],
  // 02 / 03 start your film
  startIdea: r(240, 176, 840, 440),
  startScript: r(240, 176, 840, 548),
  ideaText: r(256, 355, 808, 188),
  scriptTab: r(379, 232, 128, 36),
  // 04b story drawer
  beats: r(1212, 606, 566, 340),
  addedByDirector: r(1241, 920, 139, 21),
  approval: r(1219, 117, 684, 121),
  approvalButtons: r(1236, 160, 357, 38),
  // 06 assets: location, character, prop
  assetCard: [r(392, 159, 337, 366), r(32, 159, 338, 366), r(1111, 159, 337, 366)],
  // 08 proposal chat (one continuous column of the director panel)
  chatTop: r(1484, 196, 424, 226),
  chatProposal: r(1484, 418, 424, 494),
  camLight: r(1515, 607, 372, 82),
  approveBtn: r(1714, 744, 171, 40),
  waitingBadge: r(1692, 440, 160, 20),
  // 07 feedback bubble, take strip
  stairsFeedback: r(1531, 173, 371, 66),
  takeStrip: r(222, 900, 410, 84),
  // 09 compare
  compareTake: [r(33, 205, 917, 612), r(971, 205, 917, 612)],
  take2Selected: r(1044, 224, 78, 21),
  // 10 memory
  memAll: r(594, 232, 730, 166),
  memFilm: r(594, 414, 730, 166),
  memShots: r(594, 744, 730, 188),
  memTentative: r(614, 484, 370, 52),
  memCorrect: r(614, 332, 230, 24),
  // 11 export
  exportDialog: r(621, 240, 679, 600),
  exportRows: r(639, 383, 642, 263),
  exportZip: r(639, 697, 286, 36),
};
