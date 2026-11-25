# 短剧后期生产线

后期不是“生成失败后的补丁”，而是把独立镜头、表演、声音与平台交付组织成可控成片。对白短剧默认声音先行；生成阶段尽量保留干净画面和可分离音轨。

## 易变能力门

凡涉及模型时长、分辨率、原生音频/口型、插帧/超分能力、价格或平台交付规则，一律标注：**快照 2026-08-24，生成/发布前 live 校验；默认 14 天过期**。未核实的插件或模型能力标 `TODO_VERIFY_LIVE`。

## 声音先行

```text
锁对白 -> 生成/录制干声 -> 提取波形时间戳 -> 注入镜头提示词
-> 生成表演 -> 对白/口型精修 -> 四层混音 -> 字幕 -> 成片
```

1. **锁台词**：明确说话者、原句、语气、停顿、抢话与句尾动作。每次改词都让旧口型版本失效。
2. **先做干声**：TTS 或录音按角色分文件，保存音色来源、授权、版本和语速/情绪设置；不要先混 BGM。
3. **取时间锚**：从波形标出词组边界、爆破音、重音、呼吸、停顿和情绪峰值，形成可粘贴时序表。
4. **注入生成**：把台词、时序和对应肢体动作写入 `audio`/`action`/`motion`，明确谁说话；生成模型只负责当前已验证的音频能力。
5. **回到时间线**：选择表演最好的 subshot，再决定用原生音轨、独立 pickup 或后置 Lipsync；不要为保一条坏音轨牺牲画面。

生成阶段原则：现场拟音可保留，BGM 留到后期。原生音频、语言、多人说话与口型未 live 核验时写 `TODO_VERIFY_LIVE`，不承诺同步。

## 四层音频

| 层 | 内容 | 处理门 |
|---|---|---|
| 1. Dialogue / VO | 对白、旁白、呼吸与必要 pickup | 可懂度优先；角色音色、空间位置和句间噪声连续。 |
| 2. Hard Foley / Contact SFX | 脚步、衣料、触碰、开关、撞击、机械动作 | 对准接触帧，补足重量和材质，不用音量掩盖错误动作。 |
| 3. Ambience / Room Tone | 房间底噪、风雨、远景交通、空间混响 | 跨 cut 保持同一空间底床；换场才允许声场改变。 |
| 4. Score / Musical Cues | 配乐、情绪垫乐、主题动机 | 在情绪转折进入，主动为对白让位；单独保存 music stem。 |

不要在生成阶段把对白、环境和音乐焊成不可拆的一轨。Suno 生成、take 选择、响度测量、sidechain ducking 与 FFmpeg 验证直接复用 [audio-music-ducking.md](audio-music-ducking.md)，本文件不复制其命令和固定参数。

### 原片音轨无损回接（参考改写时）

仅当 brief 要保留原片声音、生成画面需要回接该音轨时启用；`generate_audio=false` 不证明原音乐会自动保留。

1. 先 `ffprobe` 原片和原生 take，确认要保留的音轨、编码、声道、采样率、起始时间及视频/音频各自时长。保留原生文件，只写新的 take。
2. 容器支持原编码时，显式映射生成视频和批准的源音轨并 stream-copy。下面示例保留原片第一条音轨，实际路径与音轨按本作核验结果替换：

   ```bash
   ffmpeg -v error -n -i "generated_raw.mp4" -i "source.mp4" \
     -map '0:V:0' -map '1:a:0' -c:v copy -c:a copy -movflags +faststart \
     "take_with_source_audio.mp4"
   ffprobe -v error -show_streams -show_format -of json "take_with_source_audio.mp4"
   ffmpeg -v error -i "take_with_source_audio.mp4" -f null -
   ```

   不用 `-shortest` 静默裁切，不补静帧/循环/变速来伪造整个原片。若容器不接受原音频编码，明确报告需更换容器或经批准转码，不静默转码后宣称无损。
