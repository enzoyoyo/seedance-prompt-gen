# 人脸一致性执行：证据边界与两段式工作流

通用方法（身份真源、Face Lock、最小充分视图、中性无影底板）见 [keyframe-assets.md](keyframe-assets.md)；本文件只写 provider 侧的执行细则与一致性边界：参考图与同线程都是控制手段，不是身份一致性的绝对保证。

## 执行规则

- 先保留用户批准的实际视频，再从其真实末态续写；用户明确“不用修、继续”后，不重新选角、重拍开头或擅改道具。只为新段落检查剧情衔接；真实技术阻塞单列。
- 身份参考优先使用用户已选择的图片或已批准视频中的清晰角度。不要反复从文字另造女主。若只换场景/服装，用已有参考编辑，不把每张当独立选角。
- 沿同一相关 thread 串行续写，并明确上一产物 URL、实际人物服装/发型、道具状态、空间方位和下一事件。Agent 记得对话，不等于生成模型已收到参考或能锁脸。
- 给身份、地点、风格、动作参考分别声明职责；槽位和可兼容输入以当前模型 schema 为准，不为“最多支持”而填满槽位。
- 按 adapter 的 upload 流程取得 URL，核对上传回执与下游接收。不能把「本地路径必然无效」作为已证实根因；早期本地附件请求曾触发素材审核，未做上传路径对照实验。
- **上传链路单变量排查：本地路径 vs CDN URL。** 若更换上传形式后一致性出现波动，须保持其他变量不变做单变量对照，不凭单次观察将其定性为根因。
- 首尾帧、单次长视频、同 thread 都不能保证不跳切或不漂移。明确连续时间或有意剪接，按实际镜头检查人物、服装、动作、视线、轴线及声场。
- 文本中的“保持一致”和 Agent 的复述不是测试结果。至少并排查看参考与各段实际关键帧，涉及动作和对白时还要回放/核听。

## 两段式工作流：无脸场景垫图 + 垫图补脸

分工原则：**前段出无脸场景垫图，后段在垫图上补脸。** 理由是建筑结构与光影在垫图阶段更可控，补脸阶段只需在已定构图与光照中注入角色身份，能显著减少跨镜头漂移。

### 第一段：无脸场景垫图

强制无脸底图的常用构图写法（确保垫图阶段不出现可辨识人脸）：

- `seen from BEHIND over his shoulder so his face is completely hidden`
- `framed from the COLLARBONE DOWN ONLY, head cropped above the top edge of frame`
- `bowing ninety degrees in a row, heads down and faces not visible`
- `blurred crowd, faces turned away and out of focus`
- 纯空场：`EMPTY SET MASTER PLATE — architectural reference, absolutely no people, no figures, no silhouettes`

必出的四类板：空场主景 master、关键调度 staging、手部插入 insert、门口/入场 staging。空场主景可反复复用做其他镜头底板。

### 第二段：垫图补脸

把第一段的 plate 作为参考图传入生图接口，提示词写「以参考图的构图、机位、灯光和场景为准，严格保留不变；在此基础上补全人物面部与身份」。后续微调直接把上一版产出再当参考图喂进去，逐轮修复单点缺陷。

小云雀侧的具体参数名、枚举、轮询与下载坑见 [adapter-xyq.md](adapter-xyq.md) 的「故障与重试」；本文件不复制参数，避免两处分叉。

## 审核边界：文本审核与主体库风控是两件事

### 文本审核（`ret=12004 输入文本内容审核未通过`）

直白身体描写会被文本审核拦。把同一场戏改写成服装部门／摄影部门语域是**合法的创作选择**——换的是镜头语言，不是内容本身，改写后的画面仍须符合平台规则。

| 易误判词汇方向 | 服装 / 摄影部门可拍物理描述 |
|---|---|
| 抽象暴力或激烈冲突形容词 | `choreographed blocking: brisk defensive step back as both hands grip the wooden doorframe` |
| 易触发误审的伤痕/污渍词汇 | `wardrobe continuity note: small dark mud/rust trace on the outer coat cuff, strictly confined to fabric` |
| 过分情绪化的险情氛围词 | `cinematography note: narrow tungsten practical lighting, character holding a matte metal flashlight` |

动作与物理痕迹优先写明剧情道具与光影/材质变化来源（如雨水、尘土、遮挡关系），减少抽象形容触发的文本误审。

这条只适用于文本审核。**不得用部门语域承载平台明确禁止的内容**；擦边与 red 条边界见 [platform-risk-and-compliance.md](platform-risk-and-compliance.md) 的 Provocation ladder。

### 主体库 / 真人风控（`API_INPUT_SD2_RP_POLICY_VIOLATION`）

- AI 生成的写实人像仍可能触发真人/主体审核；不能声称“AI 图一定免审”。
- 要求 subject library 审核时，走平台正式认证路线：在网页端主体库完成认证，下游按认证后的 `asset://` 资产引用提交。**不以重绘、换图来源或换措辞作为绕过方法**，这与 `platform-risk-and-compliance.md` 的 red 条「evasion of platform review」是同一条线。
- `SEEDANCE_ASSET_MODERATION_REJECTED` 只证明素材被拒；未提供具体原因时，不臆测单一触发词。
- CLI 没有主体库子命令只证明当前 CLI 未暴露该功能，不证明网页位置、API 不开放或可由其他命令绕过。
- 单张图无法可靠证明真人/AI来源；使用用户提供的来源说明。不得把视觉模型的猜测写成事实，也不因普通人物参考请求凭空设置“不能参考真人脸”的限制；平台输入限制另行遵守。
- **开拍前风控探针（禁中途降档凑数）**：当发布意图 `real_public_figures: true` 或人物造型高度贴近公众人物时，必须在身份门阶段先对目标通道同档位做 1 次最小探针核清主体库认证或风控结果，并用 `drama_setup.py identity --likeness-preflight "<通道与结果>"` 落账；若目标通道拒绝该脸型，当场向用户摆明「走官方主体库认证 / 调整角色骨相拉开距离 / 全集统一换合规通道」由用户决策，**严禁**拍到一半被拒后私自切去低分辨率无参考通道硬凑，造成同集内画质与脸型断层。

## 审美与验收

- 用户的明确审美选择优先于视觉模型的主观分数；不是为了独特就强加牙缝、歪鼻等未要求特征。
- 景深中的光斑、衣服比脸亮、没有可见缝线不自动等于物理错误；根据光线、材质、曝光与用途判断，不用伪技术标准拒收。
- 不从单次样本推出“某模型一定更好”“同厂必然一致”“只有某档才有电影感”。锁定批准样本的实际视觉与设置，未知模型标待核验。

## 目录结构

```
<项目>_制作包/
├── 01_场景垫图/     PLATE-XX_描述_staging.png
├── 02_人脸/         vN_改动_分数.jpeg + SHOTXX_定稿_分数.jpeg
└── 03_提示词包/     提示词配方.md
```

版本文件名带分数，便于回溯哪次改动真正起效。

## 行为回归样例

- 用户说“漂移可接受，按已出继续” → 保留现有片、读取真实末态、只续下一事件；不得重拍。
- Agent 回复“reference locked”但无产物 → 仍未验证，不报告锁脸成功。
- 图片为AI生成但报主体库审核 → 遵审核，不以重绘规避。
- 用户只要求拼接 → 本地合并实际可用片段，缺少收尾如实注明，不生成或重复补时。
