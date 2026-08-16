# 07 — Workflow Engine, Agents & Skills

**The guarantee this subsystem exists to provide:** the same user input produces
the same workflow route, the same stage sequence, the same skill order and the
same artifact set — **regardless of which model is executing it.**

This is Atlas's contribution to Métis, and it is what turns a set of capable
library functions into a system a team can rely on.

## 7.1 Three enforcement layers

| Layer | Mechanism | Deterministic because |
|---|---|---|
| **1. Routing** | Intent classification against an explicit pattern table | The table is data; matching is exact, not fuzzy |
| **2. Manifest** | `workflows/manifest.yaml` — stage sequence, required artifacts, validation checks, skill order | The sequence is declared, not decided at runtime |
| **3. Stage execution** | Skills run in ordinal order behind confirmation gates | Order is read from the manifest; nothing is inferred |

`REQ-WFE-001` — Same input → same route, stage sequence and artifact set,
regardless of model. Verified by running the same input under two different
models and diffing the result.

## 7.2 Routing

`REQ-WFE-002` — Intent is classified against an explicit pattern table **before**
any routing occurs.
`REQ-WFE-003` — Ambiguous input presents an explicit workflow menu. Guessing is
prohibited.
`REQ-WFE-004` — Each request routes to exactly **one** primary workflow.

| Intent pattern | Layers | Workflow |
|---|---|---|
| `analyze <KEY>` | Requirement | Requirement Analysis |
| `prepare specification for <scope>` | Requirement + Specification | Requirement Analysis (full) |
| `test <KEY>` | Requirement → Specification | Test Design (design only, no chain) |
| `generate api test cases for <KEY>` | Req → Spec → Behaviour | Requirement Analysis **→** Test Design **→** Functional Generation (chain) |
| `generate ui test cases for <KEY>` | Req → Spec → Behaviour | as above, Web specialist |
| `generate api test for <endpoint>` | Behaviour | Functional Generation (direct) |
| `design performance for <scope>` | Req → Perf → Behaviour | Performance Generation |
| `analyze code for <repo>` | Specification | Code Analysis (§13) |
| `check behaviour model for <scope>` | Behaviour | Behaviour Verification |
| `review my branch` | Behaviour → Spec → Req | Review & Merge |
| `create bug from <failure>` | Defect | Defect Management |
| `create quality report for <scope>` | All → Quality | Quality Reporting |
| `onboard <project>` | Integration | Setup & Onboarding |

**Routing rule that matters:** `test <KEY>` and `analyze <KEY>` **without**
`generate` run standalone — they pause at the end and *offer* to chain on user
confirmation. Only an intent containing `generate` enters chain mode.

## 7.3 The workflow manifest

`REQ-WFE-006` — Every workflow declares `code`, `description`, `entry_prompt` and
`stages`. Every stage declares `ordinal`, `required_artifacts`,
`validation_checks` and `skills`.

```yaml
version: 2

workflows:
  Test Design:
    code: test-design
    description: Design test coverage and automation approach
    entry_prompt: "test <KEY>, what tests are missing for <KEY>"
    stages:
      Evidence Acquisition:
        ordinal: 3
        required_artifacts: []
        validation_checks:
          - "At least one evidence source produced output"
          - "Acceptance criteria present (min 1) for the scoped requirement"
          - "Verified type registry has unverified_count == 0"
        skills:
          graph-context-loader: 1
          code-analysis-reader: 2
      Source Normalization:
        ordinal: 4
        required_artifacts: ["<graph>: Requirement, AcceptanceCriterion for scope"]
        validation_checks:
          - "Every scenario has id, title, source_ac, behaviour, precondition"
          - "Every scenario has automation_status; ambiguous evidence never counted as covered"
        skills:
          scenario-normalizer: 1
          coverage-mapper: 2
      Design:
        ordinal: 7
        validation_checks:
          - "Every missing scenario classified: extend-existing | generate-new | migration-first | duplicate-covered | blocked"
          - "No blocked or duplicate-covered scenario passed to generation"
        skills:
          automation-viability-classifier: 1
          performance-candidate-classifier: 2
          test-definition-drafter: 3
        next_workflow: functional-generation
        auto_advance: true       # chain mode only
```

