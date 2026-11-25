# Harness 防护、双阶盲审与闭环（SPEC v2.0 落地）

> 规格来源：`00-target-spec-v2.md`（SPEC v2.0 唯一验收宪章）。本文件只承载工程约束：画质下限、跨镜锚点守恒与负面崩坏零容忍。主体动作、镜头调度、光影氛围、视觉风格、单镜时长随选题自由推理，门禁只校验结构槽位是否填齐，不规定镜头数、时长、节拍、画幅或运镜套路。

脚本：`scripts/model_gate.py`（Human Gate #1）、`scripts/harness_rules.py`（L0/L1 规则与三态 Pre-Gen 引擎）、`scripts/eval_harness.py`（Pre-Gen / 双轨采样 / Clean-Room 盲审 / 熔断裁决包 / 资产前置预留与计轮）、`scripts/mistake_book.py`（错题库事务治理与 Tier-1 回归）；错题库数据在 `mistake-book.jsonl`。`drama_setup.py init` 默认写入 `drama.sop_version: "2.0"`（无降级后门）；历史既有 v1 项目保持只读与既有测试兼容。

## 1. 七步流水线与 14 道门合流

| SPEC 七步 | `drama_next.py` 门（名称与序号不变） | 卡点与脚本 |
|---|---|---|
| Step 1 需求分析 + 条件错题预筛 + 全局规格与模型门禁 `[Human Gate #1]` | 1 `intake` → 2 `script_lock` → 3 `release_intent` | `model_gate.py render --project <dir>` 出四项必选菜单 → **STOP & WAIT** → `drama_setup.py model-gate` 落锁（拒绝默认/auto/随便，绑定实际执行模型与画幅）；`eval_harness.py pre-gen` 跑 L1 预筛 |
| Step 2 角色标准资产 `[Eval & Loop]` | 5 `identity` 的候选准备段 | 首次生图前若模型门禁未锁，`identity` 门先停在 Human Gate #1；资产自修用 `eval_harness.py asset-round --reserve / --settle` 原子预留计轮（≤2 轮重跑） |
| Step 3 场景空间 `[Eval & Loop]` | 5 `identity` 的空场主景板段 | 同上 |
| Step 4 白模与空间站位 `[Eval & Loop]` | 4 `previs`（先于 `identity`，零成本推导 `required_views`） | `render_whitemodel_board.py`；白模本地离线，不算付费生成 |
| Step 5 视觉资产与白模定稿 `[Human Gate #2]` | 4/5 的 `present → 带码落锁` | 高成本批量前唯一必停卡点；跨阶回退后只对变更项新图新码增量重签（旧展示与未改哈希原图一律拒收） |
| Step 6 分镜精修、视频与音频 `[逐镜双阶 Eval & 预算 Loop]` | 6 `shot_spec` → 7 `trial` → 8 `draft_batch` → 9 `shot_acceptance` → 10 `draft_cut` → 11 `approval` → 12 `final` | `ledger_submit.py submit` 锁内强制过 Pre-Gen 并编译注入命中 L1；`ledger_submit.py accept` 强制核验绑定同一摘要与题单的真实 Clean-Room Post-Gen `PASS`；`post-gen` 判 `FAIL` 自动将 take 置 `rejected` 并推进单变量自修或跨阶 `invalidate` |
| Step 7 全片连贯性终检交付 + 错题去重入库 | 13 `post` → 14 `delivery` | `assemble_cut.py --check-seams`（核验当前锁定资产哈希与非 `stale`）；`drama_setup.py post-done` & `deliver` 强核前置完成度与真实视频解码；新发错题经 `mistake_book.py add` 入库 |

**安静执行铁律**：除 Human Gate #1、Human Gate #2（含跨阶回退的增量确认）与预算熔断上报外，中间质检（Pre-Gen 拦截、Post-Gen FAIL、靶向自修、资产轮次）一律静默自修，不中途提问打断用户。

## 2. L0 常驻底线（严格 5 条，任何题材恒挂）

