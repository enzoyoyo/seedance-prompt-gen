# Higgsfield Archive → AI Video Method Playbook

This reference distills durable, provider-neutral AI-video directing, camera, lighting, and motion craft. It is not a model catalog or CLI schema; live parameters always follow `model-adaptation.md` and `provider-execution.md`.

## Stability gate

| Layer | Treatment |
|---|---|
| Prompt structure, reference roles, camera grammar, continuity, VFX source lock, QC | durable; safe to reuse |
| Model tendencies, multimodal inputs, native audio, 4K, lip-sync, product workflows | useful hypothesis; verify live |
| Model IDs, duration/resolution enums, UI names, plans, pricing, entitlements | executable only after current API/CLI discovery |
| Revenue, RPM, “viral overnight”, “unlimited”, “best/SOTA” | reject as skill rules |

Archive = evidence and methods. Live provider = execution contract.

## The quality stack

```text
viewer objective
→ production class
→ source/reference quality
→ continuity assets
→ minimum sufficient planning representation (only the storyboard/shot list/previs actually needed)
→ prompt architecture
→ camera and beat grammar
→ live provider/schema selection
→ generation + diagnosis
→ post-production + QC
```

A magic adjective cannot repair a missing layer.

## Direction router

| User goal | First decision | Method output |
|---|---|---|
| “更电影感” | define physical camera, optics, light and performance | shot plan + camera grammar |
| “更真实，不要 AI 味” | keyframe/source quality + physical evidence | realism locks + negative constraints |
| “更有运镜” | choose movement from scene job | a small set of materially different camera options with risks |
| “完整短片” | choose the minimum planning and continuity layers required by its block modes and risks | scene map plus only the useful panels/assets/shot contracts/prompts |
| “产品广告” | choose or invent a structure and protect product truth | visible promise/proof/payoff assets required by that concept |
| “UGC/开箱/测评” | trust format and product interaction plan | avatar/voice lane + product B-roll lane |
| “真实素材做 VFX” | source-plate preservation | effect-only delta prompt + source QC |
| “批量做内容” | define invariant and test variables | content matrix + manifests + QC loop |
| “一键爆火” | treat preset as ideation only | several directions; fully direct only winners |

## Prompt architecture

### Five-question brief

Before prose, answer:

1. Who or what is in frame?
2. Where is it?
3. What visible action changes?
4. What does the camera do?
5. What mood is created by light, palette and performance?

Source: `youtube:2naw_fZu4q0`.

### Reusable contract

```text
Structure: <duration / shot count / ratio after live validation>
Objective: <visible change or viewer understanding>
Story function: <why this shot exists>
References: <a small compatible, independently testable job set for each input; split only when roles conflict>
Subject locks: <identity, product, prop and location invariants>
Storyboard/shotlist: <only when the selected planning layer needs it; continuity in/out only when state is inherited>
Shot plan: <numbered shots or timestamp beats>
Camera: <minimum applicable placement/path/direction/speed/focus fields + narrative job; compatible staged paths only when motivated and tested>
Performance/physics: <cause/load/contact/reaction/follow-through/settle + secondary responses>
Audio policy: <reference / generated ambience-SFX / post>
Negative constraints: <likely failures only>
Style lock: <repeat essential look and continuity>
```

Source: `blog:seedance-prompting-guide`; supporting atoms `youtube:IAswRvWjdD8`, `youtube:1yhwLCoY5Cc`.

### When a start frame earns its slot

Pure text-to-video lets the model invent composition, identity and light simultaneously. When those facts matter and a representative test shows that a frame improves control, lock a keyframe and animate only the intended change. Text-only or source-video routes may be better when no static boundary needs locking. A bad keyframe becomes a moving bad image.

Use first/end frames for:

- controlled reveals and transformations;
- loops;
- matched transitions;
- exact product or character composition.

## Reference-role declaration

The durable rule is semantic, not syntactic:

```text
character reference → identity, hair, wardrobe, body silhouette
product/prop reference → exact shape, material, color, scale, details
location reference → geography, architecture, light direction
style reference → palette, texture, medium; not identity
motion reference → camera path, speed or action rhythm only
first/end frame → transition boundary
reference audio → rhythm, voice, lip-sync or ambience only
```

Provider adapters differ:

