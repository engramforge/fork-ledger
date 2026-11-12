# Changelog

## 0.2.0 — first public release

Ledger schema 0.2. Ledgers written by 0.1 load unchanged.

- The ledger file is chosen by `--ledger`, then `FORK_LEDGER`, then `./fork_ledger.json`. It was previously fixed next to the script.
- New `init` command. Refuses to overwrite an existing ledger.
- Fixed: a trigger of `none` (or text beginning `none —` / `none:`) was stored as pending, which hid the fork from `wake`. It is now unscheduled. `park` refuses such a trigger.
- New `check --fix` reclassifies existing pending-with-no-condition forks and notes the change in each fork's history.
- New `start` command sets a fork ACTIVE. The status existed in 0.1 with no command to set it.
- `add` accepts `--arc` and `--depends-on`; `park` accepts `--depends-on`; `list` accepts `--arc`. `check` flags a dependency on a fork that does not exist.
- `priorwork` searches the ledger plus any files or directories passed with `--in`.
- `wake`, `report` and the graph share one state rule. `report` has an Unscheduled section.
- `fork_graph.py` reads `--ledger`, colours lanes from a palette in order of appearance, and runs on Python 3.9 and newer.
- Added a test suite and a synthetic example ledger.

## 0.1

Internal version. Not published.
