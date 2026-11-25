# Production and QC

## 成片标准

用户说“做视频/成片/最终 MP4”时，Prompt 不是交付物。必须走到可播放文件并用真实命令验证。

## 工作区

复杂项目可复制 `templates/stage-plan.md` 当制作看板：按当次目标删行，写清每块吃什么、落什么、看什么像素；不要把它当成审批门禁。下列工作区是候选结构，只创建本次 production class 真正使用的目录与记录：

```text
video-project/
  task_plan.md
  findings.md
  progress.md
  docs/
    brief.md
    asset_manifest.json
    storyboard.md
    shotlist.json
    prompt_packages/
    shot_selects.json
    generation_log.md
    qc_notes.md
  assets/
    images/{references,generated,approved}/
    videos/{source,generated,approved}/
    audio/{narration,dialogue,music,sfx}/
    subtitles/
  renders/
```

原始素材只读；输出到 sibling 或 `renders/`。

## 阶段责任

先由 brief 声明 `production_class / block_mode / applicable_stages / applicable_qc_dimensions`。未触发的阶段整行删除，不写虚构的 N/A；一旦声明某阶段或事实维度，就必须留下可审计证据。

| 阶段 | Owner | 适用时的核心证据 |
|---|---|---|
| Brief/story/product | 本 Skill | brief、目标、lane |
| Assets/continuity | 本 Skill + selected image provider | 本次需要的 asset manifest、approved refs |
| Storyboard/shotlist | 本 Skill | 决策镜需要的 panels、shot IDs、in/out |
| Prompt package | 本 Skill | provider-neutral contracts |
| Generation | 单一 provider adapter | request/job/result/local files |
| Selects | 本 Skill/剪辑 | 每 take in/out、选择/拒绝理由 |
| Existing-footage edit | `precision-video-editing` | EDL、render report |
| Motion overlays | `videoedit` / `hyperframes` | verified composition/render |
| Voice/captions/music | 对应 audio/TTS/ASR skills | 仅对存在的声音/字幕职责保留独立资产与时间线 |
| Final assembly | HyperFrames/FFmpeg/剪辑 Skill | final MP4 |
| QC | 本 Skill + media probes/vision | technical + visual notes |

## Asset manifest

每项只记录适用字段：ID、kind、canonical name、version、approval status、source hash/path、provider reference、purpose、local path、duration/ratio、rights/attribution、qa status、correction source。不存在的人物、道具、场景或音轨不建占位项。

生成结果默认 candidate。错误或旧版不得继续作为参考。

多镜项目需要中断恢复、父镜重拍或接受实际剧情偏差时，使用可选的[恢复台账与检查器](sequence-resume.md)。它复用本节的镜号、source take 与 QC 记录；单镜或只交剧本文本时不增加此表。

## Prompt log

记录当前任务实际使用的 user direction、production class、reference roles、continuity locks、camera/beat map、negative constraints、post responsibilities、provider adapter、model/schema time、request path、result path；无关槽位删除。

## Shot selects

把每次生成当 take，而不是整段真源。每个保留/拒绝 subshot 记录：

- source take/path；
- in/out；
- performance/action/dialogue reason；
- continuity status；
- audio status；
- rejection reason。

一个 take 不必承担整场戏；选择相容的最好片段再组装。

每个 take 只承认完整回放确认过的 `usable_in/out`。首尾未进入状态或已经开始崩坏的部分不进 select，宁可缩短区间也不把不稳定段落交给下一步。

只有通过区间内的帧与末态才能登记为 `state_out` 或 relay frame 并交给下一块。失败 take、未回放段落和剧本设想的末态不得接力；整条只写「成功」而没有 in/out 与理由的记录，视为未验收。

## 声音（存在音频职责时）

