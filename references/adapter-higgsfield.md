# Higgsfield NBP v2 适配器

`python3 scripts/render_nbp_adapter.py --target higgsfield --schema auto` 接收通过校验的 NBP v2 video 对象（或先规范化为 v2 IR 的 Simplified JSON），输出交接字段，不直接提交任务。真实提交仍走当前宿主可用且获授权的 `higgsfield-generate` adapter，并读 [provider-execution.md](provider-execution.md) 的预算与 live schema。本文件不复制 CLI/API 全文。

## 产品面落点（UI 待核验）

下表把公开产品面观察到的入口对到本 Skill 环节。功能名、按钮、套餐与模型列表以当日 UI 为准，逐行 `TODO_VERIFY_LIVE: hf_<feature>_ui`。不写积分价格、单次秒数或参考图配额数字。

| Higgsfield 入口（公开描述） | 本 Skill 落点 | 照跑的门 |
|---|---|---|
| Popcorn / storyboard | Lane B 导演包、决策分镜 | 自动分镜先过「只画会决定戏的分镜」；提示词重编译为 Simplified JSON → NBP v2；仅网页工作台可用 |
| Soul / Soul ID | [keyframe-assets.md](keyframe-assets.md)、[face-consistency-execution.md](face-consistency-execution.md) | 身份参考批准后冻结；官方建议参考数量 `TODO_VERIFY_LIVE: hf_soul_id_ref_count`（社区常见「20+」只作待核线索，不是合同） |
| Cinema Studio 2.5–4.0 | 分镜直出、参考视频、白模底片进成片 | 成片不得继承灰模材质；继承契约见 [blender-previs.md](blender-previs.md)、[whitemodel-previs.md](whitemodel-previs.md) |
| Cinema Studio 4.0 底座 | 与 Seedance 2.5 分栏记录：工作台能力 ≠ 底层模型能力 | 提交前读 exact model / live schema；`--prefer-models` 静默降级按 [lovart-execution-notes.md](lovart-execution-notes.md) 的 requested/reported 纪律核验 |
| Seed Audio 1.0 | [post-production.md](post-production.md) 配音 | 音色批准后冻结；音乐不得遮对白 |
| Supercomputer / 第三方模型路由 | 仅当用户点名且账户可见 | 换底层模型等于换 provider，走 [provider-execution.md](provider-execution.md)「换 provider 交接清单」 |

Cinema Studio 4.0 = Seedance 2.5 底座是帮助中心公开描述（https://higgsfield.ai/creator-hub/help-center/tools/how-do-i-use-cinema-studio ，取回 2026-09-15），不代表当前账户实际开通权限。未登录控制台前 `TODO_VERIFY_LIVE: hf_cs40_seedance25_binding`。

## 执行面选择

| 执行面 | 何时用 | 规则 |
|---|---|---|
| REST / platform API（`platform.higgsfield.ai` 一类公开域名） | 用户点名 API、或本机 CLI 不可用且用户授权 HTTP 提交 | 只构造当日 schema 中存在的字段；参数名 `TODO_VERIFY_LIVE: hf_rest_schema` |
| 本机 CLI / `higgsfield-generate` | 宿主已发现该 adapter | 先查账号、model/workflow catalog、exact schema、素材职责与真实报价；Marketing Studio 的 mode slug 以 live schema 为准 |
| 网页控制台 | 用户选择网页执行，或已核实必须在网页使用的入口/权益 | 按当前浏览器技能操作；核对实际账号、选中模型、素材、档位及 Generate 报价，不能把网页宣传权益套给 CLI/API |

用户明确要求 computer-use 操作网页时，不要改走 MCP 或未点名的插件。Blender 插件、MCP Bridge、3D Jutsu 只在用户点名且重新核验权限后使用，见 [blender-previs.md](blender-previs.md)「执行界面选择」。

## 模型/工作流发现与产品别名

1. 先查 live model catalog；专用动作控制等能力可能在 workflow catalog，使用 `higgsfield workflow list --json` 继续发现，再读取实际条目的 schema。普通模型列表无匹配不是功能不存在的证据。
2. 区分报价与创建语法：workflow 报价接口的 `workflow` 选择器不能机械复制到 `generate create` 的 job-type 位置；创建前按 live 帮助和 adapter 的已验证语法构造请求。参数本地拒绝与远端 accepted 分开记，不把前者算作已生成或以此重投后者。
3. 将截图/UI 显示名映射到实际 job type，并回读已有同类任务。`NEW` 徽标、入口改名或多参考能力不证明底层模型、审核政策已变或整段身份能稳定；不承诺未通过像素验收的修复效果。

## 参考素材选入与提交回读

