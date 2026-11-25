# Lovart 执行防错

本文件整理 Lovart 通道的执行防错与 Agent 交互注意点。锁脸与已批准素材续写见 [face-consistency-execution.md](face-consistency-execution.md)，provider 选择与预算见 [provider-execution.md](provider-execution.md)。

## 参数与实际模型

- 模型 ID 逐字从当前 adapter/live 回执核对。`generate_video_seedance_2_0` 曾报 ROUTING_FAILED；对应正确拼写为 `generate_video_seedance_v2_0`。不要凭空补写名字。
- `--prompt` 不是 `--message`。先查当前 help，不能猜 tools 等子命令。
- `--prefer-models` 是请求偏好；`--include-tools` 也不能仅凭参数存在就宣称硬锁成功。记录 requested_tool、reported_tool、产物规格；没有可信实际调用回执则模型身份未核验。
- 跑了多久、Agent 承诺、1080p 文件都不能证明调用的是 2.5。批量前先核验一次真实调用，不能用“90秒还在running”验模型名。

## 三层状态

- shell rc=0 ≠ 服务成功 ≠ 新产物成功。依次检查解析、failures/pending_confirmation/status 和实际文件。
- timeout 或 RemoteDisconnected 后先用原 thread 的 status/result 恢复；禁止盲目重提可能扣费的请求。
- `downloaded[].new` 不保证是本次新生成：更换 output-dir 会把旧 URL 再下载为 new=true。按已有 artifact URL/ID 集合排除旧产物，再核对生成事件和文件；不要依赖文件列表末项。
- 轮询保存完整 JSON/原始输出、设置总截止时间；遇 pending_confirmation、失败或 done无新产物就停。不要仅寻找 new=true 或把解析失败写成问号继续无限跑。
- 同一 thread 串行；仍 running 时不追发依赖请求。清进程按准确 PID/session，不用泛匹配 pkill 误杀其他任务。

## 费用

- `query-mode` 的 unlimited 只说明模式与返回的具体权益，不代表端到端免费。
- 已观察到：模型生成可被 unlimited 覆盖，但执行请求的 Agent 推理仍需积分；余额不足会在开始请求前失败，报错原文 `Insufficient credits to start the request. Unlimited covers generation models only — the agent … still needs a credit balance`。
- 不猜某模型免费、某档更便宜或最低充值额。pending_confirmation 的实际报价须向用户说明并得到明确批准，不能自动确认。
- 一次确认只覆盖该次报价，不能外推为后续所有任务无限授权。

## 提交与日志

- 长提示词保存为文本，Python subprocess 使用参数数组传递，避免 shell 引号和截断；经 shell 拼接会以 `zsh:4: unmatched '` 让任务 exit 1。不要将展示中的 [truncated] 当命令正文。
- 避免 `2>&1 | tail` 吞掉错误和退出码；保留完整 stdout/stderr，传播子进程 returncode。
- 单文件要求写清只生成一个文件、节拍在同次生成内完成、不要中间分镜图。但最终仍按真实文件数/时长验证，不由 Agent 的确认文本推断。

## 交互行为

### Agent 会停下来问“要开始生成吗”

返回 `status: done` 但 `generation_succeeded: false`，无产物，`agent_message` 是分镜方案 + “Shall I proceed?”。

`confirm` 子命令对这种情况无效，报错原文：

```
Error: Scheduler restore failed with status 500:
{"error":"No waiting or feedback step found"}
```

它只适用于正式的 pending_confirmation，不适用于 Agent 自发提问。正确做法是同 thread 追发消息：

```bash
python3 agent_skill.py chat --thread-id <TID> --json --download \
  --output-dir <dir> --prefer-models '...' \
  --prompt "Yes. Proceed now. Do NOT ask any further questions and
do NOT reply with text only. Generate the video immediately."
```

预防：首次提交就写进提示词「Generate the video immediately, do NOT ask questions, do NOT reply with text only.」

### 一次提交会吐多个文件

多节拍请求下，单次任务可能同时返回 1 个完整合成视频与若干拆分的分镜视频（部分可能无音轨）。取回后须先对每个文件跑 `ffprobe`，按时长与音轨区分完整版与分镜，不要假设每次只产出一个文件。

### timeout 不等于失败

```json
{"status": "running", "final_status": "timeout", "downloaded": []}
```

这是客户端等待窗口到期，服务端仍在跑。用 `status --thread-id` 回读真实状态，别重提。区分真失败：`failures` 数组非空（如 `ROUTING_FAILED`）才是真挂。错模型名会秒返 `ROUTING_FAILED`；但「跑了多久还在 running」不能反过来证明模型名正确，模型身份一律按上文 `requested_tool / reported_tool` 回执核验。

### pkill 别用宽泛匹配

清理错模型名任务时用宽泛 pattern，连带杀掉了正确的任务。按准确 PID/session 清理，杀完用 `pgrep -fl` 核对幸存者，确认该活的还活着。

## 产品面补充

MCoT、Touch Edit、Brand Kit、Auto 与 `@` 锁模型为 Lovart 公开产品描述。使用时按当日页面重读；Auto 不等于已锁 exact model，`@` / `--include-tools` 仍要回读 requested/reported。`TODO_VERIFY_LIVE: lovart_mcot_touch_brand`。