| ID | 底线 | 正向锁 + 残余负面项 | 二元判据（触红即 `FAIL`） | PASS 正例 | FAIL 反例 |
|---|---|---|---|---|---|
| L0-01 | 画质严重涂抹 / 灰模塑料感残留 | 自然光学微细节与稳定材质；`no clay/grey-box render residue, no plastic CGI smear` | 主体区域是否大面积涂抹糊化、灰模低模残留或相邻镜画质骤降？ | 浅景深背景虚化、胶片颗粒、高速运动的自然动态模糊、brief 指定的风格化画风 | 灰模质感渗入成片；人脸衣料蜡像塑料感；相邻镜从高清骤降为马赛克 |
| L0-02 | 人体解剖 / 手指畸变 / 误裁切 | 标准人体比例、五指分明、按景别保留头肩/全身；`no extra/fused fingers, no warped limbs, no unintended decapitation crop` | 是否多指/融手/断肢穿模、五官扭曲或非意图无头裁切？ | 手插兜或背影遮住手臂；brief 要求的颈下特写；挥臂瞬时拖影 | 握杯 6–7 指或手指融进杯壁；手臂穿透桌沿；全身镜切掉头部 |
| L0-03 | 无故黑帧 / 死帧 / 切镜爆闪 | 帧间曝光、白平衡连续；`no dead freeze frames, no unintended black flash or exposure strobe` | 首尾与切点 ±0.12s 是否有无动机的黑帧、冻帧、白帧爆闪或频闪？ | brief 设计的黑场转场；闪电/闪光灯且环境光响应；刻意定格片尾卡 | 切口残留 2–6 帧纯黑或冻帧；无光源变化时面部光影抽搐 |
| L0-04 | 伪文字 / 乱码水印 / 未授权字幕 | 非指定文字区干净无字；`no baked-in subtitles, no watermarks, no garbled AI text` | 是否出现模型烧录字幕、水印、乱码假字或未授权角标？ | 确定性后期渲染的字幕/HUD；用户批准并核对拼写的 Logo 卡 | 底部乱码字幕；海报/弹窗伪字；封面私加角标 |
| L0-05 | 时间轴物理崩坏 | 脚/物接触受力明确，主体数量与身份守恒；`no foot sliding, no teleportation, no sudden extra people or vanishing props` | 是否滑步、无切镜瞬移变形，或人数/关键持物凭空增减？ | 合法 `editorial_cut` 跳切；人物走出画框；遮挡物经过后的合规衔接 | 脚底打滑漂浮；凭空多出陌生人的手；持物凭空消失；载具单镜变型号 |

L0 在 Pre-Gen 核查三态动态 Schema（区分 `nbp`、`workflow_case`、`shot`，拒绝空对象、缺失/非有限 `duration_s` 与无主体槽位镜头）、跨镜服装/主光/左右站位锚点守恒、人数短语 ≤ `actor_count + crowd_count` 与禁索要烧录字幕，其余像素特征在 Post-Gen 判卷。

## 3. L1 条件规则（`IF [触发特征] THEN [Pre-Gen 约束 & Post-Gen 审片重点]`）

**未命中触发条件严禁挂载**：`harness_rules.trigger_map()` 具备中英文并列否定域感知（如「固定远景，无环绕、无镜面反射」绝不误挂）与非空槽位识别，未命中的 L1 严禁注入提示词或进判卷表；`sop_version == "2.0"` 在提交编译时真实注入命中 L1 约束并强校验 `l1_injected == triggered_l1_rules`。错题库里 `DEPRECATED` / `CANDIDATE` 规则同步从 Pre-Gen 与 Post-Gen 卸载。

