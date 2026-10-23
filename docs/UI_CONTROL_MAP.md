# Where every control lives (interface redesign)

Every control of the previous sidebar-and-columns interface still exists. Nothing was removed; this maps old to new.

| Before | Now |
|---|---|
| Project select, New project | Header project switcher (“＋ New project…”) |
| Workspace diagnostics, adapter, versions, Open ComfyUI | Settings → Workspace / Generation route |
| `543 / 0 cr · 4/0 attempts` badge, balance | Header spending chip (plain words, per area); Settings → Spending limits (ledger, caps, Check balance) |
| ISOLATED WORKSPACE badge | Header chip (full path on hover and in Settings) |
| Project panel: brief, tone/era/palette/notes, Save project | Overview → Brief & look (explicit Save, Unsaved/Saved shown) |
| Decisions | Overview → Decisions |
| Export selected takes… / Download ZIP | Header → Export |
| Film plan panel: edit, save revision, Approve, revisions, “Open shot” | Overview → plan chip / “Review plan” drawer (revision picker, Approved / Draft / Superseded labels, Edit as new revision, Approve) |
| Asset preparation: status, Upload image, Generate…, Approve for generation, Mood reference only, Use vN in planned shots, upload awaiting review, image proposals (Approve/Reject), Choose/Reject generated | Assets → select an asset (detail panel) |
| Assets sidebar: + Asset, versions, description → Save as vN | Assets → ＋ Add asset; asset detail → Versions, Description |
| Scenes, + Scene, + Shot | Shots → shot strip (＋ Shot, ＋ Scene, ＋ in a scene) |
| Shot editor: mode, scene, title, intention, action, framing, end framing, camera, camera detail, lens, depth of field, lighting, lighting detail, sound, duration, resolution, aspect, seed, start frame, references (order, update to newer version), direction notes, history | Shots → inspector → Direction |
| Lock from agent | Shots → header of the shot (“Lock from director” / “Locked · Unlock”) |
| Save, Save & propose generation | Direction → Save / Prepare proposal (Save & prepare when edited) |
| Proposal card: prompt, inputs, cost, Approve / Reject, stale banner | Shots → inspector → Proposal (and “Review & generate · cost” beside the player) |
| Take card: Approve, Reject, Unselect, Select for shot | Under the player: Approve & select (primary), Reject, Select for film; More → Approve only, Clear approval, Unselect |
| Take card: compare checkbox, compare view | Compare button → two takes fill the workspace |
| Take card: feedback reason + note, Add | Feedback button (under the player) and Details |
| Take card: Revise from this take | More → Revise from this take… (Direction opens with the revision banner) |
| Take card: Cancel, Resume, Resolve (attach / resubmit / recent jobs) | Banner under the player while a take is in flight or stuck; Details → Execution |
| Take card: input snapshot, timeline, job id, cost, time | Shots → inspector → Details |
| Agent panel: New thread, thread select, Send, Use suggestion, focus, LLM spend line, accounting | Header → Ask director (New conversation, conversation picker, Send, Use suggestion, context line, usage); Settings → Director cost accounting |
| Agent “Review in shot →” | Proposal card in the conversation: Open shot / Open asset, with the current status |
