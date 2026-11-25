# 白模参考工艺：底片只交空间合同

## 触发条件

AI 短剧成片线在发布意图之后、角色多角度资产与任何视频生成之前，默认先过本文件的白模与站位预演门：锁定剧本中出现的每个场景都须先在 `00_previs/` 产出白模站位候选（支持 `options` 多套 A/B 站位、`_compare.png` 并排对比图与每机位无标注干净灰模帧），经 `drama_setup.py present --gate previs` 生成烧入确认码的决策图展示给用户，再凭用户回复中的选项与确认码用 `drama_setup.py previs` 锁入清单（逐场 `--waive-scene` 或整集 `--waive` 同须经 `present` 并带码；整集跳过时可零 `--candidate` 运行 `present --gate previs` 生成纯豁免决策图；确认码只属用户本人，Agent 禁读取、转述或代填，属防随手代填摩擦而非密码学证明）。选定板的 `.blocking.json` 旁路自动推导各非群演（非 `"extra": true`）角色的 `required_views`，供随后的身份门只按需准备真正拍得到的角度。普通纯剧本选题、口播、单张图不加载本文件。

工具分层：默认可用零成本离线 `scripts/render_whitemodel_board.py`（输入 `templates/whitemodel-blocking-plan.json` 规格，宽 ≥1920px，人形头／躯干／下肢分体支持 `standing/seated/leaning/kneeling/lying` 五种姿态、墙挂道具 `y` 高度与实心墙遮挡判定，输出带标注俯视+全机位板、无标注干净灰模帧 `<stem>_<camera>.png`、多方案 `_compare.png` 与 `.blocking.json`）或浏览器本地片场 [stage-desk-previs.md](stage-desk-previs.md)；仅当用户明确要求调用 Blender 时才加载 [blender-previs.md](blender-previs.md) 启动本地 `.blend` 脚本分支。加载本文件不等于授权装插件或提交付费任务。

## 验收锤

> 核心准则：「3D 预演只能作为输入底片，视频生成通道输出的才是精修电影感画面；细节不必精致，预演只为稳定后续视频生成。」

底片粗糙不是理由。下面每一条都服务这两句：**Blender 只交空间合同，外观由另一路参考承担。**

## 白模参考是什么

| 事实 | 来源类型 | URL | 访问日期 |
|---|---|---|---|
| Seedance 2.5 把「白模参考」列为一级参考能力：用无纹理 3D 模型承担空间结构、主体姿态、运动轨迹与镜头机位，模型据此生成，并据白模空间信息推出符合物理的光照方向、色温、强度与投影 | 官方 | https://seed.bytedance.com/zh/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5 | 2026-09-15 |
| 同次生成的参考素材上限为 30 张图片 + 10 段视频 + 10 段音频；单次时长上限 30 秒并支持多轮延长 | 官方 | https://seed.bytedance.com/zh/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5 | 2026-09-15 |
| 官方明确把职责分栏：白模管镜头与轨迹，图片参考管外形/场景/材质/光照/色彩，prompt 里显式写「将白模渲染为……」 | 官方 | 同上 | 2026-09-15 |

上限是上限，不是目标：从白模起步，只加有唯一职责的参考（第三方教程，https://www.seedance.tv/blog/seedance-2-5-white-model，2026-09-15）。实际可用槽位与当前账户权限仍按 exact endpoint 的 live schema 读，未核即 `TODO_VERIFY_LIVE: reference_types_and_limits`。

## 失败三机理

「底片粗糙 → 成片同样粗糙」不是模型弱，是输入模式选错加职责没分栏。

| 机理 | 现象 | 修法 | 来源类型 |
|---|---|---|---|
| 一 · 刚性无关节代理 | 纯彩色方块没有可识别骨架，模型抽不出 pose，退化成普通 V2V 贴图映射——只是把方块涂得好看一点 | 主体换成有可见关节的低模人形，或改走白模参考通道而不是 V2V | 社区（Reddit 回帖，https://www.reddit.com/r/generativeAI/comments/1spp2kr/from_blender_colored_bloc_movie_to_ia_movie_how/，2026-09-15） |
| 二 · 白模残留材质 | 白模里的纹理、花哨材质、色块被模型当成**风格**继承 | 全场统一 clay shading，禁贴图；色块只做图例，不进最终渲出 | 第三方教程（https://www.seedance.tv/blog/seedance-2-5-white-model，2026-09-15） |
| 三 · 3D 粗帧当首尾帧 | 输出总会贴近原始 3D 粗帧，模型很难被推离那个视觉域（转不成动漫、转不成真实照片） | 插入 S6 首帧升级；或改用白模参考通道，让白模只进 video 槽 | 社区（Reddit 长评，https://www.reddit.com/r/ArtificialInteligence/comments/1t4kdxd/i_used_blender_as_a_layout_tool_for_ai_video/，2026-09-15） |

