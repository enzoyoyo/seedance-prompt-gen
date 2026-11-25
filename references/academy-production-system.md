# AI Video Production System Principles

Use this when an AI-video job needs repeatable project structure, named continuity assets, an authoritative production record, controlled generation tests, or source-first failure diagnosis. It complements the cinematic prompt playbook; it is not a static Higgsfield UI or model manual.

## Evidence boundary

Core production principles distilled from public AI filmmaking academy material:

| Source | Durable evidence used |
|---|---|
| [The pipeline, end to end](https://higgsfield.ai/academy/courses/cinema-studio-pro/the-pipeline) | Think → set up → generate → test; each handoff must leave a concrete trusted deliverable; repair the earliest broken handoff. |
| [Working in Claude](https://higgsfield.ai/academy/courses/cinema-studio-pro/working-in-claude) | Explicit production record outranks conversational memory: current brief, approved references, relevant skill, current shotlist. |
| [Turning thoughts into a prompt](https://higgsfield.ai/academy/courses/cinema-studio-pro/turning-thoughts-into-a-prompt) | Separate subject, action, setting, light, camera/motion, and constraints; keep a decision log. |
| [Name your assets](https://higgsfield.ai/academy/courses/cinema-studio-pro/name-your-assets) | Approved assets need stable type/project/name addresses for reliable retrieval. |
| [Proof, not promises](https://higgsfield.ai/academy/courses/cinema-studio-pro/proof-not-promises) | Approve visible pixels against downstream use, not model reputation or prompt confidence. |
| [Generating locations](https://higgsfield.ai/academy/courses/cinema-studio-pro/generating-locations) | Geography, blocking anchor, motivated light, materials, depth and reverse continuity make a location shootable. |
| [Generating characters](https://higgsfield.ai/academy/courses/cinema-studio-pro/generating-characters) | A reference sheet is literal downstream input; one defect propagates into every shot. |
| [Editing locations](https://higgsfield.ai/academy/courses/cinema-studio-pro/editing-locations) and [Editing characters](https://higgsfield.ai/academy/courses/cinema-studio-pro/editing-characters) | Apply surgical changes onto the approved master; do not stack full-frame rerenders. |
| [Test in Seedance](https://higgsfield.ai/academy/courses/cinema-studio-pro/test-in-seedance) | Test the real required motion against a known-good baseline; vary one cause at a time. |
| [Section test: foundations](https://higgsfield.ai/academy/courses/cinema-studio-pro/section-test-foundations) | Public assessment confirms authoritative-record, naming, handoff and earliest-source correction rules. |

Local records and body hashes remain in `_meta/learning-manifest.json`; all public source aliases and deduplication dispositions remain in `_meta/learning-source-ledger.json` under the archive root.

## Stability boundary

### Durable and portable

- staged handoffs with explicit deliverables;
- versioned production records;
- typed, collision-resistant asset names;
- proof-based approval tied to downstream use;
- controlled tests and earliest-source correction;
- surgical edits applied to an approved master;
- separating creative decisions from output controls.

### Provider adapters — do not universalize

- Higgsfield Element names such as `@loc_AR_rooftop`, `@char_AR_lead`, `@prop_AR_phone`;
- Cinema Studio's `@` picker and project folders;
- Claude Cowork, `.jsx` shotlists, UI labels and click paths.

### Volatile — live-check before execution

Model IDs, ranking claims, plans, entitlements, price, duration, resolution, media counts, audio support and current UI behavior. Archived Academy material supplies method; the selected provider's live schema supplies executable truth.

## 1. Production craft loop

```text
THINK
current brief + visible decision log
    ↓
SET UP
project + folders + asset naming contract
    ↓
GENERATE
proofed location / character / prop / product assets
    ↓
TEST
required motion + controlled diagnosis + keep or send one source back
```

These are craft moves that can loop, not numbered approval stages. Move on when the next action has a concrete artifact it can trust. Re-prompting downstream without repairing a broken input is not iteration; it is hiding the cause.

## 2. Authoritative production record

Conversational memory is useful recall, not authority. Before generating a shot, resolve and record:

```text
current brief
+ current reference assets and exact canonical names
+ relevant SKILL.md / method contract
+ current shotlist and continuity state
+ provider/schema check made for this run
```

If these disagree, choose the current source explicitly before spending more generations. File modification time alone does not establish authority.

Recommended shot record:

```json
{
  "shot_id": "shot-012",
  "brief_path": "docs/brief.md",
  "shotlist_path": "docs/shotlist.json",
  "prompt": "provider-neutral visible direction",
  "asset_ids": ["loc-001", "char-001", "prop-001"],
  "continuity_state_in": "named incoming state",
  "continuity_state_out": "named handoff state",
  "duration_seconds": null,
  "approved_by": "user|agent-within-approved-scope",
  "provider_schema_verified_at": null
}
```

## 3. Asset registry

Treat generated files as candidates until they pass review. A reusable asset needs:

```json
{
  "id": "loc-001",
  "asset_kind": "location|character|prop|product|brand-kit|ui|style|source-video",
  "canonical_asset_name": "loc_AR_rainy_rooftop",
  "project_code": "AR",
  "approved_source_path": "assets/locations/loc-001-master.png",
  "source_sha256": "",
  "provider_reference": "@loc_AR_rainy_rooftop",
  "approval_status": "candidate|approved|rejected|superseded",
  "version": 1,
  "correction_source": null,
  "notes": ""
}
```

`provider_reference` is an adapter. For Higgsfield UI it may be an `@` Element; for Atlas, Higgsfield CLI, Dreamina or another backend it must map to the current media-role field. The canonical asset ID/name remains stable across adapters.

## 4. Pixel proof before reuse

Judge assets for the intended downstream shot, not in the abstract. Look at pixels, not model names or prompt confidence.

- location: geography, blocking anchor, one light logic, materials, depth and required reverse continuity;
- character: one authoritative identity, readable face/eyes/hair/skin, usable views, no baked light or conflicting faces;
- product/prop: shape, scale, material, label/logo placement and hidden-side evidence required by the shot;
- UI/brand: exact static screen/kit; readable copy stays deterministic in post;
- source video: required camera path, framing, exposure, grain, timing and audio policy.

A candidate can work for one use and fail another. An armor design may work as concept art but fail as a video reference if the face is obscured.

## 5. Controlled diagnosis

Use a known-good baseline and change one suspect cause.

| Visible failure | Return to |
|---|---|
| Geometry melts or blocking changes | location source |
| Identity, face, wardrobe or body drifts | character source |
| Product silhouette, material or label drifts | product/prop source |
| Source assets hold but action/camera fails | motion direction / prompt clause |
| Shot answers the wrong idea | brief |
| More than one cause changes | inconclusive; narrow the test |

Procedure:

1. Find the first visible failure.
2. Compare it with the approved source assets.
3. Change one source or one motion clause.
4. Reapprove that source.
5. Retest the same required motion.
6. Log the diagnosis and result; do not generalize one rerun into a permanent model claim.

## 6. Locations before dependent coverage

Build the world before judging a character inside it. A known-good location removes one plausible cause from character tests.

For continuity-critical spaces:

- declare geography and playable routes before style;
- use a fixed blocking anchor instead of vague screen-left/right;
- establish foreground, midground and background;
- start with a 3/4 master when side geometry matters;
- generate the reverse as an independent continuity test;
- approve only if anchors, openings, light side, materials and depth agree.

One master wide is enough only when no later cut depends on unseen geography.

## 7. Surgical source edits

Do not stack whole-frame edits on an already edited master.

```text
approved master
→ generate candidate patch
→ inspect changed and untouched regions
→ composite/mask only the accepted patch onto the master
→ increment version + hash
→ re-run the relevant proof gate
```

Provider/model preferences in the Academy are dated examples. The durable rule is master preservation and patch-level change control.

## 8. Prompt decisions versus provider controls

Prompt content owns visible direction:

```text
subject + action + setting + light + camera/motion + constraints
```

Provider controls own delivery/runtime settings:

```text
model + duration + ratio + resolution + batch + audio flags + media-role fields
```

Do not bury output settings inside creative prose when the provider exposes a real control. If an assistant adds an unapproved prop, weather, style or camera move, require a reason, then approve, replace or remove it. Keep the decision log with the shot record.

## 9. Downstream ownership

- all AI-video methodology, Seedance reference/motion diagnosis,
  product/brand/UI planning, manifests, handoffs and final production/QC →
  `seedance-prompt-gen`;
- Higgsfield live model/schema/media-role submission → `higgsfield-generate`;
- existing-footage edit decisions and final source-aware QC → `precision-video-editing`.

Downstream skills should store only their adapter or handoff fields. Do not copy this reference into each skill.