| ID | IF（触发特征） | THEN Pre-Gen 约束（命中才注入） | THEN Post-Gen 审片重点 | Pre-Gen 错误码 |
|---|---|---|---|---|
| L1-01 | 同框可读人物 ≥2，或非否定对峙、追逐逃生、攻防 | 显式 `actors`/`actor_count`；每人独立参考槽与方位；写清运动矢量、施力者与受力者 | 逐帧核人数守恒与互动/追逐站位方向 | `CHASE_VECTOR_INVERSION:*` |
| L1-02 | 非空 `props_state` 或手部拿取/递交/进食特写、POV 手脚 | 锁 `props_state {in,out}`（跳态须 `continuity_break: true`）；写刚体接触边界 | 峰值帧五指关节与持握道具形态守恒 | `PROP_CONTINUITY_MISMATCH:*`、`HAND_PROP_DEFORMATION_WORDING` |
| L1-03 | 大角度环绕、过肩、正反打、转侧/背影调度 | 挂非正面锁定视图；白模锁机位不越 180° 轴线；写相机起止构图 | 拆分为原子题 `L1-03a`（侧背发色服装一致）+ `L1-03b`（视线与地标左右轴线守恒） | `MISSING_REQUIRED_ACTOR_VIEWS:<角色>:<视图>`、`AXIS_180_CROSSED_UNALLOWED`、`SPATIAL_ANCHOR_CONFLICT:*` |
| L1-04 | 夜景霓虹暗部、镜面玻璃反射、明暗大切换、液体/污渍物性 | 唯一主光方向与色温；反射轴向随载体运动；角色液态污渍写物性不变量 | 底色、污渍物性、暗部黑位与反射轴向自洽 | `LIQUID_STAIN_MATERIAL_LOCK_MISSING`、`MIRROR_REFLECTION_PHYSICS_CONTRADICTION`、`LIGHTING_ANCHOR_CONFLICT:*` |
| L1-05 | 手机/电脑屏幕、弹窗、大屏、可读招牌、HUD（否定式除外） | `screen_ui: "clean_plate_post_replace"`；暗屏干净底板留四角；文字交确定性后期 | 屏幕/招牌区域是干净底板或精确锁定图形 | `SCREEN_UI_REQUIRED`、`RAW_SCREEN_UI_TEXT_FORBIDDEN` |
| L1-06 | 整镜中英离散动作数超出时长预算、静态结果起镜、或有人物 ≥8s 长镜带事件残留（纯自然静物不挂） | 时长-动作密度匹配（<3s 限 1 个，4–5s 限 2 个，随秒数递增）；`OPEN ON ACTION` 写起止端点 | 预期动作终点在有效帧内真实完成且受力位移同向 | `ACTION_DENSITY_OVERLOAD:<n>_EVENTS_IN_<d>S`、`STATIC_RESULT_OPENING_INSTEAD_OF_OPEN_ON_ACTION`、`STATIC_AFTER_EVENT_LONG_DRIFT_RISK` |
| L1-07 | 可见口播、多人轮流、非中文发行、生造专名、统一配乐 | 同分段 ≤1 名说话者，句尾留白 ≥0.6s；口播语种 = 发布语种；`native_bgm: false` 只要人声环境声；专名挂 `lexicon` | 拆分为视觉口型题 `L1-07a` + 语种题 `L1-07b` + 吐字收音题 `L1-07c` + 禁碎BGM题 `L1-07d` + 本地 `ffprobe` 音画差 ≤0.25s | `MULTI_SPEAKER_IN_SINGLE_BEAT`、`DIALOGUE_LANGUAGE_MISMATCH:*`、`LEXICON_VARIANT_FORBIDDEN:*`、`NATIVE_BGM_CONFLICT_WITH_RELEASE_INTENT`、`DIALOGUE_TAIL_MARGIN_INSUFFICIENT` |
| L1-08 | 生成阶段后改角色身份图、场景主景板、白模站位或核心道具 | 波及白模与分镜标 `STALE`；旧肖像探针作废；增量 Gate #2 新哈希重签前禁跑批 | 视觉核对与新版锚点一致 + 本地强校验 `ref_sha256s` 与非 `stale` | `DOWNSTREAM_STALE_INVALIDATION_MISSING`、`INCREMENTAL_HUMAN_GATE_2_REQUIRED` |
| L1-09 | 有生成意图但四项启动要素未全部明确，或剧本未锁 | **STOP & WAIT** 显式门禁；平台推导画幅；付费前确认试价、余额回读与熔断上限 | 视觉核对真实动态非静图缩放 + 本地强校验 `requested_model == reported_model` | `HUMAN_GATE_1_NOT_CONFIRMED`、`MODEL_AND_SPEC_UNSPECIFIED`、`SCRIPT_NOT_LOCKED`、`MODEL_GATE_*` |
| L1-10 | 白模站位板、Blender 灰模或片场素模驱动视频 | 灰模不进首帧槽（先图像阶段材质升级）；电影语言复述相机轨迹；灰模只落 `00_previs/` | 材质脱离灰模感，站位与机位还原白模；交付目录零灰模底片 | `RAW_WHITEMODEL_USED_AS_FIRST_FRAME`、`CAMERA_PATH_NOT_RESTATED_FROM_PREVIS`、`PREVIS_OR_UNAPPROVED_TARGET_IN_FINAL_DIR` |
| L1-11 | 高度拟真人物参考、公众人物原型、严格审核通道、中途换 Provider | 最短镜跑通绑定参考哈希的真实结算探针；过滤通道禁用词；换通道做代表镜复现 | 视觉核对骨相肤质与锚点一致 + 本地 `ffprobe` 跨镜分辨率帧率一致 | `LIKENESS_PROBE_INVALIDATED_AFTER_ASSET_RELOCK` |
| L1-12 | 跨门框进出、车内外连贯剪辑、载具追逐/泊车、穿屏/匹配剪辑 | 载具实体锚（车型、配色、内饰、左右舵）每镜引用；穿门写两侧地面与门轴 | 载具外观内饰、穿门空间或穿屏内容前后物理守恒 | `VEHICLE_ENTITY_ANCHOR_MISSING` |

