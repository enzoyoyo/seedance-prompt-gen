# 剧本接单微格式合同

## 边界

本文件只承载 `SKILL.md` 「剧本接单两态」的逐字微格式规则，从 SKILL.md 原样下沉，措辞未改。数量口径（接单问题 ≤2、pitch 2–3、标题候选 5～6）与两态判定仍以 `SKILL.md` 与 `scripts/validate_script_gate.py` 为准，本文件不复述、不改写。创作方法见 [open-creative-director.md](open-creative-director.md)，张力门定义见 [dramatic-tension-engine.md](dramatic-tension-engine.md)，标题格式见 [title-craft.md](title-craft.md)。

## 两个固定标题的写法

这两个标题必须逐字写成行首 `### 接单问题` 与行首 `### 默认假设`；不得加括注、改写为纯文本标签或加粗。
## `### 接单问题` 节的计数规则

`### 接单问题` 节只允许以 `1.`/`2.` 开头的两个问题行；校验器会把该节内任何数字编号、`-` 或 `*` 项目都计数（不看问号），理由另起缩进行且不以问号结尾；其他节不得出现以问号结尾的独立问句。
## 「直接写」快捷路径

用户明说「直接写」：跳过提问，稿前一行写明所选形式与节拍，仍然打印张力门表。

## 校验入口

```bash
python3 scripts/validate_script_gate.py --mode intake --input <第一条回复.md>
python3 scripts/validate_script_gate.py --mode diagnosis --input <第一条回复.md>
```

错误码与节解析实现见 `scripts/validate_script_gate.py`；本文件不复制错误码表，避免两处分叉。