先分离本作获准的语义职责，再映射 live schema 的 media flags：源视频只承担获准继承的背景、动作、时序与镜头；身份卡只承担精确选中角色的身份，不带入卡内衣服、道具或室内背景；穿搭图只承担指定服装/头巾/配饰，不带入图中人物身份或无关地点。身份未获准从穿搭图继承时，保留原图并记录无脸裁图的来源/用途。参考职责清楚只是输入合同，不保证像素替换成功；普通身份参考图也不等于已调用 native Soul ID 条件字段，按真实提交方式报告。

1. 复用已批准、内容可核验的缓存资产。网页端先确认按钮打开的是站内素材选择器还是原生文件选择器；按已验证资产选取，只有实际 Upload media 控件触发文件选择时才传本地路径，避免混用。
2. 上传完成只证明进入素材库，不证明已选进当前请求。网页关选择器后回读当前表单的实际参考数量、顺序与职责，不因 gallery 出现新图就假定它已入选；CLI 则核实际 flags 和输入顺序。
3. 网页上传、异步加载或关闭 modal 后重新定位当前 Prompt 输入框，不沿用旧快照的临时元素编号。各通道提交前都回读提示词、选中模型、档位和最终报价。
4. Accepted 后用 `higgsfield generate get <job_id> --json` 回读确切任务的 reported type/mode、参数调整和实际素材条目（例如 `params.medias`），逐项匹配批准映射的数量、角色与顺序。取实际远端内容：未变换的素材比较字节/SHA-256，转换后的图像先按已记录的 resize/crop 解码对齐比较，不能把 UUID 相同当内容证明。
5. 逐项记录输入 verified/unknown/mismatch。远端输入一致可排除已验证范围内的误传，不证明生成器遵守了身份/服装指令；仍漂移或旧衣未替换时，保留像素失败而不编造上传或模型根因，也不重提任务来补回执。

## 单次授权派发与恢复

这组步骤只约束 adapter 的实际 dispatch，不替代 [provider-execution.md](provider-execution.md) 的报价、预算与授权合同：

1. 最后核价与配置后、付费 create/Generate 之前，建立任务级独占派发标记，绑定有效授权、支出/accepted-job 上限、实际模型/模式、Prompt hash 与素材映射；原子创建标记，已有标记时进入恢复而不再提交。
2. 一次 create 后保存返回任务并回读；中断或回执丢失时用 `higgsfield generate list --json` 找回、用 `higgsfield generate get <job_id> --json` 核对，等待既有任务而不重新 create。参数本地拒绝只在证实没有远端任务/扣费后才纠正；accepted 后视觉失败、审核拒绝或退款都不恢复原单次许可。
3. Download 后按 [production-qc.md](production-qc.md) 分验技术、视觉与 brief。拒收时把标记留在 consumed/recovery-only 终态，生成与验收可记已结束，但原成片目标仍未完成；不要把待授权或验收中当作拒收后的当前状态。

### 网页单次提交保护：预检与真实派发分开

仅在已获准的原生网页执行分支使用，不另建绕过认证的客户端：

1. 表单稳定后、点击前保存真实报价快照，再绑定模型、模式、媒体、张数、时长与权益；不要等到 fetch 发生才读 Generate 文本，因为按钮届时可能已进入加载态。
2. 需要阻断预检时，在转发前拦截所有生成写请求。解析 fetch 时兼容 string、URL 与 Request：从 `input.url` 或 `input.href` 取地址，从 `init.method` 或 `input.method` 取方法，从 `init.body` 或 Request 的 clone 取请求体；检查是否实际走 XHR。只保存脱敏的目标请求，不存认证头或临时签名链接。
3. 捕获后核对最终请求中的人物图、完整源视频、原生朝向/背景参数及权益。将本地主动阻断与远端 accepted 分开，状态不清先对账任务和扣费。
4. 预检结束后重新加载页面，再回读表单、媒体、报价及 Unlimited 状态；重新安装单次 guard，不堆叠旧拦截器，也不假设 reload 保留了权益开关。应用可能持有旧 fetch 引用，单独覆盖 window.fetch 不一定清除旧闭包。
5. 用点击前报价与已核配置校验实际请求；配置变化则拒发。发往网络前消耗单次 send 标记，立即保存回执；响应丢失按歧义恢复，不自动重新武装。若当前端点同时有顶层和 params 内权益标记，两处都核验，不把这个字段形态推广到所有模型。
6. 回读同一 accepted job 与余额，再轮询原任务；按本文件的素材回读步骤核验实际内容，不仅检查 ID。防重只证明提交受控，不证明视频复制了动作或镜头。

## CLI 模式与参数要点

以下为基于零成本只读探测（`higgsfield account status`、`model list/get --json`、`workflow list --json`）整理的 CLI 参数要点，`verified_at=2026-11-24`，复核随 `references/model-capability-matrix.json`；提交前仍读当日 schema。