3. 把源与结果音轨解码成相同 PCM 表示再计算哈希，程序化比较两项结果；只有相等才登记 `original_audio_pcm_hash_equal=true`：

   ```bash
   ffmpeg -v error -i "source.mp4" -map 0:a:0 -c:a pcm_s16le -f hash -hash sha256 -
   ffmpeg -v error -i "take_with_source_audio.mp4" -map 0:a:0 -c:a pcm_s16le -f hash -hash sha256 -
   ```

   哈希相等证明这条解码音频的内容相同，不独自证明呈现时间、动作节拍或尾部声画同步；再核流起始时间与时长，并完整音画合看确切输出文件。
4. 音频回接不升级视觉验收。原生视频短于源片时继续保留时长差和 coverage 待核；视觉失败的回接版仍是 `01_takes/` 中的 rejected/diagnostic，不因有原音乐或容器时长变长而进入 `02_final/`。

## 多 Take 预算

> 下表是起始生产预算，不是模型规格。数值按：**快照 2026-08-24，生成/发布前 live 校验；默认 14 天过期**；提交前结合当前积分价格、失败率和交付风险重算。

| Tier | 镜头 | 起始预算 | 通过标准 |
|---|---|---:|---|
| Tier 1 | 高潮、核心对白、身份揭示、集尾悬念、品牌英雄镜 | `5–10 Takes` | 表演、身份、动作、声音和连续性同时可用；先生成最高风险代表镜头。 |
| Tier 2 | 常规叙事、反应镜、动作过场 | `3–5 Takes` | 叙事功能完整，能与前后镜顺接；允许把兼容 subshot 组合。 |
| Tier 3 | 环境空镜、插入、背景转场 | `1–2 Takes` | 信息清楚、无伪文字/水印/闪烁，能安全剪入。 |

每个 take 记录 model/schema 时间、prompt 版本、结果路径、可用 in/out、保留/拒绝理由和 continuity 状态。预算耗尽先诊断资产、动作、镜头、声音中的唯一变量；不自动继续抽卡。

## 画面后期链

### 1. 选镜与粗剪

- 按镜头功能选 subshot，不要求一条生成承担完整场次；
- 先锁动作因果、视线、屏幕方向和道具状态，再追求花哨节奏；
- 在 cut 两侧检查 `continuity_out -> continuity_in`，错误状态不能靠快切掩盖；
- 图片锁前先保留对话与拟音调整余量。

### 2. 补帧、去闪与增稳

只对明确问题使用：帧率转换、速度重映射后的卡顿、局部闪烁或非意图抖动。先切出问题区间，再单变量处理；检查重影、双轮廓、手指复制、嘴部糊化和运动边缘。意图性手持、快门拖影和 hit-stop 不能被自动增稳抹掉。

插帧模型、目标帧率与输出分辨率属于：**快照 2026-08-24，生成/发布前 live 校验；默认 14 天过期**。报告中区分模型原生帧率/分辨率与后期交付规格。

### 3. Lipsync 与中性唇衔接

- 对白起始参考帧优先中性闭唇或自然静止唇；避免首帧已经是极端元音口型；
- 一镜优先一个清晰可见说话者，多人抢话拆 pickup 或切反应镜；
- 以音轨驱动口型，再检查眼动、下颚、脸颊、呼吸与头部节奏，不只看嘴；
- 在 B/M/P 等双唇音检查物理闭合，在词组边界检查开合与停顿；
- 原生口型不合格时保留画面表演，替换干声或做后置 Lipsync；修复后重新检查身份漂移；
- 跨 cut 让前镜句尾闭合或转为中性唇，再接下一镜，避免口型跳变。

中性唇资产的生成规范见 [keyframe-assets.md](keyframe-assets.md)；若目标模型口型能力未 live 核验，标 `TODO_VERIFY_LIVE`。

### 4. 配音与声音一致性

