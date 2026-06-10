---
marp: true
theme: default
paginate: true
style: |
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=Raleway:wght@200;300;400&display=swap');

  :root {
    --bg: #050607;
    --panel: #0b0d10;
    --panel-2: #101419;
    --line: #1b222b;
    --text: #f8fafc;
    --body: #a2aab5;
    --muted: #68717d;
    --orange: #ff6b1a;
    --cyan: #38bdf8;
    --green: #22c55e;
    --yellow: #f5a623;
    --red: #ef4444;
  }

  section {
    background: var(--bg);
    color: var(--text);
    font-family: 'Raleway', sans-serif;
    font-weight: 300;
    padding: 44px 68px;
    line-height: 1.42;
  }

  h1 {
    font-family: 'Outfit', sans-serif;
    font-weight: 800;
    font-size: 2.55em;
    line-height: 1;
    margin: 0 0 10px;
    color: var(--text);
    letter-spacing: 0;
  }

  h2 {
    font-family: 'Raleway', sans-serif;
    font-weight: 200;
    font-size: 1em;
    color: var(--body);
    margin: 0 0 16px;
    letter-spacing: 0;
  }

  h3 {
    font-family: 'Outfit', sans-serif;
    font-size: 0.62em;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    margin: 0 0 8px;
    letter-spacing: 0;
  }

  strong { color: var(--orange); font-weight: 400; }
  section::after { font-family: 'Outfit'; font-size: 0.55em; color: #222832; }
  section.lead { display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; padding: 0 90px; }
  section.lead h1 { font-size: 3.85em; }

  .kicker {
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    font-size: 0.62em;
    color: var(--orange);
    text-transform: uppercase;
    margin-bottom: 12px;
  }

  .subtitle {
    font-size: 1.05em;
    color: #ffffffa6;
    margin-top: 4px;
  }

  .chips {
    display: flex;
    gap: 8px;
    justify-content: center;
    margin-top: 22px;
  }

  .chip {
    font-family: 'Outfit', sans-serif;
    font-size: 0.56em;
    font-weight: 600;
    color: #d6dde5;
    padding: 5px 12px;
    border: 1px solid #ffffff24;
    border-radius: 999px;
    background: #00000055;
  }

  .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  .grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; }
  .row-flex { display: flex; gap: 14px; align-items: stretch; }

  .card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 14px;
    position: relative;
    overflow: hidden;
  }

  .card::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 2px;
    background: linear-gradient(90deg, var(--orange), transparent);
  }

  .card.cyan::before { background: linear-gradient(90deg, var(--cyan), transparent); }
  .card.green::before { background: linear-gradient(90deg, var(--green), transparent); }
  .card.yellow::before { background: linear-gradient(90deg, var(--yellow), transparent); }

  .card-title {
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    font-size: 0.82em;
    color: var(--text);
    margin-bottom: 8px;
  }

  .card-body {
    font-size: 0.62em;
    color: var(--body);
  }

  .tiny {
    font-size: 0.58em;
    color: var(--muted);
  }

  .metric {
    font-family: 'Outfit', sans-serif;
    font-weight: 800;
    font-size: 1.8em;
    color: var(--text);
    line-height: 1;
  }

  .label {
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    font-size: 0.53em;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 6px;
  }

  .tag {
    display: inline-block;
    font-family: 'Outfit', sans-serif;
    font-size: 0.52em;
    font-weight: 700;
    color: var(--body);
    padding: 3px 8px;
    border-radius: 4px;
    border: 1px solid var(--line);
    background: #ffffff06;
  }

  .tag.orange { color: var(--orange); border-color: #ff6b1a33; background: #ff6b1a12; }
  .tag.cyan { color: var(--cyan); border-color: #38bdf833; background: #38bdf812; }
  .tag.green { color: var(--green); border-color: #22c55e33; background: #22c55e12; }
  .tag.yellow { color: var(--yellow); border-color: #f5a62333; background: #f5a62312; }

  .stack {
    display: grid;
    gap: 10px;
    margin-top: 14px;
  }

  .stack-layer {
    display: grid;
    grid-template-columns: 310px 1fr 250px;
    gap: 12px;
    align-items: center;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px 18px;
  }

  .layer-name {
    font-family: 'Outfit', sans-serif;
    font-size: 0.92em;
    font-weight: 800;
    white-space: nowrap;
  }

  .layer-question {
    font-size: 0.58em;
    color: var(--body);
  }

  .flow {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 18px;
  }

  .flow-box {
    flex: 1;
    min-height: 62px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 10px;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }

  .flow-box .name {
    font-family: 'Outfit', sans-serif;
    font-size: 0.66em;
    font-weight: 700;
    color: var(--text);
  }

  .flow-box .note {
    font-size: 0.5em;
    color: var(--body);
    margin-top: 4px;
  }

  .arrow {
    width: 28px;
    height: 1px;
    background: #334155;
    position: relative;
  }

  .arrow::after {
    content: "";
    position: absolute;
    right: -1px;
    top: -4px;
    border-left: 7px solid #334155;
    border-top: 4px solid transparent;
    border-bottom: 4px solid transparent;
  }

  .phase-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-top: 18px;
  }

  .phase {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 13px;
    min-height: 82px;
  }

  .phase-id {
    font-family: 'Outfit', sans-serif;
    font-size: 0.56em;
    font-weight: 800;
    color: var(--orange);
  }

  .phase-name {
    font-family: 'Outfit', sans-serif;
    font-size: 0.76em;
    font-weight: 700;
    margin-top: 5px;
    color: var(--text);
  }

  .phase-note {
    font-size: 0.52em;
    color: var(--body);
    margin-top: 5px;
  }

  .table {
    display: grid;
    grid-template-columns: 140px repeat(3, 1fr);
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
    margin-top: 12px;
  }

  .cell {
    min-height: 52px;
    border-right: 1px solid var(--line);
    border-bottom: 1px solid var(--line);
    padding: 10px 12px;
    font-size: 0.57em;
    color: var(--body);
    background: #080a0d;
  }

  .cell:nth-child(4n) { border-right: 0; }
  .cell.header {
    font-family: 'Outfit', sans-serif;
    font-weight: 800;
    color: var(--text);
    background: #10151b;
  }

  .cell.rowhead {
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    color: var(--muted);
    background: #0c1015;
  }

  .terminal {
    background: #050505;
    border: 1px solid #1e293b;
    border-radius: 8px;
    overflow: hidden;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.5em;
    color: #d4d4d8;
  }

  .terminal-bar {
    height: 24px;
    background: #111827;
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 0 10px;
  }

  .dot { width: 7px; height: 7px; border-radius: 50%; background: #64748b; }
  .dot.red { background: var(--red); }
  .dot.yellow { background: var(--yellow); }
  .dot.green { background: var(--green); }
  .terminal-body { padding: 12px 14px; line-height: 1.55; }
  .prompt { color: var(--green); }
  .cmd { color: #e5e7eb; }
  .dim { color: #64748b; }

  .split {
    display: grid;
    grid-template-columns: 1.05fr 0.95fr;
    gap: 22px;
    align-items: center;
    margin-top: 18px;
  }

  .lane {
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--panel);
    padding: 10px;
    margin-bottom: 8px;
  }

  .lane-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .lane-name {
    font-family: 'Outfit', sans-serif;
    font-size: 0.62em;
    font-weight: 700;
  }

  .mini-rail {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 4px;
  }

  .mini-step {
    height: 12px;
    border-radius: 3px;
    background: #1e293b;
  }

  .mini-step.done { background: var(--cyan); }
  .merge-gate {
    border: 1px solid #f5a62344;
    background: #f5a62312;
    border-radius: 8px;
    padding: 20px;
    text-align: center;
  }

  .large-icon {
    width: 44px;
    height: 44px;
    margin-bottom: 8px;
  }

footer: ''
---

<!-- _class: lead -->
<!-- _paginate: false -->

![bg brightness:0.18](https://images.unsplash.com/photo-1515879218367-8466d910aaa4?w=1600)

<div class="kicker">agent-runner</div>

# Runner Stack

<div class="subtitle">Prompt-runner, methodology-runner, and backlog-runner</div>

<div class="chips">
  <span class="chip">Prompt modules</span>
  <span class="chip">Methodology phases</span>
  <span class="chip">Parallel backlog delivery</span>
</div>

---

### Mental Model

# Three Layers, Three Jobs

<h2>Each runner owns a different unit of work. The stack is useful because those ownership boundaries stay clean.</h2>

<div class="stack">
  <div class="stack-layer">
    <div>
      <div class="tag orange">lowest layer</div>
      <div class="layer-name" style="color: var(--orange);">prompt-runner</div>
    </div>
    <div class="card-body">Executes a markdown prompt workflow as generator, deterministic validation, judge, and revision loops.</div>
    <div class="layer-question">Can this prompt module produce a passing artifact chain?</div>
  </div>
  <div class="stack-layer">
    <div>
      <div class="tag cyan">single change</div>
      <div class="layer-name" style="color: var(--cyan);">methodology-runner</div>
    </div>
    <div class="card-body">Sequences the checked-in methodology phase prompt modules over one application worktree.</div>
    <div class="layer-question">Can one request become a verified integrated change?</div>
  </div>
  <div class="stack-layer">
    <div>
      <div class="tag green">queue layer</div>
      <div class="layer-name" style="color: var(--green);">backlog-runner</div>
    </div>
    <div class="card-body">Scans backlog folders, claims items, launches isolated methodology workers, and serializes final merges.</div>
    <div class="layer-question">Can many items move safely through the pipeline?</div>
  </div>
</div>

---

### Prompt-Runner

# The Smallest Execution Unit

<h2>Prompt-runner is content-agnostic. It cares about markdown structure, files, backend calls, verdicts, and durable traces.</h2>

<div class="flow">
  <div class="flow-box">
    <div class="name">Prompt file</div>
    <div class="note">Ordered prompt pairs plus optional metadata, variants, and placeholders</div>
  </div>
  <div class="arrow"></div>
  <div class="flow-box">
    <div class="name">Generator</div>
    <div class="note">Writes or revises files inside the run worktree</div>
  </div>
  <div class="arrow"></div>
  <div class="flow-box">
    <div class="name">Deterministic validation</div>
    <div class="note">Optional Python check before the judge call</div>
  </div>
  <div class="arrow"></div>
  <div class="flow-box">
    <div class="name">Judge</div>
    <div class="note">Returns pass, revise, or escalation outcome</div>
  </div>
</div>

<div class="grid-3" style="margin-top: 22px;">
  <div class="card">
    <div class="label">Worktree</div>
    <div class="card-body">Project files live at their real project-relative paths inside the run directory.</div>
  </div>
  <div class="card cyan">
    <div class="label">Forensics</div>
    <div class="card-body">Rendered generator prompts, judge prompts, outputs, manifests, and summaries live under .run-files.</div>
  </div>
  <div class="card green">
    <div class="label">Recovery</div>
    <div class="card-body">Resume skips completed prompts; judge-only reruns a saved judge against existing artifacts.</div>
  </div>
</div>

---

### Prompt Module Anatomy

# The Markdown Contract

<h2>A prompt module is a reusable workflow file. Prompt-runner supplies runtime paths, state, and revision mechanics.</h2>

<div class="grid-2">
  <div class="card">
    <div class="card-title">Before the generator</div>
    <div class="card-body">Required Files halt early when missing. Include Files inject context. Checks Files record optional file presence. Deterministic Validation runs a Python command after generation.</div>
  </div>
  <div class="card cyan">
    <div class="card-title">Generator and judge pair</div>
    <div class="card-body">Generation Prompt does the work. Validation Prompt decides whether the result passes. Retry Prompt customizes revision instructions when the judge asks for changes.</div>
  </div>
  <div class="card green">
    <div class="card-title">Variant fork points</div>
    <div class="card-body">A prompt can fork into named variants. The selector path chooses a passing branch, and variant-sequential can trade speed for lower simultaneous quota use.</div>
  </div>
  <div class="card yellow">
    <div class="card-title">Optimization mode</div>
    <div class="card-body">Optimize runs a baseline, compares candidate model or effort settings, requires a passing winner, and emits an optimized prompt file.</div>
  </div>
</div>

<div class="tiny" style="margin-top: 18px;">The important boundary: prompt-runner executes prompt-defined control flow, but it does not know the methodology domain.</div>

---

### Methodology-Runner

# One Request, Eight Phases

<h2>Methodology-runner owns the end-to-end control flow for one change. Each phase points to a checked-in prompt module.</h2>

<div class="phase-grid">
  <div class="phase">
    <div class="phase-id">PH-000</div>
    <div class="phase-name">Requirements Inventory</div>
    <div class="phase-note">Extract traced RI items from the raw request.</div>
  </div>
  <div class="phase">
    <div class="phase-id">PH-001</div>
    <div class="phase-name">Feature Specification</div>
    <div class="phase-note">Turn requirements into features and acceptance criteria.</div>
  </div>
  <div class="phase">
    <div class="phase-id">PH-002</div>
    <div class="phase-name">Architecture</div>
    <div class="phase-note">Define components, technology choices, and integration points.</div>
  </div>
  <div class="phase">
    <div class="phase-id">PH-003</div>
    <div class="phase-name">Solution Design</div>
    <div class="phase-note">Map features to concrete files, components, and interactions.</div>
  </div>
  <div class="phase">
    <div class="phase-id">PH-004</div>
    <div class="phase-name">Interface Contracts</div>
    <div class="phase-note">Specify operations, data shapes, and behavior boundaries.</div>
  </div>
  <div class="phase">
    <div class="phase-id">PH-005</div>
    <div class="phase-name">Intelligent Simulations</div>
    <div class="phase-note">Plan simulation artifacts when the architecture needs them.</div>
  </div>
  <div class="phase">
    <div class="phase-id">PH-006</div>
    <div class="phase-name">Incremental Implementation</div>
    <div class="phase-note">Build the change with tests and implementation evidence.</div>
  </div>
  <div class="phase">
    <div class="phase-id">PH-007</div>
    <div class="phase-name">Verification Sweep</div>
    <div class="phase-note">Verify finished behavior against requirements and features.</div>
  </div>
</div>

---

### Methodology Orchestration

# What It Adds Above Prompt-Runner

<h2>Prompt-runner executes one prompt module. Methodology-runner decides which phase runs, what it may read, what it must produce, and when the change can advance.</h2>

<div class="split">
  <div>
    <div class="flow" style="margin-top: 0;">
      <div class="flow-box">
        <div class="name">Request file</div>
        <div class="note">Copied into the application worktree as raw requirements</div>
      </div>
      <div class="arrow"></div>
      <div class="flow-box">
        <div class="name">Phase registry</div>
        <div class="note">Predecessors, inputs, output paths, prompt modules</div>
      </div>
      <div class="arrow"></div>
      <div class="flow-box">
        <div class="name">Prompt-runner call</div>
        <div class="note">In-process library execution using the same worktree</div>
      </div>
    </div>
    <div class="flow" style="margin-top: 14px;">
      <div class="flow-box">
        <div class="name">Cross-reference</div>
        <div class="note">Reject contradictions, fabricated evidence, and unsupported omissions</div>
      </div>
      <div class="arrow"></div>
      <div class="flow-box">
        <div class="name">Phase commit</div>
        <div class="note">One checkpoint per successful phase</div>
      </div>
      <div class="arrow"></div>
      <div class="flow-box">
        <div class="name">Lifecycle</div>
        <div class="note">Preserve change record, clean temporary artifacts, integrate branch</div>
      </div>
    </div>
  </div>
  <div class="card cyan">
    <div class="label">Durable state</div>
    <div class="card-body">.methodology-runner/state.json stores phase and lifecycle status for run, resume, status, and reset.</div>
    <div class="label" style="margin-top: 16px;">Visible progress</div>
    <div class="card-body">.run-files/methodology-runner/summary.txt is rewritten after phases so long runs have a compact status surface.</div>
    <div class="label" style="margin-top: 16px;">Change record</div>
    <div class="card-body">docs/changes/change-id preserves request, analysis, execution, verification, and merge handoff evidence.</div>
  </div>
</div>

---

### Backlog-Runner

# Queue Throughput Without Duplicating Methodology Logic

<h2>Backlog-runner supervises many methodology-runner executions. It does not write phase artifacts or call prompt-runner directly.</h2>

<div class="flow">
  <div class="flow-box">
    <div class="name">Active backlog folders</div>
    <div class="note">feature, defect, analysis, and investigation markdown items</div>
  </div>
  <div class="arrow"></div>
  <div class="flow-box">
    <div class="name">Atomic claim</div>
    <div class="note">One claim record prevents duplicate workers</div>
  </div>
  <div class="arrow"></div>
  <div class="flow-box">
    <div class="name">Worker launch</div>
    <div class="note">methodology-runner runs in an isolated feature worktree</div>
  </div>
  <div class="arrow"></div>
  <div class="flow-box">
    <div class="name">Merge gate</div>
    <div class="note">One target branch update at a time</div>
  </div>
  <div class="arrow"></div>
  <div class="flow-box">
    <div class="name">Archive</div>
    <div class="note">Completed only after merge, failed otherwise</div>
  </div>
</div>

<div class="card yellow" style="margin-top: 18px; padding: 12px 16px;">
  <div class="card-body">
    <span class="tag orange">one supervisor lock</span>
    <span class="tag cyan" style="margin-left: 8px;">bounded workers</span>
    <span class="tag green" style="margin-left: 8px;">no hidden success</span>
    <span style="margin-left: 12px;">Queue state is explicit: claimed, running, target_merge_pending, completed, failed, blocked, or abandoned.</span>
  </div>
</div>

---

### Parallel Safety

# Parallel Work, Serialized Delivery

<h2>The split is deliberate: feature-branch work can run in parallel, but the target branch is a shared resource.</h2>

<div class="split">
  <div>
    <div class="lane">
      <div class="lane-top">
        <div class="lane-name">feature worktree A</div>
        <span class="tag cyan">methodology worker</span>
      </div>
      <div class="mini-rail">
        <div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div>
      </div>
    </div>
    <div class="lane">
      <div class="lane-top">
        <div class="lane-name">feature worktree B</div>
        <span class="tag cyan">methodology worker</span>
      </div>
      <div class="mini-rail">
        <div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step"></div><div class="mini-step"></div><div class="mini-step"></div>
      </div>
    </div>
    <div class="lane">
      <div class="lane-top">
        <div class="lane-name">feature worktree C</div>
        <span class="tag cyan">methodology worker</span>
      </div>
      <div class="mini-rail">
        <div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step done"></div><div class="mini-step"></div><div class="mini-step"></div><div class="mini-step"></div><div class="mini-step"></div>
      </div>
    </div>
  </div>
  <div>
    <div class="merge-gate">
      <svg width="54" height="54" viewBox="0 0 24 24" fill="none" stroke="var(--yellow)" stroke-width="1.5" style="margin-bottom: 10px;">
        <rect x="3" y="11" width="18" height="10" rx="2"></rect>
        <path d="M7 11V8a5 5 0 0 1 10 0v3"></path>
      </svg>
      <div class="card-title">Final merge gate</div>
      <div class="card-body">Workers call methodology-runner with --skip-target-merge. A successful worker writes target-merge-handoff.json and stops at target_merge_pending.</div>
      <div class="card-body" style="margin-top: 12px;">Backlog-runner then validates the handoff and merges one finalized source commit into the target branch at a time.</div>
    </div>
  </div>
</div>

---

### Ownership Boundaries

# What Each Runner Owns

<div class="table">
  <div class="cell header"></div>
  <div class="cell header">prompt-runner</div>
  <div class="cell header">methodology-runner</div>
  <div class="cell header">backlog-runner</div>

  <div class="cell rowhead">Unit</div>
  <div class="cell">One prompt module or selected prompt pair.</div>
  <div class="cell">One change request in one application worktree.</div>
  <div class="cell">Many backlog items across a BacklogRoot.</div>

  <div class="cell rowhead">Input</div>
  <div class="cell">Markdown prompt file plus runtime placeholders.</div>
  <div class="cell">Requirements markdown plus phase registry.</div>
  <div class="cell">Typed backlog folders and application repo.</div>

  <div class="cell rowhead">Quality Gate</div>
  <div class="cell">Judge verdict and deterministic validation.</div>
  <div class="cell">Phase validators plus cross-reference checks.</div>
  <div class="cell">Worker result, merge handoff, and merge result.</div>

  <div class="cell rowhead">State</div>
  <div class="cell">Run directory and .run-files traces.</div>
  <div class="cell">.methodology-runner state and phase summaries.</div>
  <div class="cell">.backlog-runner claims, logs, state, and results.</div>

  <div class="cell rowhead">Terminal Truth</div>
  <div class="cell">Prompt pipeline passed, halted, or escalated.</div>
  <div class="cell">Feature branch finalized or merged for one change.</div>
  <div class="cell">Backlog item archived only after terminal outcome.</div>
</div>

---

### Normal Commands

# How People Touch The Stack

<div class="grid-3" style="margin-top: 10px;">
  <div class="card">
    <div class="card-title">Validate or run a prompt module</div>
    <div class="terminal">
      <div class="terminal-bar"><span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span></div>
      <div class="terminal-body">
        <span class="prompt">$</span> <span class="cmd">prompt-runner parse tools/methodology-runner/docs/prompts/PR-025-ph000-requirements-inventory.md</span><br>
        <span class="prompt">$</span> <span class="cmd">prompt-runner run prompt.md --backend codex --run-dir work/prompt-test</span>
      </div>
    </div>
  </div>
  <div class="card cyan">
    <div class="card-title">Run one methodology change</div>
    <div class="terminal">
      <div class="terminal-bar"><span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span></div>
      <div class="terminal-body">
        <span class="prompt">$</span> <span class="cmd">methodology-runner run request.md --workspace work/change --backend codex</span><br>
        <span class="prompt">$</span> <span class="cmd">methodology-runner status work/change</span>
      </div>
    </div>
  </div>
  <div class="card green">
    <div class="card-title">Run backlog items</div>
    <div class="terminal">
      <div class="terminal-bar"><span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span></div>
      <div class="terminal-body">
        <span class="prompt">$</span> <span class="cmd">backlog-runner once --application-repo . --backend codex --max-workers 2</span><br>
        <span class="prompt">$</span> <span class="cmd">backlog-runner status --backlog-root .</span>
      </div>
    </div>
  </div>
</div>

<div class="tiny" style="margin-top: 18px;">Use parse for prompt authoring, run or resume for a single change, and once or run for queue supervision.</div>

---

### Observability And Recovery

# Long Runs Need Evidence

<h2>The stack is designed so a stalled or failed run can be inspected without guessing from chat history.</h2>

<div class="grid-3">
  <div class="card">
    <svg class="large-icon" viewBox="0 0 24 24" fill="none" stroke="var(--orange)" stroke-width="1.5">
      <path d="M4 4h16v16H4z"></path><path d="M8 8h8"></path><path d="M8 12h8"></path><path d="M8 16h5"></path>
    </svg>
    <div class="card-title">Prompt traces</div>
    <div class="card-body">Every iteration can preserve rendered generator prompts, judge prompts, backend outputs, validation logs, and module summaries.</div>
  </div>
  <div class="card cyan">
    <svg class="large-icon" viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" stroke-width="1.5">
      <circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>
    </svg>
    <div class="card-title">Methodology state</div>
    <div class="card-body">Status, resume, and reset operate from persisted phase and lifecycle state, not from memory of what happened earlier.</div>
  </div>
  <div class="card green">
    <svg class="large-icon" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="1.5">
      <path d="M3 7h18"></path><path d="M6 7v12h12V7"></path><path d="M9 11h6"></path><path d="M9 15h6"></path>
    </svg>
    <div class="card-title">Queue truth</div>
    <div class="card-body">Claims, worker results, merge results, logs, and archive folders separate active, blocked, failed, merge-ready, and completed work.</div>
  </div>
</div>

<div class="row-flex" style="margin-top: 20px;">
  <div class="card yellow" style="flex: 1;">
    <div class="label">Safe recovery pattern</div>
    <div class="card-body">Inspect status first, resume from saved state when possible, reset only the narrow phase or item boundary that actually failed.</div>
  </div>
  <div class="card" style="flex: 1;">
    <div class="label">Archive meaning</div>
    <div class="card-body">Completed backlog is delivery evidence. Failed backlog is repair evidence. Active backlog stays dispatchable or blocked.</div>
  </div>
</div>

---

<!-- _class: lead -->
<!-- _paginate: false -->

![bg brightness:0.16](https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=1600)

<div class="kicker">Which runner should I reach for?</div>

# Choose By Unit Of Work

<div class="grid-3" style="width: 100%; margin-top: 28px;">
  <div class="card">
    <div class="tag orange">prompt-runner</div>
    <div class="card-body" style="margin-top: 12px;">Use it when the problem is prompt authoring, prompt validation, model choice, or one reusable prompt workflow.</div>
  </div>
  <div class="card cyan">
    <div class="tag cyan">methodology-runner</div>
    <div class="card-body" style="margin-top: 12px;">Use it when one request needs the full requirements, design, implementation, and verification discipline.</div>
  </div>
  <div class="card green">
    <div class="tag green">backlog-runner</div>
    <div class="card-body" style="margin-top: 12px;">Use it when many backlog items need queue supervision, worker isolation, and serialized target-branch delivery.</div>
  </div>
</div>
