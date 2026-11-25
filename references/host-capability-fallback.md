# 宿主能力退化

本 Skill 在 Hermes、Cursor、Claude Code、Codex、agy 上共用一份源码。宿主没有某工具时，**降级交付，不假装已经提交**。

## 探测顺序

1. **宿主原生工具**：当前会话里真实可调用的 image/video/browser/CLI 工具。
2. **本机 CLI**：`command -v` 能发现、且用户授权使用的 `pippit-tool-cli`、`blender`、adapter 技能里的可执行文件。
3. **手工交接包**：只交可复制 Prompt、NBP JSON、参考职责与「请在网页粘贴」步骤，并标 `NOT_SUBMITTED`。

没有探测到就停在更低一级，不编造 adapter 名、不编造已提交 job。

探测结果用 `python3 scripts/list_execution_providers.py` 打印成 `### 执行选择` 表（只报凭证名与 present/missing）；用户没点名 provider 时就停在这张表等选择，规则见 [provider-execution.md](provider-execution.md) 的「执行选择门」。图片/视频内容分析默认走 `agy --model "${AGY_MODEL:-gemini-2.5-pro}" --effort high`；本机没有 `agy` 时标 `ANALYSIS_SKIPPED`。

## 三级退化

| 级 | 条件 | 交付 |
|---|---|---|
| 自动提交 | 已发现 adapter、凭证/额度核对通过、用户授权付费任务 | 提交 → 轮询 → 本地下载 → 完整 decode → QC |
| 可粘贴命令 | 有 CLI 但缺凭证、额度、权限，或用户未授权提交 | 给出可复制命令与参数；标明尚未执行 |
| 只交 Prompt 包 | 没有对应工具 | NBP JSON + 适配器文本 + `NOT_SUBMITTED`；不写「已生成」 |

搜源工具（Grok、豆包、网页检索）不可用时，趋势与平台数字一律标 `RESEARCH_SKIPPED`，不拿训练记忆顶替 URL+日期。

## 同会话切 Skill

从别的 Skill 回到本 Skill 时，重述当前作品的资产、已批准 take、画幅与目标端；不沿用另一 Skill 的风格结论。压缩或轮次上限打断时，先写 [sequence-resume.md](sequence-resume.md) 的 manifest 再停。
