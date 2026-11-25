用途：仅为明确目标是抖音短剧的项目提供平台条件化，不替代通用叙事、生成与发布验收。
触发条件：用户明确写出“抖音”且作品是短剧；触发后本文件与 [failure-diagnosis.md](failure-diagnosis.md) 末节“仅在抖音模块启用时使用”同时生效，不复制其诊断表。
分界：[platform-packaging.md](platform-packaging.md) 管分平台交付物，[platform-risk-and-compliance.md](platform-risk-and-compliance.md) 管通用合规；本文件只管抖音短剧增量。

# 抖音短剧条件化模块

## 适用开关

同时满足“明确写抖音”和“短剧”才启用。以下单独出现均不触发：

- 红果；
- 竖屏；
- TikTok；
- 快手；
- 视频号；
- “短视频”或“社媒”。

如果目标仍含糊，保持通用路径，不把相邻平台、画幅或内容形态推断成抖音。“抖音 + 广告／带货”走 Lane C，只读取 [platform-packaging.md](platform-packaging.md)，不启用本短剧模块。

## 默认与阻塞问题

- 默认画幅：`9:16`，并立即标 `TODO_VERIFY_LIVE: aspect_ratio`（）。这是平台惯例，非法规；用户显式指定可覆盖。
- brief 未指定交付时长时，把时长列为最多两个阻塞问题之一，不先套写作节拍。
- 只有用户回答“无所谓”时，才采用约 `60–90 秒`，并立即标 `TODO_VERIFY_LIVE: delivery_duration`（）。
- 本文件唯一硬上限是单集 `<20 分钟`，提交前仍标 `TODO_VERIFY_LIVE: national_duration_ceiling`（来源日期 2026-07-31，2026-09-01 施行）。
- 受众默认泛娱乐；brief 明示年龄、圈层、题材分级或观看场景时覆盖。

## 选题增量

优先组合情绪入口、可见反差与待解好奇，但它们只是候选发动机；先服从题材、人物欲望、关系逻辑与可见代价。冲突／逆转 Lane 的完整规则读取 [story-short-drama.md](story-short-drama.md)，本文件只增加平台侧选择顺序，不复制通用叙事规则。视觉预设只定外观，不得用换风格掩盖脚本问题。

## 节奏与钩子观察

- 用“快开场、分段刺激、结尾续看点”检查方向，不把它们改成固定节拍门。
- “前 `2–3 秒`”只作 `rubric-v2` 的可测试观察项，并立即标 `TODO_VERIFY_LIVE: hook_window`（）；观察不计分、不是门。
- 不写完播率数字或统一阈值；只用同账号、同入口、相近发行阶段的真实数据比较，并标 `TODO_VERIFY_LIVE: completion_rate_threshold`（）。
- 测钩子时只改开场，把人物、场景、视觉与其他叙事变量锁住；纸面候选先做同条件声画预演，再回看是否仍成立。

## 镜头与生成难度

近景与中近景优先，让人物关系、动作和关键道具在目标画布内可读。多人同框、复杂大场景与高难运镜一律标“生成难度高”，并至少给一种替代拍法：拆成主镜与反应镜、用近景覆盖宽景、减少交叠主体，或改为固定机位加确定性后期。竖屏版本从策划阶段独立构图，不把横屏母版居中裁切当完成。

红果《关于规范AI剧角色创作的公告》（2026-08-03；行业媒体转载 https://lmtw.com/mzw/content/detail/id/256831 ，`TODO_VERIFY_LIVE: hongguo_ai_drama_rule`）：针对都市类 AI 短剧额外要求配音与角色口型精准同步；摒弃单一怼脸流水线镜头；全剧角色样貌与画风全程统一，AI 分段生成造成的人物变脸、画面畸形、表情僵硬不过审。投红果或抖音 AI 剧时，把口型同步、镜头语言多样性与跨段角色一致性当审核项处理，按 `production-qc.md` 的视觉/听觉 QC 逐镜验收，不只当作质量偏好。

## 提交前合规核对项

- AI 标识：核对每集明显位置的生成提示要求（第三十四条；来源日期 `2026-07-31`；提交前 `TODO_VERIFY_LIVE: ai_label_rule`）。
- 片头标识：核对剧名及适用许可、批准文件或节目编号的明显标注（第二十七条；来源日期 `2026-07-31`；提交前 `TODO_VERIFY_LIVE: opening_label_rule`）。
- 负面清单：核对儿童伤害、色情擦边、拜金炫富、畸形婚恋、封建糟粕、暴力复仇、低俗片名与侵权盗版等当期高风险题材（来源日期 `2026-06-03`；提交前 `TODO_VERIFY_LIVE: negative_list`）。
- 废止项：确认 `T/CEAP 1-2025` 仍为废止状态，不把其中旧时长或画幅写成现行规则（废止日期 `2025-11-19`；提交前 `TODO_VERIFY_LIVE: revoked_standard_status`）。
- 分类与准入：只按广电总局当期的许可证、备案号与平台审核口径判断，并标 `TODO_VERIFY_LIVE: classification_and_filing`（）；不写授权金额。

## 平台证据门

查询模板、证据升级规则与三段式结果见 [platform-risk-and-compliance.md](platform-risk-and-compliance.md) 的「## 平台证据门」；本文件的 `<平台>` 取「抖音短剧」，未升级项写 `TODO_VERIFY_LIVE: douyin_<topic>`（）。

抖音 AI 素材侵权预检工具：官媒转述存在该入口（2026-09-15），控件位置与字段需实时核验，`TODO_VERIFY_LIVE: douyin_ai_asset_precheck_ui`。

