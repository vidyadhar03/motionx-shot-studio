# Demo approval brief: "Under the Flyover" (night)

**Status (2026-10-21, after Stage A):**
- **Stage A ran once** (Gemini, 6 requests, calculated $0.033141; see `docs/RUNS.md`, live run 2). It produced a **draft** plan (revision 2) in `data-flyover-live`, awaiting your review.
- Live calls are disabled again.
- Stages B–D are **not** approved.

**Revision 3 approved (2026-10-21).**
- **Shots:** s1–s3 created.
- **@underpass v1** is restricted to mood/lighting reference only, so video is **blocked** for all shots until you approve a location reference.
- **@boy image proposal** `agn_cf547c26feeb4ddc` is pending: Seedream 5.0 Flash, one image, 5.43 credits. It can't run until you approve Stage C and its image cap is set.

**Since your Stage A approval:**
- Night is recorded as a **creative choice**.
- The supplied @underpass image is a **mood and night-lighting reference only**; its layout is not approved for video.
- The location mismatch is **unresolved**.
- The final location reference will be chosen before any video generation.
- The §2 mock below predates these clarifications in places (it lists night lighting from the image). The live draft is what you review now.

**Positioning:** an open-source, Comfy-powered directing workspace: describe an idea, plan shots, prepare references, approve generation, and revise with preserved creative decisions. We don't claim these concepts are unique (Higgsfield documents AI directing, script breakdown, reusable assets and human-triggered generation). Our angle is an open, local, inspectable implementation on Comfy workflows.

---

## 1. Supplied location: imported as @underpass v1

| | |
|---|---|
| Original | `~/Downloads/Deserted Flyover Shelter at Night.png`. **Not modified**: same SHA-256 and timestamp before and after |
| Imported | Byte-for-byte: PNG, 1448×1086, RGB, 2,339,924 bytes, sha256 `f0aca6dc…49aac6a`. The C2PA chunk (`caBX`) is kept |
| Recorded source | *User-supplied AI-generated image (C2PA credentials: ChatGPT / OpenAI gpt-image, created 2026-10-20); not a photograph of the actual incident.* Stored as the version's `provenance`, carried into take snapshots and exports, and **never sent to the video model** |
| Status | **Supplied / ready**. A local copy at `demo/flyover/underpass.png` is gitignored, so whether it goes into the public repo is your call. Check OpenAI's terms and the real brand names below first |
| Lighting reference | Night: warm sodium streetlight glancing off concrete pillars and wet-looking asphalt, deep shadow under the deck, cool blue-black sky with distant lit office windows |

**Visual mismatches with the brief.** I reported these and didn't edit or regenerate the image:
1. **Tent-like shelter.** A cloth sheet and black tarp are tied between the wall and the pillar, forming a lean-to. The brief says "not a tent". H3 is told to keep the location consistent with its image, so it is likely to reproduce the shelter.
2. **No raised soil planting bed.** The belongings sit on a concrete kerb/footpath at the pillar base. The only planted strip is the shrub median across the road.
3. **More than minimal belongings:** a mattress and bedding, several sacks, a bucket, and steel pots.
4. **Readable real names: "RAHEJA MINDSPACE" and "Inorbit"** (real Hyderabad landmarks), plus pier numbers P-86/P-85 and posters. These conflict with the "no brands or readable text" guardrail and may appear in the video.
5. **No U-turn:** a straight road runs beside a curved, metro-style viaduct.
6. **No traffic** ("deserted"), while the shots have occasional vehicles. That's a creative addition, and it's compatible.

**Your options** (nothing done automatically):
- **(a)** Accept the image as a mood and lighting reference and accept the differences.
- **(b)** Supply or make a revised image (no shelter, a soil bed at a U-turn, no readable names) before Stage D.
- **(c)** Keep the image and let me adjust the plan's action to what it shows. That would move the film away from what you observed.

The plan below keeps your observed description (option a), so the first video may mix both.

## 2. Corrected treatment and shot list (night)

This plan is the **hand-written rehearsal mock** (`demo/flyover/build_fixture.py`), not model output. Stage A produces the live agent's own draft for comparison.

**Logline.** At night beneath a Hyderabad flyover, a boy squats on a strip of soil, absorbed in a phone, while the traffic turns around him.

**Treatment.** Night beneath a concrete flyover. Now and then a vehicle swings through the U-turn, its headlights sliding across the pillars. On a raised planting bed of bare soil at the base of a pillar, a few bags, covers and cooking utensils mark where someone stays; there is no tent. A boy squats on the soil in dirty, torn clothes, bent over a smartphone, scrolling short videos, its glow on his face against the orange streetlight. The film watches without explaining: engines echoing under the deck, the thin sound of the reels, the small movement of his thumb. We don't learn who he is or how he came to be here. The last shot stays close on his absorbed face as headlights keep passing behind him, and leaves the contrast to the audience.