三条机理的症状行已同步进 [failure-diagnosis.md](failure-diagnosis.md)（WM-01～WM-05）。

## 参考职责分层

```
白模      → 空间布局、相对比例、地面接触、机位高度/朝向/路径、景深层次、姿态变化
角色参考  → 脸、身形、服装、身份            （不定机位，不定路径）
动作参考  → 节奏、手势、编舞、镜头速度      （不定最终造型）
风格参考  → 色板、质感、光语言              （不定主体位置与动作时序）
```

顺序：白模 → 身份 → 动作 → **风格最后加**。理由是好看的风格参考会盖掉空间逻辑（第三方教程，https://www.seedance.tv/blog/seedance-2-5-white-model，2026-09-15）。每一路参考在 prompt 里都要写「管什么、不管什么」；同一诉求不重复喂多路。

## 官方 prompt 范式

官方示例的句式（官方，https://seed.bytedance.com/zh/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5，2026-09-15）：

```text
参考 @白模1 的运镜、镜头节奏、景别变化、主体轨迹、镜头调度；
参考 @图片2 的角色外形、场景、材质、光照、色彩、氛围；
将白模渲染为……
```

第三方教程给的更细写法（https://www.seedance.tv/blog/seedance-2-5-white-model，2026-09-15）：白模参考锁主体位置、相对比例、地面接触、机位高度、镜头朝向与机位路径；角色与产品参考**只**负责外观；正文写「把灰模替换为真实的<场景>、自然皮肤、准确<产品>材质与电影级布光」，并写「一镜到底、不加人、不换位」。

「将白模渲染为……」这一句不能省。省了就落回机理三。

## 白模制备清单

提交前逐项确认（第三方教程来源同上，标注为工艺假设，不是模型合同）：

- [ ] 全场统一 clay shading，无贴图、无花哨材质、无残留装饰道具；
- [ ] 有地面平面与可见地面接触点，脚不悬浮；
- [ ] 主要遮挡物与通路几何在场（门洞、墙厚、家具、前景遮挡）；
- [ ] 主体按镜头需要分层：只承担站位、朝向与机位关系的主体用 cube/sphere 代理即可（`blender_previs.py` 支持）；需要模型读出姿态变化的主体用有可见关节的低模人形（脚本不支持，GUI 或项目脚本手工摆），只摆起止姿态，中段留给模型；
- [ ] 每个角色/道具命名，并在 prompt 里复用同名；
- [ ] 相机先定：焦距、传感器、路径、裁切、机位高度、俯仰、起止位置已写进参考说明；
- [ ] 色块与箭头只作图例，不得被读成服装配色或布景。

## S1–S8 流程

| 步 | 动作 | 产物 | 质量门 |
|---|---|---|---|
| S1 | 判定这一镜是否值得三维：只有机位路径复杂、多主体走位、精确揭示、一镜到底才进 Blender | 决策记录 | 不进 Blender 的镜走原有六入口，不新增门 |
| S2 | 搭灰盒：中性材质、场景几何、地面与主要遮挡物，去装饰道具 | `.blend` | 白模里没有任何可被误读为风格的材质 |
| S3 | 主体摆起止姿态，命名每个代理 | 已摆姿场景 | 有地面接触、无悬浮、无互相穿模 |
| S4 | 定相机：焦距、路径、抖动、时序在这里定死 | 相机动画 | 相机不穿墙、主体不出画、构图在目标画幅内；按 `blender_previs.py --check` 与 `camera-samples.json` 回读 |
| S5 | 渲两样：blockout 视频（低画质即可）+ 首帧 PNG；走 ComfyUI 路线时另渲 depth / normal / Canny / OpenPose 序列 | `previz.mp4` + `first.png`（+ 控制通道序列） | 完整 decode + ffprobe 回读 |
| **S6 首帧升级** | 用图像模型把 Blender 首帧升成电影质感，只改画质不改构图 | `first_graded.png` | **并排比对构图与姿势；不合格重做 S6，不带着塌掉的首帧进 S7** |
| S7 | 生成：首选白模参考路线 | 成片草稿 | 逐条对**布局**验收，不只看好不好看 |
| S8 | 局部返修，不整段重渲 | 定稿 | 全片播放 + 核听 + 与白模布局对照 |

### S6 首帧升级的提示词强制项

第一方来源（Flick，https://flick.art/blog/blender-ai-filmmaking，2026-09-15）的原文要求：**构图 100% 一致、机位 100% 不变、取景 100% 不变、角色姿势 100% 一致**，只升画质。写法：

