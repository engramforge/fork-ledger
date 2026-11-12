# The Fork Ledger: deferred work with explicit wake conditions

**Jeff Gray · EngramForge · Working note, November 2026**

## Summary

Projects lose work at decision points. One option is taken; the others are deferred "until later" and never looked at again, because nothing records what "later" meant. The Fork Ledger is a plain-JSON record of those deferred branches in which every entry states the condition that should bring it back. Its contribution is to treat two states as first-class that ordinary trackers leave invisible: a wake condition that can no longer occur, and no wake condition at all. This note describes the mechanism, reports what its first weeks of use in one research program showed, and states what has not been tested.

## 1. The problem

A deferral is a small promise about the future: *we will revisit this when X*. Three things go wrong with it.

1. **X happens and nobody notices.** The condition was met, but the deferred item was not in front of anyone at the time.
2. **X becomes impossible.** The experiment the item was waiting on is cancelled. The item is now waiting on nothing, yet looks the same as an item that is waiting patiently.
3. **X was never stated.** The item was set aside with no condition. It will resurface only by accident.

The cost shows up as rediscovery. In the program this tool came from, a component designed in the spring was independently re-derived from first principles four months later, and one line of work ran for two months on an assumption that an earlier, unconsulted finding had already contradicted.

Language-model agents have the same weakness, and it has now been measured. Recent benchmarks study *prospective memory*: carrying an intention forward and acting on it when a later cue arrives. On PM-Bench, the best configuration tested reached 65.1% F1 [1]. TriggerBench reports that prospective recall is markedly harder for current models than answering direct questions about the same context, and that it degrades as the context grows [2]. A long working session with an agent is exactly the setting in which "we'll come back to that" is said and lost.

## 2. The mechanism

Each fork is a record with a title, a kind (deferral, unchosen branch, designed-but-not-built, open question, or an unwritten rule), the reason it was parked, and a **trigger**: the wake condition in plain language. Its trigger status is one of four values.

| Trigger status | Meaning |
| --- | --- |
| `pending` | Waiting on a stated condition |
| `FIRED` | The condition has happened |
| `orphaned` | The condition can no longer happen |
| `none` | No condition was recorded |

One command, `wake`, returns everything that needs a decision now: fired triggers, orphaned triggers, unscheduled items and work in flight. Items parked behind a live condition stay out of the way.

Four rules keep the record honest:

- **Closing requires a reason.** The tool refuses to close a fork without one.
- **Nothing is deleted.** Forks are amended, closed or superseded, and every change is appended to the fork's history.
- **"None" is not a condition.** A fork whose trigger is "none" is classified as unscheduled however it is phrased.
- **The tool does not evaluate triggers.** Deciding that a condition has occurred is a judgment made by a person or an agent. The tool records that judgment and keeps it visible.

Forks may declare dependencies on other forks. A companion script draws the ledger as a dated graph and detects cycles, since two forks that each wait on the other will wait forever.

The whole thing is two Python files with no dependencies and one JSON file that can be read, diffed and committed.

## 3. What use in one program showed

The ledger was seeded in late August 2026 with 36 forks swept from the previous month of work, some dated back to when the deferral was originally made. By its last update in early October it held 72 forks. The figures below are from that single ledger and one operator; they are observations, not a controlled result.

| State | Forks |
| --- | ---: |
| Resolved (closed or superseded, each with a reason) | 19 |
| Parked behind a live condition | 30 |
| No wake condition | 17 |
| Trigger fired, still open | 5 |
| Trigger orphaned | 1 |

Three observations follow.

**Unscheduled work is common.** Seventeen of 72 forks (24%) have no wake condition. On the tool's first run against its own seed data, the integrity check flagged nine such items, among them three designed components that had sat untouched for four to six months.

**The record can lie if "none" is allowed to pass as a condition.** Seven of those seventeen were stored with trigger text beginning "none" but marked as pending, which hid them from `wake`. The defect was in the tool, not the operator: version 0.1 accepted the text and classified it as a real condition. Version 0.2 classifies by meaning and repairs old ledgers. This is the kind of silent failure the tool exists to prevent, and it occurred inside the tool.

**Visibility is not action.** Five forks whose conditions have already been met remain open, and the ledger contains one circular dependency. The tool surfaced all of them. It did not cause any of them to be acted on.

## 4. Related work

Personal-productivity practice has long had the pieces: *Getting Things Done* keeps "waiting for" and "someday/maybe" lists and a tickler file that resurfaces items on a date. Architecture decision records capture the decision taken and the alternatives considered, but not a condition under which a rejected alternative should be reopened. Issue trackers model "blocked by" relations between tickets; a wake condition here is a statement about the world, and is often an event that no ticket represents.

On the agent side, PM-Bench [1] and TriggerBench [2] establish prospective memory as a measured weakness. Liu and Gabriel's benchmark has since been used to evaluate external memory scaffolds, including typed intention stores for small models [3], which is the closest published relative of this tool. The Fork Ledger differs in aim: it is an operator-facing record for long-running human and agent work, with orphaned and unscheduled items as explicit states, and it makes no claim about model internals.

No priority claim is made beyond that description. The individual ideas are old; the specific combination and the two first-class failure states are what is offered.

## 5. What is not established

- **No outcome measurement.** There is no evidence here that using the ledger improves project outcomes or reduces rediscovery. The motivating incidents happened before the tool existed.
- **No agent evaluation.** The ledger has not been run as a scaffold on PM-Bench, TriggerBench or any other benchmark. The claim that it helps agents is a hypothesis.
- **One user.** All usage data comes from a single operator working with AI assistants on one program.
- **Triggers are unverified text.** Nothing checks a trigger against the world, so a fork can sit "pending" after its condition has occurred.

A fair test would fix a benchmark and a model, compare an agent with and without the ledger as its only added scaffold, and set the pass bar before any run.

## References

[1] G. Liu and S. Gabriel. *PM-Bench: Evaluating Prospective Memory in LLM Agents.* arXiv:2607.12385, July 2026.

[2] T. Zhang et al. *TriggerBench: Investigating Prospective Memory for Large Language Models.* arXiv:2606.23459, June 2026.

[3] *Making Prospective Memory SLM-Shaped: Typed Intention Stores for Small-Model Agents.* arXiv:2609.01272, September 2026.

## AI assistance

The tool's code and this note were drafted with an AI assistant (Anthropic's Claude) under the author's direction. The author made the design decisions, reviewed the output and is responsible for the content.

## License

© 2026 EngramForge, Inc. This note is licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/. The accompanying code is licensed under the Apache License 2.0.
