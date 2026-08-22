# Test Technique Reference

Use this guide to choose test design techniques that fit the requirement instead of defaulting to generic happy-path coverage.

This reference follows the ISO/IEC/IEEE 29119-4 technique families:

- specification-based,
- structure-based,
- and experience-based.

## Specification-Based Techniques

| Technique | Use When | Typical Coverage Focus | Typical Output | Notes |
|---|---|---|---|---|
| Equivalence Partitioning | Inputs can be grouped into valid and invalid classes | Representative values from each class | Valid account type, unsupported account type | Pair with BVA for ranges and lengths |
| Boundary Value Analysis | Rules depend on ranges, limits, thresholds, counts, or lengths | Minimum, maximum, just-below, just-above values | Amount `0`, `1`, `999`, `1000`, `1001` | Good for numeric, date, size, and pagination rules |
| Classification Tree Method | Inputs vary across several categories or dimensions | Well-structured combinations of classes | Payment type x role x workflow state tree | Useful when the domain has many dimensions but needs clarity |
| Syntax Testing | Inputs must conform to a grammar, schema, or format | Valid and invalid syntax paths | File format cases, structured payload variants | Good for parsers, DSLs, file formats, and structured requests |
| Combinatorial Testing | Many option combinations exist and exhaustive testing is too large | High-risk interaction pairs or tuples | Browser x locale, role x region | Use pairwise by default unless risk justifies higher-order combinations |
| Decision Table Testing | Outcomes depend on combinations of business rules | Condition combinations and resulting actions | Role x status x feature-flag matrix | Strong for policy-heavy features |
| Cause-Effect Graphing | Inputs and rules interact in more complex logical combinations | Mapped relationships between causes and outcomes | Eligibility or approval logic graph | Useful when decision tables become too dense |
| State Transition Testing | Behavior changes by lifecycle state or status | Allowed, blocked, repeated, and recovery transitions | Draft to Submitted, Submitted to Approved | Include invalid or repeated transitions, not just happy paths |
| Scenario Testing | The feature is primarily a user or system workflow | End-to-end journeys and alternate flows | Create order, amend order, cancel order | Good for multi-step business behavior |
| Random Testing | Data space is large and stochastic sampling provides useful signal | Broad, varied execution across input space | Randomized payload or record selection | Use with explicit seed or reproducibility notes when possible |

## Structure-Based Techniques

| Technique | Use When | Typical Coverage Focus | Typical Output | Notes |
|---|---|---|---|---|
| Branch Testing | Internal control flow materially affects behavior | Branch coverage over decisions | Success and failure path coverage | Best when code or design visibility exists |
| Decision Testing | Single decision points drive outputs | True or false outcome coverage | If-else and switch decision coverage | Simpler than MC/DC for moderate logic |
| Branch Condition Testing | Conditions within one branch need individual exercise | Condition truth values within branches | Multi-condition validation cases | Useful for compound predicates |
| Branch Condition Combination Testing | Combinations of branch conditions matter | Combined truth-value coverage | Compound decision truth tables | Use selectively to avoid combinatorial explosion |
| MCDC Testing | High-criticality logic needs strong confidence | Independent effect of each condition | Safety or compliance logic coverage | Strong choice for high-risk rule engines or controls |
| Data Flow Testing | Data lifecycle and variable use matter | Definition-use paths and stale data risks | Setup-use-update-delete path checks | Helpful for stateful or data-sensitive logic |

## Experience-Based Techniques

| Technique | Use When | Typical Coverage Focus | Typical Output | Notes |
|---|---|---|---|---|
| Error Guessing | Historical defects or operational risk indicate likely weak spots | Experience-based negative checks | Null dependency response, stale cache, duplicate submit | Use prior incidents and defect clusters as inputs |
| Checklist-Based Testing | The team already uses a domain or regression checklist | Repeatable coverage for common risks | Audit fields present, logs written, alerts emitted | Good for release gates and operational readiness |
| Exploratory Testing | Requirements are incomplete or risk is not fully known | Time-boxed learning and defect discovery | Session charter for ambiguous validation behavior | Capture a charter, objective, and evidence expectations |
| Risk-Based Testing | Some requirements have much higher business impact than others | Depth proportional to risk and failure cost | Payment failure gets broader negative coverage | Use as a prioritization overlay, not a standalone technique |

## Selection Workflow

1. Start from the test basis.
	- Requirements, user stories, tickets, incidents, designs, and interface contracts define what can be tested.
2. Identify risk and complexity.
	- Higher business risk or technical complexity usually justifies broader technique combinations.
3. Choose the primary technique family.
	- Specification-based for externally visible behavior.
	- Structure-based for code or design internals where coverage logic matters.
	- Experience-based where ambiguity, defect history, or operational intuition matters.
4. Combine techniques where needed.
	- A realistic design often needs scenario testing plus decision tables plus boundary checks, not one technique only.

## Selection Hints

- Prefer equivalence partitioning plus boundary value analysis for numeric ranges, lengths, and date windows.
- Prefer decision tables or cause-effect graphing when several rules combine to produce one outcome.
- Prefer state transition testing when status, workflow stage, or lifecycle drives behavior.
- Prefer scenario testing when the main concern is a business journey across components.
- Prefer structure-based techniques only when the visibility and value justify them.
- Add error guessing, checklists, or exploratory sessions when operational failures have already happened in similar areas.
- Make the coverage objective explicit whenever a technique is selected so the resulting cases do not become vague or redundant.