- Seedance web may use `@图片1 / @视频1 / @音频1`;
- some prompt examples use `<<<image_1>>>`;
- Higgsfield CLI uses media-role flags;
- Atlas uses request-schema fields.

Never paste one adapter into another backend. One input should carry a small, compatible and independently testable job set—not every job. Split it only when responsibilities conflict, compete for attention or exceed the live reference budget.

## Camera grammar

### Physical placement

Credible placement makes the image feel filmed:

- through windshield / dashboard-mounted;
- tabletop or counter height;
- over-the-shoulder;
- static corner/surveillance view;
- low-angle hero position;
- 3/4 room angle with two walls visible.

### Shot-size logic

- wide: geography, scale, threat, before-state;
- medium: action and relationship;
- close-up: reaction, material or proof;
- macro: food/product texture;
- an establishing view is often useful before complex coverage when geography is not already legible; deliberate withholding or an already established space may omit it;
- after every cut, re-anchor screen direction and object state.

When a story links an expansive exterior to a confined interior, their scale contrast can make one abstract tension visible at two levels; the edit and events must establish that meaning rather than assuming the spaces explain themselves.

### Motivated movement

| Movement | Job | Typical failure |
|---|---|---|
| locked-off | product readability, VFX source plate | no internal action |
| slow dolly-in | realization or premium reveal | generic without a beat |
| tracking/side follow | journey and action | screen-direction drift |
| handheld micro-jitter | UGC, urgency, documentary | chaos if exaggerated |
| orbit | product hero/object | geometry deformation |
| pan/tilt/crane reveal | hidden subject or scale | reveal shown too early |
| whip-pan/match cut | transition and energy | mismatched shot size/geometry or an unmotivated pre-lap that obscures the landing |

For a whip pan, declare direction, duration and actual subjects, then land on compatible shot size and screen geometry. Dialogue commonly starts after the camera lands; an intentional pre-lap is allowed when the edit/sound design requires it and intelligibility plus spatial relation pass QC.

A short shot defaults to the smallest coherent camera path. Orbit, dolly and pan may be staged in one shot only when they form a motivated continuous trajectory and a representative test proves the geometry/readability; otherwise split for safer attention and repair. A camera clause names only the dimensions that change execution—such as placement, path, direction, speed/focus, boundary composition and narrative job. A movement name by itself is incomplete when those omitted dimensions remain decision-critical.

### Optics with purpose

- a wide equivalent FOV at the chosen sensor/distance: spatial energy with possible perspective exaggeration;
- a moderate-wide equivalent FOV: common subject/environment balance;
- a normal equivalent FOV: common product/portrait balance;
- a narrow equivalent FOV with greater camera distance: common compressed portrait effect;
- macro: material and surface detail;
- shallow depth: isolate one subject;
- deep focus: preserve geography/action readability.

Numeric focal lengths are examples, not universal effects: sensor/crop, camera distance and framing change the result. Camera-body and lens-brand names are optional. The observable effect—field of view, perspective, depth of field, falloff and distortion—is the real instruction.

## Adaptive generation-block routing

`block_mode` answers how one sequence is generated and assembled. It is not a story form, a provider mode or a duration template. Duration is a live capability ceiling, not story structure; camera count is a directing choice, not a professionalism score.

| Mode | Choose when | Do not infer |
|---|---|---|
| `continuous_block` | continuous time, performance, sound field or one photographic behavior is itself valuable | that it needs cuts, or that a locked-off/observational take is defective |
| `covered_scene` | one scene event needs distinct spatial, reaction, eyeline or scale responsibilities to be visible | a fixed shot count, or that coverage must come from one multi-shot generation |
| `independent_pickup` | exact dialogue/lip-sync, a key reaction, complex contact, effect or local repair needs failure isolation | that every insert advances story time or needs a full scene package |
| `post_insert` | exact text, UI, legal copy, subtitle, deterministic replacement or overlay must be controlled | that repeated prompting will make generative pseudo-text reliable |

Choose the smallest mode that preserves the selected viewing experience:

