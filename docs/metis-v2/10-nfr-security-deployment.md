# 10 — Non-Functional Requirements, Security & Deployment

## 10.1 Non-functional targets

| Category | Target | Notes |
|---|---|---|
| **Scale** | 10⁶–10⁷ nodes, 10⁷–10⁸ edges | Reference point: 500 services, 5,000 requirements, 50,000 tests, 5 years of history. Bounded traversal via team/service partitioning |
| **Latency** | P95 context-assembly retrieval ≤ 300 ms | Achieved by hybrid indexing and **no model call in the retrieval hot path** |
| **Ingestion throughput** | A 50,000-episode backfill completes within one maintenance window, resumably | The realistic worst case is a full-project backfill |
| **Concurrency** | 15 concurrent agent sessions × 3 headroom | DD-7. An engineering assumption, explicitly not an observed fact — replace with real numbers once usage data exists |
| **Availability** | **Single instance. No HA target in v1** | DD-2 selects Community Edition, which has no clustering or online backup. The availability target is explicitly **out of scope**, not merely unmet — see §10.2a |
| **CPG build** | Minutes to hours per repository | Batch only, never request-path (`REQ-OPS-006`) |
| **Auditability** | Every fact's origin and every rollback fully reconstructable | Bi-temporal model plus episode provenance |

`REQ-OPS-012` — Load testing is performed at the documented target load before
production enablement. A target that has never been tested is an aspiration.

**On CONST-021's numbers:** the concurrency and burst figures are a grounded
engineering estimate from stated assumptions, not a fact about any organisation.
They are the first numbers to replace once pilot usage data exists, and they are
re-validated quarterly.

## 10.2 Authentication and authorisation

| Requirement | Rule |
|---|---|
| `REQ-SEC-001` | OAuth2 with per-user scoping |
| `REQ-SEC-002` | Access tokens have a bounded lifetime; refresh tokens are revocable |
| `REQ-SEC-003` | Tokens are **re-validated every request**, never cached from issuance |
| `REQ-SEC-004` | Cross-team access is denied **even when a valid node identifier is supplied** |
| `REQ-SEC-005` | A non-interactive token path exists for CI and automation |
| `REQ-SEC-013` | Every externally-visible write is attributable to a named identity |

`REQ-SEC-003` and `REQ-SEC-004` together are the pair that actually matters.
Caching a token's claims from issuance means a revoked user keeps working until
expiry. Scoping only at query-construction time means a caller who already knows a
node id can read across team boundaries — which is exactly what pinned memory
blocks and incident data must not permit.

**Acceptance test:** issue a valid token for team A, request a node belonging to
team B **by its exact id**, assert denial.

## 10.2a Community Edition constraints (DD-2)

Neo4j Community is selected. Four consequences, each with its compensating
control. None is a blocker; all are real.

| Enterprise feature unavailable | Consequence | Compensating control in v1 |
|---|---|---|
| **Clustering / failover** | Single instance. No HA | Availability target removed from §10.1 rather than left as an unmet number |
| **Online backup** | No hot backup | `REQ-OPS-005a` — scheduled offline dump with a **verified restore drill**. Backup window is real downtime and must be scheduled, not assumed away |
| **Native role-based access control** | Database cannot enforce team scoping | `REQ-SEC-004a` — **application-level scoping**, enforced in one place |
| **Multiple databases per instance** | Only one database plus `system` | The CPG cannot live in a second database on the same instance. It stays as `cpg.bin` artifacts (§13.2, revised) |

`REQ-OPS-005a` — Backup is a scheduled offline dump. A restore drill MUST be
performed and MUST reproduce the graph. An untested backup is not a backup.

`REQ-SEC-004a` — With no native RBAC, team scoping MUST be enforced at the
application layer, in a **single choke point** through which every query passes.
Scoping applied per-call-site is how a cross-team leak eventually happens: one new
tool forgets, and nothing catches it.

`REQ-SEC-004b` — A test MUST assert that **no query path bypasses the scoping
choke point.** This is stricter than testing that scoping works — it tests that
it cannot be avoided. Enterprise's native RBAC would have made this structural;
without it, the test is the only thing standing in its place.

**This is the one place where the conservative choice costs more work rather than
less.** Application-level RBAC is more code and more risk than a database
enforcing it. Recorded so it is a known trade, not a surprise.

### RBAC model

Roles are scoped by owning team. Four base roles:

| Role | Read | Propose | Approve | Administer |
|---|---|---|---|---|
| Consumer | own team | — | — | — |
| Contributor | own team | ✅ | — | — |
| Reviewer | own team | ✅ | ✅ | — |
| Platform admin | all | ✅ | ✅ | ✅ |

Approval authority is deliberately separate from contribution authority: the
reviewer gate (§06.7) is meaningless if the proposer can approve their own
proposal.

## 10.3 Data protection