```text
以提供图为构图与姿势参考：构图 100% 一致、机位 100% 不变、取景 100% 不变、角色姿势 100% 一致；
只把材质、皮肤、布光与介质质感升级为电影级成片质量；不移动主体、不改景别、不加人、不换镜头。
```

再叠 [cinematic-method-playbook.md](cinematic-method-playbook.md) 的胶片语域与受控瑕疵词表。用哪个图像模型按当前宿主可用且获授权的 image adapter 决定，本文件不固定模型名。原文的「exactly / 100%」是提示意图，不是下游效果保证——所以质量门是并排比对，不是相信提示词。

### S7 首选路线：白模参考

白模视频进 video 槽，`first_graded.png` 与角色/场景图进 image 槽，prompt 按上文分栏。底座可以是 Seedance 2.5 直连或 Higgsfield Cinema Studio 4.0（其底座即 Seedance 2.5，官方帮助中心，https://higgsfield.ai/creator-hub/help-center/tools/how-do-i-use-cinema-studio，2026-09-15），细则见 [adapter-higgsfield.md](adapter-higgsfield.md)。

备选路线（都要按 exact endpoint 读 live schema，参数枚举 `TODO_VERIFY_LIVE`）：

| 路线 | 要点 | 来源类型 | URL | 访问日期 |
|---|---|---|---|---|
| Kling O3 V2V | `video-to-video/edit` 与 `.../reference` 两条端点；prompt 内用 `@Video1`/`@Image1`/`@Element1` 挂载 | 第三方托管平台文档 | https://fal.ai/docs/model-api-reference/video-generation-api/kling-video-o3-standard-video-to-video | 2026-09-15 |
| Runway Aleph 2.0 | in-context 视频编辑，支持关键帧锚点（`first`/`last`/秒级时间戳），动词用 change/replace/swap/add/remove/restyle/relight | 第三方官方接入文档 | https://runware.ai/docs/models/runway-aleph-2-0/guides/editing-video | 2026-09-15 |
| Luma Modify Video | `media.url` + 可选 `first_frame.url` + `mode`；白模重塑要用 `reimagine_*`，`adhere_*` 会把灰模质感保留下来 | 官方文档 + 本地推断 | https://docs.lumalabs.ai/docs/modify-video | 2026-09-15 |
| 本地 Wan VACE | ComfyUI 逐帧 restyle，见下文控制通道路线 | 第一方 + 开源 | https://flick.art/blog/blender-ai-filmmaking | 2026-09-15 |

`reimagine_*` 优于 `adhere_*` 是按官方 mode 语义做的本地推断，未实测，记 `TODO_VERIFY_LIVE: luma_mode_semantics`。

## 质量门：对布局验收，不只看好看

S7 之后逐条核对，任一不成立就回到最早出错层：

- [ ] 主体位置、相对比例、地面接触点与白模一致；
- [ ] 机位高度、朝向、路径、景别变化与白模一致；
- [ ] 事件时点（经门、揭示、接触、cut）与白模帧点一致；
- [ ] 灰模材质、色块服装、标记文字、僵硬关节**没有**被继承；
- [ ] 角色身份来自批准的身份参考，不是白模的方块轮廓；
- [ ] 全片完整播放，不靠抽帧判定。

「长得像」不算通过。逐条对布局是第三方教程的明确要求（https://www.seedance.tv/blog/seedance-2-5-white-model，2026-09-15）。

## Blender 里做到什么程度

- **做**：相机焦距与传感器、路径、裁切、主光**方向**。白模的空间信息会被模型用来推物理光照的方向、色温、强度与投影（官方，https://seed.bytedance.com/zh/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5，2026-09-15）。
- **不做**：材质、贴图、最终打光强度、人物面部细节——这些交给参考图。
- **临界点**：只保留会影响构图、接触、遮挡、机位安全的几何。太简单会产生深度歧义，太复杂会与参考冲突（第三方教程，同上）。
- 第一方实操结论：blockout 不需要好看，`less detail is often better`（Flick，https://flick.art/blog/blender-ai-filmmaking，2026-09-15）。同一来源也写了取舍：Blender 控得越多，输出越可预测，模型的生成余量越少；取舍点由镜头决定。

## 常见失败对照表