1. Write the unit's `story_state_in/out` or the sensory/interpretive difference it promises.
2. Ask whether uninterrupted time, performance, sound or camera behavior carries meaning. If yes, test `continuous_block` first.
3. List coverage responsibilities actually needed by the edit. If more than one view must prove them, use `covered_scene`; views may be separate jobs that overlap the same story time.
4. Isolate lip-sync, contact, reaction, effect or repair risk as `independent_pickup` only when that isolation buys control.
5. Route exact, legal or replaceable surfaces to `post_insert`.
6. Then read the exact model's live duration, multi-shot, reference, edit and extend capabilities. Capability can constrain the plan; it cannot invent the plan's dramatic grammar.

A sequence may combine modes, but every generation job names one primary block mode and a reason. If the reason is only “the model can output 30 seconds,” “short videos need cuts,” or “cinematic means multiple cameras,” the route is not justified.

If a television, projection or other nested screen must play stable content, approve the inner clip as its own asset before building the outer shot; feed it through a supported reference role or deterministic screen replacement instead of asking one generation to invent both layers.

The archived four-part 15-second beat map—establish, action, impact, payoff—is one scalable example for work that genuinely has those beats. Transformation and short-film spines are palettes, not defaults; a held observation can contain one slow readable change.

For inter-block handoff, first mark `continuous_time` or `editorial_cut` and follow [continuity-storyboard.md](continuity-storyboard.md#状态交接). Do not use a similar end frame as a universal substitute for edit logic.

After a dense reveal or emotional peak, protect readable processing time before dialogue. Generated dialogue is semi-stable: prefer one clearly visible speaker, an exact line, voice tone and micro-pauses; when visual load competes with speech, generate a dedicated pickup and complete timing/mix in post after live audio checks.

## Storyboard and shot-list handoff

Choose the minimum sufficient planning layer:

- storyboard for framing, positions and light direction;
- animatic for timing, movement and edit rhythm;
- 3D previs only when exact camera/body geometry changes execution.

Do not board every line. Prioritize action, emotionally complex coverage, camera-critical beats, reveals, transitions and continuity-state changes. Each sequence brief keeps only the applicable who/where/visible-beat/emotional/reference/screen-direction/inherited-state evidence needed by its downstream decision; do not fill irrelevant dimensions.

Use arc-level panel distribution while exploring coverage. When a reveal, turn, eyeline or camera angle must land at a fixed position, direct each panel. Approve panels for story clarity, coverage, identity/light/geography continuity and edit usefulness, then label `scene_id / sequence_id / panel_id` and compile them into the shot list.

Full contract: [storyboard-camera-direction.md](storyboard-camera-direction.md).

## Continuity assets

### Minimum sufficient character view set

Before making a sheet, write a view requirement manifest:

```text
required_views / required_details / downstream_shots / minimum_pixel_readability
```

High-reuse, identifiable characters still need an approved identity anchor and outfit baseline. Then choose the minimum representation that covers the manifest: one high-resolution image, separate crops, two panels, a 3-panel or 6-view layout, or no sheet. A 3-panel is useful only when its particular front/back-or-3/4/face responsibilities match downstream shots and each cell remains readable; it is not a universal default. A one-off back-view extra may need only silhouette and wardrobe. Several conflicting faces in one image can increase drift, so keep one identity anchor.

Create separate approved variants whenever wardrobe, damage, dirt, carried props or another recurring story state changes. Assign the active variant in continuity-in/out; do not ask prose alone to remember a torn or injured state.

### Product or prop sheet

Write `required_views / downstream_shots / minimum_pixel_readability` first. Front, side, 3/4/top, scale, material and recurring details are candidates; include only those that resolve the current geometry, interaction or recognition risk. Exploded views are useful only when structure matters to the shot.

### Location sheet

Capture the minimum views that prove the geography used downstream. Wide, 3/4, entry/exit, key-light direction and spatial relationships are candidates, not a fixed checklist.

### Global style prefix + named shots

For long campaigns, keep a shared style/continuity prefix and separately editable shot prompts (`1a`, `1b`, `2a`). Change the global look once without rewriting every action.

Sources: `youtube:ODNzk5x2tR4`, `blog:cinematic_headphones`, `blog:Santiago-breakdown`.

## Physical realism

Replace “ultra realistic” with visible evidence:

- motivated, explainable light sources with mutually coherent direction, falloff and shadows;
- skin/material imperfections;
- motion blur tied to actual movement;
- inertia, gravity and contact;
- dust, water, steam, debris or reflection responding to the event;
- body beats such as jaw tightening, fingers pausing or shoulders freezing.

For complex action, write a force chain: cause → load/coil → contact/force → reaction/weight transfer → follow-through → settled end state. Add clothing, prop, surface, dust/water/debris, light and focus responses. Use a held State A, a visible transition cue and a distinct State B instead of constant undifferentiated energy.

Use three optional physical diagnostics when significant movement or subject entry is at risk:

- **Weight:** mass must be visible in acceleration, deceleration, lag and settling; nothing starts or stops instantly or glides at a mechanically constant speed without cause.
- **Ground truth:** feet, paws, wheels, hulls or props make real contact and transfer load; the surface responds through compression, deformation, displaced material, splash, shadow or friction as applicable.
- **Physical entry:** in a continuous shot, a new subject enters through a frame edge, occlusion or another visible causal path instead of spawning mid-frame. An intentional editorial cut may establish a new subject without this rule.

These are diagnostics, not mandatory Prompt headings. Keep only the terms that expose the current failure.

One impossible event integrated through light, contact and occlusion is more credible than several unrelated effects.

### 可观察表演与收尾自检

情绪不是一帧标签，而是有触发和延迟的时间过程。先写说话或动作之前的可见状态，再写触发它变化的事件或具体词位，最后写变化完成后进入的稳定状态；不要让反应提前于触发发生。

按本镜风险选择最小充分的身体与声音通道，例如呼吸、肩背、手、目光、音量与停顿。矛盾情绪分配到不同通道，让保护性的反应先出现、真实情绪稍后才漏出来，比同时端出两种表情可信。通道之间不得互相争抢；写不进画面的心理活动不写。相机在这里只负责观察或伴随，不接管主体动作。

有接触时不在本节另写力链：按 [prompt-contract.md](prompt-contract.md#动作与物理) 的因果链编译一次即可，本节只判断这一镜是否真的需要完整链——没有接触的简单表演不必硬写。AU/FACS 只作可选校准，模型解析不稳定时保留自然语言的可见证据。

收尾自检：末态是否稳定到可剪、可交接；每条写下的响应是否能被镜头或话筒观察；有没有多余修辞在和主动作抢注意力；生成后完整回放，按实际暴露的表演或物理问题单变量返修，不一次同时改动作、机位与情绪。

### 表演节拍编译增量

- 复杂镜先定导演读法，再把它翻成可观察动作；镜头、调色、声音服从读法，不从漂亮镜头倒推戏。
- 节拍按「人物在做什么、防线怎样变化」命名。保护性反应先出现，真实情绪随后漏出；相邻拍不得无过程跳档。
- 重复句式用呼吸、目光、音量或速度的可见差量演转折；停顿必须对应一个正在做的决定，不以“电影感”插空。
- 表情先用眉、眼、鼻翼、唇、下巴及身体/声音的自然语言描述，再按需要用 AU/FACS 校准。面部动作写开始、峰值触发与消退，不从第一帧拉满。
- 每拍保留时间段、人物目的、变化、触发词、脸部、目光/身体、声音/呼吸、结束状态中真正影响生成的字段；不得为填表编造。
- 一拍只给一次反应，随后进入动作；给眼睛一个可观察任务，不靠补眼神光代替人物正在处理的信息。
- 喜剧收尾可让前置动作快速推进，把最终反应留作全段最长镜头；停顿必须落在人物正在处理包袱的时刻，并由实际剪辑试听决定。

## Controlled film texture and color arc

### 受控瑕疵，不是脏滤镜

胶片感来自可解释的捕捉行为：细颗粒随曝光区变化、强光边缘轻微 halation/bloom、特定入射角出现 flare、人工跟焦可能出现微小过冲。每镜只保留与摄影装置、叙事和当前画面相符的必要瑕疵；没有必要时可以为零。需要跨镜延续时再保持频率和强度一致；随机叠灰尘、刮痕、色散和剧烈 gate weave 会把连续性问题伪装成“风格”。

先保证身份、空间、光线和运动通过，再在后期统一颗粒/高光响应。生成阶段的瑕疵用于指导捕捉质感，不能替代 deflicker、调色或真实 QC。

### 颜色弧服务剧情状态

如果作品用颜色承担状态变化，为相关阶段记录主色、辅色、饱和度、对比度、肤色保护和实体光源。以下只是可改写、重排或删除的示例弧，不是固定叙事顺序：

```text
秩序：受控中性色 + 稳定曝光
压力：冷色或低饱和扩张，人物肤色被环境吞没
危机：警示色只在道具/光源/伤口等叙事载体出现
选择/释放：色温、明度或饱和度发生可见转折
余波：保留前一阶段的一处颜色残留，证明代价仍在
```

颜色变化必须由时间、地点、光源或动作触发；不能在 cut 后无因换 LUT。为跨模型镜头保存 palette/HEX 作为比对锚，但最终以画面关系和肤色连续性验收，不把某组 HEX 当通用电影配方。

跨时代叙事可让旧时代人物进入现代彩色环境后仍保留黑白，用同帧色彩冲突标示时代归属；只有观众无需台词也能稳定读懂这套规则时才采用。

### 胶片语域与器材写法

本段是上面「受控瑕疵」的具体写法层，不是另一套标准。

不写 `cinematic`、`beautiful lighting`、`4K`、`masterpiece` 这类无指向词；把想要的结果拆成捕捉行为：

```text
shot on ARRI Alexa with Cooke S4 anamorphic primes, Kodak Vision3 5219 emulsion,
practical tungsten key from frame left, heavy fill falloff into shadow,
visible grain in the shadows, subtle halation on the practical bulbs,
shallow depth of field with the far wall dissolving into bokeh
```

**器材与胶片品牌名按目标端分叉。** 上面这种写法在不做版权风控的目标端可直接用；小云雀会以 `创作失败：内容涉及版权限制` 拒收品牌名，那一端按 [adapter-xyq.md](adapter-xyq.md) 的「品牌名替换表」换成通用光学描述，可见特征（颗粒、halation、色差、暗角、浅景深）照写不减。两处措辞不同、目标画面相同，不要用一端的写法覆盖另一端。

配套的可见特征词，按本镜需要挑，不叠满：

- 曝光与宽容度：`highlight rolloff`、`crushed blacks retaining texture`、`latitude in the overexposed window`
- 镜头行为：`anamorphic flare across the frame`、`focus breathing on the rack`、`chromatic aberration at the frame edge`、`vignetting`
- 载体质感：`fine grain that moves`、`gate weave held to a minimum`、`halation blooming off the practical`

### 畸形手与景别取舍

将中景适度收紧为特写有时能减少手部结构崩坏，但这取决于具体动作幅度与构图遮挡，不能将其误当成“收紧景别必治畸形手”的固定规律，也不能反推“远景必然坏手”。

与之冲突时以 [seedance-first-frame-action.md](seedance-first-frame-action.md) 的首帧撤回条款为准：如果收紧景别会让首帧丢失必须可见的状态或动作起点，优先保住首帧契约，改用重抽、改手部动作描述或后期处理。该文件反向指回本段。

## Product and advertising archetypes

The following are composable examples, not lanes that must be chosen intact. Merge, reorder, delete or invent beats to fit the promise, product proof, audience and format. Product lock, honest visible proof, claim consistency and required disclosure remain the gates.

### Product hero

```text
scroll-stopping product image
→ product in use
→ one feature demonstrated physically
→ macro proof/material insert
→ clean hero hold
```

### UGC

```text
human hook
→ use case/problem
→ proof or demonstration
→ casual finish
```

If reliable physical product interaction is not available, separate talking head/voice from product B-roll.

### Unboxing

```text
package arrives
→ tactile opening
→ product reveal
→ close detail
→ first-use reaction
```

### Product review

```text
claim/question
→ visible test
→ proof and limitation
→ verdict
```

### Hyper motion

```text
recognizable product silhouette
→ rapid but traceable feature transformations
→ product reassembly
→ hero frame
```

### TV spot / narrative commercial

```text
situation or emotion
→ product action as turning point
→ payoff
→ clean brand frame in post
```

### App marketing

Use static UI/keyframes or abstract interface motion. Exact text, legal copy and CTA belong in post, not inside generative video.

Product lock always wins over camera spectacle: preserve silhouette, label placement, materials, scale and key surface details.

Sources: Marketing Studio Blog cluster, `youtube:JXr9xztCznA`, `youtube:8EkoyS1102k`.

## Real-footage VFX

```text
Use the uploaded video as the source plate.
Preserve face, performance, wardrobe, props, framing, camera movement,
lens character, exposure, grain, color temperature, timing and scale.
Change only <named object/layer/world/effect>.
Make the change interact through emitted/cast light, contact shadow,
occlusion, reflection, debris, heat, water or surface reaction.
Do not re-frame, re-time or rewrite the source background.
```

The source clip should already contain the desired camera path. Analyze subject, camera, lens, light, timing, ratio, frame rate and source audio before prompting.

Sources: `blog:VFX-with-Seedance-4k`, `blog:vfx_4k`, `youtube:Yte-UGhYkPQ`.

## Faceless and batch production

### Faceless long-form

- retention/fact script before visuals;
- 30–45 visual beats for a five-minute explainer is a planning range, not a fixed rule;
- source every hard claim;
- reference channels supply hook/chapter/thumbnail patterns only;
- narration, captions, title and thumbnail are separate assets;
- localized editions derive from a locked source package but re-QC translation, VO duration/pronunciation, cultural context and local title/thumbnail packaging;
- title and thumbnail should be complementary, truthful and legible at the target surface; they may use one or several focal relations and need not use a question grammar;
- log average-view-duration/drop-off by chapter/open-loop and convert it into the next script change;
- originality and disclosure are channel-level QC, not solved by AI generation.

### Content factory

```text
invariants: product/brand/character/facts
variables: hook / avatar / setting / format / opening frame / voice / duration
workflow: calendar → batch assets → batch clips → package → publish → analyze drop-off
```

Do not scale a format before a small batch proves it. “100+ videos from one prompt” is a marketing claim, not a completion standard.

## MCP/Agent and production orchestration

Treat an MCP/Agent thread as an execution surface, not as evidence that work is complete. Record:

- tool/connector and auth status;
- workspace/project;
- live job/model ID;
- request/prompt artifact;
- job/clip ID and result URL;
- local downloaded path;
- manifest/QC status.

Batch generation should be resumable: deterministic filenames, per-item status, retry only missing/failed items and keep successful outputs untouched.

Treat each generation as a take. Keep a shot-level selects ledger with source path, in/out range, chosen performance/action/line, continuity status and rejection reason; assemble the best subshots across takes instead of forcing one generation to carry an entire scene.

Final edit keeps script truth, timing, VO, SFX/BGM, captions and legal/brand text under deterministic control.

## Provider adaptation gate

Before submission:

1. load the named execution skill;
2. list current models/capabilities;
3. inspect target schema;
4. translate the provider-neutral prompt contract into its media roles and fields;
5. validate cost/auth/entitlement where relevant;
6. submit and verify; poll only for asynchronous jobs, and download only when the provider returns a remote artifact that must be persisted locally.

Always verify current model availability via live `model list` rather than historical UI screenshots.

## Iteration and QC

Change one variable per retry. Log failure as one of:

- wrong composition/keyframe;
- identity or product drift;
- reference-role confusion;
- camera/timing noncompliance;
- physics/light integration failure;
- pseudo-text/watermark;
- provider/schema mismatch.

Test the highest-risk representative shot before easy coverage. Classify the first failure as identity/face, location/background, motion/physics, causal order or continuity-state error; return to the matching source anchor and repeat the same test.

生成块与返工预算按交付类型和镜头风险决定，不由模型时长上限反推。对模型高风险角度，可用整镜持续成立的背向、远离或缩小调度规避。定位问题时，只可将最小版与增加一个字段的版本并排比较；差集用于判断图已承载什么、文字还缺什么。

Prompt/package passes only when:

- [ ] objective and production class are explicit;
- [ ] decision-critical sequences use the minimum approved planning representation required by their risks; panels and a numbered shot list exist only when that representation needs them;
- [ ] references and invariants are explicit;
- [ ] beat map fits duration;
- [ ] each shot has the smallest coherent camera behavior needed for an explicit narrative job; staged paths are motivated and tested;
- [ ] physical action has cause, force, response and a settled end state;
- [ ] state changes use approved variants;
- [ ] continuity survives cuts;
- [ ] the highest-risk representative shot passed before batch generation;
- [ ] volatile capability was verified live;
- [ ] exact text and legal copy are assigned to post;
- [ ] request/result metadata is saved;
- [ ] generated/final media has real technical and visual QC.