| Observed (your brief) | Creative additions |
|---|---|
| It was night | The fictional boy's age (about 10), build, hair and clothing colours |
| A homeless child squatting beneath a flyover in Hyderabad | Lighting taken from your supplied AI-generated image: warm sodium streetlight, deep shadow, blue-black sky |
| Dirty, torn clothes | The phone's cold screen glow on his face |
| Deeply absorbed in scrolling reels on a smartphone | Occasional vehicles and headlights; sound design without music |
| At a U-turn, on a raised planting bed containing soil | Camera: a static wide, a slow push-in, a static close-up; order and durations |
| A few bags, covers and basic cooking utensils; not a tent | Gestures; an old phone in a scuffed case; screen content never readable |
| You found the contrast disturbing (the starting point, not shown) | |

- **I treated "night" as part of what you observed**, because you asked for the brief to be corrected. If it was a creative choice, tell me and I'll move it to the additions.
- **Late-afternoon daylight is removed.** The brief, the project direction (palette: *night: warm sodium streetlight…*), the decisions, every shot (`low_key_night`) and the @boy prompt now say night.

**Guardrails** (unchanged): fictional child; no backstory; no causal claim about the phone; dignity; no real brands or readable text; no slow motion and no music.

| Shot | Action | Camera | Duration | Sound | Assets |
|---|---|---|---|---|---|
| **s1 The U-turn** | At night, an occasional vehicle turns through the U-turn, headlights sweeping the pillars. On the raised soil bed at a pillar's base, bags, covers and utensils sit near @boy, squatting, head bent over an old smartphone, its screen glowing | wide · static · low-key night | 5 s | an occasional vehicle, engines echoing, a distant horn; no music | **@boy, @underpass** |
| **s2 Absorbed** | @boy squats, elbows on knees, thumb flicking up the screen of an old smartphone in a scuffed case; its cold glow on his face against the orange streetlight; headlights pass behind, softly out of focus | medium → medium close-up · slow push-in | 6 s | engines quieter; the phone's thin reel audio becomes audible; no music | @boy, @underpass |
| **s3 The screen** | Close on @boy's absorbed face, lit by the phone's shifting glow; he keeps scrolling as headlights pass, out of focus | close-up · static | 5 s | the phone's audio close over distant traffic; a far horn; no music | @boy, @underpass |

- The plan has no direction warnings.
- **@phone is deferred:** the plan has no phone asset; the smartphone is described in the action.

## 3. The only proposed image prompt

**@boy**: Seedream 5.0 Flash, 832×1248 (2:3), no input references, about 5.43 credits:
> Full-body character reference photo of a fictional Indian boy about 10 years old, thin build, short untidy black hair, barefoot, wearing a faded, torn and dusty grey T-shirt and dark blue shorts. Standing straight and facing the camera, arms relaxed, calm neutral expression. Photographed at night against a plain dark background under warm sodium-orange streetlight from one side, with soft fill so his face and clothes stay clearly readable; photorealistic, natural skin texture, sharp focus. Dignified, not posed for pity. No text, no logos, no other people. Portrait 2:3.

- **Why night with fill:** you asked for night. The soft fill keeps his face readable, which H3 needs to keep him consistent.
- **Risk:** the provider may refuse or alter a photoreal child in hardship (untested). If you'd rather keep his face less prominent, say so before Stage C.
- **No location prompt:** the location is supplied, so no location generation is planned.

## 4. Workflows and settings

| Purpose | Workflow | Settings | Price source | Estimate |
|---|---|---|---|---|
| @boy image | `seedream_flash_image`: `ByteDanceSeedreamNodeV3`, "seedream 5.0 flash" (official templates, MIT) | 832×1248, random seed, watermark off, no references | ComfyUI 0.42.1 price badge: flat $0.02574/image | 5.43 credits |
| First video (s1) | `h3_reference`: MiniMax H3 reference-to-video | 5 s, 768P, 16:9; Image 1 = @boy, Image 2 = @underpass | Price badge: $0.1287/s at 768P (no extra-image charge up to 5) | 135.78 credits |
| Agent | Gemini `gemini-3.8-flash`, Interactions API, no retries, thinking low | per stage | dated table in `studio/agent/pricing.py`: $0.75/$3.75 per 1M tokens; calculated as `gemini.v2` (conservative) | per stage |

- **Validation:** the image graph is checked offline with 0, 2 and 10 references.
- **Not yet confirmed:** any real image output or charge.
- **Video path:** references go directly into H3; no intermediate frame is composed.

## 5. Staged live calls, budgets and stop points

All stages run in **`data-flyover-live`**, which is already seeded locally with the corrected brief, 6 decisions and @underpass v1 (with provenance). It has 0 plans, 0 generations and 0 LLM usage. The real paid take (`data/`) and the earlier Gemini history (`data-live1/`) aren't touched.

I set one stage's variables, run it once, reset them to 0, and **stop for your review**. Fixed rules for every stage:
- no automatic retries;
- no provider fallback;
- no Anthropic calls;
- a failure is reported, not repeated.

