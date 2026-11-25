# Faceless YouTube edutainment workflow · Higgsfield + Seedance

> **参数快照 2026-08-24，生成/发布前 live 校验；默认 14 天过期。** 下文模型名、账户可用性、平台规则与生成规格若出现具体值，均为历史流程例或创作目标，不是永久 provider 能力。

Use this when the user asks to build or automate a faceless YouTube channel, evergreen edutainment explainers, Bright Side-style storytelling, or a YouTube packaging system with Higgsfield / Seedance.

Sources studied: normalized local Higgsfield source map, Blog workflows `blog:faceless-channel` and `blog:faceless-channel-one-prompt`, paired YouTube archive items `youtube:wU_bmWb6bhg` and `youtube:Bf74TY20CrM`, plus current YouTube policy sources when the workflow is applied. Revenue and RPM claims in titles are excluded.

## Core decision

Treat the article as a **workflow inspiration**, not a literal production contract.

Adopt:
- high-RPM evergreen niche selection;
- reference-channel pattern extraction;
- act-level retention mapping;
- scene-by-scene AI visuals;
- packaging system: title, thumbnail, tags, timestamped description;
- multilingual editions as separately quality-controlled packages;
- average-view-duration/drop-off feedback into the next script;
- topic queue for scaling.

Reject:
- promising `$39,500/month`, `$31.69+ RPM`, or any revenue outcome;
- claiming “AI automatically bypasses reused-content strikes”;
- relying on one vague 5-minute generation prompt as the final deliverable;
- copying a reference channel’s assets, wording, titles, thumbnails, or proprietary style one-to-one.

## When to use this reference

Load this reference when the user says or implies:
- “faceless YouTube channel” / “无人出镜油管频道”
- “edutainment explainer” / “科普解释类频道”
- “用 Higgsfield + Seedance 做 YouTube 内容机器”
- “分析 Bright Side 这种频道并复刻方法论”
- “自动生成视频、缩略图、标题、tag、description”
- “批量生产一个频道的视频选题和成片”

This reference is one lane inside `seedance-prompt-gen`, not a separate router.
For a single prompt, product/logo/UI promo, or final MP4, stay in the
canonical skill and load only the execution or post-production adapter it
selects.

## Faceless 与批量生产的通用骨架

本节是与 provider 无关的通用骨架；下文 Higgsfield + Seedance 的具体流程是它的一种实现。

顺序：可核验脚本 → narration beats → visual beats → 资产 → 生成/来源素材 → 配音/字幕 → 组装 → 包装 → QC。参考频道只提供 hook、章节、视觉节奏和 thumbnail pattern，不提供事实；硬事实必须回到一手来源。五分钟解说可用 30–45 个视觉 beat 作为起始规划范围，不是固定指标。narration、captions、title、thumbnail 是不同资产。

### 文章转视频

1. 保留原作者归属；不能把第三方内容写成原创。
2. 抽取可以被画面支撑的事实与动作。
3. 给每个 narration beat 分配：真实来源素材、锁定静帧、AI generated shot、图表或字幕卡。
4. AI 生成镜头只承担画面功能，不替代事实证据。
5. 精确文字、引语、数字在后期叠加，见 [post-production.md](post-production.md)。


### Content factory

```text
invariants: 品牌/产品/角色/事实/合规
variables: hook / persona / setting / format / opening frame / voice / duration
workflow: calendar → batch assets → batch clips → package → publish → analyze
```

小批验证后再扩量。一次只变一个测试轴；不把「100 条一键生成」营销话术当能力标准。

### 可恢复批处理

deterministic filename；per-item status；请求/结果/job ID；成功项不重跑；只重试 missing/failed；付费 POST 前查已有 job；每批包含 QC 抽样与失败分类。跨会话恢复见 [sequence-resume.md](sequence-resume.md)。

### 本地化版本

从锁定 source package 派生，但每种语言独立验证：翻译、配音时长/发音、文化语境、title/thumbnail 与最终 render。出海地区版的重锁要求见 [platform-overseas.md](platform-overseas.md)。

### Title/thumbnail 与学习闭环

互补而非重复：一个手机上可读的焦点；标题制造问题，thumbnail 不直接重复答案。视觉包装和事实准确是不同质量层。记录 average view duration、drop-off 对应的章节/开放环，再把观察转成下一版脚本或镜头变更；不要用播放量反推单个模型「最好」。

## Production-grade workflow

### 0. Lock deliverable first

Before generating anything, write the output contract. The values below are an archived example, not required durations, aspect ratios, languages or asset counts:

```text
Deliverable: YouTube package / finished MP4 / channel topic system
Duration: 5 min long-form / 60-90s short / 15s test clip
Aspect ratio: 16:9 YouTube / 9:16 Shorts / both
Language: EN / ZH / bilingual
Assets: script, scene map, prompts, voiceover, clips, thumbnails, metadata
Verification: fact ledger, ffprobe, visual QC, policy checklist
```

For complex production, select only the applicable evidence and handoff artifacts from this palette; do not create empty files to imitate the example:

```text
task_plan.md
source_extract.md
fact_ledger.md
reference_channel_pattern.md
script.md
scene_map.csv
voiceover_script.md
generation_prompts.md
higgsfield_requests/
higgsfield_results/
assets/videos/generated/
assets/audio/narration/
assets/images/thumbnails/
locales/<locale>/
package_youtube.md
retention_feedback.csv
qc_notes.md
```

### 1. Pick a value-first niche

Finance, technology and educational/edutainment are examples from the archived workflow, not guaranteed high-RPM lanes.

Skill rule: choose a niche because it supports **viewer value + evergreen replay + sourceable expertise**, never because a blog title promises RPM or revenue.

A topic is qualified only when it has:
- a specific question with broad curiosity;
- enough reliable facts or events to support the promised runtime and claims without padding;
- a visual progression whose cadence follows information density, attention and accessibility rather than a fixed interval;
- a defensible payoff such as insight, proof, consequence, correction or reframe—an artificial twist is not required;
- low copyright risk and no need to impersonate real people.

### 2. Reverse-engineer the reference channel safely

Use the reference channel only to extract patterns:

```text
hook style
viewer POV / roleplay frame
act count and timestamp rhythm
clip density
visual change cadence
voiceover sentence length
fact/twist placement
thumbnail/title grammar
```

Do not copy:
- exact title wording;
- exact thumbnail composition;
- exact script phrasing;
- channel-specific character, logo, or branded assets.

### 3. Build the retention skeleton before the script

The archived Higgsfield article used the following 9-act map for one five-minute edutainment example. It is a pattern study, not a default contract; derive act count, order and timing from the topic, audience promise and current platform evidence:

| Act | Time | Purpose | Visual rule |
|---|---:|---|---|
| 1 Hook | 0:00–0:25 | impossible question / direct viewer role | 3 fast visuals, no exposition |
| 2 Calm + signs | 0:25–0:55 | normal world + warning signs | contrast calm image with one unsettling detail |
| 3 Inciting event | 0:55–1:35 | the “point of no return” | bigger motion, larger scale, audio shift |
| 4 Escalation | 1:35–2:05 | consequences become physical | visual density increases |
| 5 Decision | 2:05–2:45 | choice, tradeoff, human stakes | closer shots, fewer abstractions |
| 6 Night / hidden mechanism | 2:45–3:25 | explain the invisible force | metaphor visuals or diagram-like shots |
| 7 End state | 3:25–3:55 | outcome lands emotionally | slower, clearer images |
| 8 Discovery / proof | 3:55–4:25 | evidence, later discovery, data | archival-feeling visuals or map/objects |
| 9 Twist + outro | 4:25–5:00 | surprising correction + next question | one final memorable image |

Scene density is risk-adaptive: create enough visual beats to make every new claim, relation or emotional turn legible, then let shot/clip duration follow the information, performance, accessibility and live provider limit. A long static hold is valid when observation is the point and representative QC proves it works; do not impose a fixed beat count or interval.

### 4. Research and fact ledger

Before scripting, produce `fact_ledger.md`:

```text
Claim | Source URL/title | Confidence | How it appears in script | Visual idea
```

Rules:
- Never let the model invent “deep research.” Use actual sources.
- Separate facts from narration metaphors.
- For finance, health, law, disaster, history, and public figures, keep claims conservative and source-backed.
- If a fact is uncertain, phrase it as uncertainty in the script or remove it.

### 5. Script contract

The script must contain:
- an early, readable reason to continue before avoidable setup; the exact hook timing follows the format, audience and platform evidence;
- viewer role or perspective: “you are the apprentice / investor / engineer / witness” when appropriate;
- narration units that remain intelligible at the intended pace; related ideas may share a sentence when clarity improves;
- no generic AI phrases: “in today’s fast-paced world”, “unlock the secrets”, “breathtaking journey”;
- line-by-line voiceover timing;
- traceable visual-beat IDs at each visual or evidentiary handoff, without forcing a new image for every spoken line.

Example structure:

```text
C01 00:00-00:07 VO: “See that mountain? In ten minutes, it will erase a city.”
VIS: quiet street, mountain in background, one tiny ash particle lands on fruit.
SFX: distant low rumble, market ambience.
SOURCE: [source id]
```

### 6. Generation routing

The following is a historical route candidate, not a permanent default. Select the current authorized host, exact model and adapter only after live discovery and the user's task boundary:

```text
Hermes image2 / GPT Image 2 keyframes → Atlas Cloud Seedance → Higgsfield MCP fallback/special capability → FFmpeg/HyperFrames final assembly
```

Use Higgsfield MCP when:
- Atlas Cloud fails or lacks access;
- user explicitly asks for Higgsfield;
- the job needs Higgsfield-specific assets/workspace/Soul/Marketing Studio;
- a historical account run found Higgsfield's `seedance_2_0` path faster; current model availability and speed must be verified live.

Before submitting through Higgsfield:

1. run `higgsfield model list --video --json`;
2. run `higgsfield model get <job_set_type> --json`;
3. derive duration, resolution, aspect ratio, media inputs and generated-audio fields from that response;
4. keep reference audio and generated output audio as separate controls;
5. do not copy Atlas fields or archived UI limits into the CLI request.

