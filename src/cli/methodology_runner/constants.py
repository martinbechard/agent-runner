"""Tunable constants for the methodology-runner pipeline.

All numeric thresholds and mode switches referenced by multiple
modules live here so they can be adjusted in one place without
hunting through the codebase.  Per CLAUDE.md: never scatter literal
constants through code.

Any constant that becomes user-configurable in the future should
first be promoted to a CLI flag; until then, changes here require
a code change and re-release.
"""
from __future__ import annotations


ARTIFACT_FULL_CONTENT_THRESHOLD = 5000
"""Size (in bytes) above which a prior-phase artifact is replaced by a
summary rather than passed in full to the Skill-Selector."""

MAX_SKILLS_PER_PHASE = 8
"""Maximum number of skills (generator + judge combined, counted uniquely)
the Skill-Selector is allowed to pick for a single phase.  Caps the
generator prelude size under the inline fallback design."""

MAX_CATALOG_SIZE_WARNING = 100
"""Catalog entry count above which a warning is logged.  Not a halt;
simply a hint that context may become tight."""

SKILL_LOADING_MODE = "skill-tool"
"""Default skill-loading mode for the prelude.

- "skill-tool": prelude instructs the generator/judge to invoke the
  Claude Code Skill tool by name.  Requires Phase 0 validation to
  have confirmed that the Skill tool works inside nested claude
  --print calls.
- "inline": prelude contains the full SKILL.md content of every
  selected skill, delimited by section markers.  Fallback design
  with zero dependency on the Skill tool.

Flipped via Phase 0 validation outcome.  See
``phase_0_validation.py`` and spec section 9.
"""

MAX_CROSS_REF_RETRIES = 2
"""Default maximum re-generation attempts when a phase's cross-reference
verification fails.  Mirrors the existing default in orchestrator.py;
re-exported here for consistency."""
