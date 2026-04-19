# CD-001 — Prompt Runner

Component design for the `prompt-runner` CLI.

## 1. Purpose

`prompt-runner` executes a sequence of prompt pairs defined in a markdown file. For each pair it runs the generation prompt through a configured coding-agent backend, optionally runs the validation prompt in a separate backend session, and iterates on failures up to a configured maximum.

The runner is content-agnostic. Its only hardcoded knowledge is the structural markdown contract described below.

## 1.1 Run/worktree model

For prompt-runner, the run directory is the editable worktree for that run.

- Project files that the generator or judge should read or write live directly under `run_dir` at their real project-relative paths.
- Runner-owned temporary and forensic files live under `run_dir/.run-files/`.
- When a new run starts from a separate source project tree, prompt-runner initialises `run_dir` by copying the source tree into the run worktree before execution.
- When `run_dir` is the project root, `.run-files/` must stay gitignored.

## 2. Input contract

### 2.1 Top-level prompts

Each prompt starts with a level-2 heading whose first word is `Prompt`.

Accepted forms:

- `## Prompt 1: Title`
- `## Prompt: Title`
- `## Prompt Title`
- `## Prompt 3 — Title`
- `## Prompt`

Any number in the heading is ignored. Prompt indices are positional.

Optional prompt-heading markers:

- `[interactive]`
- `[MODEL:...]`
- `[EFFORT:...]`
- `[VARIANTS]`

`[interactive]` and `[VARIANTS]` are mutually exclusive.

### 2.2 File-level metadata and normal prompt subsections

Prompt files may declare one file-level metadata block before the first prompt:

- `### Module`

Rules for file-level metadata:

- `### Module` applies to the whole file, not to one prompt pair.
- `### Module` may appear at most once.
- No other `### ...` subsection is allowed before the first prompt heading.

Normal prompts then use exact `###` subsection headings. Allowed subsection names are:

- `Required Files`
- `Include Files`
- `Checks Files`
- `Deterministic Validation`
- `Generation Prompt`
- `Validation Prompt`
- `Retry Prompt`

Rules:

- `### Generation Prompt` is required.
- `### Validation Prompt` is optional.
- Metadata subsections must appear before `### Generation Prompt`.
- `### Retry Prompt`, if present, must appear after `### Validation Prompt`.
- Each subsection may appear at most once per prompt pair.
- Only the exact reserved subsection level is structural; deeper headings remain part of the prompt body.

### 2.3 Variant prompts

A heading marked `[VARIANTS]` is a fork point.

Structure:

```markdown
## Prompt 2: Audit [VARIANTS]

### Variant A: Long checklist

#### Generation Prompt

generator for variant A

#### Validation Prompt

validator for variant A
```

Rules:

- Each variant starts with `### Variant <name>: <title>`.
- Prompt subsections inside a variant use `####` headings.
- A variant may contain multiple prompt pairs by repeating `#### Generation Prompt` and optional `#### Validation Prompt`.
- Standalone `[MODEL:...]` and `[EFFORT:...]` lines between variant pairs update defaults for the next pair in that variant.

### 2.4 Metadata semantics

- `Required Files`: each non-empty line is a path that must exist before generation.
  - Missing required files halt the run before any backend call.
  - Required files do not inject their contents into prompts.
- `Include Files`: each non-empty line is a path that must exist and whose text must be injected into the generator and judge prompts.
- `Checks Files`: each non-empty line is a path whose existence should be recorded without failing the prompt.
  - Missing check files are logged as warnings.
  - Checks files do not inject their contents into prompts.
- `Deterministic Validation`: each non-empty line becomes one argv element for a Python validator invoked after generation and before judging.
- `Retry Prompt`: optional revision-only instruction block for generator retries.
  - `Retry Prompt` defaults to `REPLACE`.
  - `[REPLACE]` replaces the default retry instruction block.
  - `[APPEND]` appends custom retry instructions after the default block.
  - `[PREPEND]` prepends custom retry instructions before the default block.
  - Runner-supplied retry context such as `<REQUIRED_CHANGES>` remains available.
