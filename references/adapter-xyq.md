# 小云雀 NBP v2 适配器

`python3 scripts/render_nbp_adapter.py --target xyq` 只接收通过校验的 NBP v2 video 对象，输出交给 `pippit-tool-cli generate-video` 的参数，不直接提交任务。

## 字段映射

| NBP v2 键 | XYQ CLI 参数 | 规则 |
|---|---|---|
| `characters`、`subject`、`scene`、`action`、`camera` | `prompt` | 角色只写状态与服装描述；去除 canonical 标签后编排，不补写事实或风格。纯标签服装改写为对应 `参考图N`。 |
| `light`、`audio.ambience`、`audio.music` | `prompt` | 仅在输入存在时进入情绪氛围。 |
| `audio.dialogue`、`audio.sfx` | `prompt` | 仅在输入存在时进入声音段。 |
| `style` | `prompt` | 去除 canonical 标签后作为视频类型；纯标签改写为对应 `参考图N`，缺失则用“短剧镜头”。 |
| `duration.target_s` | `duration` | 直接透传，不由适配器改值。 |
| `aspect_ratio` | `ratio` | 先按 scope=cli 的 capability allowlist 校验，通过后透传。 |
| `live_params.resolution` | `resolution` | 可选；存在时先按 scope=cli 的 capability allowlist 校验。 |
| capability `exact_model_id` | `model` | 缺失时为 `null` 并报 `CAP_MISSING:exact_model_id`。 |
| `omni_reference` 的 character/prop/location/style | `image[]` | 保留引用，不内置配额数字。 |
| `omni_reference/edit/extend` 的 motion | `video[]` | 只按已验证 `task_mode` 交接。 |
| `omni_reference` 的 audio | `audio[]` | 保留引用。 |
| `first_last_frame` | `generate_type`（CLI `--generate-type`） | 输出 `1`，`image[]` 恰好为首帧、尾帧。 |
| `first_frame` | `image[]` | 只输出单张首帧；不猜 `generate_type`，报 `XYQ_FIRST_FRAME_TYPE_UNVERIFIED`。 |

`image[]` / `video[]` / `audio[]` 输出 canonical `@Tag`；提交前必须按 registry 解析为 pippit 本地路径或 asset id，适配器不做解析。
参数名依据只读参考 `xyq-skill` / `pippit-tool-cli` 官方参数定义；模型枚举及服务端合法性由 `xyq-skill` 与服务端决定。

## 帧模式规则

- 模式来自 validator 通过的 `task_mode`；`use` 只认精确 `first_frame` / `last_frame`，不做子串猜测。
- `first_last_frame` 固定输出 `generate_type: 1`（CLI `--generate-type`），`image[]` 恰好两项且首帧在前、尾帧在后，不夹带其他媒体。
- `first_frame` 只交付一张 `image`；除首尾帧值外没有带日期官方枚举，因此省略 `generate_type` 并告警。

## 逐字传递原则

交接 xyq-skill 时逐字传递已编译的 `prompt`，不扩写、不润色、不翻译；编译只移除 canonical 标签并引用已绑定素材，不引入输入里没有的风格或事实。

## 能力凭据

只读取 `--capabilities` 的 `claims[]` 带 `key` 条目，同 key 优先 scope=cli；若 model 数值更高，报 `CAP_ENTRY_LOWER:<key>:cli<model`。缺条目用 `CAP_MISSING` warning；`CAP_EXCEEDED:<key>:actual>limit`、`CAP_EXCEEDED:<key>:actual<limit`、`CAP_EXCEEDED:<key>:value>allowed_list` 进入 `errors[]` 并返回 rc 1，不截断、不放行。

## 提示词公式