### Manifest rules

| Rule | Requirement |
|---|---|
| Stage ordinals are unique within a workflow | `REQ-WFE-007` |
| Stages execute in ordinal order, no skipping, no reordering, no backtracking | `REQ-WFE-008` |
| Skills within a stage execute in declared numeric order | `REQ-WFE-009` |
| Parallelism only where explicitly marked | `REQ-WFE-009` |
| Conditional skills declare their condition in the manifest, evaluated from **request shape**, never model inference | `REQ-WFE-010` |
| A workflow runs completely or not at all — no partial runs | `REQ-WFE-006` |
| The manifest is validated **before** execution | `REQ-WFE-005` |

`REQ-WFE-010` is the one most often violated in practice. A condition such as
"skip repository analysis when no ticket key was given and a repository name was"
is a **deterministic property of the request**, and must be written that way —
not left to the model to judge whether the step "seems necessary".

## 7.4 Stage execution and validation gates

```
Load and validate manifest
    │
    for each stage in ordinal order:
        ├─ resolve required_artifacts (graph queries, §7.6)
        ├─ execute skills in ordinal order
        ├─ run validation_checks — ALL must pass
        ├─ present stage summary + artifacts
        └─ confirmation gate
```

`REQ-WFE-011` — A failing validation check **blocks advancement**; no downstream
stage may run.

`REQ-WFE-012` — On failure the engine **does not** attempt recovery, auto-fixing,
or an alternative path. It reports and blocks:

```
ERROR: Stage cannot proceed
Reason:   <the validation_check that failed>
Fix:      <the explicit action required>
Produced: <actual artifacts>
Expected: <declared artifacts>
```

`REQ-WFE-016` — Actual output not matching declared expected output stops
execution and reports the mismatch. It is never assumed acceptable.

### Fail-fast semantics

| Condition | Behaviour |
|---|---|
| Validation failure | Block, ask for a fix |
| A skill crashes | Log and continue to the next skill — do **not** auto-retry |
| A required artifact is missing | Block advancement — never substitute another |
| The manifest itself is invalid | Stop immediately, before any stage runs |

## 7.5 The Stage Confirmation Protocol

```
[C]ontinue to next stage
[R]eview this stage in detail
[B]ack to previous stage
[X]it workflow
```

| Mode | Trigger | Behaviour |
|---|---|---|
| **Standalone** | `analyze <KEY>`, `test <KEY>`, `prepare …` | `REQ-WFE-013` — **Always pauses** after every stage. Never auto-advances. `[C]` is unavailable until all validation checks pass |
| **Chain** | Entry intent contains `generate` | `REQ-WFE-014` — Auto-advances with a single progress line per stage. **Stops and shows the full menu on any validation failure** |

**Why two modes rather than one.** Always-pausing creates confirmation fatigue on
a legitimate multi-step job, and fatigue produces reflexive `[C]`. Never-pausing
allows a bad batch to run silently to completion — which is the actual expensive
failure. Chain mode auto-advances through *progress* and hard-stops on the *first
sign of trouble*, which targets the real risk rather than the visible one.

`REQ-COST-003` — Before a materially larger-than-typical batch begins, the
proposed plan and stage count are shown and explicit confirmation is required —
**before starting**, not only between stages once it is already running.

## 7.6 Artifacts: the significant change from Atlas

In Atlas, stages communicated through JSON files under `.atlas/tmp/…`, and those
files were the source of truth for the next stage. In Métis they are not.

`REQ-WFE-015` — **Stage inputs are graph queries.** File artifacts are disposable
projections for human inspection, never the source of truth.