- 每个角色固定一个 approved voice asset；记录语言、口音、表演范围、授权和版本；
- 同场对白统一麦克风距离感、房间混响和噪声底；跨场景才改变声学空间；
- 先做对白编辑与降噪，再铺拟音、环境和音乐；
- 不用自动拉伸硬塞台词。删词、重录或调整画面 hold 时，要同步更新字幕时间码。
- 参考音色来源三选一：目标语言 TTS 干声；真人授权录音；从已批准的生成 take 里抽出干声。抽声时记 `shot_id`、`source_sha256` 与时间区间，只作参考音色，不进成片；
- 主要角色的 voice asset 在批量生成前批准并冻结；换音色即新版本，旧 take 标 superseded，不与新版本混剪；
- 参考音色的语言与目标市场一致，不用中文音色驱动外语台词。

### 5. 音乐与音效

- 配乐服务情绪弧，不逐镜填满；在对白和关键拟音前做空间；
- Foley 对准接触，环境声负责空间连续，设计音效只强化剧情证据；
- J-cut/L-cut 可提前声音或延后画面，必须服务信息与情绪，不当默认装饰；
- 混音先听移动端对白可懂度，再看响度数据；交付标准由目标平台/客户 live 确认。

### 6. 转场

优先选择有因果的转场：动作动量承接、视线承接、构图匹配、遮挡切、光线切、声音先行。只有剧情需要世界状态变化时才用粒子、破碎、液体或重力翻转。每个转场检查方向、速度、光色、空间和音响是否能在切点接上。

### 7. 字幕与精确文字

- 模型生成阶段保持 `NO ON-SCREEN TEXT`；字幕、身份牌、CTA、价格和法律文字在后期确定性生成；手机、电脑、投屏等屏幕特写一律在镜头规格标 `screen_ui: "clean_plate_post_replace"`（生成阶段出纯色／暗屏干净板，后期贴入精确 UI 画面），禁止让视频模型直出可读屏幕文字；
- 字幕从 approved dialogue 自动对齐后再人工校词，不让 ASR 改写人名、数字或剧情证据；生造品牌词按发布意图 `lexicon` 统一标准拼写与读音提示；
- 导出 macOS 剪映专业版草稿（`draft_content.json`）时，禁止写入 Windows 盘符路径（如 `"D:"`、`"C:\\..."`）或本机不存在的字体路径与字体名，否则剪映丢字并退回默认黑体；交付前跑 `python3 scripts/check_jianying_draft.py --draft <草稿JSON或目录>` 扫描盘符与字体；
- 保留可编辑字幕源与烧录版本，按平台重新排版安全区；
- 说话者不清时用位置、颜色或标签区分，但不遮脸、手和关键道具；
- 逐集 AI 标识与平台元数据见 [platform-packaging.md](platform-packaging.md)。

### 8. 调色、质感与超分

先匹配曝光、白平衡、黑位、肤色和光源方向，再做全片风格。去闪/超分/面部恢复只解决已识别问题；锐化、颗粒与 LUT 不能掩盖身份漂移或拓扑错误。保留无颗粒清洁母片，平台版本再按交付需求处理。

## 短剧后期脚本

AI 短剧过了成片门之后用这五个脚本；它们只做机械步骤，取舍全部来自参数或项目配置，脚本里没有内置的分辨率、字幕样式、配乐风格或响度目标。

