# Platform Risk and Compliance

## Distinguish three kinds of risk

Do not compress all risk into “allowed/blocked.”

1. **Removal or legal risk:** prohibited content, rights violations, unlawful use, or missing required disclosure.
2. **Recommendation eligibility risk:** content may remain available but be age-restricted, ineligible for broad recommendation, or harder to find.
3. **Creative and audience risk:** cheap provocation, trust loss, brand damage, audience mismatch, or comments that overwhelm the intended story.

Rules vary by platform, market, account, product mode, and date. Read
[`platform-evidence-ledger.jsonl`](platform-evidence-ledger.jsonl) for the
machine-audited claim state and
[`2026-platform-evidence.md`](2026-platform-evidence.md) for its human review
index. Neither file is a publication authorization.

## Provocation ladder

### Green — broad-reach default

- fictional interpersonal conflict;
- moral ambiguity with credible positions;
- selfish, flawed, abrasive, or contradictory characters;
- critique of behavior, institutions, or social habits without targeting a protected group;
- implication, flirtation, jealousy, status games, embarrassment, or dark humor that remains non-explicit and non-exploitative;
- an invitation to interpret or debate, without coercing engagement.

### Amber — disclose recommendation and audience risk

- sustained hostile profanity aimed at a private figure, even fictionalized to resemble a real person;
- sexualized framing, prolonged intimate behavior, or suggestive visual emphasis;
- distressing fear, injury, humiliation, or fictional violence beyond what a broad audience expects;
- controversy constructed around sensitive identity stereotypes;
- realistic AIGC involving recognizable people or events where consent, labeling, or misleading context is uncertain;
- manipulative prompts designed mainly to inflame comments.

An amber choice needs a real creative reason. If the user has explicitly authorized bounded risk, it may be developed with a clear eligibility note and a safer publishable alternative where useful. Do not label it “compliant traffic” merely because removal is uncertain.

### Red — do not turn into a tactic

- sexual content involving minors or youth-like characters;
- hate or demeaning attacks based on protected attributes;
- doxing, sexual harassment, threats, targeted humiliation of a real private person, or coordinated abuse;
- fake authoritative sources, crisis events, endorsements, or harmful impersonation;
- dangerous or illegal instruction, exploitation, or evasion of platform review;
- undisclosed realistic synthetic media where disclosure is required;
- political persuasion or sensitive political content; this Skill's active brief excludes political content by default.

Offer a fictional, non-targeted, non-deceptive transformation that preserves the dramatic need when possible.

## “引战” versus genuine disagreement

Use disagreement that emerges from the work:

- a choice with competing costs;
- unequal obligations;
- a character who is right for the wrong reason;
- consequences that make both readings uncomfortable;
- missing certainty the audience can interpret from visible evidence.

Do not command users to attack, shame, mass-report, or leave a prescribed insult. Do not falsify facts or omit decisive context merely to farm anger. An honest question may invite discussion; an engagement trap makes the audience perform for the metric.

## Sexual suggestion and “擦边”

Romantic tension and emotional implication can be part of a story. Keep consent, age, and narrative function clear. Avoid sexualized framing as a default hook because it can create audience, rights, age-rating, removal, or recommendation risk. This ledger does not currently contain a traceable platform-body claim for specific kissing/framing categories; check the target platform, market, actor, account, product mode, and effective rule live before assigning a platform outcome.

If the intention is allure rather than explicit sexuality, direct performance, status, proximity, withholding, costume, sound, or implication without reducing a body to recommendation-risk framing. Never mix sexual suggestion with minors or youth-coded presentation.

## AI disclosure and likeness

- Preserve provenance for faces, voices, music, fonts, footage, and IP.
- For documentary or historical reconstruction, keep source evidence for each visual choice and mark where the record ends and generative reconstruction begins in the film or production record.
- When identity must be protected, design it into coverage with physical occlusion, rear views, and distance that prevents feature resolution; verify the final render at its delivery size and do not rely on blur as the only safeguard.
- Do not assume a disclaimer cures impersonation, misinformation, or rights violations.
- TikTok's canonical Help URL is currently `official_url_only`: a localized-body observation was reported, but its exact URL/locale was not retained and the target English body was not independently extracted. Treat labeling text and creator/automatic controls as **`UNREAD / TODO_VERIFY_LIVE`** until a traceable official body and target-account UI are recorded.
- Douyin's agreement body supported prominent labeling for non-real or potentially confusing generative-AI audio/video. The exact control name, location, and fields remain `TODO_VERIFY_LIVE`; do not invent them.
- The NRTA micro-drama propositions are recorded from a **single-source official body read only**. Article 34's per-episode conspicuous-label obligation and Article 17's classification/authorization proposition still lack a normalized official-body hash and an actual filing/publishing path receipt.

