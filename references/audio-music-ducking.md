# Suno BGM + narration ducking workflow

> **参数快照 2026-08-24，生成/发布前 live 校验；默认 14 天过期。** 下文 Suno UI、CDP 端口、endpoint、response field 与下载路径接口形态随版本变化，使用前重新验证当前登录会话和接口行为。

Use when a finished short video needs AI-generated background music that supports narration without covering it.

短剧全链路中的对白、拟音、环境、配乐四层职责与声音先行顺序见 [post-production.md](post-production.md)；本文件只维护 BGM 生成、选择、ducking 与混音验证细节。

## When to use
- User asks to add Suno AI music / BGM to an existing narrated short.
- User is logged into Suno in Chromium/Chrome and wants the agent to generate, download, and mix.
- Output must preserve a finished video while replacing/remixing only the audio track.

## Suno prompt pattern
For narration-led film essays, use Advanced mode and leave Lyrics blank with instrumental enabled.

Style field example:

```text
Instrumental cinematic underscore for a quiet film-essay short. Sparse felt piano, warm low strings, soft analog synth pad, subtle tape hiss, distant room ambience, very gentle low pulse, muted brushed percussion only near the middle. 72 BPM, minor key, intimate, restrained, reflective, tactile atmosphere. Starts almost silent with single piano notes and room tone; slowly adds warm strings and a soft heartbeat-like pulse through the middle; resolves into a small warm lift at the end. Designed to sit underneath spoken narration, with no lead vocal and no busy melody.
```

Exclude styles:

```text
vocals, singing, lyrics, rap, choir lead, spoken word, EDM drop, hard drums, bright corporate pop, upbeat uk garage, aggressive trap, busy lead melody, loud snare, distorted guitar
```

## Browser CDP extraction notes (optional)
If a local Chromium/Chrome debugging instance is running with `--remote-debugging-port=<PORT>`, you can inspect Suno tracks via CDP without manual downloads:

1. Open/create a tab via CDP:
   ```bash
   curl -s -X PUT 'http://localhost:<PORT>/json/new?https://suno.com/create'
   ```
2. Use CDP Network capture to inspect `https://studio-api-prod.suno.com/api/feed/v3` responses.
3. New clips expose:
   - `id`
   - `status`
   - `audio_url`
   - `media_urls`
   - `metadata.tags`
   - `metadata.negative_tags`
   - `metadata.make_instrumental`
4. For streaming clips, do **not** download the `encoded=true` audiopipe URL as an MP3; it may save a non-MP3 byte stream. Use:
   ```bash
   curl -L -A 'Mozilla/5.0' -H 'Referer: https://suno.com/' \
     -o bgm.mp3 'https://audiopipe.suno.ai/?item_id=<clip_id>'
   ```
5. For completed clips, `https://cdn1.suno.ai/<clip_id>.mp3` may 403 outside the browser session. The audiopipe URL above is more reliable.

## Choose the take
Generate comparison takes only when selection uncertainty, consequence and budget justify them; use the smallest sufficient set rather than a fixed minimum. When comparing, prefer the take with:
- Lower integrated loudness for easier underscore mixing.
- Larger loudness range if it feels more cinematic and less constant.
- No obvious vocal remnants despite instrumental mode.

Measure first 54 seconds or target length:

```bash
ffmpeg -hide_banner -nostats -t 54 -i bgm.mp3 \
  -filter_complex ebur128=peak=true -f null - 2>&1 | tail -n 25
```

## FFmpeg ducking mix
Preserve video stream, remix only audio:

```bash
ffmpeg -y \
  -i final_without_bgm.mp4 \
  -i bgm.mp3 \
  -filter_complex "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[orig]; \
    [1:a]atrim=0:54,asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo, \
    highpass=f=55,lowpass=f=9000,afade=t=in:st=0:d=2,afade=t=out:st=51:d=3,volume=0.25[music]; \
    [music][orig]sidechaincompress=threshold=0.03:ratio=10:attack=45:release=850:makeup=1[mduck]; \
    [orig][mduck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.93[outa]" \
  -map 0:v:0 -map "[outa]" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 -movflags +faststart \
  final_with_suno_bgm.mp4
```

Adjust only `volume=0.18–0.30` first. Do not raise music until narration clarity is verified.

## 短剧后期 `scripts/remix_score.py` 编排与旁路证据

短剧整集去残留原生 BGM 并铺连续配乐统一走 `scripts/remix_score.py --project <目录> --cut <整集> --config <混音配置> --output <文件>`（详见 `post-production.md`）：

- **预分离分轨复用**：当 `stems_dir` 下已存在全部 `keep_stems` 对应的 `<stem>.wav` 时，自动跳过 `demucs` 分离并在结果记 `stems_reused: true`，改配乐参数秒级重混。
- **配乐裁切与淡入淡出**：`score[]` 除 `file`、`start`、`gain_db` 外，支持可选 `clip_start`、`clip_end`（源音频内裁切区间）与 `fade_in_s`、`fade_out_s`（段首尾平滑过渡，避免硬切）。
- **独立环境底噪轨（`ambience`）**：可选 `ambience[]`（含 `file`、`start`、可选 `end`、`gain_db`、`fade_in_s`、`fade_out_s`）绕过 `sidechaincompress` 直入主混音总线，防止人声触发 ducking 时连带抽吸房间底噪／雨声／空调声。
- **按区间局部声学处理（`span_effects`）**：可选 `span_effects[]` 按 `[start, end]` 对指定 `stem`（如 `vocals`）施加 `highpass`、`lowpass`、`gain_db`，无需手改底层滤镜图即可做出电话音、隔门音或回忆闷音。
- **混音旁路证据**：每次实跑写出 `<output>.remix.json`（含 `cut_sha256`、`output_sha256`、`separator_model`、`keep_stems`、`score_files`、`ambience_files`），供 `drama_setup.py post-done` 在 `native_bgm=false` 时硬核验成片确经去残留混音。

## 事件轨与歌唱声线

- 环境动效写成事件轨：到达间隔不规则、相邻事件不复制；对白所在区间安排相对安静窗口。若对白走外部配音，交由后期 ducking 实现同一目标。
- 只有项目明确包含音乐生成时才采集歌唱声线，并与说话声线分开维护；记录音域、演唱音色、常用声区、风格取向与标志性技巧，不写歌手名或歌名。
- 音乐平台的拒稿策略属于 live 规则：`TODO_VERIFY_LIVE`。策略未核实前只报告风险，不宣称必然通过或拒绝。

## Verification
Run all checks before reporting done:

```bash
ffprobe -v error -show_entries format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -of json final_with_suno_bgm.mp4
ffmpeg -v error -i final_with_suno_bgm.mp4 -f null -
ffmpeg -hide_banner -nostats -i final_with_suno_bgm.mp4 -filter_complex ebur128=peak=true -f null - 2>&1 | tail -n 16
```

If possible, also render/check the ducked BGM stem alone. A narration-safe target is often around `-31 LUFS` for the ducked BGM stem when the final program is near `-15 LUFS`, i.e. music roughly 15 LU below the program/narration.

## Reporting
Include:
- Final video path.
- Suno clip IDs and chosen take.
- Prompt + exclude styles.
- Mix settings.
- Final specs and loudness numbers.
- Decode check result.