## 4. Pre-Gen Eval（生成前文本逻辑审校）

```bash
python3 scripts/eval_harness.py pre-gen --project <项目目录> --shot <shot_id>   # 读 shots.json 与清单
python3 scripts/eval_harness.py pre-gen --input <镜头/NBP/考题.json>            # 单镜头 / NBP / 错题考题
```

`ledger_submit.py submit` 在门禁与锁内 `prepare` 自动执行 Pre-Gen 并把提示词摘要、错题库摘要与 `triggered_l1_rules` 写入 take。

## 5. Post-Gen Clean-Room 独立视觉盲审

- **物理与上下文硬隔离**：`run_judge()` 在项目目录之外的临时 `clean_room` 目录以 `cwd=str(bundle)` + 净化环境变量启动独立无状态进程；所有入包图片经 PIL 重解码重编码剥离 PNG `tEXt`/EXIF 元数据，入包视频经解码校验并 `ffmpeg -map_metadata -1` 剥离容器标签，杜绝伪装文本与隐藏提示词泄露；`assert_clean_room_isolated()` 拦截中英文历史结论词与短片段抄袭（CJK 8 字 / ASCII 20 字符）。
- **双轨采样**（`eval_harness.py sample`）：
  * `--track dual`（支持原生视频流时默认）：低码率 `360p` 审片流 `<stem>.lowrate.mp4` + 首帧、尾帧、动作峰值帧、切点前后帧（项目模式自动解析同档上一镜 `approved` 尾帧）高清 PNG + 锚点并排板。
  * `--track contact`（仅支持图像输入时）：`2 fps` 均匀抽帧 + 首帧 + 尾帧 + 动作峰值帧带时间戳编号序列拼图 `<stem>.contact.jpg`（多输入同名视频按序号+哈希独立分目录防覆盖）。
- **轻量人工回传入口**（纯提示词模式）：`python3 scripts/eval_harness.py post-gen --clip <成片或截图> --expected-action "<一句话>" --anchor <基准图> [--l1 L1-02]`。
- **防覆盖与防盲猜**：默认调用 `agy --model gemini-2.5-pro --effort high --disable-slash-commands --output-format json --json-schema <schema> --add-dir <clean_room>`（可通过 `AGY_MODEL` 环境变量覆盖模型）；裁判非零退出码、重复题号、缺失帧号/时间戳定位证据或当前介质不可观察项（如静音拼图遇 `L1-07b` 音频题）绝不签 `PASS`（有 `FAIL` 判 `FAIL`，否则判 `ANALYSIS_SKIPPED` / `ANALYSIS_INCOMPLETE` 退出码 4）；`--mock-verdict` 显式标 `mock: true` 且在正式 `accept` 中硬拒收。

## 6. 原子级 Yes/No 判卷表

判卷表 = L0 五题 + 活跃命中 L1 原子视觉/听觉子题（每题配 1 个 PASS 正例与 1 个 FAIL 反例，L0 见第 2 节表格）：