- narration、dialogue、SFX、BGM 分开；
- 原生 audio 能力 live 校验；
- 复杂对白可独立 pickup；
- 中文高质量配音用当前已配置 TTS provider，长文/多角色用专用 dubbing 工作流；
- 配音生成后再做时间戳/字幕；
- 音乐在对白下按听感和 loudness 调整，不能只凭默认 dB。
- 口型回归脚本主动覆盖需要双唇闭合的词、口播数词，以及带短否定和停顿的句子，分别检查闭合、韵律与停顿自然度。

## 字幕与精确文字

精确中文、CTA、价格、Logo、法律/品牌文案由确定性后期生成。FFmpeg 缺 `subtitles/ass` filter 时，不循环调语法；使用 `bash {baseDir}/scripts/run_burn_chinese_subtitles.sh --help` 验证 OpenCV/PIL fallback 环境，再调用该 wrapper 烧录字幕并 mux 音频。wrapper 会清理污染的 `PYTHONPATH/PYTHONHOME`，避免 macOS 上 Python ABI 串用。

## 多 take 与本地合成

- 保持 deterministic filenames；
- 缓存键必须包含 brief/storyboard/source/prompt hash，不能只按 `seg_001.mp4`；
- concat 前统一 codec、尺寸、fps、音频；
- 不用 modulo 循环补足源视频；更换 source window 必须仍在 approved 子区间内；hold 或重复素材须符合批准 brief，不能只明示就擅自改变交付形式；
- 合成后比对视觉、音频与目标 timeline 时长。

## 技术 QC

最低：

```bash
ffprobe -v error -show_streams -show_format -of json renders/final.mp4
ffmpeg -v error -i renders/final.mp4 -f null -
```

检查：container/codec、尺寸/比例、fps、时长、音轨、文件大小、完整 decode。

## 视觉/听觉 QC

完整播放对所有成片适用；其余检查只在对应对象存在时启用：

- 多镜头/长片需要的 contact sheet；
- 存在 cut 时检查前后帧；
- 使用关键帧/reference 时做对照；
- 完整播放；
- 有字幕或平台移动端交付时检查可读性；
- 按已声明对象检查人脸/手/产品/UI/文字/水印/黑帧；
- 有音频时检查声画同步、爆音、对白清晰度和音乐遮挡。

## 分轨审片

任务返回成功只说明生成完成，不说明素材可剪。静态预览与缩略图只能证明构图、身份和明显状态，不能证明完整动作、声音或可剪区间。按下列通道依次过一遍，每条通道只判它能证明的事；本次不存在的对象整行删除，不写 N/A。

- 候选筛选：看缩略图或关键帧，只标构图、身份、明显状态是否值得进入完整回放。
- 完整回放：确认身份、接触点、物理、表演与节奏；记录问题时间码。
- 静音只看画面：判断动作是否成立、有无漂移与穿模；仅对视觉承诺的剧情/动作判断静音可读。声音主导作品不要求静音完整理解，画面动作仍须成立，音画关系另在合看通道核验。
- 只听音频：判断台词清晰度、环境声与音乐是否互抢、有无爆音与断点。
- 音画合看：判断说话者、口型、动作与声音落点是否对齐，环境声是否随画面变化。
- 目标比例与手机小屏复核：字幕可读性、安全区、首个可读时刻在实际观看尺寸下是否仍成立。

每条通道写下发现与证据时间码，再回到「适用维度质检矩阵」定位最早需修真源。没有可播放的本地文件与完整 decode 时，任何通道都不构成成片验收结论。

## 付费批量门

只有授权允许多次生成时，批量前才生成最高风险代表镜头和获准的低成本预览，通过后再扩批。单次/失败不重试时，直接验获准规格的那一条；不为预览、可靠性评估或返工自动增加付费任务。POST 超时先查任务，不重复花费。

不要用一条惊艳样片证明模型可靠；在明确获准的同类多次运行中记录关键约束通过情况与失败类型，把最佳样片和常态分布分开报告。

## 适用维度质检矩阵