- 官方公式是固定五段顺序：视频类型 → 内容要点 → 情绪氛围 → 画面风格 → 时长。适配器按此顺序编译，缺段留空槽，不打乱顺序。
- 正文第一句用自然语言声明参考素材的作用与产物形态（据什么、做几秒、什么片种）；`@` 只负责挂载，职责写进句子里。
- 「内容要点」填必须出现在画面里的具体专名清单，不填抽象形容词，便于逐项验收（落点在 `prompt-compiler.md`，此处只引用）。
- 参考素材用途二选一：只定调子选「全模态参考」（UI 名称一律 `TODO_VERIFY_LIVE`），本镜起止构图/道具状态必须可控才选「首尾帧」。
- 图片、视频、音频三路参考先分派职责：图定外观与构图，视频定节奏与风格，音频定声音与卡点；同一诉求不重复喂三路。
- 提交前显式确认模型、画幅比例、时长三项，任一缺失不提交；时长须与提示词正文秒数一致。
- 沉浸式短片是试片档：单镜样片验证风格方向后再进正片，验收只看画面质感、运镜与段间衔接，不用叙事标准否掉合格试片；单镜试片留在对话式，跨镜资产复用才切画布模式。

## 短剧工作流落点（教程观察，UI 待核验）

下表把第三方教程里观察到的小云雀短剧工作流功能，对到本 skill 的环节与门；只记「它替代哪一步、哪些门照跑」，不记操作步骤、限免次数、语言数、场景数、片段数或模型版本号。功能名、按钮名与入口位置以当日 UI 为准，逐行 `TODO_VERIFY_LIVE: xyq_<feature>_ui`；实际调用仍走主入口 Provider 路由表里的 `xyq-skill` 与 `xyq-short-drama-skill`，本文件不复制它们的参数与命令。