### 草稿升级：CLI 与 REST 是两套 ID

| 执行面 | 草稿 | 升成片 | 记账 |
|---|---|---|---|
| CLI（`seedance_2_5`） | `draft: true` 出 480p 草稿，回执给 `job_id` | 新建一次 create，带 `--draft_job_id <草稿 job_id>`；`draft` 与 `draft_job_id` 互斥 | 草稿与成片是**两次计费、两个 job ID** |
| REST | 草稿回执给 `draft_id` | 调 `finalize-draft`，传 `draft_id` | 同样两次计费；`draft_id` 与 CLI 的 `job_id` 不可互换 |

- ledger 每个 take 同时记 `draft_job_id`（或 `draft_id`）与成片 `job_id`，两笔扣费分开归因；不要因为「已经付过草稿」把成片当免费。
- 升级请求超时或回执丢失：先用 `higgsfield generate list --json` / `get <job_id> --json` 找回，确认没有已 accepted 的成片任务前不重发，否则会重复扣费。
- Cinema Studio 4.0（`cinematic_studio_video_4_0`）workflow schema 没有 `draft`／`draft_job_id`，`resolution` 只到 1080p；要草稿就走底层 `seedance_2_5`，并在通道能力卡写明草稿与成片不同入口。

### `--prompt` 不能以 `@` 开头

CLI 会把以 `@` 开头的 `--prompt` 当成本地文件路径读取（否则 CLI 会报错退出）。canonical 标签（`@char_mira_v01`）不得放在 prompt 首字符：适配器把首个标签前置一个普通词（如「镜头：」），或改用 JSON／文件入参；`render_nbp_adapter.py --target higgsfield` 遇到首字符 `@` 时报错或按已验证转义写法改写，不静默提交。

### Soul ID 与 Cinema Studio 是不同句柄

| 句柄 | 是什么 | 用法边界 |
|---|---|---|
| Soul ID（`custom_reference_id`） | 用 20–80 张照片在 `/v1/custom-references` 训练出的持久身份 | `text2image_soul_v2` 接受它（单张 `image_reference`，与 `style_id` 互斥）；跨模型能否使用只看当次 `model get` |
| `cinematic_studio_soul_cast` | Cinema Studio 的选角 workflow | 是 workflow，不是底层模型；产出的角色图仍按 [keyframe-assets.md](keyframe-assets.md) 过身份 QC |
| `cinematic_studio_video_4_0` | 与 `seedance_2_5` 同源 schema，另加机身、镜头、光圈、年代、类型、节奏、色板、光线参数 | 光线三种写法（`light='custom'`、`light_id`、`light_custom`）互斥；workflow 报价选择器不能照搬到 `generate create` |

普通身份参考图不等于调用了 Soul ID；报告里按真实提交字段写。

### Popcorn 与 4K：都在生成之外

- Popcorn 是网页工作台的多镜头分镜预演，当日 CLI `workflow list` 中没有；只能经网页工作台（浏览器自动化桥）使用，产物是分镜图，进视频前重编译为 Simplified JSON → NBP v2。
- 4K 是后处理：`bytedance_video_upscale`（1080p／2k／4k）、`topaz_video`（1080p／2160p，可插帧）、`video_upscale` 都是独立放大模型，单独计费。交付报告分开写原生生成分辨率与放大后交付分辨率；网页低清流（736x400 一类）放大救不回脸部细节。
- 余额：每次提交前实时回读当前账户积分余额，不足时前置阻断，不按历史余额估算。

## 白模 / 底片怎么进 Cinema Studio

核心原则：Blender 预演只作为输入底片，视频生成通道输出的才是精修电影感画面。

- 底片只进 `00_previs/`，职责是机位、路径、时点、站位。
- Cinema Studio 提交时：白模/预演视频承担 `role: motion`；外观、服装、材质走批准的图片参考；**风格参考最后加**。
- 禁止把灰模 beauty RGB 当首尾帧且不经 S6 升级。升级与质量门见 [whitemodel-previs.md](whitemodel-previs.md)。
- CLI 能否直接挂预演视频、还是必须进 Cinema Studio 界面：`TODO_VERIFY_LIVE: hf_previs_video_slot`。批量提交前须先完成单条实测核验。

## 字段映射（NBP → Higgsfield）

与 `render_nbp_adapter.py --target higgsfield` 一致：canonical `@Tag` 提交前按 registry 解析为实际上传/媒体 ID，适配器不做解析。`media_roles` 只写当日 schema 承认的角色名；未核即 `TODO_VERIFY_LIVE: hf_media_roles`。

跨通道（Higgsfield 工作台 vs Seedance 直连 vs Atlas）的分辨率、时长、积分**不可比**，见 [provider-execution.md](provider-execution.md)。
