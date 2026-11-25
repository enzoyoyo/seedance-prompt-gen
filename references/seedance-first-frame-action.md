# 首帧动作诊断：不要从抽帧过度推断

## 已撤回的结论

少数失败不能证明模型“无法从动作中段开始”。单张静帧里门尚未推开，也不能直接证明整段视频没完成推门、转身或递物动作。先回放动作区间，不从首帧判整条废。

“ALREADY 反复堆叠必定有效”“垫图必定解决”“收紧景别同时治好融合手”均未获充分验证，不作为制作规则。

## 可执行流程

1. 分开定义首帧状态、可见动作过程与末态，不把瞬间、已完成、空杯和再次投掷等冲突要求混在一起。
2. 对照剧本逐段查看实际发生时间；只有关键事件确实缺失才诊断动作失败。
3. 重测只改一个变量，保留原提示词、参考、模型回执与输出。重复失败后重审输入/动作复杂度/审核/机位，不无预算地堆否定词。
4. 首帧图是候选控制方式，需当前模型确实支持相应输入模式，并通过正常审核。附件不自动等于首帧。
5. 首帧图生成成功只证明静帧成功；审核拒绝或没有视频时，不得声称图生视频路线已经跑通。
6. 站位、道具归属、室内外、视线和动作方向写成可见约束；景别根据动作可读性选择，跪地等全身动作不一律裁成特写。
7. 雨水、阴影或深色污渍在部分帧可能产生视觉歧义，应结合完整回放判断；用户已认可当前画面后保留，不擅自更改设定重拍。

## 首帧锚定与物性防漂移写法

长镜头仅靠首帧图锚定时，越往后越容易发生服装底色或局部水渍/污痕物性漂移（例如雨夜浅色风衣下摆的一处泥水溅落，到后段扩散成整件外套变色甚至误变伤口质感）。

因此除了首帧参考图之外，必须把不可变物性与负面约束显式写进提示词，不依赖首帧图自身撑住全程：

```text
HARD CONSTRAINT: the rain splash stain stays on the lower hem of the trench coat only.
It must NEVER spread upward across the collar or skin, and never morph into a dark injury mark.
The coat base colour remains light khaki throughout the shot.
```

物性不变量的落点（`characters[].state`、`negative`、`continuity.in_state/out_state`）见 [prompt-compiler.md](prompt-compiler.md)。

## OPEN ON ACTION：不要用「动作完成后」当开场

剧本写「第 1 帧即见推门/闯入动作」时，生成的必须是动作进行中（门扇正在推开、身体重心前倾），而不是动作完成后的静态站姿。

- 写结果（错）：`a woman standing still inside the doorway after opening the door`
- 写动作（对）：`OPEN ON ACTION, first frame mid-swing as Claire forces the heavy wooden door open into the dim hallway`

生成前先回查剧本该镜的时间码与动作描述，不凭「哪张图好看」选开场。

景别与首帧的取舍：收紧景别若会让首帧丢失必须可见的状态或动作起点，以本节的首帧契约为准，不为收窄画面而牺牲首帧动作起点（详见 [cinematic-method-playbook.md](cinematic-method-playbook.md) 的「畸形手与景别取舍」）。

## 验收层级

单帧：构图/该时刻状态；联系表：抽样连续性；完整播放：动作和剪辑；核听/转录：语言与台词；解码：技术完整性。不能相互替代。
当前 provider 不支持 video_url 时，报告未完成视频/音频理解；改用获准的可用视频或音频工具，不伪造完整验收。
