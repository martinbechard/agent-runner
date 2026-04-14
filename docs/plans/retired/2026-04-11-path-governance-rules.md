# Rules: File Path Governance For Methodology-Runner And Prompt-Runner

## 1. Decision Ownership

- **RULE:** File placement policy MUST be implemented as explicit runtime logic, not as free-form prompt text.
  - **BECAUSE:** Prompt text is advisory, so the model can interpret it inconsistently across runs.
  - **BECAUSE:** A policy that protects repo structure has to be deterministic, or it will fail exactly when the model is underconstrained.

  **REVIEW:** this chain doesn't hold, the fact that prompt text is advisory is NOT because a policy that protects repo structure has to be determininstic, they are both indepdendent reasons for the RULE. The better way to decompose this is:
  - **RULE:** File placement policy MUST be implemented as explicit runtime logic, not as free-form prompt text.
  - **BECAUSE:** Prompt text is advisory, so the model can interpret it inconsistently across runs.
  - **BECAUSE:** A policy that protects repo structure has to be deterministic, or it will fail exactly when the model is underconstrained.
    - **HOWEVER:** Agents need to recognize the need to call runtime code through inference, **AND** the rules to apply depend on a semantic of the file e.g. a typescript file that is part of application versus one that is part of a test would go to different places.
    - **CONCLUSION:** the RULE is not proven because the solution is not fully deterministic; at best we can say, File placement policy OUGHT to be explicit runtime logic ASSUMING a means of systematically invoking it from an LLM can be found AND sufficient and extensible semantics can be implemented in runtime.

    Alternative: use an LLM but highly specialized and isolated, that can potentially use a tool but could evaluate the kind of content in the file and apply various principles about organizing folders in a project, and recording the decision for next time.

  **RESPONSE:** agreed on the bad BECAUSE nesting; fixed above.

  **RESPONSE:** agreed that the stronger claim is not "fully deterministic end-to-end", but "the policy boundary should be explicit even if some classification remains semantic and model-assisted".

  **RESPONSE:** revised interpretation of this rule:
  - the policy itself should be explicit runtime logic
  - the invocation of that policy may still depend on agent inference or a backend adapter
  - the semantic classification needed to choose a path may be implemented either by deterministic rules, by a specialized model, or by a hybrid

  **RESPONSE:** I still prefer keeping the rule as written rather than downgrading it to OUGHT, because the core point is architectural separation: policy should not live only in natural-language prompt text. That remains true even if one implementation of the policy uses an isolated model internally.

**REVIEW:** Agreed, however OUGHT was a way of highlighting that without a conclusive chain of causality, the assertion was gratuitous and reflected an intuition rather than a demonstration. To make it a strong rule, we need a more definitive FACT about how things could be done, otherwise we're just hoping.

Current situation: we have an agent to make a decision that can do everything but might be inconsistent, even though it is supposed to maintain a list of paths and reasonsins to use them.
Desired situation: we want some code capable of doing the same i.e. taking a decision; but non-LLM code needs to be deterministic and a human or an AI has to make up the rules for it.
Plus if new types of content or new file roles come up, needs to adapt.
Therefore I maintaint it's a non-trivial problem to do this with some deterministic code, and even if we did, the integration is via LLM judgement as to categorization and when to call it, what to do for new categories etc. I am not convincend it's possible to build a system of reasonable complexity to handle this better than just an LLM agent. Perhaps it's better to see how we can improve the effectiveness of this agent?

**RESPONSE:** agreed that the current rule, as written, overclaims.

**RESPONSE:** the strongest defensible claim is not:

- runtime logic alone can replace an LLM organiser

**RESPONSE:** the stronger defensible claim is:

- shared path-governance policy MUST have an explicit integration boundary
- that boundary MAY be implemented by deterministic code, by a specialized LLM agent, or by a hybrid
- backend-specific prompt text alone is not a sufficient place to define that boundary
  **REVIEW:** These are all unsubstantiated assertions that take the original rule in a redundant direction.