| 小云雀功能（教程观察） | 本 skill 落点 | 照跑的门与规则 |
|---|---|---|
| 短剧 Agent／Scriptbird：喂入剧情主线后补细节，对话式反复改稿；「生成分集大纲」「生成剧本正文」按钮把主线拆成分集与场次，场次带出场人物、目标语言台词与神态提示 `TODO_VERIFY_LIVE: xyq_drama_agent_ui` | 「故事·大纲·连续分集」入口的草稿来源；核心冲突与主线仍由用户与当前会话模型定 | 输出仍过主入口剧本张力门八行与 [human-texture-and-script-gate.md](human-texture-and-script-gate.md)；它默认的分集结构不当固定节拍；人工核对时间线、人物知情与语域，出海版按 [platform-overseas.md](platform-overseas.md) 重写不翻译 |
| 风格库：保存风格提示词并由后续素材继承，画面比例在此统一；内置预设风格 `TODO_VERIFY_LIVE: xyq_style_library_ui` | [continuity-bibles.md](continuity-bibles.md) 的风格前缀与 `templates/visual-style-bible.md` 的母版画幅栏位 | 预设风格只当候选，风格圣经仍需批准；画幅按主入口默认假设与目标平台定，不因库里的预设值改动 |
| 角色来源三选一：手写提示词生图（自研生图模型 AnyCook）、读取剧本自动识别角色、角色库现成角色（脸部大图、表情参考、全身三视图）；角色设计功能按地区、文化、肤色、五官、体型、发型调整；参考图加入画布供生视频引用 `TODO_VERIFY_LIVE: xyq_character_tools_ui` | [keyframe-assets.md](keyframe-assets.md) 的角色资产来源三选一与最小充分视图 | 主角手动锁定，识别与库结果人工修后再批准；库角色核对授权、地区外观与年代；画布内素材仍按 manifest 记 `approval_status` 与 `rights_or_attribution` |
| 读取剧本拆出同一角色不同剧情阶段的装扮 `TODO_VERIFY_LIVE: xyq_stage_look_ui` | keyframe-assets.md 的阶段形象分版本 | 各阶段共享身份锚、另设服装与状态锚；[failure-diagnosis.md](failure-diagnosis.md) 的 `XA-01` 行仍适用 |
| Seed Audio 生成角色参考音频；或先抽一次视频、从 take 里提取声音作参考 `TODO_VERIFY_LIVE: xyq_reference_voice_ui` | [post-production.md](post-production.md) 配音与声音一致性节的参考音色三来源 | voice asset 批准后冻结，换音色即新版本；参考音色语言与目标市场一致；抽取来源记 `shot_id`、`source_sha256` 与时间区间 |
| 识别剧本里反复出现的核心场景并生成场景图，先自动再手动调整 `TODO_VERIFY_LIVE: xyq_scene_identify_ui` | continuity-bibles.md 的场景基准图 | 入口、出口、遮挡、走位、主光方向与正反打关系仍要人工定；自动图只是 candidate |
| 分集视频页「生成脚本」：每集拆成剧情片段，再拆成分镜，每镜自带提示词并自动调用角色、场景参考与声音；编辑按钮增删分镜、改提示词；批量抽卡后手动优化 `TODO_VERIFY_LIVE: xyq_storyboard_script_ui` | 主路径「只画会决定戏的分镜」与「写运动变化过程」两节；Lane B 导演包 | 自动分镜先过决策分镜筛选，只保留会改变信息、关系、目标或状态的镜；自动提示词按 [prompt-compiler.md](prompt-compiler.md) 重编译为 NBP v2 后再走本适配器；自动挂载的参考仍要职责分离；批量前先测代表镜，重做只改一个变量 |
| 视频重制转绘：上传国内成片作视频参考，选目标地区与语言，拆解角色、场景、站位、机位后改成当地版本 `TODO_VERIFY_LIVE: xyq_remake_ui` | Lane E 的已有成片改地区版；platform-overseas.md 的本地化重做 | 源视频只借调度、机位与时序；身份、服装、地点与语言重锁并重新批准；直译版不算出海交付 |
| 一键合成把片段拼成整集；打通剪映；或逐片段导出到剪辑软件手动剪 `TODO_VERIFY_LIVE: xyq_auto_assemble_ui` | 主路径「做声画后期」与 Lane F；[production-qc.md](production-qc.md) | 自动拼接的整集仍分验技术、视觉与 brief，任一失败或 `needs_review` 不签 PASS；字幕、画内文字与 AIGC 披露按 [platform-packaging.md](platform-packaging.md) 分轨 |
| 3D 导演台 / 智能预演 | 站内空间预演；替代本机 Blender 的一部分 blocking | 用户点名本地 Blender 仍走 [blender-previs.md](blender-previs.md)；未点名且只在小云雀链路内 → 用站内导演台，不自动开本地 Blender。`TODO_VERIFY_LIVE: xyq_3d_director_ui` |
| 片段重拍 | 单镜重抽，对应 sequence-resume 的 take 替换 | 判废 take 记 `rejected`，不得再进剪辑表 |
| 角色库 | 脸部与全身参考入库 | 库角色仍要批准；真人图走主体库/认证，不得换措辞绕过 |

不吸收：教程里的限免次数、语言覆盖数、场景数、片段数、秒数、模型版本号、导出参数、后续版本预告与分账／补贴说法；数字按主入口数字规则只能与 URL+日期同行或写 `TODO_VERIFY_LIVE`。具名观察来源（ScriptBird / AnyCook / 资产画布 / 3D 导演台）只作家谱，UI 以当日为准。

## 故障与重试

使用当前适配器前请核对实时命令枚举。下表只记「报错原文 → 处理动作」；所有参数名与枚举 `TODO_VERIFY_LIVE: xyq_cli_flags`，**执行前先跑 `pippit-tool-cli <subcommand> --help` 确认当前枚举**，不照抄本表的参数值。

