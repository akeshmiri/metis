# Identification techniques

Standard practice. Each technique is good at something and bad at something
else, and the second half is the part usually left out.

| Technique | Finds | Is bad at |
|---|---|---|
| **Brainstorming** | Breadth, fast, across a mixed group | Anchoring — the first few suggestions shape the rest. Dominant voices crowd out quiet ones, so the output reflects the room, not the project |
| **Checklist / RBS prompt** | The known categories, reliably; the things everyone forgets | Anything not on the list. A checklist is a floor and reads like a ceiling |
| **Assumption analysis** | Risks hiding as certainties — "the data will be clean", "the API will not change" | Assumptions so deep nobody states them. It only surfaces what somebody can articulate |
| **SWOT** | Opportunities, which most techniques miss entirely | Precision. It produces themes, not risks — "competition" is not a register row |
| **Root-cause analysis** | The shared cause behind several symptoms; stops five rows being one risk | Speculative risks that have not happened yet — there is no root to analyse |
| **Interviews** | Depth, and what people will not say in a group | Scale, and interviewer bias. Slow |
| **Delphi** | Expert judgement with the anchoring removed — anonymous, iterated | Speed. Needs real experts and several rounds |
| **Lessons from prior projects** | Risks that actually occurred, with real frequencies | Anything novel about *this* project. Prior lessons are systematically over-weighted |
| **Document review** | Contradictions between plan, contract and design | Anything not written down, which is where most risk lives |

## Two rules that matter more than the technique

**Identify, then rate — never at once.** As soon as a number is attached the
conversation becomes about the number, and candidates stop arriving. Collect
first.

**A risk is a cause, an event and an effect.** "Database" is not a risk. *"If the
migration script has not been tested against production-scale data (cause), it
may exceed the maintenance window (event), delaying the release by a sprint
(effect)"* is one. A register full of one-word rows cannot be responded to,
because nobody can tell what would have to change.

## Distinguish a risk from an issue

A risk is uncertain; an issue has already happened. Issues in a risk register
crowd out the uncertain things the register exists for, and their probability is
1, which distorts every aggregate. Move them.
