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

### 2.2 Normal prompt subsections

Normal prompts use exact `###` subsection headings. Allowed subsection names are:

- `Required Files`
- `Checks Files`
- `Deterministic Validation`
- `Generation Prompt`
- `Validation Prompt`

Rules:

- `### Generation Prompt` is required.
- `### Validation Prompt` is optional.
- Metadata subsections must appear before `### Generation Prompt`.
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
- `Checks Files`: each non-empty line is a path whose existence should be recorded without failing the prompt.
- `Deterministic Validation`: each non-empty line becomes one argv element for a Python validator invoked after generation and before judging.

Metadata path resolution is relative to the run worktree root.

## 3. Parser model

The parser produces these normalized objects:

```python
@dataclass(frozen=True)
class PromptPair:
    index: int
    title: str
    generation_prompt: str
    validation_prompt: str
    heading_line: int
    generation_line: int
    validation_line: int
    required_files: tuple[str, ...] = ()
    checks_files: tuple[str, ...] = ()
    deterministic_validation: tuple[str, ...] = ()
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

`generation_line` and `validation_line` point at the subsection heading lines.

## 4. Parser errors

Every parse failure raises `ParseError(error_id, message)`.

Stable parser error IDs:

- `E-NO-GENERATION`
- `E-BAD-SECTION-ORDER`
- `E-DUPLICATE-SECTION`
- `E-UNKNOWN-SUBSECTION`
- `E-NO-VARIANTS`

Messages must identify the prompt or variant, cite the relevant line number, and include a concrete repair instruction.

## 5. Serialization contract

Any internal synthetic prompt file emitted by the runner must use the same heading-based format as user-authored prompt files.

That includes:

- `## Prompt N: Title`
- optional `### Required Files`
- optional `### Checks Files`
- optional `### Deterministic Validation`
- `### Generation Prompt`
- optional `### Validation Prompt`

Synthetic prompt files and all other runner-owned artifacts are stored under `run_dir/.run-files/`.

## 6. Testing focus

Tests must cover:

- heading parsing and positional indexing
- interactive and directive stripping
- required/checks/deterministic subsections
- validator-less prompts
- variant forks
- multiple prompt pairs within one variant
- unknown, duplicated, or misordered subsections
- serializer output in heading-only format