- Prompt bodies may also embed file contents inline with `{{INCLUDE:...}}`.
  - `{{INCLUDE:path/to/file}}` reads the named file and replaces the directive with the file text.
  - `{{INCLUDE:placeholder_name}}` first resolves the placeholder, then reads the resulting file.
  - Inline include is for cases where the prompt body itself should contain the source text rather than pointing at a path.
- Prompt bodies may also embed runtime-created files inline with `{{RUNTIME_INCLUDE:...}}`.
  - `{{RUNTIME_INCLUDE:path/to/file}}` reads the named file later, when the specific generator or judge message is assembled.
  - Runtime include is for artifacts that do not exist when the prompt pair is first rendered, such as a generated inventory file embedded inside the validation prompt's `Context` section.

Metadata path resolution is relative to the run worktree root.
Inline include resolution is relative to the run worktree first and then to the prompt file's own directory when the worktree path does not exist.

## 3. Parser model

The parser produces these normalized objects:

```python
@dataclass(frozen=True)
class PromptPair:
    index: int
    title: str
    generation_prompt: str
    validation_prompt: str
    retry_prompt: str
    heading_line: int
    generation_line: int
    validation_line: int
    retry_line: int
    required_files: tuple[str, ...] = ()
    include_files: tuple[str, ...] = ()
    checks_files: tuple[str, ...] = ()
    deterministic_validation: tuple[str, ...] = ()
    retry_mode: str = "replace"
    module_slug: str | None = None
    interactive: bool = False
    model_override: str | None = None
    effort_override: str | None = None


@dataclass(frozen=True)
class VariantPrompt:
    variant_name: str
    variant_title: str
    pairs: list[PromptPair]


@dataclass(frozen=True)
class ForkPoint:
    index: int
    title: str
    heading_line: int
    variants: list[VariantPrompt]
```

`generation_line`, `validation_line`, and `retry_line` point at the subsection heading lines.

`module_slug` is file-scoped metadata propagated onto every parsed prompt pair in the file.
If the file omits `### Module`, the runner must infer one file-level module slug from the first prompt title and apply it consistently across the file.

## 4. Parser errors

Every parse failure raises `ParseError(error_id, message)`.

Stable parser error IDs:

- `E-NO-GENERATION`
- `E-BAD-SECTION-ORDER`
- `E-DUPLICATE-SECTION`
- `E-UNKNOWN-SUBSECTION`
- `E-NO-VARIANTS`

`### Module` inside a prompt pair or variant pair is invalid and must be rejected as an unknown subsection, because module scope belongs to the whole file.

Messages must identify the prompt or variant, cite the relevant line number, and include a concrete repair instruction.

## 5. Serialization contract

Any internal synthetic prompt file emitted by the runner must use the same heading-based format as user-authored prompt files.

That includes:

- `## Prompt N: Title`
- optional file-level `### Module`
- optional `### Required Files`
- optional `### Include Files`
- optional `### Checks Files`
- optional `### Deterministic Validation`
- `### Generation Prompt`
- optional `### Validation Prompt`

Synthetic prompt files and all other runner-owned artifacts are stored under `run_dir/.run-files/`.
Runner-owned artifacts for one prompt file are grouped under `run_dir/.run-files/<module-slug>/`.

Per-iteration forensic traces must also include the exact rendered backend input prompts:

- generator input prompt for each iteration
- judge input prompt for each iteration
- generator output capture for each iteration
- judge output capture for each iteration

These traces must be stored in runner-owned paths under `.run-files/` and must reflect the exact prompt text after placeholder resolution, inline includes, preludes, and revision feedback assembly.

## 6. Testing focus

Tests must cover:

- heading parsing and positional indexing
- interactive and directive stripping
- required/checks/deterministic subsections
- include-file injection
- inline `{{INCLUDE:...}}` expansion
- late-bound `{{RUNTIME_INCLUDE:...}}` expansion
- validator-less prompts
- variant forks
- multiple prompt pairs within one variant
- unknown, duplicated, or misordered subsections
- serializer output in heading-only format
- persistence of rendered generator and judge input prompts for each iteration
