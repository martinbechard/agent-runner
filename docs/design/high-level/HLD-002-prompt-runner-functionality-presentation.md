---
marp: true
theme: default
paginate: true
title: Building a Disciplined Agent Execution Layer
description: LinkedIn document carousel explaining prompt-runner as the low-level markdown-driven execution layer for predictable AI engineering workflows.
style: |
  :root {
    --bg: #050607;
    --surface: #0c1016;
    --panel: #111827;
    --panel2: #101522;
    --border: #202938;
    --soft-border: #151b27;
    --text: #f8fafc;
    --body: #a4adba;
    --muted: #687385;
    --label: #7a8595;
    --orange: #ff7a1a;
    --blue: #38bdf8;
    --green: #22c55e;
    --yellow: #f5b84b;
    --red: #ef4444;
    --purple: #a78bfa;
  }

  section {
    background: var(--bg);
    color: var(--text);
    font-family: Avenir Next, Inter, Segoe UI, Helvetica, Arial, sans-serif;
    font-weight: 400;
    padding: 50px 64px;
    line-height: 1.28;
  }

  section::after {
    font-size: 0.56em;
    color: #2b3648;
    font-weight: 700;
  }

  h1, h2, h3, h4, p {
    margin: 0;
  }

  h1 {
    font-size: 2.44em;
    line-height: 1.02;
    font-weight: 800;
    color: var(--text);
    max-width: 1000px;
  }

  h2 {
    margin-top: 10px;
    margin-bottom: 20px;
    font-size: 1.04em;
    font-weight: 400;
    color: var(--body);
    max-width: 900px;
  }

  h3 {
    font-size: 0.6em;
    line-height: 1.1;
    text-transform: uppercase;
    color: var(--label);
    margin-bottom: 10px;
    font-weight: 800;
  }

  h4 {
    font-size: 0.78em;
    color: var(--text);
    margin-bottom: 7px;
    font-weight: 800;
  }

  p, li {
    color: var(--body);
    font-size: 0.72em;
  }

  strong {
    color: var(--orange);
    font-weight: 800;
  }

  table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0 8px;
    font-size: 0.58em;
  }

  th {
    color: var(--label);
    text-align: left;
    text-transform: uppercase;
    font-weight: 800;
    padding: 4px 10px;
  }

  td {
    background: var(--surface);
    color: var(--body);
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    padding: 9px 11px;
    vertical-align: top;
  }

  td:first-child {
    border-left: 1px solid var(--border);
    border-radius: 7px 0 0 7px;
    color: var(--text);
    font-weight: 800;
  }

  td:last-child {
    border-right: 1px solid var(--border);
    border-radius: 0 7px 7px 0;
  }

  section.lead {
    display: flex;
    flex-direction: column;
    justify-content: center;
    text-align: center;
    align-items: center;
  }

  section.lead h1 {
    font-size: 3.28em;
    max-width: 930px;
  }

  .kicker {
    color: var(--blue);
    font-weight: 800;
    font-size: 0.58em;
    text-transform: uppercase;
    margin-bottom: 12px;
  }

  .subtitle {
    color: var(--body);
    font-size: 0.88em;
    max-width: 780px;
  }

  .grid2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .grid3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
  }

  .grid4 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }

  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 17px;
    position: relative;
    overflow: hidden;
  }

  .panel::before {
    content: '';
    position: absolute;
    inset: 0 0 auto;
    height: 2px;
    background: linear-gradient(90deg, var(--orange), transparent);
  }

  .blue-line::before { background: linear-gradient(90deg, var(--blue), transparent); }
  .green-line::before { background: linear-gradient(90deg, var(--green), transparent); }
  .yellow-line::before { background: linear-gradient(90deg, var(--yellow), transparent); }
  .purple-line::before { background: linear-gradient(90deg, var(--purple), transparent); }
  .red-line::before { background: linear-gradient(90deg, var(--red), transparent); }

  .panel p {
    font-size: 0.63em;
  }

  .small {
    font-size: 0.62em;
  }

  .tiny {
    font-size: 0.52em;
    color: var(--muted);
  }

  .muted { color: var(--muted); }
  .blue { color: var(--blue); }
  .orange { color: var(--orange); }
  .green { color: var(--green); }
  .yellow { color: var(--yellow); }
  .red { color: var(--red); }
  .purple { color: var(--purple); }

  .pill {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--panel2);
    color: var(--body);
    font-size: 0.5em;
    font-weight: 800;
    padding: 5px 10px;
    margin: 3px 5px 3px 0;
    text-transform: uppercase;
  }

  .tag {
    display: inline-flex;
    align-items: center;
    border-radius: 5px;
    font-size: 0.5em;
    font-weight: 800;
    padding: 4px 8px;
    text-transform: uppercase;
  }

  .tag.blue { background: #38bdf812; border: 1px solid #38bdf833; color: var(--blue); }
  .tag.green { background: #22c55e12; border: 1px solid #22c55e33; color: var(--green); }
  .tag.yellow { background: #f5b84b12; border: 1px solid #f5b84b33; color: var(--yellow); }
  .tag.red { background: #ef444412; border: 1px solid #ef444433; color: var(--red); }
  .tag.purple { background: #a78bfa12; border: 1px solid #a78bfa33; color: var(--purple); }

  .callout {
    background: #ff7a1a10;
    border-left: 3px solid var(--orange);
    border-radius: 0 8px 8px 0;
    padding: 13px 15px;
    color: var(--body);
    font-size: 0.66em;
  }

  .codebox {
    background: #07090d;
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 15px 17px;
    color: #d8dee9;
    font-family: Menlo, Consolas, monospace;
    font-size: 0.57em;
    line-height: 1.52;
  }

  .stack {
    display: grid;
    grid-template-rows: repeat(3, 1fr);
    gap: 12px;
    margin-top: 18px;
  }

  .stack-row {
    display: grid;
    grid-template-columns: 190px 1fr;
    gap: 14px;
    align-items: center;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 9px;
    padding: 16px 18px;
  }

  .stack-num {
    color: var(--blue);
    font-weight: 800;
    font-size: 0.66em;
    text-transform: uppercase;
  }

  .stack-title {
    color: var(--text);
    font-weight: 800;
    font-size: 0.9em;
  }

  .chevrons {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 9px;
    margin-top: 22px;
  }

  .chevron {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    min-height: 132px;
    padding: 14px 13px;
  }

  .chevron .num {
    color: var(--orange);
    font-weight: 800;
    font-size: 0.56em;
    text-transform: uppercase;
    margin-bottom: 7px;
  }

  .chevron p {
    font-size: 0.55em;
  }

  .score-rule {
    display: grid;
    grid-template-columns: 74px 1fr;
    gap: 12px;
    align-items: center;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 10px;
  }

  .score-rule .rank {
    color: var(--orange);
    font-size: 1.2em;
    font-weight: 800;
  }

  .score-rule p {
    font-size: 0.63em;
  }
---

<!-- _class: lead -->

<div class="kicker">Open Source Engine Blueprint</div>

# Building a Disciplined Agent Execution Layer

<p class="subtitle">Beyond vibe coding: using markdown-driven contracts to run predictable, self-correcting AI engineering workflows.</p>

<div style="margin-top: 28px;">
  <span class="pill">Prompt-Driven Development</span>
  <span class="pill">Executable Specifications</span>
  <span class="pill">Auditable Runs</span>
</div>

---

### Automation Stack Context

# Where Does This Fit in an Agent Factory?

<h2>To systematically clear a software backlog with AI, you need a decoupled architecture.</h2>

<div class="stack">
  <div class="stack-row">
    <div>
      <div class="stack-num">Layer 1</div>
      <div class="stack-title">Backlog Runner</div>
    </div>
    <p>Breaks functional product features into discrete, claimable work items for autonomous execution.</p>
  </div>
  <div class="stack-row">
    <div>
      <div class="stack-num">Layer 2</div>
      <div class="stack-title">Methodology Runner</div>
    </div>
    <p>Orchestrates multi-phase engineering methods: requirements, architecture, design, implementation, validation.</p>
  </div>
  <div class="stack-row" style="border-color:#38bdf866; box-shadow:0 0 0 1px #38bdf822 inset;">
    <div>
      <div class="stack-num">Layer 3</div>
      <div class="stack-title">Prompt-Runner</div>
    </div>
    <p>The low-level execution engine. It processes prompt pairs, manages agent sessions, runs validators, and logs immutable evidence.</p>
  </div>
</div>

---

### Operating Model

# Parallel Agents Require Isolated Workspaces

<div class="grid2">
  <div class="panel green-line">
    <h4>Production code paths</h4>
    <p>Completed deliverables land in real project-visible paths such as src/module.py, tests/test_module.py, or docs/design.yaml.</p>
    <div style="margin-top:18px;">
      <span class="tag green">clean diff</span>
      <span class="tag blue">reviewable files</span>
    </div>
  </div>
  <div class="panel purple-line">
    <h4>Scratchpad evidence paths</h4>
    <p>Temporary files, rendered prompt inputs, LLM outputs, raw logs, metrics, and summaries stay isolated inside .run-files.</p>
    <div style="margin-top:18px;">
      <span class="tag purple">audit trail</span>
      <span class="tag yellow">debug context</span>
    </div>
  </div>
</div>

<div class="callout" style="margin-top:24px;">
The run directory is an isolated worktree. Agents can operate without corrupting active project state or polluting version control with execution debris.
</div>

---

### Markdown Contract

# Specs as Code: The Markdown Contract

<div class="grid2">
  <div class="codebox">
    ## Prompt: Implement parser<br/>
    <br/>
    ### Required Files<br/>
    docs/request.md<br/>
    <br/>
    ### Generation Prompt<br/>
    Build the behavior.<br/>
    <br/>
    ### Validation Prompt<br/>
    Audit the result and emit a verdict.
  </div>
  <div>
    <div class="panel blue-line">
      <h4>Document structure is execution logic</h4>
      <p>Instead of ad-hoc chat sessions, workflows are declared as structured markdown contracts.</p>
    </div>
    <div class="panel green-line" style="margin-top:12px;">
      <h4>Hard boundaries</h4>
      <p>Prompt headings define sequence. Required files are checked before network calls. Generation and validation roles are explicitly separated.</p>
    </div>
  </div>
</div>

---

### Execution Loop

# The Generate, Audit, and Commit Cycle

<div class="chevrons">
  <div class="chevron">
    <div class="num">Step 1</div>
    <h4>Render</h4>
    <p>Combines placeholders, file includes, and system preludes into exact backend inputs.</p>
  </div>
  <div class="chevron">
    <div class="num">Step 2</div>
    <h4>Generate</h4>
    <p>Calls the code generator session and modifies the isolated workspace.</p>
  </div>
  <div class="chevron">
    <div class="num">Step 3</div>
    <h4>Validate</h4>
    <p>Runs local checks such as tests, linters, type checks, or schema validators.</p>
  </div>
  <div class="chevron">
    <div class="num">Step 4</div>
    <h4>Judge</h4>
    <p>A separate AI validation agent audits the artifact and issues a formal verdict.</p>
  </div>
  <div class="chevron">
    <div class="num">Step 5</div>
    <h4>Commit evidence</h4>
    <p>Persists metrics, logs, summaries, prompt inputs, and outputs to the audit trail.</p>
  </div>
</div>

<div class="callout" style="margin-top:24px;">
This loop is the antidote to vibe coding: every generated artifact is tied back to an executable specification and a validation record.
</div>

---

### Resilience And Token Conservation

# Managing State to Prevent Token Waste

<div class="grid2">
  <div class="panel red-line">
    <h4>The failure mode</h4>
    <p>Long-running agent pipelines hit network drops, rate limits, validation halts, or local test failures. Restarting from scratch burns time and API budget.</p>
  </div>
  <div class="panel green-line">
    <h4>The recovery model</h4>
    <p>Prompt-runner caches execution state and generated outputs to disk. Resume can pick up at the interrupted point without replaying completed LLM calls.</p>
  </div>
</div>

<table style="margin-top:24px;">
  <thead>
    <tr><th>Persisted state</th><th>Why it matters</th></tr>
  </thead>
  <tbody>
    <tr><td>Rendered prompt inputs</td><td>Exact instructions are reproducible after the run</td></tr>
    <tr><td>Generated artifacts</td><td>Completed steps are reused instead of regenerated</td></tr>
    <tr><td>Verdicts and summaries</td><td>Later steps know which work is already approved</td></tr>
  </tbody>
</table>

---

### Hard Rules Vs. Soft Logic

# Anchoring AI Behavior with Deterministic Checks

<div class="grid3">
  <div class="panel blue-line">
    <h4>Generate code</h4>
    <p>The agent writes or updates files inside the run worktree.</p>
  </div>
  <div class="panel yellow-line">
    <h4>Run local validator</h4>
    <p>Tests, type checks, schema linters, or custom scripts run before the LLM judge call.</p>
  </div>
  <div class="panel purple-line">
    <h4>Feed objective evidence</h4>
    <p>The judge receives concrete validation logs alongside the generated artifact.</p>
  </div>
</div>

<table style="margin-top:24px;">
  <tbody>
    <tr><td>Exit code 0</td><td>Tests pass. Success logs are fed to the AI judge to verify functional intent.</td></tr>
    <tr><td>Exit code 1</td><td>Tests fail. Failure logs drive automated revision instead of a loose review.</td></tr>
    <tr><td>Exit code above 1</td><td>The validator itself failed. The run halts so tooling can be fixed.</td></tr>
  </tbody>
</table>

---

### Decoupled Agent Economics

# Decoupling Roles to Optimize Unit Economics

<h2>One premium model for every task is an expensive default. The engine lets the builder and auditor take different routes.</h2>

<div class="grid2">
  <div class="panel blue-line">
    <h4>The Builder</h4>
    <p>Bulk code generation can use faster, high-throughput, or specialized coding models where the task is mostly implementation work.</p>
    <div style="margin-top:18px;"><span class="tag blue">generation</span></div>
  </div>
  <div class="panel purple-line">
    <h4>The Auditor</h4>
    <p>Validation prompts and selector choices can use premium reasoning models where correctness and judgment matter most.</p>
    <div style="margin-top:18px;"><span class="tag purple">judging</span> <span class="tag green">selection</span></div>
  </div>
</div>

<div class="callout" style="margin-top:24px;">
Role-specific routing improves aggregate cost without collapsing the quality bar for the final decision.
</div>

---

### Variant Forks

# Running Parallel Experiments with Variant Forks

<svg viewBox="0 0 980 320" style="width:100%; height:320px; background:var(--surface); border:1px solid var(--border); border-radius:8px;">
  <rect x="60" y="122" width="170" height="76" rx="10" fill="#101522" stroke="#202938"/>
  <text x="92" y="155" fill="#f8fafc" font-size="19" font-weight="800">One spec</text>
  <text x="92" y="181" fill="#a4adba" font-size="14">same contract</text>
  <path d="M248 160 C334 82, 400 70, 486 92" fill="none" stroke="#687385" stroke-width="2"/>
  <path d="M248 160 C334 238, 400 250, 486 228" fill="none" stroke="#687385" stroke-width="2"/>
  <rect x="508" y="52" width="190" height="86" rx="10" fill="#111827" stroke="#38bdf866"/>
  <text x="545" y="89" fill="#38bdf8" font-size="19" font-weight="800">Variant A</text>
  <text x="545" y="116" fill="#a4adba" font-size="14">isolated run dir</text>
  <rect x="508" y="184" width="190" height="86" rx="10" fill="#111827" stroke="#a78bfa66"/>
  <text x="545" y="221" fill="#a78bfa" font-size="19" font-weight="800">Variant B</text>
  <text x="545" y="248" fill="#a4adba" font-size="14">isolated run dir</text>
  <path d="M716 95 C784 106, 820 126, 866 154" fill="none" stroke="#687385" stroke-width="2"/>
  <path d="M716 227 C784 216, 820 194, 866 166" fill="none" stroke="#687385" stroke-width="2"/>
  <rect x="842" y="122" width="98" height="76" rx="10" fill="#22c55e12" stroke="#22c55e66"/>
  <text x="858" y="155" fill="#22c55e" font-size="18" font-weight="800">Selector</text>
  <text x="866" y="181" fill="#a4adba" font-size="14">winner</text>
</svg>

<div class="callout" style="margin-top:16px;">
When a complex task has multiple valid approaches, the specification can fork the environment, validate both paths, and converge through a selector.
</div>

---

### Selection Mechanics

# How the Engine Selects the Winning Code Path

<div class="grid2">
  <div>
    <div class="score-rule">
      <div class="rank">01</div>
      <p>A passing validation verdict always beats a non-passing candidate.</p>
    </div>
    <div class="score-rule">
      <div class="rank">02</div>
      <p>Fewer revision iterations win because first-pass correctness matters.</p>
    </div>
    <div class="score-rule">
      <div class="rank">03</div>
      <p>Lowest wall-clock execution time wins when quality ties.</p>
    </div>
    <div class="score-rule">
      <div class="rank">04</div>
      <p>Total token consumption acts as the final tie-breaker.</p>
    </div>
  </div>
  <div class="panel green-line">
    <h4>Selector Judge</h4>
    <p>After candidates run, a dedicated selector evaluates scorecards and outcomes. This keeps selection disciplined instead of relying on a loose preference call.</p>
    <table style="margin-top:20px;">
      <tbody>
        <tr><td>Variant A</td><td>Pass, 2 revisions, 41k tokens</td></tr>
        <tr><td>Variant B</td><td>Pass, 1 revision, 37k tokens</td></tr>
        <tr><td>Winner</td><td>Variant B</td></tr>
      </tbody>
    </table>
  </div>
</div>

---

### Production-Grade Robustness

# Built for Stability, Not Demos

<h2>Higher-level backlog orchestrators only work if the execution layer is boring, strict, and repairable.</h2>

<div class="grid4">
  <div class="panel green-line">
    <h4>255+ tests</h4>
    <p>Regression coverage for parser behavior, iteration loops, variant forks, and CLI config discovery.</p>
  </div>
  <div class="panel blue-line">
    <h4>Typed errors</h4>
    <p>Parser failures use explicit error IDs and line references so malformed specs are repairable.</p>
  </div>
  <div class="panel purple-line">
    <h4>Role isolation</h4>
    <p>Generation, validation, selection, and local validators each have a clear place in the lifecycle.</p>
  </div>
  <div class="panel yellow-line">
    <h4>Evidence first</h4>
    <p>Every meaningful call leaves logs, metrics, outputs, and summaries for later inspection.</p>
  </div>
</div>

<div style="margin-top:24px;">
  <span class="tag red">E-NO-GENERATION</span>
  <span class="tag red">E-BAD-SECTION-ORDER</span>
  <span class="tag red">E-DUPLICATE-SECTION</span>
  <span class="tag yellow">E-BAD-PATH-ENTRY</span>
  <span class="tag yellow">E-UNKNOWN-SUBSECTION</span>
  <span class="tag yellow">E-NO-VARIANTS</span>
</div>

---

### Summary And Next

# Summary: Markdown In. Auditable Code Out.

<div class="grid3" style="margin-top:22px;">
  <div class="panel green-line">
    <h4>Core takeaway</h4>
    <p>Prompt-runner transforms fragile prompt strings into a version-controlled, self-correcting execution layer.</p>
  </div>
  <div class="panel blue-line">
    <h4>Open source posture</h4>
    <p>The tool is transparent, reproducible, and designed for professional engineering pipelines.</p>
  </div>
  <div class="panel purple-line">
    <h4>Coming next</h4>
    <p>At scale, automated agent work needs cost governance and behavioral insight across active runs.</p>
  </div>
</div>

<div class="callout" style="margin-top:28px;">
Next topic: the companion reporting and observability tool for real-time token tracking and tool-call auditing.
</div>