The underlying 2026-07-10 check already showed static notes were wrong; **参数快照 2026-08-24，生成前 live 校验；默认 14 天过期**. Therefore this reference intentionally stores no permanent Seedance parameter table.

Full 5-minute video rule:
- Do **not** submit one giant prompt and call it done.
- Split into scene clips, save request/result JSON for each clip, download every result, then assemble.
- Voiceover, subtitles, thumbnail text, title, and description are post-production/package assets, not things to trust the video model to render.

### 7. Voiceover and audio

The article’s “AI voice must sound natural and fit the context” becomes this rule:

- generate narration separately with the configured TTS stack;
- use a voice that matches the niche: calm documentary for history/science, sharper for finance/tech;
- add breath gaps and pacing manually;
- mix AI video SFX low under narration;
- do not rely on Seedance/Higgsfield to generate readable speech, dialogue, or Chinese subtitles.

#### Localization lane

Do not treat one-click translation as a finished edition. Derive each locale from the locked source package, then re-check:

- meaning, terminology and cultural references;
- VO pronunciation, duration and scene timing;
- caption line breaks and reading speed;
- title/thumbnail information gap in the target language;
- final mix and render independently.

### 8. YouTube packaging system

After the video is assembled or at least scripted, generate the applicable parts of `package_youtube.md`. Variant counts are set by the actual test hypothesis, budget and current platform fields; zero is valid for an unused field:

```text
Title candidates: smallest sufficient comparison set, grouped by tested angle
Thumbnail concepts: smallest sufficient comparison set, each with visual hierarchy and optional short text
Description: platform-appropriate opening plus an outline/timestamps when useful
Tags: only relevant current-platform fields, no keyword stuffing
Pinned comment: only when the publishing plan uses one
A/B test hypothesis: what each thumbnail/title is testing
Shorts cutdowns: only when requested, with a count justified by distinct reusable hooks
```

Thumbnail rules:
- a truthful, immediately legible information gap, contrast, proof or question appropriate to the topic;
- the minimum focal hierarchy that stays readable at the target display size; multiple elements are allowed when their relation is the point;
- title and thumbnail carry complementary rather than redundant information; their relationship may be a question, proof, contrast, consequence or other truthful information gap suited to the topic;
- if text is used, use only as many words as remain readable and necessary in the target language;
- no unreadable AI microtext;
- generate thumbnails as images, not video frames, when clarity matters;
- verify at small size.

### 9. Scaling without inauthentic-content risk

The article suggests “make me 2 more videos.” Turn that into a controlled topic queue:

```text
Topic | Hook | Unique facts | Visual arc | Risk | Status
```

Only produce another video if:
- the topic has materially different facts/substance;
- the hook is not just a variable swap;
- visuals are not template-identical;
- sources are fresh enough for the topic;
- metadata is not mass-generated spam.

After publishing, update `retention_feedback.csv`:

```text
video_id | chapter/open_loop | expected_retention_job | actual_AVD/drop_off | diagnosis | next_script_change
```

Scale only after this loop identifies which hooks, chapter bridges and open loops actually held attention.

## YouTube policy and monetization guardrails

YouTube allows AI-assisted production, but the channel still needs original, authentic value.

Checklist:
- [ ] If realistic/photorealistic AI content is meaningfully generated or altered, mark the upload’s AI disclosure accurately.
- [ ] Do not portray a real person saying/doing something they did not do unless clearly disclosed and safe.
- [ ] Do not depict realistic disasters, public events, crimes, or public figures in a misleading way.
- [ ] Do not mass-produce near-identical videos with only small variable swaps.
- [ ] Add original explanation, research, commentary, or education value.
- [ ] Keep sources/rights notes in the workspace.
- [ ] Do not promise monetization, RPM, or channel revenue.

Important: YouTube’s disclosure flow does not by itself make a video ineligible for monetization, but inauthentic/repetitive content can affect the entire channel.

## Quality checklist before delivery

- [ ] `fact_ledger.md` exists and every hard claim maps to a source.
- [ ] `scene_map.csv` maps each material claim/turn to enough visual evidence at a cadence justified by the format.
- [ ] Every generated clip has saved request/result JSON and local media path.
- [ ] `ffprobe` confirms final MP4 duration/resolution/audio stream.
- [ ] Visual QC sampling covers the beginning, end, cuts/transitions, declared state changes and highest-risk intervals; sample density scales with runtime, cut density and risk rather than a fixed frame count.
- [ ] No generated subtitles, logo, watermark, or pseudo-text inside clips unless intentionally added in post.
- [ ] Voiceover is intelligible, paced, and mixed above SFX/BGM.
- [ ] The YouTube package includes only current-platform fields and test variants that the delivery actually uses; each retained field has a clear purpose.
- [ ] Localized editions have independent translation/VO/timing/packaging QC.
- [ ] Published episodes feed chapter/open-loop drop-off evidence into `retention_feedback.csv`.
- [ ] AI disclosure / originality / copyright risk has a written status in `qc_notes.md`.