在生成前声明 `applicable_qc_dimensions`，只对存在的对象与交付职责判 `pass/fail/needs_review`；无关维度直接删除，不伪造证据或 N/A。技术 decode 与完整播放始终是成片硬门。每个**适用**维度记录证据帧/时间码和修复真源；总评不能掩盖失败或待核，不得把缺少证据写成 pass。

| 维度及触发条件 | 可观察验收 | 失败回到 |
|---|---|---|
| 人脸/身份；有可识别角色或身份连续性时 | 先确认当前批准标准，再与批准身份并排比对可见骨相、眼距、发际线及跨段角色区分；仍要求精确身份而必要特征被遮挡时记 `needs_review`。若用户已明确接受选定人物加墨镜，按新合同检查可见鼻唇、轮廓和眼镜稳定，不以旧的眼部比对门阻塞新目标，也不宣称隐藏的身份特征已核验 | 当前批准的 character master / face lock |
| 服装/状态；声明服装或可变状态时 | 先核指定服装是否真正迁移，再查剪裁、纹理、领口、袖口、层级和配饰的时序；源衣服稳定不算替换成功，局部头巾符合不能抵消衣服失败；伤口、污渍只按计划变化 | wardrobe variant / 状态机 |
| 道具恒存；道具承担动作/证据/连续性时 | 外形、尺度、材质、持有者、左右手与破损状态不消失/复原 | prop sheet / 道具时间线 |
| 空间与光；跨镜空间/轴线/光向需连续时 | 门窗家具、轴线、视线、主光方向、曝光与色温可接 | scene bible / topology / shot ledger |
| 运动物理；存在运动、接触或环境响应时 | 起因、负载、接触、重心、惯性、余势和环境响应可见 | action chain / camera clause |
| 口型/台词；有可见说话者与同步对白时 | 口播语言与 brief 的目标发布语言一致（如出海英文剧不得出现中文口播）；说话者正确，音素闭合、停顿和表情对齐 | `audio.dialogue` 语言（prompt-contract.md「语言契约」）/ dialogue pickup / lipsync / TTS timing |
| 画面伪影；所有生成/编辑画面 | 无拓扑撕裂、闪烁、身份融合、伪文字、水印、黑帧 | keyframe/source / 局部修复 / deflicker |
| 声音层级；有音频交付时 | 适用的对白、拟音、环境与音乐层清楚、同步且无爆音 | 实际存在的音轨与混音真源 |
| 平台交付；用户要求发布/平台成片时 | 已选平台的画幅、安全区、字幕、封面/标题、码率与 AI 标识符合本次 live 规则 | selected-platform export / deterministic post |

通过意味着能指出证据，不意味着“模型返回 done”。任何已声明身份、空间、道具、状态、文字、声音或平台事实失败时，不用后期包装掩盖，先回最早真源修复并复测同一镜头。

## 增量迭代与质检

- 验证档只验画面质感/运镜与分段衔接；故事完整度不属于该档，但正片仍走完整 QC。
- 场景换角度同时验两件事：新角度带来新的深度信息，原锚点相对位置不变；只过一项都不放行。
- 依赖视觉叙事的分镜表在出图前做静音测试；访谈、解说等声音驱动形式按自身合同验，不强求无声完整可懂。
- 资产必须在实际动作、景别、地点及必要同框组合里验证；经验性的固定测试次数只作参考，不作硬门。
- 若一次生成对应一个文件且失败件完整保留，可把镜头目录文件数当迭代重量；它只用于复盘排序，不代表金额或质量。
- 同一镜头修改到 `15–20 次` 仍不收敛时，优先换镜头构造；迭代重量只在上述记录条件成立时使用，二者都不进入验收门。
- `prompt adherence` 与画面观感分开验：逐项查具名物体、颜色、运镜、事件顺序；精确屏幕文字仍由确定性后期负责。
- 节奏先在剪辑/预览层改切点和镜头时长，再决定哪些镜头必须重生成；特定平台实时重算能力标 `TODO_VERIFY_LIVE`。
- 成片增加一遍 cut-only 审片：不评单镜漂亮程度，只查每个切点的运动、光线、情绪与时长交接。

