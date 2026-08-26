## Migration And Deprecation Ledger

| ID | Current source/value/component | Target token/specification | Disposition | Consumers | Phase | Completion evidence | Status |
|---|---|---|---|---|---|---|---|
| MIG-001 | [path/value] | [target] | preserve / alias / consolidate / replace / deprecate / exception | [consumers] | [phase] | [test/render/search] | planned / in progress / complete |

### Migration Rules

- Preserve intentional behavior while moving consumers incrementally.
- Introduce canonical tokens or specifications before removing old values.
- Keep compatibility aliases until a repository search proves no consumers remain.
- Record documented exceptions with owner, reason, and recheck trigger.
- Do not mark a row complete without implementation and verification evidence.