| | Atlas | Métis v2 |
|---|---|---|
| Stage input | Read a JSON file written by a prior stage | Query the graph |
| Cross-run memory | None — everything re-fetched | The graph persists |
| Handoff between workflows | Inline context or file paths | Graph node ids |
| Artifact on disk | Load-bearing | Inspection convenience |
| Stale artifact risk | Real — a stale file silently feeds a later run | Eliminated — the graph carries validity windows |

Artifact paths, where written, follow one pattern:

```
<workspace>/.metis/tmp/<workflow-code>/<scope-id>/<ordinal>-<stage-name>/<artifact>
```

Each artifact directory carries a metadata file recording the producing stage,
the graph query that produced it, and the commit/episode ids it reflects — so an
artifact can always be traced back to graph state rather than trusted on its own.

## 7.7 Skill structure

`REQ-SKL-001` — Every skill follows one structure:

```
workflows/skills/<name>/
├── SKILL.md          # frontmatter, purpose, step index, non-negotiable rules
├── steps/
│   └── NN-<stage-slug>.md
├── knowledge/
│   └── <topic>.md
├── scripts/
├── resources/
├── configs/
└── tests/
```

`REQ-SKL-002` — **The content boundary rule:** always-enforced rules live in
`SKILL.md`; supporting detail lives in `knowledge/`. A rule buried in a knowledge
file is a rule that will be skipped.

`REQ-SKL-007` — Every skill declares its **"when to stop and ask"** conditions
explicitly, as a table. A skill with no stop conditions has not been thought
through.

`REQ-GRD-032` — The four RPI gates are documented **once** in a shared protocol
document and referenced. They are never re-prosed per skill.

### Presentation-producing skills

`REQ-SKL-006` — Generation logic (`scripts/`) and visual structure
(`templates/`) are versioned independently. A template redesign must not require
touching generation logic, and a rendering-library swap must not require touching
templates.

## 7.8 Skill catalogue

Grouped by the layer they serve. Skills marked **↺** are ported from Atlas with
inputs rebound to the graph; **✚** are new; **⊘** are retired.

### Requirement layer
| Skill | Status | Purpose |
|---|---|---|
| `jira-intake` | ↺ | Fetch, normalise to UIF, land as Episode (§05) |
| `requirement-miner` | ✚ | Four-stage mining (§05.6–5.9) |
| `requirement-quality-checker` | ✚ | EARS + 29148 + vagueness on demand |
| `graph-context-loader` | ✚ | Resolve a scope to its graph subtree — replaces every "re-fetch the ticket" step |
| ~~`confluence-reader`~~ | ⊘ | Second intake source, out of scope (§01.5) |
| ~~`atlassian-analyzer`~~ | ⊘ | Zephyr/Scale intake, out of scope |

### Specification layer
| Skill | Status | Purpose |
|---|---|---|
| `code-analysis-runner` | ✚ | Orchestrate the Joern sidecar (§13) |
| `code-analysis-reader` | ✚ | Serve verified type registry, endpoints, transitions from the graph |
| `contract-analyzer` | ↺ | OpenAPI/Swagger parsing and drift cross-check |
| `database-schema-analyzer` | ↺ | Schema inventory |
| `repository-cloner` | ↺ | Checkout at a named commit |
| ~~`git-repository-analyzer`~~ | ⊘ | ~11k LOC superseded by the CPG (§12.1) |
| ~~`code-explorer`~~ | ⊘ | Superseded by the verified registry (§13.7) |

### Design layer
| Skill | Status | Purpose |
|---|---|---|
| `scenario-normalizer` | ↺ | ACs → structured test scenarios |
| `coverage-mapper` | ↺ | Scenarios → automation coverage status |
| `automation-viability-classifier` | ↺ | extend / generate / migrate / duplicate / blocked |
| `performance-candidate-classifier` | ↺ | Identify load-test candidates from SLA-tagged requirements |
| `test-definition-drafter` | ↺ | Produce the structured plan generation works from |
| `behaviour-verifier` | ✚ | Determinism, guard atomicity/completeness, reachability (§08) |