## 防止误验收：先观察、再对照

生成段与最终母版都执行；本节扩展既有分轨审片，不另建一套管线。

- 审片先给中性任务：描述谁在何处、对谁做了什么、物体如何移动及可见时间码；再对照批准 brief。不要先告诉审片者“这里已经完整过门”或“这是不是荒谬穿帮”。提示词、脚本、先前 PASS 和批评性结论都不是像素证据。
- 结论分为 **观察 / 推断 / 未核实**。一张静帧不能证明速度、动作顺序或全程 POV；缩略图看不清的肢体不能被断言为多手；蒙太奇逆叙不能仅凭重排就叫反向播放。ASR 文本不能独自证明听感或有无幻听。
- 每个核心剧情事件复用 QC notes 记录：批准 brief 版本、期望事件、实际可见事件、`source_take/source_hash/usable_in/out`、`timeline_in/out`、证据路径、`actual_playback` 的方式/覆盖区间和 `pass/fail/needs_review`。未实际连续回放时直写未回放；工具无法播放则待核或请求人工回放，不让 contact sheet 代签。播放器 `ended`、无 error、帧总数或稀疏 `requestVideoFrameCallback` 记录只证明对应播放/呈现事实，不证明每个解码帧都已被视觉审查；分别写明回放覆盖、实际检查帧和尚未核实的内容。
- 合成前核对 EDL/concat/构建脚本实际读取的文件及裁切边界。只批准了子区间，就不能拿整条原 take 拼接或抽另一时间点接力；回闪、替换镜和重新 retime 同样检查。渲染后绑定 `master_hash`，在最终文件重新查对应动作及接缝，防止审 A 交 B。
- `technical_status`、`visual_status`、`brief_status` 分开记录；技术通过不抵消叙事、物理、表演或形式失败。任一适用门失败即不能交付合格正片；证据不足则 `needs_review`。非阻塞瑕疵须说明不影响什么，而不是为省费用自行降级。
- 新证据推翻旧验收时，**撤回旧 PASS** 并追加更正与证据；保留旧报告可追溯。不得覆盖原批准 brief 或把计划动作改写成“已发生”，用更新文档为错误成片补票。

## 条件防错门：按本作承诺触发

| 触发条件 | 可见失败与拒收理由 | 修复与复测 | 不误伤的边界 |
|---|---|---|---|
| 追逐关系、逃生或攻防 | 静音回放显示目标始终在前领路、替主角开门、主角尾随，而本作承诺的攻击/逼退/封路未发生 | 把角色运动矢量、目标与受力者写回 `characters/action/continuity`；先核污染首帧是否含跟随对象，必要时回关键帧，不只加“更恐怖”；重测一次完整攻防与主角应对 | 有意护送、猎人追猎物、喜剧追逐可以成立；但不能事后编“护送反转”免除前文承诺的危险 |
| 人眼 POV 的肢体与道具归属 | 自身多出肢体、另一个同制服背影被误作自己、腕戴物变手持棍、道具无接触交换就复制/换手 | 在 `characters/references/continuity` 记录身体/屏幕左右、可见手数、持握与腕戴位置；逐帧追踪疑似肢体从谁身上进入，确认后回最早坏帧修；已错的末帧不得续 | 不要求手和道具每帧都可见；合理遮挡、自然摆臂、主角低头看腿、镜中倒影或他人伸手不自动算第三人称/多肢；但各自须可追踪 |
| 连续时间的越界路径 | 虽出现门框/遮挡，摄像机仍穿玻璃/墙体、未跨越界面即换地点，另一侧地面/朝向无法连接 | 在 `scene/action/camera/continuity` 锁两侧地面、门轴与可达路线；回放接触→开口→越界→落点，不够可读就拆动作；遮挡只藏剪点，不能藏不存在的路径 | `editorial_cut` 可省略过程，但须有可读的时间/空间桥；不得再声称无间断一镜到底；奇异空间需前文规则与可见转换支持 |
| 承诺惊吓、搏斗或快速运动 | 怪物只站着摆姿势、威胁动作没有逼近/侵入/撞击/封路及回应，或快跑被后期拖成慢走；音效很响不等于视觉动作成立 | `action` 写预备→威胁变化→主角闪避/受力→余势；一段只验证可承载的主事件；按实际播放测距离、反应与节拍；`retime` 同核源/输出时长和速度方向，正常速度合看，不用加速掩盖缺失动作 | 氛围、凝视、静止恐怖不强加跳吓；惊吓效果只能给带依据的观看判断，不能承诺人人害怕或固定次数；允许合法慢镜但不能偷换快节奏 brief |
| 关键反转依赖前文事实 | 结尾只靠新字幕/广播宣布新身份，画面没有相应线索、动作或状态变化；必要道具已漂移却继续用它作证 | 对照伏笔→主角行动→结果，修最早缺失视觉证据或提出改案；声音可以揭示未知信息，不能否定可见事实来替坏镜辩解 | 声音主导的作品按原合同验；不强求所有故事静音即可完全理解 |