| Requirement | Rule |
|---|---|
| `REQ-SEC-006` | Episode payloads store **references, not raw secrets or sensitive personal data**, where content is sensitive |
| `REQ-SEC-007` | Sensitivity classification resolves per repository from configuration and **fails closed** |
| `REQ-SEC-008` | Content classified above the configured threshold is **never sent to an external model** |
| `REQ-SEC-009` | PII flags propagate as access-control tags through derived entities |
| `REQ-SEC-010` | The audit log is itself access-controlled |
| `REQ-SEC-011` | Credentials never appear in logs, artifacts, compressed content or generated output |
| `REQ-SEC-014` | The model-provider data-retention posture is recorded in configuration and enforced by the classification gate |

### The classification gate

Every repository and content source carries a sensitivity classification. Before
any model call, the gate resolves the classification of the content and blocks the
call if it exceeds the configured threshold.

`REQ-SEC-007`'s fail-closed rule means an **unclassified** source is treated as
the most restrictive class, not the least. This will block work until someone
classifies it — which is the intended behaviour, because the alternative failure
sends unclassified content to a third party.

**Note on RD-6:** the data-retention posture is a real recorded decision, not a
stalled task. Whichever posture is recorded, the gate enforces it; the gate does
not have an opinion about which posture is correct.

## 10.4 Configuration model

| Requirement | Rule |
|---|---|
| `REQ-PLT-002` | No configuration in code — model names, classifications, endpoints, credentials all resolve through the configuration layer |
| `REQ-PLT-003` | The server **refuses to start** when no configuration exists. Starting with defaults is prohibited |
| `REQ-PLT-004` | Resolution follows a documented precedence — project → host → template — **first-found-wins, no silent merging** |
| `REQ-PLT-005` | Credentials resolve from a path distinct from general configuration and are not readable through general file-read tooling |

`REQ-PLT-003` looks unfriendly and is deliberate: a system that starts with
defaults will run against the wrong Jira instance, with the wrong model, under the
wrong classification, and produce plausible output the whole time.

`REQ-PLT-004`'s no-merge rule prevents the failure where a project file supplies
three of five fields and the remaining two come silently from a host file that
someone forgot existed.

## 10.5 Containers

| Requirement | Rule |
|---|---|
| `REQ-OPS-001` | All components are container images built from committed Dockerfiles |
| `REQ-SEC-012` | Containers run as **non-root** with a **read-only root filesystem, set at the container level** |

The container-level placement is called out because setting `readOnlyRootFilesystem`
at pod level instead of container level is silently ineffective — it was one of
five real chart bugs found in v1 only by deploying for real.

Five images, matching §02.3: `mcp-server`, `review-api`, `ingestion-worker`,
`scheduler`, `joern-sidecar`. The sidecar carries a JVM and needs its heap sized
explicitly (§10.7).

## 10.6 Deployment chart

| Requirement | Rule |
|---|---|
| `REQ-OPS-002` | Deployment is by a versioned chart that passes lint and template rendering **in CI** |
| `REQ-OPS-003` | Every referenced resource is defined by the chart; a referenced-but-undefined resource **fails CI** |
| `REQ-OPS-004` | Environment overrides merge predictably; array-replacement semantics are documented and tested |

`REQ-OPS-003` exists because of a specific real failure: in v1 every pod spec
referenced a service account by name and **no chart template ever created it** —
the chart passed lint and would have failed at pod admission in any real cluster.
Lint does not catch dangling references; a test that resolves every reference does.

`REQ-OPS-004` exists because environment override files **replace** arrays rather
than merging them, so an override supplying one item silently drops the rest.

**Chart CI checks:**

| Check | Fails when |
|---|---|
| Lint | Template syntax is invalid |
| Render | Templates do not render for every values file |
| Reference resolution | Any referenced resource is undefined |
| Override semantics | A per-environment override drops values it was not meant to |
| Security context | Any container runs as root, or has a writable root filesystem |
| Secret wiring | A declared secret is not actually mounted or referenced |

## 10.7 Resource sizing

| Component | Profile | Notes |
|---|---|---|
| `mcp-server` | CPU-light, memory-moderate, horizontally scaled | Stateless |
| `review-api` | As above | Stateless |
| `ingestion-worker` | Memory-heavy during Cognify batches | Vertical |
| `scheduler` | Light, single instance | Cron-driven |
| `joern-sidecar` | **Memory-dominant.** JVM heap sized to the largest repository | See below |
| Graph | Memory-dominant; page cache sized to the working set | Clustering at Enterprise tier |

**Joern heap sizing** is the one genuinely new operational concern. Published
figures give a sense of the range: a single driver's source tree produces roughly
9 million nodes and 84 million edges at ~3.7 GB heap; a whole operating-system
kernel reaches 48 million nodes and 431 million edges and needs a 90 GB heap.

`REQ-OPS-006` — Because build times run minutes to hours, this is a scheduled job
with its own resource envelope, never a request-path component.

## 10.8 Observability

| Requirement | Rule |
|---|---|
| `REQ-PLT-011` | A health endpoint reports database connectivity, schema version and configuration validity |
| `REQ-PLT-012` | Schema version is recorded in the graph and checked at startup; a mismatch **blocks startup rather than migrating implicitly** |
| `REQ-OPS-007` | Guardrail metrics are exported to the organisation's existing metrics surface, **not a parallel dashboard system** |