| 题号 | 原子是非题 | PASS 正例 | FAIL 反例 | 自修路由 |
|---|---|---|---|---|
| L1-01 | 可见人物数量守恒且追逐/互动方向符合预期动作？ | 追击者在后逼近、逃生者在前；有意护送引路者在前 | 逃生戏反派在前替人开门；凭空多出第三人 | `cross_stage_rollback_stale` |
| L1-02 | 峰值帧五指关节解剖正常且持握道具形态边界清晰守恒？ | 五指自然握持、接触面刚体边界清晰 | 多指粘连、手穿桌沿、道具中途变形换色 | `slow_or_split_shot` |
| L1-03a | 转侧/背影时发际线、发色与服装背面与基准锚点图一致？ | 正面转背影发色、领口剪裁与锚点一致 | 正面棕发转背影变黑发；环绕后换脸换衣 | `boost_identity_anchor` |
| L1-03b | 人物视线与背景固定地标的左右空间关系连贯、无突兀越轴？ | 过肩/环绕中左右方位平滑过渡、视线对位准确 | 无过渡时左右站位或背景门窗突然镜像翻转 | `cross_stage_rollback_stale` |
| L1-04 | 底色、液体污渍物性与主光方向稳定，反射方向与位移自洽？ | 墨渍仅留浅灰围裙表面随布料移动；反射同步同向 | 墨渍蔓延至皮肤或变色；倒影与真人反向脱节 | `boost_identity_anchor` |
| L1-05 | 屏幕/招牌区域为无伪字干净底板或精确锁定图形？ | 暗屏自然反光无乱码字，四角清晰 | 屏幕自发生成残缺假英文或招牌笔画融化 | `post_clean_plate_fix` |
| L1-06 | 预期动作关键终点在有效帧内真实完成且受力位移同向？ | 转身奔跑或破门后退在片内完整发生 | 全片停留在蓄势/原地竖拇指，预期动作未发生 | `slow_or_split_shot` |
| L1-07a | 同一发言时刻仅单一目标说话者张嘴发声（无双人同开口抢话）？ | 发言者口型自然、倾听者安静闭嘴 | 双人同时张嘴抢话，或全程闭嘴硬配画内台词 | `post_clean_plate_fix` |
| L1-07b | 音轨中说话人声的语种与目标语种一致？（需音轨） | 全段保持目标语种自然发音 | 英文台词吐出中文或夹杂伪外语乱音 | `post_clean_plate_fix` |
| L1-07c | 音轨台词吐字清晰完整、句尾收音自然未被硬截断？（需音轨） | 关键台词清晰可辨、句尾完整无截断 | 台词含混糊音或句尾最后词被切镜硬截断 | `post_clean_plate_fix` |
| L1-07d | 音轨背景保持干净环境声、无未经请求的杂乱原生 BGM？（需音轨） | 仅干净环境底噪，人声主次分明 | 自发混入嘈杂碎配乐盖过人声 | `post_clean_plate_fix` |
| L1-08 | 人物与场景外观与当前新版基准锚点图一致、无旧版特征混入？ | 五官发色与新版锚点吻合（另由本地强核哈希） | 仍呈现已作废旧版发色、旧服饰或旧陈设 | `cross_stage_rollback_stale` |
| L1-09 | 待审视频呈现真实三维动态而非单图缩放平移或黑屏凑时长？ | 主体具自然帧间动态（另由本地强核模型一致） | 单张静图机械放大平移或黑屏冻帧凑时长 | `cross_stage_rollback_stale` |
| L1-10 | 交付画面已完成材质渲染脱离 3D 灰模素模质感且站位合理？ | 皮肤衣料材质写实细腻，无灰盒网格残留 | 直接残留 3D 灰模素模人偶或无纹理几何块 | `cross_stage_rollback_stale` |
| L1-11 | 人物面部骨相、眼距与肤质颗粒同身份基准锚点图一致？ | 正侧骨相紧贴锚点（另由本地强核分辨率一致） | 骨相漂移成另一人或出现假脸磨皮断层 | `boost_identity_anchor` |
| L1-12 | 载具车型配色内饰、跨门框空间或穿屏画面前后物理守恒？ | 车辆涂装与方向盘全程一致；沿门洞连续通过 | 敞篷中途变硬顶；未过门洞直接穿墙换景 | `cross_stage_rollback_stale` |