No source body hash, account UI, or published-post readback has been fabricated or promoted.

## 平台证据门

本节是平台规则与发布证据核验的唯一定义处。[2026-platform-evidence.md](2026-platform-evidence.md) 是被 `platform-evidence-ledger.jsonl` 的 `review_sha256` 钉住的人读审计快照，改动它会使 claim 的 `review_ref` 失配，因此保持原文不动；它与本节重复的三段式与证据边界以本节为准。

### 证据升级规则

任何平台规则、榜单、热点、审核口径、披露字段、分成条款都默认是 `TODO_VERIFY_LIVE: <平台>_<主题>`。**只有同时带完整 URL 与来源日期的条目才可升级为依据**；升级后按 claim 写进 [platform-evidence-ledger.jsonl](platform-evidence-ledger.jsonl)，发布当日以官方当前页面为准。不在任何条件化模块里硬编码榜单、趋势、审核规则原文或平台条款原文。数字同样按主入口的数字规则处理：与 URL+日期同行，或写 `TODO_VERIFY_LIVE`。

### 实时查询模板

`<平台>` 只替换为 brief 已出现的平台名，`<主题>` 只替换为「热点」「题材趋势」「上架要求」或「审核规则」，不预填结论：

```bash
# 先探测可用检索工具，再发起带日期与完整 URL 的官方来源查询；结果默认为 TODO_VERIFY_LIVE: <平台>_<主题>
python3 scripts/list_research_tools.py --json
grok -p "查询<平台> 短剧 <主题>；只列带完整 URL 与来源日期的当前依据，找不到就明确说未找到。" --output-format json
```

检索工具缺少凭证或环境未配置时记 `RESEARCH_SKIPPED`（不猜测环境变量，不读取或回显密钥值），不以训练记忆代替实时查询。

### 三段式结果：repository / planning / publish

- `repository`: checks ledger schema, coverage, provenance, revision, and
  effective-window consistency. `PASS` means only `publishable=false`.
- `planning`: may deliver scripts, masters, risk notes, and live-check TODOs;
  its verdict is `PLANNING_ONLY` and `authoritative=false`.
- `publish`: needs direct official-body hashes and same-day evidence for the
  exact platform, market, product mode, actor, and account. The first implementation deliberately
  omits the unreachable receipt-matching chain, so publish remains fail-closed.

Production publish rejects user-supplied `--as-of`. Historical evaluation is
allowed only for repository/planning or pure tests and never becomes an
authoritative publication decision. CLI contract: planning/publish require
`--platform`, `--market`, `--product-mode`, and `--actor`; publish additionally
takes a non-secret `--account-context`. The first batch has no `--receipts`
argument or positive publish outlet: publish always returns `BLOCK` / exit `2`.

Unresolved evidence is therefore compatible with non-executable planning, but
never with a claim that publication is ready or complete.

### 证据存放边界

Do not put screenshots, cookies, tokens, account names, or credential-bearing
exports in this reusable Skill. Do not fill a body hash from a review summary,
URL, search snippet, or metadata. When a real publication workflow exists, keep
its text/DOM/JSON receipts in the publication project and add a validator only
after that receipt path is reachable and tested.

The evidence layer must never encode fixed duration, hook, reversal, shot,
panel, completion-rate, or distribution-weight formulas. 历史包装与历史流程例只能作字段清单，不能当当前规则。

## 剧本期合规检查

合规与平台适配在剧本阶段先跑一次，逐项定位到场次/句子，并写明缺哪条当前规则；不输出不可核验的过审、上榜或推荐概率。此关改故事源文本，发布关再处理逐集标识、备案/许可、AIGC 披露与包装，二者不能互相替代。所有规则仍需执行当日的官方证据。

## Publishing decision

Before external publication, the publication project—not this reusable
Skill—must be able to record and validate:

```text
platform / market / product mode / actor / account context
current official body evidence and captured_at
content classification and recommendation-risk notes
AI label and per-episode disclosure plan（AI 剧：每集提示标识 + 分级/备案门，见 2026-platform-evidence.md）
controlled real-person certification path (`asset://` / 主体库)，不得换措辞绕过
likeness / voice / music / footage / font / IP rights
age and minor-safety review
final render and metadata evidence
published-post readback when claiming publication
```

Do not store screenshots, credentials, cookies, tokens, or account names in the
Skill ledger. The first-batch CLI intentionally has no `--receipts` parameter or
positive publish outlet; until a reachable same-day receipt pipeline exists and is tested,
the publish stage must return `BLOCK`/exit `2`, and production publish rejects
user-supplied `--as-of`. If a current rule or right cannot
be verified, mark it unresolved and stop publication; a creative package can
still be delivered as non-executable planning material.
