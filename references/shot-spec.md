# 镜头规格

镜头规格是剧本锁定之后、花钱之前的唯一拍摄依据：一个 JSON 文件（默认项目目录下 `shots.json`），提交脚本从它展开命令，验收脚本拿它对台词。它只约束「能不能对得上、拍得出」，不规定拆几镜、每镜多长、怎么写提示词。

## 切分原则

只有一条：**按 beat 切；状态接不上或台词超出单条时长才拆。** 一个镜头可以带一个或多个相邻 beat；一个 beat 被拆成几镜时，每镜都标这个 beat。单条时长上限来自该通道能力卡里带核实日期的 `limits.max_duration_s`，不写死在这里，也不凭记忆。

## 字段

片级（对所有镜头生效，镜头可覆盖）：

| 字段 | 含义 |
|---|---|
| `channel` | 通道名，对应清单 `drama.channels` 里的一张能力卡 |
| `model` / `models` | exact model id；`models` 按档位给（`draft`／`lowres`／`final`） |
| `ratio` | 画幅，必须等于发布意图的 `aspect_ratio` |
| `style_suffix` / `identity_note` | 片级风格与身份说明，展开时接在每镜提示词后 |
| `refs` | 参考表：`{名字: {path, role, url?}}`，`role` 是提示词里对这张图的称呼；`url` 只给按 URL 传参考的通道用（上传后记下，展开为 `{ref_urls}`） |
| `post_beats` | 后期制作的 beat（如片尾卡），不需要生成镜头 |
| `inherits` | 系列分集：指向父目录的规格，未写的片级字段从父级取 |

镜头（`shots` 下以镜号为键）：

| 字段 | 含义 |
|---|---|
| `beat` / `beats` | 覆盖的 beat 编号，必须是锁定剧本里的 |
| `duration` | 秒，不超过通道卡上限 |
| `refs` | 用到的参考名，顺序即传给通道的顺序；每个参考文件（含首帧静帧）的摘要必须属于带码决定的 `identity_assets`（含父级系列）或选定的 `00_previs/` 干净帧／站位板，否则报 `SHOT_REF_NOT_USER_DECIDED` |
| `channel` / `model` / `models` | 可选：这一镜走别的通道或模型时写；镜头自己的 `models[档]`、`model` 先于片级 `models[档]`、`model` |
| `line` | 这一镜要说的台词；多人写 `A: 词 / B: 词`；无对白留空 |
| `prompt` | 提示词 |
| `reuse` | 复用已有片段的路径；有它就不提交，走 `ledger_submit.py reuse` |
| `reuse_tiers` | 可选：`reuse` 只用于这些档位（如接手来的草稿只算 `draft`），其余档位照常提交；不写即所有档位都复用 |
| `reuse_job_ids` | 可选：旧台账给这条片段记过的任务 ID（`audit_takeover.py` 的 `recorded_ids`），`reuse` 时一并入账，草稿接手后仍能按 ID 升成片 |
| `actors` | 未豁免白模场景且有人物的生成镜头**必填**：在场角色 id 数组（须属于该场选定白模板上的演员，无角色空镜写 `[]`），长度须等于 `actor_count` |
| `actor_count` | 未豁免白模场景的生成镜头**必填**：本镜在场角色人数非负整数，等于 `len(actors)` 且不超过选定候选的 `expected_actor_count`；提示词出现「数量词 + 人物名词」（中英文）大于 `actor_count + crowd_count` 时报 `PROMPT_HEADCOUNT_EXCEEDS_ACTORS` |
| `crowd_count` | 可选：本镜显式声明的群演人数非负整数（仅用于放行有群演镜头的提示词人数检查） |
| `previs_ref` | 未豁免白模场景的生成镜头**必填**：指向 `00_previs/` 内该场选定候选的干净灰模机位帧或站位板；非旁路工具（`stage_desk`／`blender` 等）须与该场选定文件摘要一致 |
| `camera` | 可选：对应白模选定候选上的机位 id，写了就必须存在于该候选的 `cameras` 中 |
| `screen_ui` | 提示词或台词涉及屏幕、界面、弹窗、手机、大屏等词时**必填**（缺填报 `SCREEN_UI_REQUIRED`）：只许写 `"none"` 或 `"clean_plate_post_replace"`（生成出纯色／暗屏干净板，后期贴 UI），写直出屏幕字报 `RAW_SCREEN_UI_FORBIDDEN` |
| `props_state` | 可选：跨镜关键道具进出状态 `{"in": {"<道具名>": "<状态>"}, "out": {"<道具名>": "<状态>"}}`（非对象或空键值报 `INVALID_PROPS_STATE`）；同场相邻在用镜头若后镜未标 `continuity_break: true`，前镜 `out` 与后镜 `in` 同名道具状态不一致即报 `PROP_CONTINUITY_MISMATCH:<prev>-><curr>:<prop>:<v1>!=<v2>` |
| `continuity_break` | 可选布尔值（非布尔报 `INVALID_CONTINUITY_BREAK`）：显式声明本镜与同场上一镜存在时间跳跃或刻意跳切，放行 `props_state` 跨镜交接比对 |
| `supersedes` + `changed_variables` | 重拍条目：替代哪一镜、改了哪一个变量 |
| `expected_action` | 可选：一句话预期动作摘要，Clean-Room 盲审的唯一剧情输入（不得粘贴提示词；未写时 `eval_harness.py post-gen` 要求 `--expected-action`） |