| 脚本 | 做什么 | 关键点 |
|---|---|---|
| `scripts/check_post_deps.py` | 查 ffmpeg／ffprobe／whisper／demucs 等是否就绪 | 缺什么报什么并以非零退出，`next` 写明下一步；demucs 在它自己的解释器里查（`--demucs-python` 或环境变量 `DEMUCS_PY`，通常是单独的虚拟环境）；`asr_models_on_disk` 列出本机已有的转写模型。不静默降级、不代装 |
| `scripts/assemble_cut.py --project <目录> --tier <档位> [--prefix <前缀>] [--fade-ms <毫秒>] [--check-seams] [--cutlist-out <cut.otio>] [--cutlist-in <cut.otio>] --output <文件>` | 按规格顺序把 `approved` 的 take 拼成整集或分幕粗剪 | 只收 `approved`，缺一镜就拒绝；`--prefix <镜号前缀>` 可按幕／按场先拼分幕粗剪（记入 `drama.act_cuts`，不覆盖整集 `drama.cuts`）查轴线与切点；首尾死帧或闪帧用 `--trim 'SPEC_ID=START,END'`（半角逗号分隔秒数，可重复）裁净；`--fade-ms <非负整数>` 在归一化片段首尾加微淡入淡出防切点爆音；`--check-seams` 用 `blackdetect` + `freezedetect` 扫描每个切点 `±0.12s` 并写 `<输出>.seams.json`，检出黑场或冻帧即报 `CUT_SEAM_DEFECT` 阻断落账；v7（`sop_version: "3.0"` 或启用 `--cutlist-in`／`--cutlist-out`）默认 `24` fps 并做帧级 CFR 归一化（旧项目未传 `--fps` 时取第一条片段）；`--loudness <目标>` 不给就不动响度；`--end-card <秒>` 可选静音黑场片尾；写出审阅摘要 `<输出>.timeline.json` 与可回读的 `<输出>.otio`（或 `--cutlist-out` 指定路径） |
| `scripts/remix_score.py --project <目录> --cut <整集> --config <混音配置> --output <文件>` | 用 `htdemucs` 分离音轨后剥掉 AI 原生片段夹带的残留背景乐，换成一条连续配乐与可选环境底噪 | 保留哪些分轨（如 `vocals`）、静音区间、配乐裁切（`clip_start`／`clip_end`）与淡入淡出（`fade_in_s`／`fade_out_s`）、增益与压低量、绕过 sidechain 直入主总线的可选 `ambience` 轨、按区间对指定分轨施加 `highpass`／`lowpass`／`gain_db` 的可选 `span_effects`（电话音／回忆闷音等），全部写在项目的混音配置里，缺项即拒绝；`stems_dir` 下已有全部 `keep_stems` `.wav` 时自动跳过 `demucs` 分离（`stems_reused: true`）；混音写出 `<输出>.remix.json` 旁路证据（含 `cut_sha256`、`output_sha256`）；demucs 用 `--demucs-python` 或 `DEMUCS_PY` 指定的解释器 |
| `scripts/burn_chinese_subtitles.py`（唯一字幕入口） | 烧录字幕和／或输出 SRT | `--timeline` 模式支持 `--shot-cues <JSON>`（`镜号 -> [{start, end, text\|lines}]` 片段内相对时间手写字幕，非法报 `SHOT_CUES_INVALID`），当所有带词镜头均由 `--shot-cues` 覆盖时免传 `--asr-dir`、免跑 whisper；其余镜头按词级时间戳对齐字幕（转写缓存在 `--asr-dir`），没听到的句子报 `CUE_NOT_ALIGNED`，现转写须给 `--asr-model`（或 `ASR_MODEL`），否则报 `ASR_MODEL_NOT_CHOSEN`；传入 `--project` 时对输出字幕逐行执行 `release_intent.lexicon` 专名门禁（`LEXICON_VARIANT_FORBIDDEN`）；`--subtitles` 模式沿用手写时间的 JSON |
| `scripts/check_jianying_draft.py --draft <草稿JSON或目录>` | 扫描剪映草稿里的盘符路径与缺失字体 | 递归检查 `draft_content.json`（含 `materials.texts[].content` 内嵌 JSON 字符串），逐处报出残留盘符（`WINDOWS_DRIVE_PATH`）、不存在的字体路径（`MISSING_FONT_PATH`）与本机未安装的字体名（`MISSING_FONT`） |