**RESPONSE:** agreed. These bullets were too abstract to carry the argument.

**RESPONSE:** the key fact supporting the rule is therefore narrower:

- if path policy exists only as prompt text, then it is not inspectable, versionable, or enforceable as a system component
  **REVIEW:** This patently false, prompt text can be reaad even by humans, it can be versioned in source control. It isn't fixed logic like code, but the application of the code isn't enforceable in the context of an LLM so this weakness while true, doesn't make any difference in the context of an agentic system. This is because the LLM that decides they need a new file will invent the name without making a tool call so there's no way to enforce it choosing the right thing. Can you think of one?

- once it is an explicit component boundary, we can still choose an LLM as the decision engine behind it

**RESPONSE:** agreed. "Inspectable" and "versionable" were wrong here; prompt text can obviously be both.

**RESPONSE:** the real distinction is not inspectability. It is interception.

**RESPONSE:** a prompt-only policy cannot force the decision to pass through a single choke point.

**RESPONSE:** one concrete way to enforce that choke point is:

- instrument the write tool or file-creating shell wrapper in the harness
- detect attempted writes to paths not already approved in the current turn or run
- require a path-resolution step before allowing the write to proceed

**RESPONSE:** in other words, enforcement is only realistic if it happens at the tool boundary, not at the reasoning boundary.

**RESPONSE:** this does not solve everything:

- it does not stop the model from thinking of a bad name
- it does stop the model from successfully writing that file without passing through policy

**RESPONSE:** that is the concrete mechanism I should have stated earlier.

**RESPONSE:** so the corrected claim is:

- prompt text alone is insufficient if we want enforceable governance
- enforceability requires interception at the tool or harness level
- the path decision behind that interception may still be delegated to a specialized LLM agent

**RESPONSE:** on your substantive point, I agree there is no proof today that deterministic code will outperform a well-designed specialized agent on path classification.

**RESPONSE:** that changes my preferred formulation of the rule to:

- the policy boundary MUST be explicit
- the decision engine behind that boundary MAY remain agentic

**RESPONSE:** in practical terms, that means the next design step should probably focus less on "replace the organiser with hardcoded rules" and more on:

- making invocation systematic
- making inputs to the organiser explicit
- making outputs structured and logged
- making backend adaptation separate from the path decision itself

**RESPONSE:** I think that addresses your objection more directly: the important architectural move is not determinism for its own sake, but extracting the decision out of ad hoc prompt prose into an explicit callable mechanism.
**REVIEW:** OK but as there are technical issues involved, your intuition about a more reliable architecture may be unrealistic.
I have tried to see how we could meet the refined rule, but I fail to see concretely how we can achieve it. Here is a summary of the three evels:

1. no project organiser: the LLM will use best judgement to put files in the right place; even with coding standards, over time files get misplaced, e.g. we end up with both a "test" and "tests" folder, and a "**TEST**" subfolder within code.
2. we use the project-organiser agent: not production tested yet, but the hope is that it will recognize content of a type it saw before and keep it grouped with similar files; also capable of coming up with organization rules for new types of files
3. instrumented agent to ensure any new files get properly place: this might be doable with hooks or something depending on the agentic harness, and would give perfect fidelity, but I'm not sure it can be done. My understanding is that hooks are also adviserey - they inject commands into the LLMs stream to try to make it do the right thing.

I'm open to suggestions as to how to actually get this done, otherwise we have to come back to 2) just a plan old agent.

**RESPONSE:** this is helpful, and I think it narrows the realistic options a lot.

**RESPONSE:** given your three levels, I currently see only two technically credible paths:

- use the `project-organiser` agent as the path decision engine
- add harness-level interception so file writes must either use an approved path or request one

**RESPONSE:** without interception, level 2 is guidance only. It may be good guidance, but it is not governance.

**RESPONSE:** with interception, level 2 becomes much stronger:

- the organiser still does the semantic judgement
- the harness ensures the judgement is actually consulted before a new file is written

