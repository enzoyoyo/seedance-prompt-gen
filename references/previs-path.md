# 制作路径选择：前置白模站位门与 3D 预演路径

AI 短剧成片线在发布意图之后、花钱做角色多角度资产之前，默认先过 `00_previs/` 白模与站位预演门（`drama_setup.py present --gate previs` → 用户回复图内确认码 → `drama_setup.py previs`）：零成本先把每场几何、人物站位朝向、180° 轴线与机位取景出成可选灰模方案交用户选定，并由选定板的 `.blocking.json` 推导出每个角色真正会被拍到的 `required_views`，再进身份资产门与镜头规格；逐场 `--waive-scene` 或整集 `--waive` 同样须经带码决策图确认（Agent 严禁读图代填确认码）。三维工具细节与案例见 [blender-previs.md](blender-previs.md)，白模参考与首帧升级见 [whitemodel-previs.md](whitemodel-previs.md)，本地片场见 [stage-desk-previs.md](stage-desk-previs.md)。

## 1. 预演深度由镜头复杂度与用户拍板决定

| 路径 | 流程 | 适合 | 代价 |
|---|---|---|---|
| 离线灰模站位板（短剧默认起步） | `render_whitemodel_board.py` 出每场 A/B 站位候选与干净机位帧 → `present` 带码选定锁 `00_previs/` → 按推导 `required_views` 锁角色与主景板 → 镜头规格 → 视频 | 绝大多数对白、双人对峙、室内外调度镜头 | 零费用、秒级离线出图；静态机位板不含逐帧骨骼动画 |
| 3D 动态预演路径 | 分镜 → 三维建模/片场运镜 → 编译提示词 → S6 环境首帧升级 → 视频 | 机位路径复杂、多主体走位、精确揭示、一镜到底 | 多一个三维工具环节与审片轮次；需本地软件或云端授权 |
| 混合（推荐整集用法） | 全集每场先过离线灰模站位板锁轴线，S1 判定值得三维动态预演的难镜再升三维运镜 | 大多数含少量复杂调度难镜的短剧 | 在清单 `previs.scenes` 与镜头 `previs_ref` 标清每镜预演源 |
| 用户显式豁免 | 用户明确要求跳过白模（`drama_setup.py previs --waive --user-words "..."`） | 极简纯空镜或用户已自带全套实拍参考 | 复杂调度容易中途越轴、串位且返工更贵 |

## 2. 五步与本 Skill 现有环节的映射

五步不是新管线，每一步都落在已有合同上：

| 五步 | 对应环节 | 交付物 | 合同来源 |
|---|---|---|---|
| 1 分镜 | 工艺环 4 决策分镜 + S1 判定 | shot list，难镜标「3D 预演候选」 | SKILL.md 工艺环、whitemodel-previs S1 |
| 2 建模 | S2 灰盒 → S3 摆姿 → S4 定相机 → S5 渲染 | `previz.mp4`、`first.png`；片场为 `<片场名>-<机位名>.json`、机位 PNG、`-站位.txt`、`-运镜.webm`；只落 `00_previs/` | whitemodel-previs S2–S5、blender-previs 最小交接信息、stage-desk-previs |
| 3 编译提示词 | 工艺环 6 运动 Prompt + 白模接口 | 逐镜 NBP；白模作 `role: motion` 引用 | prompt-contract、whitemodel-previs「与本 Skill 合同的接口」 |
| 4 环境资产图 | S6 首帧升级 + location plate | `first_graded.png`、地点板 | 本文件第 4 节、keyframe-assets「参考图职责与预算」 |
| 5 视频 | S7 白模参考生成 → S8 局部返修 | 成片镜头，按执行选择门出单 | whitemodel-previs S7–S8、provider-execution |

锁资产（工艺环 3）仍在分镜之前完成；3D 预演只决定空间，不重做人物与道具资产。

## 3. 建模工具四选一

| 工具 | 何时选 | 取舍 | 状态 |
|---|---|---|---|
| 本地 Blender（默认脚本 `scripts/blender_previs.py`） | 用户要 `.blend` 源文件、要离线可复现、或已有 `.blend` 接续 | 免费、可控、可交 `.blend`；需本机安装，摆姿与相机靠脚本或 GUI | 脚本仅出 cube／sphere 代理 |
| Higgsfield 3D Jutsu（云端场景） | 用户已授权 Higgsfield 且不想装软件；要从同一场景直接出多角度图 | 免安装，可接 angles 出图与 Seedance 2.5 出视频；需授权与额度，按次计费 | `.blend`／GLB 能否下载以实际下载为准，`TODO_VERIFY_LIVE: jutsu_blend_export` |
| 小云雀站内 3D 导演台 | 已在小云雀链路内，且未点名本地 Blender | 不出本地工程文件；与小云雀生成链路一体 | 按 [adapter-xyq.md](adapter-xyq.md)，`TODO_VERIFY_LIVE: xyq_3d_director_ui` |
| 本地片场（浏览器白模导演台，`tools/stage-desk/`） | 只想快速摆人、定机位，不装软件、不付费 | 免费、离线；9 种姿势素模、机位、路点、运镜 webm；不出 `.blend`、不出逐帧相机矩阵 | 按 [stage-desk-previs.md](stage-desk-previs.md)，`scripts/stage_desk_handoff.py` 转 `00_previs/`；`TODO_VERIFY_LIVE: stage_desk_slots` |

用户未指定工具时，按上表「何时选」给一句推荐与理由，由用户定；不替用户付费、不替用户授权。3D Jutsu 不是本地 Blender，口径以 [blender-previs.md](blender-previs.md)「执行界面选择」为准。

## 4. 环境资产图交接

环境资产图把白模的空间合同转成生成模型能读的场景参考，继承空间，不继承灰模外观。

| 项 | 内容 |
|---|---|
| 输入 | 白模首帧 `first.png`、S4 锁定的机位与焦段、地点设定文字、已锁定的人物与道具资产 |
| 输出 | `first_graded.png`（同机位升级的首帧）；需要多机位时，按相同空间出地点板 |
| 继承 | 机位、取景、纵深关系、主体站位、光的方向 |
| 不继承 | 方块轮廓、灰模材质、临时色块 |
| 生成方式 | 本地路径用 S6 首帧升级提示词；3D Jutsu 路径可用场景 angles 出图（计费，需授权） |
| 下游 | 首帧进视频首帧槽或参考槽；地点板按 keyframe-assets 的 location plate 职责只锁空间，不管动作 |
| 验收 | 叠画对照：主体位置、地平线、消失点与白模首帧一致；不一致回 S6 重出，不改白模 |

## 5. 槽位与合同边界

- 白模视频与升级首帧怎么同时进模型，以 [blender-previs.md](blender-previs.md)「继承契约」为准；首尾帧模式不夹带其他引用，冲突时用 `omni_reference` 或 `planning_only` 并标 `TODO_VERIFY_LIVE: mode_compatibility`。
- 不新增 NBP 根键；白模只作 `role: motion` 引用。
- `00_previs/` 产物不进成片目录，底片不得当成品。

## 6. 当前不做

- 人形代理由本地片场提供（9 种姿势素模，见 [stage-desk-previs.md](stage-desk-previs.md)）；`blender_previs.py` 仍只出方块与球体代理，Blender 内要人形时用 GUI 摆带关节低模，或用 3D Jutsu 资产库的人形模型。
- 实际生成效果、3D Jutsu 导出能力、Seedance 2.5 槽位组合均未在本仓库实测，按 `TODO_VERIFY_LIVE` 处理。