`assemble_cut.py` 与 `remix_score.py` 支持 `--dry-run`，只打印将执行的 ffmpeg 命令。草稿整集与成片整集用同一个 `assemble_cut.py`，区别只在 `--tier`。做完后 `drama_setup.py post-done --output <文件>…` 登记产物：每个文件须经 `ffprobe` 解码出视频流与帧（拒绝 1 字节或非视频文件），含音轨时视频流与音频流时长差须 `≤ 0.25s`（否则报 `POST_OUTPUT_AV_DURATION_MISMATCH`）；当 `release_intent.native_bgm == false` 且产物含音轨时，强制核验匹配 `output_sha256` 的 `<输出>.remix.json` 旁路证据（缺失报 `POST_REMIX_EVIDENCE_MISSING`、摘要不匹配报 `POST_REMIX_EVIDENCE_MISMATCH`），仅用户明确豁免时传 `--waive-remix`（记 `waived_remix: true`）。

## v7 成片技术硬门

成片终检可使用 `eval_harness.py media-qc` 传入真实源片、字幕、对白干声、OTIO 剪辑表与元数据机检；机检只覆盖可程序化测量的硬门与节奏提示，`visual` 与 `brief`（及无硬错的有声音轨 `audio`）始终保留 `needs_review`，必须再按 [production-qc.md](production-qc.md) 人工连续观看与听音：

```bash
python3 scripts/eval_harness.py media-qc --input renders/final.mp4 \
  --delivery-mode full_film --creative-mode short_drama \
  --claimed-resolution native_1080p --raw-clip 01_takes/s01_raw.mp4 \
  --subtitle subs/final.srt --audio-route replace_dialogue \
  --dialogue-stem stems/dialogue.wav --cutlist renders/cut.otio \
  --metadata renders/media-meta.json --json
```

- **自动测量硬门（触发即 `errors` 非空、退出码 `1`）**：视频流可读且无残留 `extra_mjpeg_streams`、主视频帧率 `>= 23.976`（低于报 `FRAME_RATE_BELOW_24`）、原生档位与 `--raw-clip` 源短边及成片短边核对、字幕重叠与整条字数、`>= 0.5s` 持续窄带合成音、`full_film` 响度／真峰值门限、换配音后残留原生人声、`edge-tts`／`espeak` 机器音色来源（`video_clips` 与 `full_film` 均拒），以及 `--metadata` 显式锁定 `locked_one_take`／`hard_duration_s` 时的违锁。
- **自动软提示与人工复核边界**：传入 `--cutlist` 时按 `--creative-mode` 检查平均镜长（`ASL_PACING_REVIEW`）与短剧超长单镜（`LONG_HOLD_REVIEW`）并发出 warning（预检 `OCCLUDED_LIMB_ACTION` 除非升级或违锁也作 warning）；字幕安全区是否遮脸／手／道具、镜尾 hold 物理稳定度、台词气口与动作兑现属于人工复核，机检不代签 PASS。

### 画面：恒定帧率、干净流、分辨率诚实

```bash
# 归一化：恒定 24fps，用大写 V 排除 attached_pic 封面流，单引号防止 zsh 将 ? 当通配符
ffmpeg -v error -i take.mp4 -map '0:V:0' -map '0:a:0?' -r 24 -fps_mode cfr \
  -c:v libx264 -crf 16 -pix_fmt yuv420p -c:a aac -ar 48000 take_cfr.mp4
ffprobe -v error -show_streams -of json take_cfr.mp4
```

- 拼接前每条 take 都过 CFR 归一化（`-r 24 -fps_mode cfr`）；可变帧率片段直接拼会让音画渐漂。
- 部分通道（实测 Grok 网页下载）在容器里夹带 `mjpeg` 封面流（`attached_pic`），示例用 `-map '0:V:0' -map '0:a:0?'` 剥掉；若容器内含未标 `attached_pic` 的独立 `mjpeg` 流，先用 `ffprobe` 查清真正主视频流的绝对 `index`（如 `-map '0:1'`，`media_inspection.py` 的 `primary_index` 同样排除 `attached_pic` 与额外 `mjpeg` 流）。
- 分辨率诚实：交付说明写 `native`（`ffprobe` 实测源片分辨率）与 `delivered`（放大后）两列。声明 `--claimed-resolution native_1080p` 时必须同时传 `--raw-clip` 核对源片短边（缺源片报 `NATIVE_CLAIM_UNVERIFIED`），实测源片或成片**短边**（`min(width, height)`）低于声明档位（例如竖屏 `720×1280` 短边仅 `720`）、或带 `--upscaled-from` 却宣称原生时，报 `NATIVE_RESOLUTION_MISMATCH` 阻断交付；如实披露「原生 736x400，放大至 1080p」（`--upscaled-from 736x400`）可交付，但不得写成原生 1080p。