| 报错原文 | 处理动作 |
|---|---|
| `net/http: TLS handshake timeout`（`upload_file` / `submit_run` / `get_thread` 三个接口都出现过） | 网络抖动，不是任务失败。按固定次数与间隔重试，重试前先用 `get_thread` 确认上一次是否其实已经落单，避免重复计费。 |
| 上传参考图持续超时 | 解法一：压缩参考图后再传（`ffmpeg -v error -i plate.png -vf "scale=720:-1" -q:v 3 plate.jpg -y`）。解法二：特写插入镜、手部镜、无特定场景结构的镜头本就不依赖场景垫图，去掉 `--image` 走纯文生视频绕开上传接口。 |
| `创作失败：内容涉及版权限制` | 提示词里出现了具体器材与胶片品牌名。按下方「品牌名替换表」改写后重提。 |
| `ret=12004 输入文本内容审核未通过` | 文本审核拦截，且此时**退出码可能为 0**，必须检查返回体而不是只看 exit code。改写为服装部门／摄影部门语域后重提，写法见 [face-consistency-execution.md](face-consistency-execution.md)。 |
| `模型参数配置不合法：resolution=1080p 仅支持 seedance2.0_vision、Seedance_2.5`（`ret=2`） | 当前 model 与 resolution 组合不被接受。改用报错文本里点名的 model，或把 resolution 降到该 model 支持的档；组合支持情况以当次报错与 `--capabilities` 为准，本文件不列模型能力矩阵。 |
| `未知参数: --download` | 下载参数是 `--download-dir <dir>`，不是 `--download`。写错会重复空转直到进程被杀。 |
| 查询返回 `"completed": false` | 正常排队，不是失败。完成标志是 `"completed": true`，不是 `status` 字段；查询必须同时传 `--run-id` 与 `--thread-id`。 |
| 轮询超过客户端等待窗口被转后台 | 用宿主的后台进程/等待机制接管，回读真实状态，不重新提交可能扣费的请求。 |

### 品牌名替换表（目标端分叉）

具体器材与胶片品牌名在小云雀会触发版权风控，在不做版权风控的目标端仍可用。**只对小云雀（以及任何做版权风控的目标端）执行下表替换**；[cinematic-method-playbook.md](cinematic-method-playbook.md) 的胶片语域配方保留品牌名写法，两处按目标端选择，不互相覆盖。

| 小云雀禁用 | 通用光学描述替代 |
|---|---|
| `ARRI Alexa` | `anamorphic prime lens look` |
| `Cooke S4` | `prime lens` |
| `Kodak Vision3 5219` | `35mm film emulsion` |
| `Montblanc` 等实体商品品牌 | `fountain pen` 等通用品类词 |

替换的是词，不是画质目标：颗粒、halation、色差、暗角、浅景深这些**可见特征仍要写全**，见 `cinematic-method-playbook.md` 的受控瑕疵段。

### 生图参数（逐行待核验）

- 模型名、`--ratio` 数值与画幅的对应关系、`--resolution` 档位：`TODO_VERIFY_LIVE: xyq_generate_image_enums`。这些枚举是最容易随 CLI 版本漂移的东西，写死会直接生成错命令，执行前必须 `--help` 核对。
- 单张高分辨率出图耗时与轮询转后台阈值随队列变化，不写死秒数；按实际返回体判断。

## 短剧提交配方（`ledger_submit.py` 用）

建议在首次运行前先执行零成本命令确认当前 CLI 枚举（`--help`、`generate-video --help`、`query-result --help`、`model list`、`model describe Seedance_2.5_draft`、`model describe Seedance_2.5`、`get-credit-balance`）。下方模板仅经 `ledger_submit.py submit … --` 调用并先 `--dry-run`，勿直接裸跑 `generate-video`。

### 能力卡初始值

`drama_setup.py channel --name xyq --card <卡.json>`；核实日换成你重跑零成本命令的那天，`expires_at` 取核实日后一个月内。

