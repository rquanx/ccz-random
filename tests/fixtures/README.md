# Test fixtures

Sanitized save files, memory snapshots and diagnostic samples belong here.
Do not add a player's live `SV` directory or files containing personal paths.

Suggested folders:

- `saves/`: minimal save samples for parser and validation tests.
- `memory/`: captured byte ranges with a JSON description of the game state.
- `diagnostics/`: redacted `.jsonl` events used to reproduce failures.

Every fixture should include its source game version, capture state and expected
result in a neighboring JSON file.