## 7. 靶向归因自修闭环与双重预算熔断

- **自动状态流转**：项目模式下 `eval_harness.py post-gen --project <dir> --take <id>` 判 `FAIL` 时自动在锁内将 take 转为 `rejected`、写入 `drama.repair_queue`：命中 `cross_stage_rollback_stale` 自动触发 `apply_invalidation` 作废源头与下游并打开增量 Gate #2；命中动作/锚点自修则生成单变量重拍计划（`prompt_only` 置 `AWAITING_CLIP_RETURN`）；触及熔断则当场落盘 `qc/escalation_<shot>_<tier>.md`。
- **局部上限**：同一根镜（跨档累计超出各档首跑的重跑数）自修重跑 ≤ 2 轮（`preparing` 在锁内原子预留名额）；单个角色/场景资产用 `eval_harness.py asset-round --reserve / --settle` 同样 ≤ 2 轮，触及上限当场落盘 `qc/escalation_asset_<id>.md`。
- **全局上限**：整片**跨全档位（`draft` + `lowres` + `final`）累计视频重渲染次数** ≤ `min(5, floor(活跃生成镜头数 × 30%))`（各档首次生成不计重跑，重跑跨档累加；`drama.spend_history` 追加记账，标记 `STALE` 或替换/移除镜头永不冲销已发生消费；仅无任务 ID 的前置余额拒单释放预留）。
- **熔断裁决包**：抽取绑定同一 `clip_sha256` 的真实问题帧截图与 `.cleanroom.json` 根因；若供应商在产出画面前即失败，显式标 `NO_FRAMES_PRODUCED_BY_PROVIDER` 并列终态任务凭证。

## 8. 跨阶回退、全依赖链 `STALE` 与增量重签

- `drama_setup.py invalidate --project <dir> --stage character|scene|previs --target <id> --reason "<根因>"` 在单锁事务内沿 `character/scene → previs_scenes → 根镜与修订链 → 含 preparing 与历史 ref_sha256s 的 takes` 标 `STALE`，立即作废旧 `presentations` 与旧粗剪批准，并记录 `invalidation_id` 与旧资产哈希 `old_sha256s`。
- 增量重签强制要求：① 使用作废之后新生成的 `present` 决策图；② 严禁对作废目标使用 `--waive*`；③ 新锁定的资产/白模 SHA-256 必须与 `old_sha256s` 不同（原旧图重签报 `INVALIDATED_SOURCE_NOT_UPDATED`）；④ 逐目标核销，未重签目标继续保持阻断。
- `assemble_cut.py`、`has_reviewed_take`、`draft_job_id`、`confirm --kind draft-cut`、`post-done` 与 `deliver` 全量复核当前锁定资产实时 SHA-256 与非 `stale` 状态；SPEC v2.0 禁用 `impact --decision keep` 或旧片 `reuse` 洗白强制作废。

## 9. 错题库事务治理与成本分层验证

- `mistake_book.py` 在排他文件锁内执行写回，内置零私域词（支持 `SEEDANCE_PRIVATE_BLOCKLIST` 与外部词表注入并脱敏报错）：写回依次过 **全量 ACTIVE 冲突检查（含同 ID/同规则）** → **规范化考题指纹去重（同内容考题仅增 `hit_count` 不重复落库）** → **语义去重** → **可执行检测器与考题准入（支持声明式 `detector`，缺检测器或考题暂存为非活跃 `CANDIDATE`）** → **写盘前内存全量 Tier-1 回归事务（任一失败回滚不落盘）**。
- **Tier-1**：`python3 -B scripts/mistake_book.py validate && python3 -B scripts/mistake_book.py tier1-run`（16 道考题 100% 精准拦截/放行，0 warnings）。
- **Tier-2**：对真实正常叙事片与历史故障废片执行独立 `agy` Clean-Room 盲审闭环，验证正例 `PASS`、反例 `FAIL` 并真实驱动项目状态流转。
