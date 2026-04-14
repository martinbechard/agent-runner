# Codex JSON Judge Smoke

## Prompt 1: Generator And Judge

```
Read docs/input.txt and write docs/output.txt containing exactly one line: RESULT: success
Then reply with one sentence confirming the file was written.
```

```
Verify that docs/output.txt exists and contains exactly one line: RESULT: success
If correct, respond briefly and end with VERDICT: pass
If not correct, explain the mismatch and end with VERDICT: revise
```