**RESPONSE:** so my concrete suggestion is not "replace the agent with deterministic code".

**RESPONSE:** it is:

- keep the specialised organiser agent
- move enforcement to the harness or tool boundary if the runtime allows it
- if the runtime does not allow interception, then accept that the organiser is advisory and optimise for consistency, logging, and memory rather than pretending we have hard enforcement

**RESPONSE:** this also answers your earlier skepticism. I agree that, absent interception, a plain old specialised agent may be the best practical option.

**RESPONSE:** the architecture only becomes meaningfully more reliable if there is an actual enforcement hook at write time.

**REVIEW:** Yes and this is the difficult part because we are doing CLI harnesses not directly invoking the LLMs. Maybe we can have a mechanical file check post execution of an agent, we use git to do a diff with before calling the agent to see what new files were created, then we have some sort of validation as to whether these files were whitelisted yet, and when they are new files, we call an agent to evaluate if it makes sense where they were put - basically we could call the project-organiser. So that makes it a judge and if the project organiser says some files are in the wrong place, we send that feedback back to the agent to do another pass.

**RESPONSE:** agreed. This is the first mechanism in the discussion that is both concrete and compatible with a CLI harness.

**RESPONSE:** it is weaker than pre-write interception, but it is still meaningful because it gives:
- mechanical detection of newly created files
- a single review point for placement decisions
- an explicit correction loop when placement is judged incoherent

**RESPONSE:** I think this changes the implementation direction materially.

**RESPONSE:** the practical design would be:
- snapshot workspace before the agent turn
- diff workspace after the turn
- identify newly created paths and moved paths
- subtract any paths already whitelisted by the caller or methodology phase
- send the remaining paths plus file content and surrounding project context to `project-organiser` as a review agent
- if the review passes, record the decision
- if the review fails, feed the relocation or naming feedback back into the generator for another pass

**RESPONSE:** this means the organiser is acting as a post-hoc path judge rather than a pre-write path oracle.

**RESPONSE:** that is an important distinction because:
- it avoids needing tool-level interception that the CLI harness may not support
- it still creates a disciplined feedback loop instead of leaving placement entirely to hope

**RESPONSE:** the limitation is also clear:
- the wrong files may be created briefly before the correction pass
- so this is corrective governance, not preventive governance

**RESPONSE:** but for a CLI-based harness, corrective governance may be the most realistic strong option available today.

**RESPONSE:** I agree this is a better near-term direction than the more abstract adapter argument I was making earlier.

- **RULE:** Backend-specific tool instructions MUST NOT appear in the shared policy layer.
  - **BECAUSE:** Claude-style agent wording and Codex-style agent wording are different execution details, not business rules.
    - **BECAUSE:** If policy is expressed in backend language, the policy becomes non-portable and breaks when the backend changes.

**REVIEW:** agreed, AND there could be different ways of doing this e.g. through external tools or through using different SKILLS fils adapted to the runtime

**RESPONSE:** agreed. The rule should be read as "shared policy stays backend-neutral; adapters may realize it through tools, skills, or backend-specific execution paths".

## 2. Fixed Paths Versus New Paths

- **RULE:** When methodology-runner specifies a concrete artifact path, the default behavior MUST be to treat that path as authoritative.
  - **BECAUSE:** Methodology-runner owns phase-level artifact structure and is the right place to define canonical outputs such as `docs/requirements/requirements-inventory.yaml`.
    - **BECAUSE:** If a lower-level agent can silently override those paths, phase outputs stop being predictable and the methodology loses traceability.

- **RULE:** When a lower-level agent needs a file that was not predeclared by methodology-runner, the path MUST be resolved through project conventions before the file is written.
  - **BECAUSE:** This is the actual chaos case: incidental files, helper files, support files, and implementation details that emerge during work.
    - **BECAUSE:** Those files are exactly where ad hoc directory creation and inconsistent naming tend to accumulate.