### 字幕：互斥、短句、安全区

- 相邻两条同区域字幕 `end[i] <= start[i+1] - 0.08s`，即间隔 ≥ 0.08s，绝不重叠出双行重影（违者报 `SUBTITLE_CUE_OVERLAP`）。
- 整条字幕 cue 中文累计 `<= 24` 字（机检合并同条内多行计字，超长报 `SUBTITLE_LINE_TOO_LONG`）；超长按语义拆成两条独立 cue，不靠换行或缩字号硬塞。
- 烧录位置在目标画幅的移动端安全区内，不压脸、手和关键道具（人工小屏复核）；`cinema` 模式无字幕或只用极简底部电影字幕，不用花字和贴纸。

### 声音：禁合成嗡鸣，禁机器读对白

- 禁止 `>= 0.5s` 的持续窄带合成音（正弦／锯齿波嗡鸣、拿振荡器冒充配乐或环境声，检出报 `SYNTH_BUZZER_OR_TONE_DETECTED`）。允许 `< 0.35s` 的短促机械拟音（卡扣、开关、齿轮咬合），它们是真实接触声，不是合成嗡鸣。
- `video_clips` 与 `full_film` 交付中，对白禁用 `edge-tts`、`espeak` 一类机器朗读（`--voice-source` 或 `metadata.voice_source` 命中即报 `DIALOGUE_VOICE_PROVENANCE_REJECTED`）；用已批准音色的 ElevenLabs（或已验证的原生中文口播）。机器 TTS 只可用于内部对时间的临时占位。
- 外接配音（`--audio-route replace_dialogue`）前先确认原生 take 里的人声已剥离或静音，并传入 `--raw-clip` 与 `--dialogue-stem` 对照审计，避免双语人声叠在一起（残留报 `RESIDUAL_NATIVE_AUDIO`／`RESIDUAL_NATIVE_SPEECH_ENERGY`）。
- 三层 stem 审计，每层单独可听、可导出：① 原片／原生音轨（留档，判断要不要用）；② 对白 stem（逐句核说话者与原句）；③ 最终混音（对白 + 拟音 + 环境 + 配乐）。只有最终混音进成片，前两层用于追溯。
- `full_film` 终混响度硬门：整合响度 `-14 ± 2 LUFS`（`-16..-12 LUFS`，超出报 `AUDIO_LOUDNESS_OUT_OF_RANGE`），真峰值 `<= -1.0 dBFS`（超出报 `AUDIO_TRUE_PEAK_TOO_HIGH`）；用 `ebur128` 实测，不估。

```bash
ffmpeg -nostats -i final.mp4 -filter_complex ebur128=peak=true -f null - 2>&1 | tail -12
```

### 剪辑表：OTIO 无损往返

`assemble_cut.py` 导出的 `<输出>.timeline.json` 只记录帧起止（`source_in/out`、`timeline_in/out`）与取整秒数供人工审阅，不含还原有理数时间所需的 `rate`，不可作为输入回读。真正用 `RationalTime`（帧数 `value` + 帧率 `rate`）保存有理数时间、支持无损回读复拼的是 OpenTimelineIO 文件：通过 `--cutlist-out cut.otio` 写出（v7 默认亦写出 `<输出>.otio`），单镜 `redo` 或微调切点后用 `--cutlist-in cut.otio` 重新读入组装，并传给 `media-qc --cutlist cut.otio` 核对切点与总时长。

## 交付物分级