上述修复按最早失败层选择一个变量做对照。诊断不等于批准重拍、付费或改变用户 brief。

SPEC v2.0 项目把上表与 L0/L1 规则对齐为原子级 Yes/No 判卷表（每题一个 PASS 正例、一个 FAIL 反例），由 `scripts/eval_harness.py post-gen` 在 Clean-Room 隔离目录里交独立视觉模型判；送审媒体按双轨采样（`2 fps` + 首/尾/动作峰值帧带时间戳拼图，或低码率审片流 + 高清关键帧）。判卷是证据之一，不替代本节的先观察再对照与完整回放；规则、采样与自修路由见 `harness-guardrails-and-eval.md`，错题回写与回归见 `scripts/mistake_book.py`。

## 时长与形式诚信

- 从实际时间线按独占区间核对 `new_motion / still_animation / reused_footage / hold_or_black` 的来源与时长，转场重叠不双计；叠字层不单计底片时长。镜头数、文件数、总秒数都不等于可用剧情覆盖。
- 声明不等于批准：已承诺动态视频/连续 POV，余额不足时不得自动换成静图推焦、循环、碎片回放或黑屏凑满。先按 [预算门](provider-execution.md) 停提交，报告可用范围、缺口与选择；用户同意缩短、补预算或更换形式后才能按新合同完成。可交预览，但不能称原要求已完成。
- 不是禁止静帧、闪回或黑场：原 brief 已选择的动态漫画、定格、记忆重构、必要静默/黑场均可用；每段须贡献信息/情绪/结构、保持可读节奏并按该形式验，不设置跨题材统一比例或秒数。确定性字幕/合成/VFX 也不等于降级；问题是用不相符形式替代缺失的关键行动。
- 快速回闪、抖动和红光不能代替剧情推进；按实际播放检查刺眼、难定位和不必要的高频闪烁，优先减少突变而非只加警告；未做专门检测不得称无光敏风险。

边界案例见 [templates/delivery-gate-cases.json](../templates/delivery-gate-cases.json)：只作合成情境的规则回归与审查输入，不是已生成视频、模型行为得分或观众效果证据。

## 交付前阻断门

交付动作本身被这四项阻断，不等用户抱怨才补 QC。四项都做完才允许签 PASS：

1. **并排比对**：每段抽首帧、中帧、末帧，与该角色的批准身份参考并排放在一起看；不是「看过生成结果」，是两图同屏对照骨相、眼距、发际线、服装层级与道具归属。
2. **完整播放**：从头到尾播一遍本次要交付的那个文件，不是 contact sheet、不是缩略图、不是别的 take。
3. **`ffprobe` 回读**：对交付文件实跑 `ffprobe -v error -show_streams -show_format -of json`，回读时长、音轨数、分辨率，与批准规格逐项对；`ffmpeg -v error -i <file> -f null -` 完整 decode 通过。
4. **逐段模型核对**：每一段列出 `requested_model / reported_model`。不一致的段单独标出，按实际执行模型重新判画质基准，不按点名模型宣称。