| Stage | Calls | Verifies | Expected | Hard caps (separate budgets) | Stop with |
|---|---|---|---|---|---|
| **A: plan** | Gemini: `models.get` metadata (no tokens) + **one agent session**, about 5–7 requests | The live agent sees the existing @underpass (image and provenance), reuses it, plans night shots with only @boy + @underpass, keeps observed vs added separate, invents no backstory, and writes a **draft** via the nested `write /plan` schema (untested on Gemini) | **$0.03–0.07** | LLM `BUDGET_USD=0.15`, `MAX_LIVE_REQUESTS=8`, `MAX_OUTPUT_TOKENS=4096`, `THOUGHT_ALLOWANCE=4096`, `MAX_TURNS=8`. Image and video caps 0 | the draft plan vs §2 |
| **B: @boy prompt** *(optional)* | Gemini: one session of about 3 requests | Proposes only @boy, with an exact prompt. Skip it and click Generate yourself for no LLM cost | $0.01–0.02 | LLM cumulative `0.21` / `12` requests | the pending image proposal |
| **C: @boy image** | Seedream 5.0 Flash ×1. A second try only if you ask. Balance read before/after | First real image through the proxy → ComfyUI → Partner Node; charge vs 5.43; how the provider handles the prompt | **5.43 credits** | Image `STUDIO_IMAGE_BUDGET_CREDITS=11`, `STUDIO_IMAGE_MAX_PAID_ATTEMPTS=2`. Video cap 0 | the image; you choose or reject it |
| **D: first video (s1)** | Either you click Propose, or Gemini proposes in a tiny session of ≤ 3 requests. Then **one H3 take**, @boy + @underpass | First real reference-to-video with these references: consistency, and whether the shelter/brands from the image leak in; charge vs 135.78 | **135.78 credits** (+ ≤ $0.02 if the agent proposes) | Video `STUDIO_BUDGET_CREDITS=140`, `STUDIO_MAX_PAID_ATTEMPTS=1`. LLM cumulative `0.26` / `15` requests | the take; you write the real feedback |

**Maximum totals:**
- LLM **$0.26** (expected $0.04–0.11);
- images **11 credits** (expected 5.43);
- video **140 credits** (expected 135.78);
- **about $0.98 worst case**.

Removed since the previous brief: the location image fallback (5.43), @phone (5.43), and the matching image budget.

**Why the LLM caps sit above the expected cost:** the app checks each request against the cap using a pre-call *estimate* of about $0.035, which assumes full output and thinking. The supplied image adds about 1,600 estimated input tokens per request once read. If a stage hits the cap early, I report it and don't raise the cap.

**Later, not in this approval:** feedback on s1 (any example stays **provisional** until we watch the real take), s2/s3 takes, and the demo video.

## 6. Corrected Stage A request (exact text)

Sent once, to a new thread in `data-flyover-live`:

> Draft a short-film plan from the brief for my review: a compact treatment and about three night shots. The location already exists as @underpass v1, a user-supplied AI-generated image (not a photograph of the actual incident); reuse that handle, use its night lighting as the visual reference, and don't plan to generate it. Use only @boy and @underpass in the shots, and describe the smartphone in the action rather than as a separate asset. Keep what I observed separate from your additions. Write the plan as a draft and stop: don't propose any image or video generation.

**What the agent will have:**
- the corrected brief (night, and the provenance sentence) and the project direction (night palette);
- 6 decisions, including night and "@boy + @underpass only; phone deferred";
- `list /assets` showing @underpass v1; `read /assets/underpass/v1` returns the image, its description and its provenance;
- the `film-planning` skill, which now says to reuse existing assets, treat a supplied AI stand-in as non-documentary, and describe deferred props in the action.

**What it can't do, enforced in code rather than by the prompt:**
- approve a plan (no tool for it);
- propose any asset image before a person approves a plan, or ever for an asset marked "upload";
- propose a video, because no shots exist until you approve the plan.

## 7. Smallest first stage to authorise

**Stage A only:** one Gemini planning session, at most 8 requests, a $0.15 cap, expected about $0.03–0.07. It makes no image or video calls. Suggested wording: *"Approve Stage A with the caps in the brief."* Ideally, decide on the location options in §1 first, because they affect how you'll judge the plan.

## 8. Offline rehearsal (fake only)

Run in a separate rehearsal folder with the replay mock. Your real image was imported; the generated images were FAKE.

1. **Seed:** brief + 6 decisions + @underpass v1, imported unchanged (sha matches).
2. **Plan:** the mock agent read the brief, skill, decisions, assets and the @underpass image, then wrote revision 1 (draft): 3 night shots, assets @boy + @underpass.
3. **Approval:** a person approved it. That created s1–s3 with @underpass already pinned. Status: @boy missing, @underpass ready.
4. **Image proposal:** the mock agent proposed only @boy (~5.43 credits) → pending.
5. **Image approved:** a person approved it (FAKE image) and chose it → pinned to s1–s3. Both assets ready.
6. **First video:** the mock agent proposed s1 → **pending** (~135.78 credits) with Image 1 = @boy, Image 2 = @underpass. Not approved; no take.

The compiled s1 prompt contains night lighting and no provenance text, so the "AI-generated" note never reaches the model.