| 现象 | 根因 | 修法 | 来源类型 |
|---|---|---|---|
| 成片仍是低模塑料感 | 白模带材质被当风格 / 首帧未升级就直喂 | 改 clay shading；插入 S6 | 第三方教程 + 社区 |
| 动作僵硬 | 用了无关节刚体代理，或反过来锁死了精细关节 | 用带关节低模；只摆起止姿，中段留给模型 | 社区 + 本地推断 |
| 模型自己改运镜 | prompt 没复述相机行为 | 用明确电影语言复述白模机位（`smooth tracking shot` / `slow push-in` / `locked frame`） | 社区 |
| 主体漂浮或穿模 | 白模缺地面与接触点 | 加地板平面与接触点 | 第三方教程 |
| 多主体串位 | 代理未命名、图例箭头冲突 | 每个角色命名并在 prompt 复用；同一时间段只给一个主导动作 | 第三方教程 |
| 切不干净 | 没有稳定末态 | 预留 final hold | 第三方教程 |
| 转不成想要的风格 | 结构约束过强 | 降结构权重（Luma 换 `reimagine_*`、VACE 降 strength），或接受「只能在三维域内美化」 | 本地推断 |

## 另一条路线：Blender → ComfyUI 控制通道

Blender 出 depth / normal / Canny / OpenPose / segmentation 通道，EEVEE 或 Workbench 渲染，进 ComfyUI ControlNet，再由本地 Wan VACE 逐帧 restyle，合成回 Blender（第一方 + 开源，https://flick.art/blog/blender-ai-filmmaking，2026-09-15）。Blender 的 Z pass 是逐像素真实场景距离的真值，脚本化序列没有理由再用预处理器估深度（开源项目 README，https://github.com/ismael-joffroy-chandoutis/comfyui-blender-temporal，2026-09-15）。现成 previs 打包器 `blockout`（Apache-2.0，开源仓库，https://github.com/wassermanproductions/blockout，2026-09-15）导出 `reference.mp4 / depth.mp4 / normal.mp4 / stills / prompt.txt / comfyui-workflow.json / metadata.json`。

分叉条件：

| 选白模参考路线 | 选控制通道路线 |
|---|---|
| 目标端支持视频参考 + 多图参考，且当前账户可用 | 目标端不支持视频参考，或必须离线/本地完成 |
| 要的是「换视觉域」（灰模 → 真实或动漫） | 要的是「逐帧结构精确对齐」（产品、UI、机械运动） |
| 有授权预算跑云端生成 | 有本机 GPU 与 ComfyUI 环境 |
| 接受模型在中段自行补运动 | 需要每一帧都被控制信号钉住 |

两条路线不混用同一批参考：控制通道路线的 depth/normal 序列不是 NBP 的 `role: motion` 参考，不塞进生成请求的 video 槽。

## 官方插件：只作「使用时重新核验」的指针

即梦提供 Seedance 2.5 白模渲染的 Blender / Maya 插件；Blender 侧路径为 `Edit → Preferences → Add-ons → Install from Disk`，N 键 Sidebar 选 `Jimeng` 面板，「相机渲染」或「本地上传」后「上传至即梦生成」，白模视频直接落为参考视频输入（第三方转载的官方手册，https://www.blenderx.cn/blog/seedance25，2026-09-15）。

使用前须按当前插件状态重新确认：安装、账号权限、面板名称、上传链路与计费都在使用时重新核验；不把手册描述当本机已具备的能力，也不为使用插件要求用户登录或付费。

## 不作规则的争议

**方块 vs 带关节低模，哪个更适合白模参考：证据互斥，本地 A/B 前不作规则。** 第一方来源（Flick）与一条 Reddit 帖主张方块更好、细节 mannequin 会变成牢笼；另一条 Reddit 回帖与 seedance.tv 主张必须有可见关节否则抽不出骨架。两侧都只有社区/第一方叙述，且可能取决于目标端是否走白模参考通道。本文件在制备清单里默认「带关节低模」，理由只是它同时满足两侧的下限；要把任一侧写成规则，先本地各跑 1 镜 A/B。 当前分层默认：站位/朝向/机位关系用方块代理，需读姿态的主体用带关节低模；这只是默认，不是 A/B 结论。

## 与本 Skill 合同的接口

- 白模视频按现有映射为 `role: motion` 的 canonical `@Tag`（例如 `@motion_previs_s01_v01`），非空 `use` 里写「只承担机位与轨迹，不继承材质与颜色」；**不新增 NBP 根键**。
- 首尾帧模式不能夹带其他引用，与官方白模范式（白模视频 + 多张外观图）冲突；目标端确实支持时走 `omni_reference`，表达不了就停在 `planning_only` 并记 `TODO_VERIFY_LIVE: mode_compatibility`。
- 预演产物只落 `00_previs/`，汇总交付默认排除；交付分级见 [post-production.md](post-production.md)。
- 参考职责与预算的通用规则见 [keyframe-assets.md](keyframe-assets.md)；编译与字段落点见 [prompt-compiler.md](prompt-compiler.md)；执行界面选择、继承契约与本地脚本见 [blender-previs.md](blender-previs.md)。