任一项未做，交付里必须写「视觉未验」并说明缺的是哪一项，不签 PASS。四项齐全但其中任一项失败，是 `reject` 或 `needs_review`，也不是 PASS。

### 要的动作 vs 实际演的动作

逐拍列表对照，一拍一行，不合并写「动作基本对」：

| 拍 | 要的动作 | 实际演的动作 | 判定 |
|---|---|---|---|
| 1 | 推门冲入 | 手扶门把蓄势，门未推开 | fail |
| 2 | 破门而入 | 门关着，人站在门前等待 | fail |

「蓄势」不算「泼出」，「站在门前」不算「破门」：动作的可观察终点没发生就是没发生，不用「氛围到位」抵扣。每个 fail 回 [节拍预算](prompt-compiler.md#节拍预算) 查是不是一次塞了太多拍，再按最早失败层单变量重测。

承诺复现源片原动作/音乐时，复用上述逐拍表记录源片与结果的同秒对照，覆盖早、中、晚、真实末态并在高风险动作附近加密；源/结果帧率不同时按时间戳对齐，不按相同帧号比较。关键动作、脚步、手势及末段身份分别判定，再完整音画合看核对原音乐与节拍。若用户已批准 retime，先绑定批准的时间映射而非直接比较同秒；没有批准则不能靠裁掉真实舞步、变速或用站立/走路替代来过门。

源片要求同时保留动作、背景与镜头时，分开判定这三项：动作相似不证明手机滚转/末尾俯拍复现，末帧在海边也不证明开头和中段一直沿用原背景。按同一时间戳查看开头、转换点和结尾；快动作短片可从每 0.2 秒抽样起步，在疑似问题处加密，保存实际检查帧清单，不把抽样称逐帧全检。旋转画面先区分机位滚转与人物身体姿态，不能由静帧方向误判动作。

以下载文件的 ffprobe 结果为准，不用任务元数据中取整的 duration 判定截短；UI 的分辨率档也不保证实际宽高或比例。独立比对源/输出宽高与显示比例，禁止拉伸、裁切或填边来掩盖未获准的构图变化。播放器 decodedFrames 与文件帧数是不同统计，不能拿前者覆盖媒体探测值。

用户要整个原片时，分别记录源视频、原生生成视频及后期文件的视频流/音频流/容器时长。完整原片输入不证明输出覆盖了所有原动作；帧数差受帧率影响，原生时长较短也不能单独证明具体源帧被遗漏，须查时间映射和真实末态。接回较长原音轨可能延长容器时长，但不会补出缺少的动态画面，不得据此宣称完整视频已还原。原音轨无损回接与 PCM 核验用 [post-production.md](post-production.md) 的原片音轨分支，音频通过不抵消视觉或 brief 失败。

## v7 连续观看与四栏判定

机检（`eval_harness.py media-qc`）和抽帧都只是证据之一。每个要交付的文件按三种方式各看一遍，缺哪一种就如实写哪一栏 `needs_review`：

1. **连续观看**：用播放器从头到尾不跳播一遍，正常速度；记录问题时间码。
2. **多帧接触表**：按固定间隔加首、尾、动作峰值帧拼成一张接触表，与批准身份参考并排看。
3. **实际听音**：戴耳机或外放把声音完整听一遍——对白是否清楚、说话者对不对、有无合成嗡鸣、字幕是否与声音同步。

四栏判定，每栏只写 `pass`／`fail`／`needs_review`／`not_applicable`，并附证据（时间码、帧路径、实测数值）：

| 栏 | 看什么 | 主要证据 |
|---|---|---|
| `technical` | 解码、帧率 CFR、流结构（已剥 `mjpeg`）、实测分辨率与披露一致、时长、响度与真峰值 | `ffprobe`、完整 decode、`ebur128` |
| `visual` | 身份、手与肢体（无凭空多手、遮挡肢体未被驱动）、道具恒存、空间轴线、伪文字 | 连续观看 + 接触表 |
| `audio` | 对白清楚且说话者正确、无 `>= 0.5s` 合成嗡鸣、无机器读对白、字幕互斥与同步；静帧或无音频职责时为 `not_applicable` | 实际听音 + stem |
| `brief` | 批准剧本的动作与台词逐拍发生；`creative_mode` 的硬项成立 | 「要的动作 vs 实际演的动作」表 |

- `audio=not_applicable` 仅限静帧交付（`images_only`）或明确无音频职责的无音轨镜头；预期有声（如 `audio_route` 为 `keep_native` 或 `replace_dialogue`）却缺音轨属于 `AUDIO_STREAM_MISSING`，判 `fail`。
- 宿主没有音频播放或分析工具时，有声交付的 `audio` 栏写 `needs_review` 并说明缺什么工具，**不得伪造 PASS**；总评随之不能是 PASS。
- 所有**适用**栏（非 `not_applicable`）全部 `pass` 才签总 PASS；任何一栏 `fail` 即拒收，任何适用栏 `needs_review` 即待核。
- 节奏类偏差（ASL、hold、气口）按 [cinema-vs-short-drama.md](cinema-vs-short-drama.md) 只出编辑建议，不单独构成 `fail`，除非违背了用户显式锁定的一镜到底（`locked_one_take`）或硬时长（`hard_duration_s`）。

### 单变量重做与血缘

```bash
python3 scripts/eval_harness.py redo --project <项目目录> \
  --parent-take-id <old_take_id> --take-id <new_take_id> \
  --changed-factor "<字段: 旧值->新值>" --json
```

短参数别名 `--take`（同 `--parent-take-id`）、`--factor`（同 `--changed-factor`）与可选 `--change "<新值>"` 同样可用；省略 `--take-id` 时按 `next_take_id` 自动分配新 ID。

- 每次重做只允许传一个 `--changed-factor`（多传报 `RETAKE_CHANGED_VARIABLES_NOT_ONE`；取值可写 Simplified JSON 字段名、`refs.<标签>`、`keyframe` 或 `provider` 及前后变化）。
- 命令在 `drama.redo_plans[<new_take_id>]` 写入 `status: "planned"` 记录（含 `parent_take_id`、`changed_factor`、`change_value`、`shot_id`、`tier`、`downstream_stale`），将父 take 标 `stale: true`，并把依赖父 take 的 `cuts`／`act_cuts`、`post`、`delivery` 自动标 `stale: true` 作废重拼。
- 同时改两个因子的 take 标「无法归因」，不作为某一修法有效的证据。
- 重做仍受小项目重试配额与预算冻结约束（见 [provider-execution.md](provider-execution.md)）。

## 完成清单

- [ ] 原始 brief、用户确认的剧本版本与最终成片逐场一致：开场是该版本剧本的第一场（或用户已批准的改动），无剧本外的重复场景，无未批准的剧情改动
- [ ] 本次使用的资产版本明确，无 superseded 输入
- [ ] 需要跨镜守恒的 continuity in/out 已更新；单镜或无连续性职责不造字段
- [ ] provider/model/schema 与结果可追踪
- [ ] 存在多 take/剪辑职责时，shot selects 完整
- [ ] 存在的音轨、字幕、精确文字由确定性后期控制
- [ ] ffprobe 与 decode 通过
- [ ] 所有 applicable_qc_dimensions 通过；无关维度已删除
- [ ] 可重建缓存与无用临时文件已清理；请求、失败任务/产物、拒收报告及扣费/退款证据仍可追溯，未把诊断真源当垃圾删除
- [ ] 最终路径可直接交付