## 回归样例

- rc=0 + failures → 失败，不是成功。
- new=true + 历史 URL → 旧产物，不推进下一段。
- timeout + running → 有界查询，不重新生成。
- unlimited + insufficient credits → 费用阻塞，停止重试。
- requested 2.5 + reported 2.0 → 报告不一致，不说2.5已经锁住。

## 短剧提交配方（`ledger_submit.py` 用）

脚本路径示例：`<skills_dir>/lovart-api/scripts/agent_skill.py`（下称 `<lovart>`），使用前先跑 `--help` 确认参数；密钥仅从 `LOVART_ACCESS_KEY` / `LOVART_SECRET_KEY` 环境变量读取，不写进命令。模板只能经 `ledger_submit.py submit … --` 使用，先 `--dry-run`；不要直接调用 `chat`。

### 能力卡初始值

```json
{
  "recipe": "references/lovart-execution-notes.md",
  "draft_tier": {"value": false, "verified_at": "2026-11-09", "source": "real submissions: no draft mode, lowest offered was 480p"},
  "draft_upgradable": {"value": false, "verified_at": "2026-11-09", "source": "no draft-to-final path; a final is a new generation"},
  "balance_query": {"value": false, "verified_at": "2026-11-12", "source": "agent_skill.py --help lists no balance command"},
  "recover_by_id": {"value": true, "verified_at": "2026-11-12", "source": "result --thread-id / status --thread-id"},
  "ref_transport": {"value": "URL attachments: upload each ref once, record its url in the spec refs", "verified_at": "2026-11-12"},
  "plan_required": {"value": "unknown", "verified_at": "2026-11-12", "source": "agent_skill.py --help lists no plan tier"},
  "daily_limit": {"value": "unknown", "verified_at": "2026-11-12", "source": "agent_skill.py --help lists no daily quota"},
  "limits": {"max_duration_s": {"value": 20, "verified_at": "2026-11-09", "source": "a 20 s clip was delivered; lower bound seen, not the official maximum"}},
  "expires_at": "2026-12-09"
}
```

`max_duration_s` 没有零成本的查法：`TODO_VERIFY_LIVE: lovart_seedance_max_duration`。上面的 20 是实际出过片的下限；要用更长时长，先让用户在 Lovart 网页上看当前上限，再把值和日期写回卡。查不到余额，所以试价后草稿批次门要用户原话：`ledger_submit.py confirm --kind unknown-cost --channel lovart --user-words "<原话>"`。

规格里：`channel: "lovart"`；`models` 三档都填工具名 `generate_video_seedance_v2_5`；`refs` 每项多一个 `url`，来自 `<lovart> upload --file <参考图>` 的返回值（上传不生成内容，但仍只在身份锁定后各传一次）。

### 两档命令模板

没有草稿档，按 `drama_next.py` 的规则先出低清（`lowres`），用户点头后再出成片（`final`，整条重新生成，画面会与低清不同，交付前要重新逐镜验收）。

| 档 | `--id-field` | `--` 之后的适配器命令 |
|---|---|---|
| 低清 | `thread_id` | `python3 <lovart> --timeout 150 chat --json --mode fast --include-tools {model} --prefer-models '{"VIDEO":["{model}"]}' --attachments {ref_urls} --prompt 'Generate the video immediately with one single call to {model}. Do not ask questions, do not reply with text only, do not make storyboard images, do not split into multiple clips, do not rewrite or translate the dialogue. Settings: aspect ratio {ratio}, duration {duration} seconds, lowest available resolution, native audio on. The attached images are references in the order the prompt names them. {prompt}'` |
| 成片 | `thread_id` | 同上，把 `lowest available resolution` 换成用户点头的分辨率。`TODO_VERIFY_LIVE: lovart_final_resolution_price`：成片单价与可选分辨率没有零成本查法，提交前把这一条的报价问题当面交给用户 |

- 没有参考图的镜头，把 `--attachments {ref_urls}` 两项一起删掉。
- `--timeout 150` 是 `agent_skill.py` 自己的等待窗口，要短于 `ledger_submit.py --timeout`（默认 300 秒）：这样即使视频还在生成，`chat` 也会带着 `thread_id` 按时返回，台账记成 `submitted`，不会因为被杀掉而变成 `unknown`。
- 开头那句「立即生成、不要提问」是防 Agent 停下来问方案（见上「交互行为」）；它属于本通道的适配器语法，不是通用提示词句式。

### 回读、找回与确认

- 结果：`python3 <lovart> result --thread-id <thread_id> --json --download --output-dir <项目>/clips/<镜号>`。先看 `failures`、`pending_confirmation`、`final_status`，再看下载到的文件；一次可能吐多个文件，按 ffprobe 时长与音轨挑完整那条（见上「一次提交会吐多个文件」）。然后 `ledger_submit.py settle --take <take> --state succeeded --file clips/<镜号>/<文件> --reported-model <回执里的工具名>`。
- `pending_confirmation`：把报价原样告诉用户，得到原话才 `python3 <lovart> confirm --thread-id <id> --json --download --output-dir <目录>`。
- 状态未知：`python3 <lovart> threads --json` 列本机保存过的线程；不在里面就去 Lovart 网页历史找，找到后 `settle --state submitted --job-id thread_id=…`。不重提。
