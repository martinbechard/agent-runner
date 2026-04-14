# Agent Instructions

## 1. File Placement

- **RULE:** Before creating any new file in this repository, Codex MUST determine the target path with the repository's file-placement mechanism.
  - **BECAUSE:** This repository uses a living taxonomy in `docs/project-taxonomy.md`, and file placement is part of the design of the repo rather than an aesthetic preference.

- **RULE:** Codex SHOULD prefer the dedicated `project_organiser` custom agent when it is available in the current runtime.
  - **BECAUSE:** A dedicated agent keeps the taxonomy-reading context isolated from the main task and reduces path-placement drift.

- **RULE:** If the dedicated custom agent is unavailable, Codex MUST use the `project-organiser-use` skill or consult `docs/project-taxonomy.md` directly before writing the file.
  - **BECAUSE:** The fallback still needs to be taxonomy-driven; the absence of the agent is not permission to guess.

- **RULE:** Codex MUST NOT rely on an external `claude` CLI wrapper to classify file placement.
  - **BECAUSE:** File placement must work in Codex-native flows and should not depend on a separate product's authentication state.

- **RULE:** If no existing taxonomy category fits, Codex MUST update `docs/project-taxonomy.md` before placing the new file.
  - **BECAUSE:** New artifact types should extend the taxonomy instead of bypassing it.

- **RULE:** Codex SHOULD NOT reclassify files that already exist unless the task is specifically about moving or renaming them.
  - **BECAUSE:** The placement mechanism is for new-file decisions; routine edits should not trigger unnecessary file churn.
