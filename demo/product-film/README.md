# MotionX Shot Studio: product film

A 55-second, 1920×1080, 30 fps motion-graphics film built with [Remotion](https://www.remotion.dev/) (React +
TypeScript) from the showcase screenshots in `../showcase/screens/`. The intent and beat-by-beat plan are in
[STORYBOARD.md](STORYBOARD.md).

This folder is self-contained. It doesn't touch the app, its databases or media, or any real workspace.

## Commands

```bash
cd demo/product-film
npm ci                    # once
npm run studio            # live preview with scrubbing (Remotion Studio)
npm run render            # → out/motionx-shot-studio-demo.mp4 (H.264 High, yuv420p, CRF 16, AAC 192k)
npm run verify            # codec, size, fps, exact frame count, full decode, clean first/last frames
npm run contact-sheet     # → out/contact-sheet.jpg (frames pulled from the rendered MP4)
npm run stills -- 0 455 1649   # → out/stills/fNNNN.png, single frames for review
```

`render` and `studio` first run `npm run assets`. That step copies the screenshots into `public/screens/`, failing
unless each one is a 1920×1080 PNG, and synthesises `public/audio/score.wav`. A render takes about 30 s on an M-series
Mac. The first run downloads Chrome Headless Shell (Remotion's renderer). The Inter and Newsreader fonts load from
Google Fonts at render time.

`out/` and `public/` hold only generated files and are gitignored, matching the repo's habit of keeping rendered media
out of Git.

## Editing

| What | Where |
|---|---|
| Copy, honesty lines, closing link | `src/content.ts` (`COPY`, `DISCLOSE`, `END_CARD_LINK`) |
| Screenshot crops (screenshot pixels) | `src/content.ts` (`CROP`) |
| Section ranges, disclosure range, sound cues | `src/timeline.json` |
| Beat timing within a section | the scene file in `src/scenes/` (frame numbers are absolute) |
| Palette, fonts, type scale | `src/theme.ts` |
| Easing and springs | `src/lib/anim.ts` |
| Contact-sheet frames | `src/sheet.ts` |

Reusable pieces:

- `Panel`: a precise crop of a real screenshot, with reveal, offset and cross-dissolve.
- `Focus`: an amber outline, drawn on, around a region given in screenshot pixels, with an optional dim and label.
- `Headline`, `Eyebrow`, `Caption`, `Tag`: masked line reveals and supporting type.
- `Disclosure`: the persistent honesty line.
- `Wordmark`: the brand lockup.
- `Tech`: the execution graphic.
- `EndCard`: the closing card.

**Closing link.** The local repository has no remote and no public URL has been verified, so `END_CARD_LINK` is `null`
and the end card shows no link. Set it to a verified URL to add one line under the closing tagline.

## Honesty and disclosures

The screenshots come from the isolated "The Last Light" showcase (see `../showcase/INDEX.md`). It uses procedural
sample art, fake-adapter placeholder clips and a scripted, labelled director. Nothing in the film comes from the real
workspace or the flyover project.

- From the first UI frame until the execution graphic, the lower left reads *Illustrative workspace · sample media and
  simulated conversations*.
- **Chat:** tagged *Simulated conversation*. The app's own *[Mocked agent - demo script]* line stays in the proposal
  crop.
- **Compare:** keeps the app's *FAKE placeholder* badges and adds *Sample takes · an illustrative lighting change, not
  model output*. The revision is about light only. No still claims camera movement.
- **Memory:** tagged *Editable preference memory · not model training*.
- **Export:** tagged *Takes + manifest.json · not an assembled film*.
- **No clicks:** approval controls are outlined, never clicked. No generation or paid submission is shown happening.
  The proposal's *no cost (fake)* badge is the app's own label for the fake adapter.
- **Execution graphic:** shows the real route, simplified. MotionX → Comfy SDK + local proxy → Comfy workflows in
  local ComfyUI → Partner Nodes → hosted image and video inference. Gemini is shown apart, as the Director. Nothing
  suggests inference runs on the user's Mac.
- **References in Production:** the lines from shots 1 and 2 to harbour, keeper and lantern follow the shot plan's
  asset lists in `scripts/showcase.py`. Shot 3 lists none, so it gets no line.

## Audio and licensing

The sound is entirely procedural: `scripts/make-audio.mjs` synthesises it deterministically, with no samples,
recordings, stock music, voice or paid audio service. It's a low open-fifth pad that lifts to D major for the end card,
filtered-noise air on transitions, soft ticks on focus outlines, a two-note bell when take 2 is chosen, and a small
Schroeder reverb. It sits at about −19 LUFS integrated with a −9 dBFS peak. There is no voiceover. The film is
designed to read without sound.

Third-party components:

| Component | Licence |
|---|---|
| Remotion | Remotion licence: free for individuals and companies of up to three people; larger companies need a company licence |
| Inter, Newsreader | SIL Open Font License 1.1, loaded through `@remotion/google-fonts` |
| Screenshots | This project's own UI, captured from the showcase |

## Verified

`npm run verify` on the final render gave:

- H.264 High, yuv420p, 1920×1080, 30/1 fps.
- 1650 frames, so the video stream is exactly 55.000 s.
- A full decode with no errors.
- AAC 48 kHz stereo.
- Frame 0 is the plain ground (max luma 35). The last 0.2 s is the settled end card.

The container reports 55.019 s because of AAC frame padding (1024-sample frames). It stays well under 60 s.

Frames from every beat and every transition were checked at full size and at half size (960×540). At half size the
headlines, captions and tags read clearly, while dense UI text inside panels (badges, small metadata) is only legible
at full size.

## Known limitations

- Crops are 1.0–1.45× of 1920×1080 captures, taken at device pixel ratio 1. They are sharp at 1080p but not
  4K-ready. A 4K version would need recaptures at DPR 2.
- On the Board and Compare panels the small status badges read at full size but not at half size. The headline and
  outlines carry the meaning there.
- The "Every addition is marked" label overlaps the lower edge of the beats panel slightly.
