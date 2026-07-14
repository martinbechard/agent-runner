# Agent-Runner Structured Artifact Review Checklist

Use this Review Checklist for any structured design, plan, architecture, workflow, or rules document review.

## Completion Format

For every question record:

- Status: pass, fail, question, or n/a.
- Question: copy the objective question being answered.
- Quoted evidence: quote the exact target or input text that supports the status.
- Assessment: explain why the quoted evidence passes, fails, is unclear, or is not applicable.
- Correction: state the expected change for failed or questionable items.
- Authority: cite the directive, source, contract, or project rule that supports the correction.
- Impact: state the practical consequence if the issue remains unresolved.

Do not mark pass without quoted evidence.

## Skill Workflow Questions

- Question: Does the review identify the target artifact path before scoring checklist items?
- Question: Does the review identify the input artifact paths or directives before scoring checklist items?
- Question: Does the review name review-checklist-structured.md as the generic base checklist?
- Question: Does the completed review checklist save next to the target using target-name.review-checklist-structured.md?
- Question: Does the checklist exist before findings are written?
- Question: Are findings derived from failed or questionable checklist items rather than independent opinion?
- Question: Do findings cite checklist item IDs and target locations?
- Question: Does every finding state a correction, authority, and impact?
- Question: Is severity based on practical impact instead of writing preference?

## Input Coverage Questions

- Question: Are all material input directives traced to target locations or marked as not applied?
- Question: Are missing directive applications marked as failures or open questions instead of ignored?
- Question: Does the target avoid contradicting stated input directives?
- Question: Are unsupported requirements or claims flagged with quoted evidence?

## Internal Logic Questions

- Question: Are concepts introduced before they are used?
- Question: Does the document follow a logical dependency order?
- Question: Does the document avoid material contradictions?
- Question: Are requirements distinguished from solution choices?
- Question: Are goals distinguished from features where relevant?

## Structured Design Scope Questions

- Question: When the target is a component or prompt-chain design, does it explain the workflow rather than only the final artifact contract?
- Question: Are skills treated as compact operational artifacts rather than the place where the whole component workflow is explained?
- Question: When the target is an architecture document, does it stay focused on system shape, boundaries, interactions, responsibilities, and major boundary-shaping technology choices?
- Question: When the target is a component design document, does it explain the chosen component or workflow without silently redesigning system boundaries?
- Question: Does the target avoid mixing architecture and component design concerns so heavily that decision scope becomes unclear?

## Writing And Section Model Questions

- Question: Does the document use plain English, short sentences, and simple words?
- Question: Are jargon, buzzwords, and abstract phrasing avoided unless clearly needed?
- Question: Are technical terms defined once when first introduced?
- Question: Are vague words such as robust, seamless, optimize, leverage, and enhance removed or made specific?
- Question: Does the document stay concrete and actionable?
- Question: When relevant, does the document include finality, technical directives, constraints, definition of good, and test cases?
- Question: When the target is a component design document, are finality, technical directives, and definition of good kept distinct?
- Question: When the target is an architecture document, are system shape, boundaries and interactions, constraints, and definition of good kept distinct?

## Markdown And YAML Questions

- Question: When both markdown and YAML exist, does markdown remain the authority unless the user asked for YAML as primary?
- Question: Does the YAML preserve the markdown document's real section structure?
- Question: Do grouped items remain grouped rather than flattened into unrelated entries?
- Question: Are stable IDs preserved in YAML entries?
- Question: Does the YAML avoid generic type fields unless the task explicitly called for that style?

## Findings

Report findings first. Treat missing directive coverage, contradictions, unsupported claims, scope blur, section-model drift, and evidence-free pass assessments as review findings.