三个目录，产物只能落其中一个（棕色地带接手时，`audit_takeover.py reconcile` 自动扫描项目根目录及 `01_takes/`、`02_final/`、`clips/`、`clips_v2/`、`images/`、`output/` 下的媒体文件，按 `matched / orphan / ambiguous / missing` 分类，需关联已有视频 take 时显式传 `--choose SHOT=FILE --apply`）：

| 目录 | 收什么 | 不收什么 |
|---|---|---|
| `00_previs/` | Blender/灰模/白模渲染、代理片、定位图、`camera-samples.json` 一类的预演凭据 | 任何要给用户看成片效果的文件 |
| `01_takes/` | 已下载的生成 take，含 `status=candidate` 与 `status=rejected` | 已进成片的母版 |
| `02_final/` | `status=approved` 且完整 decode 通过的成片、clean master、平台 renders 与字幕源 | 底片、代理、判废 take |

`02_final/` 只收同时满足两条的文件：对应 take 在 [恢复台账](sequence-resume.md) 里是 `status=approved`；`ffmpeg -v error -i <file> -f null -` 完整 decode 通过。缺任一条就留在 `01_takes/`，不靠改目录名升级。

用户说「放一个文件夹」「汇总一下发我」时默认只搬 `02_final/`。底片与候选要用户点名才含，点名时在交付说明里写清哪些是底片；不要把 `00_previs/` 的灰模渲染混进汇总目录当成片交付。核心判准：「画面不劣质不等于不是底片」——底片的判定标准是它在流水线里的位置，不是它看着糙不糙。

`templates/asset-manifest.json` 的 `tier: previs|take|final` 记录同一分级。`tier=final` 的条目必须 `approval_status=approved`，否则 `validate_nbp_prompt.py` 的 registry 解析报错。

## 分轨与版本

```text
V1 picture / V2 overlays_and_titles
A1 dialogue_vo / A2 foley / A3 ambience / A4 music
captions_source / captions_burned / ai_disclosure
clean_master / platform_renders / qc_report
```

文件名包含 episode、shot/timeline version、language 和 mix version。旧对白、旧字幕或错误 take 标记 `superseded`，不得继续引用。

## 成片验收

- [ ] 对白已锁，波形锚与镜头动作一致；
- [ ] 四层音频可分别静音与导出，音乐没有遮住对白；
- [ ] Lipsync 在词组边界和双唇音可见闭合，中性唇跨 cut 自然；
- [ ] 补帧/去闪/增稳没有制造重影、复制或塑料脸；
- [ ] 动作、视线、道具、服装、光线与环境声跨 cut 连续；
- [ ] 转场有叙事理由，字幕和精确文字由后期生成；
- [ ] clean master、stems、字幕源和平台 renders 齐全；
- [ ] `ffprobe`、完整 decode、contact sheet、cut 前后帧和完整播放均通过；
- [ ] 多 Take 选择与拒绝理由可追溯，原生规格和后期规格分开记录；
- [ ] 易变模型与平台能力已 live 核验或带 `TODO_VERIFY_LIVE`。

## 声画后期增量

- TTS 音色按角色所需的年龄感、语言、音色与情感范围选型，再逐句核对人物气场；字段名和取值读取当次 provider schema，不写死供应商分类。
- 转场素材预留与运动速度相称的头尾把手，并让运动方向与声音同时匹配；切点落在遮挡真正覆盖画面的时刻。来源中的帧数与覆盖比例是个案值，不照搬。
- 剪辑速度服从段落用途：推进段可更紧，承载情绪与调性的段落可更缓；不把全片统一快切当平台规律。
- 实拍、旧素材与生成片段先按来源归组，再分别识别闪烁、色温、锐度、细节或运动平滑度问题；对齐可以升、降或统一质感，不默认把某一侧放大。
- 每项去闪、稳定、超分或锐化指定唯一处理端并写入工程记录，防止重复处理或两端漏做。

## 证据边界

配乐生成与 ducking 细则见 [audio-music-ducking.md](audio-music-ducking.md)。具体插件、响度、帧率、分辨率、价格和平台交付值不在本文件固化。
