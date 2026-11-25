# 本地片场：浏览器白模导演台

## 触发与边界

仅当用户点名「片场」「本地导演台」，或在 shot list 末尾的可选菜单里选定本地片场时加载，由 [previs-path.md](previs-path.md) 带入。「片场」指真实拍摄现场的口语（片场纪实短剧、片场花絮、片场事故）不触发。加载本文件不等于启动片场。

片场不接任何生图、生视频模型；不替用户付费、授权或登录。它只产出空间底片，后续生成按原有执行选择门走。

## 片场是什么

随本 skill 分发在 `tools/stage-desk/`：three.js 本地页面，Node 静态服务只监听 127.0.0.1。打开方式：双击 `tools/stage-desk/打开片场.command`，或在该目录 `npm start`；首次运行会自动 `npm install`。

- 坐标：1 格 = 1 米，Y 向上；机位绕自身旋转后朝 +Z 看；机位总在场景根层，不进组。
- 能摆：人体素模（站立、行走、跑步、半蹲、单膝跪、伸手、对峙、回头、观察 9 种姿势）、方块、球体、柱体、五人弧形群众、打组。
- 能定：机位位置与朝向、视野（18–80°，垂直视野）、6 种画幅、看向对象、地面路点、走位播放。
- 能录：沿路点走位的运镜 webm（浏览器支持 MediaRecorder 时）。
- 不随工程保存：导入的 `.glb`（重开后为占位方块）、360° 全景天幕。
- `GET /api/health` 返回 `{"ok": true, "version": 1}`，只作探活；没有写接口，没有 MCP。

## 交出什么

| 文件 | 来源按钮 | 内容 | 去向 |
|---|---|---|---|
| `<片场名>-<机位名>.json` | 交接（或保存） | 工程 JSON：`version: 1`、`exportedAt`、`nodes[]`（`actor/primitive/model/group/camera`，位置、欧拉弧度旋转、缩放、姿势、视野、画幅）、相机 `lookAt` 世界坐标、`path[[x,z]]`、`lookAtId`、`activeShotId` | 复制进 `00_previs/` |
| `<片场名>-<机位名>-<画幅>.png` | 交接（或截图） | 机位静帧，长边 1600，已隐藏机位与轨迹辅助线 | 经 S6 后才进首帧槽 |
| `<片场名>-<机位名>-站位.txt` | 交接（或复制站位） | 逐对象：画面左右几米、前方几米、脚相对镜头高度、朝向、姿势、所属组 | prompt 空间句与布局 QC 对照 |
| `<片场名>-运镜.webm` | 录运镜 | 当前机位沿路点走位的录屏 | `role: motion` 参考 |

「交接」一次下载前三件。浏览器若拦截多文件下载，按提示允许一次。

## 转成 00_previs

`scripts/stage_desk_handoff.py`，纯标准库，从本 skill 根目录运行：

```bash
python3 scripts/stage_desk_handoff.py --help
python3 scripts/stage_desk_handoff.py --project templates/stage-desk-project.json --shot S01 --camera "机位 1" --check
python3 scripts/stage_desk_handoff.py --project <片场名>-机位1.json --shot S01 --camera "机位 1" \
  --still <片场名>-机位1-16x9.png --motion <片场名>-运镜.webm --output <项目>/00_previs/S01-stage-r01
```

- `--check` 只校验并打印推断字段，不写文件。
- 输出目录已存在即拒绝（`OUTPUT_EXISTS`），改用新修订目录；与 `scripts/blender_previs.py` 同口径。
- 拒绝：未知 `type`、非有限坐标、工程里没有相机、`--camera` 找不到或重名、相机在组内、未知画幅或姿势、父子环。错误走 stderr，非零退出。
- 产物：`manifest.json`（`status: planning_only`、文件 sha256、`visual_qc` 与 `geometry_qc` 为 `needs_review`、`provider_submission: not_performed`）、`camera.json`（机位世界位置、前向、垂直/水平视野、画幅、35mm 等效焦距换算值、看向点、路点、逐对象相对位置与是否在画框内）、`blocking.md`（与片场右侧站位说明同口径）、`nbp-camera-fragment.json`（`camera` 四字段候选与可选 motion 引用）。输入原样复制为 `stage-project.json`、`still.png`、`motion.webm`。
- `templates/stage-desk-project.json` 是最小 fixture（1 角色、1 方块、1 机位、2 路点），只供测试与 `--check`。