```json
{
  "recipe": "references/adapter-xyq.md",
  "draft_tier": {"value": true, "verified_at": "2026-11-12", "source": "model describe Seedance_2.5_draft: 先生成480P样片后，再选择满意的版本渲染成片"},
  "draft_upgradable": {"value": true, "verified_at": "2026-11-12", "source": "generate-video --help: --draft-task-id ... used to render a final video"},
  "balance_query": {"value": true, "verified_at": "2026-11-12", "source": "get-credit-balance → total_remain_amount"},
  "recover_by_id": {"value": true, "verified_at": "2026-11-12", "source": "query-result --thread-id --run-id"},
  "ref_transport": {"value": "local file path via --image (the CLI uploads it)", "verified_at": "2026-11-12"},
  "plan_required": {"value": "unknown", "verified_at": "2026-11-12", "source": "pippit-tool-cli --help does not expose plan tier"},
  "daily_limit": {"value": "unknown", "verified_at": "2026-11-12", "source": "pippit-tool-cli --help does not expose daily quota"},
  "limits": {"max_duration_s": {"value": 30, "verified_at": "2026-11-12", "source": "model describe: duration.max"}},
  "expires_at": "2026-12-12"
}
```

规格里：`channel: "xyq"`，`models: {"draft": "Seedance_2.5_draft", "lowres": "Seedance_2.5", "final": "TODO_VERIFY_LIVE"}`。`final` 见下方「成片」一行的核法。

### 三档命令模板

| 档 | `--id-field` | `--` 之后的适配器命令 |
|---|---|---|
| 草稿 | `thread_id`、`run_id`（各写一次） | `pippit-tool-cli generate-video --model {model} --draft --task-type reference --prompt {prompt} --ratio {ratio} --duration {duration} {refs:--image}` |
| 低清（无草稿档时） | 同上 | `pippit-tool-cli generate-video --model {model} --resolution 480p --task-type reference --prompt {prompt} --ratio {ratio} --duration {duration} {refs:--image}`（`480p` 取自 2026-11-12 `model describe Seedance_2.5` 的 `resolution.options`） |
| 成片（草稿已点头） | 同上 | `pippit-tool-cli generate-video --model {model} --draft-task-id {draft:draft_task_id}`：继承草稿的 seed 与参考，画面不变，不再传提示词。`TODO_VERIFY_LIVE: xyq_final_model`——`models.final` 填哪个 key、成片分辨率与单价都没实测过；第一次转成片前先 `model describe` 两个 key 并把报价给用户，结算后用 `settle --reported-model` 记回执模型，再把核实结果写回本节 |

完整一行（草稿，`--dry-run`）：

```bash
python3 scripts/ledger_submit.py submit --project <项目> --shot <镜号> --tier draft \
  --id-field thread_id --id-field run_id --dry-run -- \
  pippit-tool-cli generate-video --model '{model}' --draft --task-type reference \
  --prompt '{prompt}' --ratio '{ratio}' --duration '{duration}' '{refs:--image}'
```

占位符在 shell 里加单引号，避免花括号被展开。

### 回读、找回与余额

- 结果：`pippit-tool-cli query-result --thread-id <thread_id> --run-id <run_id> --download-dir <项目>/clips/<镜号>`。`"completed": false` 是排队，不是失败；`completed: true` 且有 `videos[0]` 才算出片。然后 `ledger_submit.py settle --take <take> --state succeeded --file clips/<镜号>/<文件> --job-id draft_task_id=<videos[0].draft_task_id> --duration-s <秒>`——草稿档必须把 `draft_task_id` 记进去，成片档的 `{draft:draft_task_id}` 只从这里取。
- 状态未知（超时、无 ID）：有 `thread_id` 就 `pippit-tool-cli get-thread --thread-id <id>` 查；连 ID 都没有，去小云雀网页历史找，找到后 `settle --state submitted --job-id thread_id=… --job-id run_id=…`。不重提。
- 余额：`pippit-tool-cli get-credit-balance > <项目>/qc/xyq_balance.json` 读 `total_remain_amount`（单位：积分），然后 `ledger_submit.py balance --channel xyq --amount <数> --unit 积分 --source "pippit-tool-cli get-credit-balance" --readback-file qc/xyq_balance.json`。试价结算后（及任何失败/`unknown` take 后）再读一次并附回读文件，草稿批次门才会放行。
- 输出第一行可能是「本次空间：…」的提示，后面才是 JSON；`ledger_submit.py` 会从中取 ID，不需要处理。
