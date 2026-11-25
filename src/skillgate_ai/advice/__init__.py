"""Copy-paste fix loop: fail → why → a description that would actually trigger.

Re-export shim. Code lives in the submodules listed below. Patching a name on this
shim does not affect code inside the package; patch the submodule that defines it.
"""

from __future__ import annotations

from skillgate_ai.advice.behavior import _behavior_fix as _behavior_fix
from skillgate_ai.advice.behavior import behavior_fail_line as behavior_fail_line
from skillgate_ai.advice.behavior import behavior_question_ids as behavior_question_ids
from skillgate_ai.advice.fixes import _trigger_fix as _trigger_fix
from skillgate_ai.advice.fixes import advise_suite as advise_suite
from skillgate_ai.advice.fixes import advise_task as advise_task
from skillgate_ai.advice.model import _MEAL_NOISE as _MEAL_NOISE
from skillgate_ai.advice.model import BEHAVIOR_FAIL_LEAD as BEHAVIOR_FAIL_LEAD
from skillgate_ai.advice.model import TRIGGER_SECONDARY_NOTE as TRIGGER_SECONDARY_NOTE
from skillgate_ai.advice.model import FixAdvice as FixAdvice
from skillgate_ai.advice.quality import _PADDED_TOKEN as _PADDED_TOKEN
from skillgate_ai.advice.quality import _THIN_HINT as _THIN_HINT
from skillgate_ai.advice.quality import _VAGUE_HINT as _VAGUE_HINT
from skillgate_ai.advice.quality import _VAGUE_TOKENS as _VAGUE_TOKENS
from skillgate_ai.advice.quality import _WHEN_HINT as _WHEN_HINT
from skillgate_ai.advice.quality import _WHEN_SPLIT as _WHEN_SPLIT
from skillgate_ai.advice.quality import _content_tokens as _content_tokens
from skillgate_ai.advice.quality import description_is_usable as description_is_usable
from skillgate_ai.advice.rewrite import apply_description_fix as apply_description_fix
from skillgate_ai.advice.rewrite import description_from_paste as description_from_paste
from skillgate_ai.advice.rewrite import rewrite_skill_description as rewrite_skill_description
from skillgate_ai.advice.synth import _description_from_prompts as _description_from_prompts
from skillgate_ai.advice.synth import _force_keywords as _force_keywords
from skillgate_ai.advice.synth import _retarget_description as _retarget_description
from skillgate_ai.advice.synth import _tighten_description as _tighten_description
from skillgate_ai.advice.synth import _when_clause as _when_clause
from skillgate_ai.advice.synth import (
    synthesize_trigger_description as synthesize_trigger_description,
)
from skillgate_ai.advice.text import _clip as _clip
from skillgate_ai.advice.text import _command_fail_snippet as _command_fail_snippet
from skillgate_ai.advice.text import _frontmatter as _frontmatter
from skillgate_ai.advice.text import _is_script_failure as _is_script_failure
from skillgate_ai.advice.text import _suggested_steps as _suggested_steps
from skillgate_ai.advice.text import _task_output_path as _task_output_path