## camera 四字段的推断口径

全部标「推断，可改」，导演判断优先。

- `shot_size`：主体中心到镜头的深度乘垂直视野得可见高度，除以人高 1.75 m（道具按形状高度）。≤0.3 特写，≤0.5 近景，≤0.8 中景，≤2.2 全景，其余远景。主体取看向对象；看向对象不在镜头前时取前方最近的角色。
- `angle`：镜头高出主体头顶 0.25 m 以上为俯拍；低于主体身高 55% 为仰拍；其余平视。
- `movement`：有 ≥2 个路点且本机位是工程当前机位时写「沿路点推轨，看向 <对象>」；否则 `locked`。片场只让当前机位走路点，其他机位有路点也按固定机位推断并记 warning。
- `lens_note`：垂直视野、画幅与 35mm 等效焦距。等效焦距由垂直视野与画幅得对角视野，按全画幅对角 43.27 mm 折算，是换算值，不是实拍镜头参数。

## 与 S1–S8 的映射

| 步 | 片场覆盖 | 说明 |
|---|---|---|
| S1 判定 | 不变 | 不值得三维的镜不开片场 |
| S2 灰盒 | 覆盖 | 方块/球体/柱体/群众、地面网格、统一 clay 材质；墙与门洞用拉伸方块搭 |
| S3 摆姿 | 覆盖 | 9 种姿势素模；只摆起止姿态，中段留给模型 |
| S4 定机位 | 覆盖 | 视野、画幅、位置、看向、路点；`camera.json` 回读 |
| S5 出首帧与运镜 | 覆盖 | 机位 PNG + 运镜 webm；不出 depth/normal/OpenPose 通道 |
| S6 首帧升级 | 不变 | 片场 PNG 必经 S6 才进首帧槽 |
| S7 生成、S8 返修 | 不变 | 按 [whitemodel-previs.md](whitemodel-previs.md) 逐条对布局验收 |

## 职责边界

片场只交空间合同：站位、朝向、相对比例、地面接触、机位高度/朝向/视野、路点。不交材质、服装、面部、光的强度。

失败三机理照旧，见 [whitemodel-previs.md](whitemodel-previs.md)「失败三机理」：

- 素模有关节，但姿势是刚体预设，只锁起止，不锁中段表演；
- clay 色只区分对象，不是服装配色；
- 片场 PNG 是 3D 粗帧，直接当首帧会把成片锁在素模视觉域，症状见 [failure-diagnosis.md](failure-diagnosis.md) WM-06。

## 与 NBP 合同的接口

- 不新增根键，不改 [prompt-contract.md](prompt-contract.md)。
- PNG 进首帧槽前必经 S6，产出 `first_graded.png`。
- 运镜 webm 作 `@motion_stage_s01_v01`（按镜号与修订号改），`role: motion`，`use` 写「只承担机位与路径，不继承灰模外观」。
- `camera{shot_size,angle,movement,lens_note}` 取 `nbp-camera-fragment.json` 的候选，标「推断，可改」，由当前镜头改定。
- 首尾帧模式不夹带其他引用；与 motion 引用冲突时走 `omni_reference`，表达不了就停在 `planning_only` 并记 `TODO_VERIFY_LIVE: mode_compatibility`，继承契约见 [blender-previs.md](blender-previs.md)。
- 预演产物只落 `00_previs/`，不进成片目录。

## 和其他建模工具怎么选

- 要 `.blend` 源文件、逐帧相机矩阵（`camera-samples.json`）或离线可复现 → 本地 Blender。
- 已授权 Higgsfield、要从同一场景直接出多角度图 → 3D Jutsu。
- 已在小云雀链路内 → 站内 3D 导演台，见 [adapter-xyq.md](adapter-xyq.md)。
- 只想快速摆人、定机位，不装软件、不付费 → 本地片场。

## 未验与不做

- `TODO_VERIFY_LIVE: stage_desk_slots`：片场 PNG 与运镜 webm 进各 provider 的槽位组合未实测。
- 运镜 webm 是画布实时录屏，帧率随机器负载变化；`camera.json` 只记静态机位，不逐帧记录路径插值。
- 不出 depth/normal/OpenPose 控制通道；要走 ComfyUI 控制通道路线用 Blender。
- 不做 MCP；等「让 agent 自己摆站位、设机位、出图」成为真实需求再做。