### Metrics that must be emitted

Beyond the DQ catalogue (§06.12), the operational signals:

| Signal | Alert condition |
|---|---|
| Extractions with a valid source span | **Any value below 100% is a pipeline bug — page immediately** |
| Cognify rejection rate | A sudden spike indicates a connector regression, not worse content |
| Draft-tier facts later rejected | A rising trend means confidence defaults are miscalibrated |
| High-risk entities promoted with one source | Target zero; any nonzero value is a guardrail breach |
| Open `Disputed` count and time-to-resolution | A growing backlog usually means the precedence table is misconfigured |
| Judge disagreement by connector | Isolates which source type produces over-generalised extractions |
| Reviewer override rate | A rising trend indicates extraction-quality regression |
| Quarantine queue depth and age | The leading indicator for reviewer capacity |
| False-acceptance rate on the adversarial set | The single most important safety number |
| Mean time-to-rollback | Should trend down as tooling matures |
| CPG build duration and failure rate | Per repository |
| Cost per 1,000 episodes | `REQ-OPS-010` — **measured, replacing any estimate** |

## 10.9 Backup, restore and drift

| Requirement | Rule |
|---|---|
| `REQ-OPS-005` | Backup and restore are exercised, with restore **reproducing the graph** |
| `REQ-OPS-008` | Environment drift is verified by infrastructure-as-code diff against committed configuration, not manual comparison |
| `REQ-OPS-009` | Rollback of a bad ingestion run is exercised at least once before production enablement |

A rollback path that has never been executed is a claim. So is a backup that has
never been restored.

## 10.10 Runbooks

`REQ-OPS-011` — Runbooks exist for, at minimum:

| Scenario | Must cover |
|---|---|
| Ingestion failure | Diagnose, resume from checkpoint, confirm no duplicates |
| Review-queue backlog | Triage order, capacity escalation, and the explicit rule that **timeout-promotion is not an option** |
| Contradiction spike | Check the precedence table **first**, before assuming the data is bad |
| Bad ingestion run | Identify the job, roll back, verify prior state restored, record the rollback |
| CPG build failure | Frontend errors, heap exhaustion, partial-parse detection |
| Schema version mismatch | Why startup is blocked and how to migrate deliberately |
| Credential rotation | Without a full redeployment |
| Model provider outage | What degrades (Stage 2 mining) and what does not (everything deterministic) |

## 10.11 Risk register

| Risk | Mitigation | Residual |
|---|---|---|
| Reviewer bottleneck under a conservative quarantine policy | Reviewer time budgeted explicitly, not assumed absorbed | Real. The safe failure mode is "nothing approved" — safe, but still a failure |
| Precedence-table misconfiguration | `history()` makes "why did this fact win" always inspectable (`REQ-TMP-010`) | Low |
| Judge model cost and latency at scale | Tracked explicitly; a cheaper judge substituted once judge-vs-human agreement data exists | Medium until measured |
| Graph write contention at high commit velocity | Incremental delta-subgraph validation; batch ingestion | Medium |
| Sensitive data in episodes | Reference-not-raw storage; PII propagation; fail-closed classification | Low |
| Ontology rigidity vs. real-world messiness | Explicit extension mechanism; partial adoption supported | Medium — the four-place rule makes change deliberately expensive, which is intended |
| **Single-instance graph, no HA** | Accepted under DD-2. Compensated by a tested offline backup and restore drill (`REQ-OPS-005a`) | **Accepted.** Data loss window equals the backup interval. Revisit only if production adoption happens |
| **Application-level RBAC instead of native** | Single choke point plus a bypass test (`REQ-SEC-004a`/`b`) | **Medium.** More code and more risk than a database enforcing it — the one place the conservative choice costs more, not less |
| **No formal security/compliance review before pilot** | The underlying controls (§10.2–10.3) remain in force regardless — this accepts skipping *external review* of them, not dropping them | **Open.** Revisit before the generic write path is enabled beyond pilot, since that is where an unreviewed gap first matters |
| **No named ownership of the review queue** | The no-auto-promotion fail-safe means an unstaffed queue degrades to "nothing gets approved" | **Open.** Safe, but it means the platform stops producing new Approved facts. Worth an owner before quarantine volume matters |
| Joern version churn breaking query packs | Version pinned per pack; upgrades are reviewed changes with a full pack test re-run | Low |

## 10.12 Rollout posture

| Phase | Scope | Guardrail posture |
|---|---|---|
| Pilot | One service; Jira intake + code analysis; read-only tools | **All ten layers active from day one, not phased in** |
| Expand | More services; contract and test-suite evidence | Validate the precedence table against real conflicts |
| Gated write-back | Enable the generic write path per confidence tier | Watch reviewer override rate closely before widening |
| Full scale | All onboarded services, consolidation at scale | Adversarial testing becomes recurring governance, not a launch checklist item |

`REQ-MCP-006` — The generic write path remains disabled until the guardrail stack
has a production track record. This is a phase gate, not a permanent restriction —
and the track record is the evidence, not the elapsed time.
