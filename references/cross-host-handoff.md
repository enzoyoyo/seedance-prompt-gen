# 跨宿主接力

用户常在一个宿主里写剧本、在另一个宿主里拍，或者中途换会话。接手方的义务是把已有的东西认下来，不是重做一遍。

## 带来的剧本是锁定输入

用户带来在别处写好的剧本，是锁定输入，不是待改的草稿。不润色、不调顺序、不补台词、不「顺手」修错别字；发现问题列给用户，由他改，改完重新锁。接手方对剧本只做一件事：给 beat 编号，且编号不改动任何一个字。

## 接手五件事

```bash
python3 scripts/audit_takeover.py --script <剧本> [--project <项目根目录>] [--spec <规格>] \
  [--clips-dir <片段目录>] [--records <旧台账.json>]… [--numbered-out <带编号副本>]
```

只读、离线，不提交、不重拍。输出一份接手报告（打印 JSON，不落 md）：

1. **编号**：列出已有 beat 编号；剧本没编号时，`--numbered-out` 写出一份只插入编号的副本，脚本自检去掉编号后与原文逐字节相同，做不到就拒绝并让人手工编号。原文件不动。
2. **映射**：每个 beat 由哪些镜头覆盖，`missing_beats` 列出没人拍的 beat。
3. **片段清点**：用 ffprobe 读每个片段的时长、尺寸、有无音轨。状态只来自 `--records` 台账里记在**这个文件名**上的验收结论：有通过 → `reuse_candidate`；有拒收 → `rejected`；没有结论 → `pending_acceptance`（待验收，不是可复用）。读不出 → `redo`，对不上在用镜头 → `orphan`。不按文件名猜含义（`_rejected`、`_t2` 之类不算证据）。同一镜有多个可用片段时列在 `shot_choices`，由用户逐镜选一条，脚本不替人选；台账里记了却不在磁盘上的文件列在 `records_file_not_on_disk`。台账里找不到任何带状态或文件的记录（`UNRECOGNIZED_LEDGER`）、或验收词不认识（`UNRECOGNIZED_VERDICT`），直接报错，向用户问清结构，不猜。
4. **无 ID 记录**：旧台账里有状态却没有任何任务 ID 的提交，列在 `records_without_id` 交给用户，去通道自己的历史里找回；**不重提**。
5. **绕门脚本告警**：扫描项目目录内直接调用通道生成命令（未走 `ledger_submit.py`）的手写 `.py`/`.sh` 脚本，在 `bypass_scripts` 与 `warnings`（`BYPASS_PROVIDER_SCRIPT`）里列出文件、行号与通道名（只告警，退出码仍为 0）。

报告之后回到 `drama-gates.md` 的门序：锁剧本 → 发布意图 → 白模 → 身份 → 规格。用户选定的片段写成规格里该镜的 `reuse`，再由 `drama_next.py` 指到 `ledger_submit.py reuse` 入账，之后照样过四项逐镜验收（`accept`）——`reuse_candidate` 也不例外，这是旧片段进入 `takes[]` 的唯一通路；`rejected` 永不复用；`redo` 与 `missing_shots` 才进入提交。

## 交出去时

换宿主或结束会话前，项目目录里应当只凭文件就能续上：`resume-manifest.json`、`script.lock.json`、镜头规格、片段与 `qc/` 证据。口头进度不算交接；`drama_next.py` 在新宿主里跑出的门，就是交接结论。

## 写作宿主观察

写作阶段用哪个宿主是用户的选择。当前带日期的实测观察登记在 `model-adaptation.md` 的「写作宿主观察」，接单时提醒用户一次即可；它是会过期的观察，不是规则，也不改变「在哪里问就用哪里的模型写」。