### Behaviour layer
| Skill | Status | Purpose |
|---|---|---|
| `test-developer` | ↺ | Router: classify API/Web intent, enforce shared rules, route to specialist |
| `api-test-developer` | ↺ | API automation + test-case drafting |
| `web-test-developer` | ↺ | Web automation + test-case drafting |
| `performance-test-developer` | ↺ | Load-test generation |
| `test-case-publisher` | ↺ | **Sole owner** of external test-management writes |

### Quality & SDLC layer
| Skill | Status | Purpose |
|---|---|---|
| `code-reviewer` | ↺ | Severity-classified review with registry verification |
| `merge-request-creator` | ↺ | MR draft, AI-authorship labelling, confirmation gate |
| `defect-reporter` | ↺ | Defect draft from real failure evidence |
| `quality-reporter` | ↺ | Scoped quality and release reports from the graph |
| `deck-renderer` | ↺ | Point-in-time PPTX snapshot |
| `site-renderer` | ↺ | Always-current static site |

### Platform layer
| Skill | Status | Purpose |
|---|---|---|
| `review-assist` | ↺ | Walk a reviewer through one quarantined item |
| `onboarding` | ↺ | The project onboarding runbook |
| `academy` | ↺ | Explanation content assembly |
| `config-manager` | ↺ | Configuration and credential resolution |
| `metrics-reader` | ↺ | Analytics queries against the organisation's metrics store |
| `k8s-observer` | ↺ | Cluster evidence collection for defect triage |

`REQ-SKL-008` — No skill may create a competing router. There is one entry point.

## 7.9 Agent generation

`REQ-SKL-003` — Agent definitions for every client are **generated from one
source** (skill frontmatter) so client variants cannot drift.
`REQ-SKL-004` — A drift test fails when a skill definition and its generated agent
disagree.
`REQ-SKL-005` — The catalogue is discoverable at runtime through a tool call.

Agents group skills into the workflow families of §7.2. They are a *packaging*
concern, not a second place where behaviour is defined.

## 7.10 Manifest validation

Runs in CI, before any deployment:

| Check | Fails when |
|---|---|
| Mandatory fields | A workflow lacks `code`, `description`, `entry_prompt` or `stages` |
| Stage completeness | A stage lacks `ordinal`, `required_artifacts`, `validation_checks` or `skills` |
| Ordinal uniqueness | Two stages in one workflow share an ordinal |
| Skill existence | A named skill has no corresponding skill directory |
| Chain integrity | `next_workflow` names a workflow that does not exist |
| Condition determinism | A conditional skill's condition is not expressed as a property of request shape |

## 7.11 Determinism testing

| Test | Method |
|---|---|
| Cross-model | Run the same input under two models; diff stage sequence and artifact set. Must be identical |
| Regression corpus | A fixed set of inputs with expected stage sequences, asserted in CI |
| Ambiguity | An input matching no pattern must produce the menu, never a route |
| Gate enforcement | An injected validation failure must block, and no downstream stage may execute |
| Chain stop | An injected failure mid-chain must stop and show the full menu |

## 7.12 Anti-patterns, stated explicitly

Each of these appeared in the prior systems' own documentation as something to
avoid — carried forward because they are the failures that actually recur.

| Anti-pattern | Why it is prohibited |
|---|---|
| Routing without classifying first | Produces different routes for the same input across sessions |
| Guessing an ambiguous intent | A wrong route silently produces confident, wrong work |
| Skipping a stage because it "looks unnecessary" | The manifest, not the model, decides |
| Reordering skills within a stage | Later skills depend on earlier outputs in ways not always visible |
| Auto-advancing in standalone mode | Removes the only human checkpoint |
| Recovering from a validation failure automatically | Converts a caught problem into a hidden one |
| Substituting a missing artifact | The substitute is a fabrication with an artifact's authority |
| Generating a summary report instead of the requested artifact | Looks like completion; is not |
| Referencing a class, path or endpoint without verifying it exists | The single most common hallucination in generated code |