## 不变量

`python3 scripts/validate_shot_spec.py --project <目录>` 检查，全过才出镜头规格门：

1. 每个 beat 至少被一镜覆盖，或列在 `post_beats`；镜头不引用不存在的 beat。
2. 每句剧本对白都落在某一镜的 `line` 里，`line` 里没有剧本之外的词；有译文表时，译文与剧本原句、镜头台词三方对得上。
3. **参考图角色写在提示词开头**：第一句就交代每张参考图是谁／是什么；用到的参考都被提到，不提未声明的图号；参考文件真实存在。
4. 时长不超过通道卡上限；通道卡缺失、缺该上限或已过期，都算不通过，先去核实。
5. 重拍条目只改一个变量（`changed_variables` 恰好一项），同一镜不被两条条目同时替代。
6. `ratio` 与发布意图一致。
7. 空间、人数、参考出处、跨镜道具状态与专名约束（`validate_shot_spec.py --project` 与 `ledger_submit.py` 同查）：镜头按其声明的 `beat`／`beats` 前缀（如 `S3-B2`、`S1-B2B` → `S3`、`S1`）归属场景；场景未豁免白模时，`actors`、`actor_count` 与 `previs_ref` 必填且匹配选定板（非生成 `reuse` 镜豁免），提示词中英人数短语不得超出 `actor_count + crowd_count`；每张 `refs` 须经用户带码选定或来自 `00_previs/` 干净帧；涉及屏幕界面词汇必填 `screen_ui` 且禁直出文字；声明 `props_state` 的同场相邻在用镜头（未标 `continuity_break: true`）前后同名道具 `out`→`in` 状态必须一致（`PROP_CONTINUITY_MISMATCH`）；发布意图带 `lexicon` 时，镜头 `line`、`prompt` 与译文表不得出现禁用拼写变体（`LEXICON_VARIANT_FORBIDDEN`）。

8. SPEC v2.0 项目提交前另跑 `python3 scripts/eval_harness.py pre-gen --project <目录> --shot <镜号>`：时长与动作密度（`ACTION_DENSITY_OVERLOAD`）、`OPEN ON ACTION`、侧背视图与 180° 轴线、载具实体锚、反射与液态物性锁，以及命中的 L1 条件规则（未命中不挂载）；规则与错误码见 `harness-guardrails-and-eval.md`。它只拦结构与物理硬伤，不规定镜头数、时长或句式。

## 系列

分集目录放在系列目录下。身份参考、片级风格与通道从父目录继承：参考文件先在本集 `refs/` 找，再到父目录 `refs/` 找；规格用 `inherits` 指向父级规格。身份资产只在系列层锁一次，分集不重新生成身份。

## 译文表

对白与字幕是两种语言时，项目里放一张译文表（清单 `drama.translations`），按镜号列 `[原句, 译句]`。原句必须是剧本原话，译句必须等于该镜 `line` 里的词；改译文就改这张表和规格，不动剧本。用户在发布意图里决定某句字幕后期改写（如敏感词）时，该行写成 `[原句, 译句, 显示字幕]`：门只核前两列，第三列只用于烧字幕（`burn_chinese_subtitles.py --show 2,1`）；剧本和原句一字不动。