- **RULE:** A caller-provided path MAY be revalidated against conventions, but it MUST NOT be silently rewritten when the caller marked it as fixed.
  - **BECAUSE:** Silent rewrites hide disagreement between layers and make failures harder to debug.
    - **BECAUSE:** If the caller was wrong, that should be visible as a policy decision, not masked as if the original request had been coherent.

**REVIEW:** OK.

## 3. The Three Cases

- **RULE:** The system MUST distinguish among `new`, `fixed`, and `fixed-with-verification` path intents.
  - **BECAUSE:** The three cases have different owners and different failure modes.
    - **BECAUSE:** Treating them as one generic “ask the organiser” flow causes contradictions.

- **RULE:** `new` intent MUST mean “no path exists yet; choose one using repo rules.”
  - **BECAUSE:** In this case, the low-level agent has discovered a legitimate need that the higher-level planner could not know in advance.
    - **BECAUSE:** Low-level code generation is where file granularity becomes concrete.

- **RULE:** `fixed` intent MUST mean “the caller has already decided the full path; use it as-is.”
  - **BECAUSE:** Some artifacts are part of the methodology contract, not a suggestion.
    - **BECAUSE:** Phase outputs need stable locations for later phases, verification, and summaries.

- **RULE:** `fixed-with-verification` intent SHOULD mean “the caller chose the path, but the policy layer checks it and either accepts or flags it.”
  - **BECAUSE:** This gives safety without removing caller authority.
    - **BECAUSE:** It lets the system catch convention drift while preserving deterministic ownership.

**REVIEW:** OK.

## 4. Challenge Behavior

- **RULE:** If a `fixed` path violates conventions, the policy layer MUST report the violation explicitly instead of improvising an alternative.
  - **BECAUSE:** A hidden rewrite converts a design disagreement into silent behavior.
    - **BECAUSE:** Silent behavior is harder to review than an explicit mismatch.

- **RULE:** If a `fixed-with-verification` path violates conventions, the policy layer SHOULD either reject it or return a proposed correction with a recorded rationale.
  - **BECAUSE:** This mode exists specifically to challenge weak caller decisions.
    - **BECAUSE:** Its purpose is quality control, not blind obedience.

**REVIEW:** OK.

## 5. Practical Integration

- **RULE:** Methodology-runner MUST pass phase artifact writes as `fixed` or `fixed-with-verification`.
  - **BECAUSE:** It already knows the required artifact names and locations.
    - **BECAUSE:** Those outputs are part of the methodology, not discovered implementation details.

**REVIEW:** Alternative is to adopt an approach of responsibilitty of verification at the level of the agent needing a file to be invented hence Methodology-runner must verify ALL the files it authors; this also reduces the need to challenge if it's systematically done

**RESPONSE:** agreed in part. I think there are two distinct responsibilities:

- methodology-runner should verify the paths of files it explicitly authors
- lower-level agents should verify or resolve the paths of files they invent during execution

**RESPONSE:** I do not think methodology-runner should be the sole verifier for all file creation, because it cannot foresee many low-level incidental files and it lacks the local implementation context that motivated them.

**RESPONSE:** the practical consequence is:

- methodology-runner should systematically verify its declared phase artifacts
- prompt-runner or the backend adapter should handle invented files at execution time

**RESPONSE:** that change would reduce the need to challenge methodology-runner-provided paths, because verified caller paths are stronger than merely asserted caller paths.

- **RULE:** Prompt-runner SHOULD invoke path resolution only for writes whose paths are genuinely undecided.
  - **BECAUSE:** Forcing every write through an organiser adds friction and creates false conflicts with already-correct paths.
    - **BECAUSE:** The organiser is valuable when there is uncertainty, not when there is already a known target.

- **RULE:** Every path decision MUST be logged with requested intent, supplied path, final path, and rationale.
  - **BECAUSE:** File-governance policy is only useful if path decisions can be audited later.
    - **BECAUSE:** When a repo starts drifting, the first debugging question is who chose the path and why.

**REVIEW:** OK.
