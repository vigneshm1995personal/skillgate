"""Author I/O pack: cases.yaml + fixtures inputs + golden outputs.

The skill directory is the only blob store. Pinned cases are the Deploy trust
path; drafts and suggest-from-skill checks are not.
"""

from __future__ import annotations

from skillgate_ai.case_pack.dataset import _OPTIONAL_OUTPUT_NOTE as _OPTIONAL_OUTPUT_NOTE
from skillgate_ai.case_pack.dataset import MISSING_GOLDEN_REASON as MISSING_GOLDEN_REASON
from skillgate_ai.case_pack.dataset import _preview_file as _preview_file
from skillgate_ai.case_pack.dataset import actual_output_state as actual_output_state
from skillgate_ai.case_pack.dataset import case_for_task as case_for_task
from skillgate_ai.case_pack.dataset import dataset_view as dataset_view
from skillgate_ai.case_pack.dataset import golden_state as golden_state
from skillgate_ai.case_pack.dataset import no_trigger_output_warning as no_trigger_output_warning
from skillgate_ai.case_pack.dataset import task_missing_golden as task_missing_golden
from skillgate_ai.case_pack.models import _CASE_ID_RE as _CASE_ID_RE
from skillgate_ai.case_pack.models import _JSONISH_RE as _JSONISH_RE
from skillgate_ai.case_pack.models import CASES_REL as CASES_REL
from skillgate_ai.case_pack.models import EXPECTED_WITHOUT_TARGET as EXPECTED_WITHOUT_TARGET
from skillgate_ai.case_pack.models import NO_TRIGGER_OUTPUT_WARNING as NO_TRIGGER_OUTPUT_WARNING
from skillgate_ai.case_pack.models import PACK_FINGERPRINT_FIELDS as PACK_FINGERPRINT_FIELDS
from skillgate_ai.case_pack.models import PIN_NEEDS_EXPECTED as PIN_NEEDS_EXPECTED
from skillgate_ai.case_pack.models import PIN_NEEDS_EXPECTED_HINT as PIN_NEEDS_EXPECTED_HINT
from skillgate_ai.case_pack.models import CaseFileCopy as CaseFileCopy
from skillgate_ai.case_pack.models import CaseGolden as CaseGolden
from skillgate_ai.case_pack.models import CaseInput as CaseInput
from skillgate_ai.case_pack.models import CasePack as CasePack
from skillgate_ai.case_pack.models import PackCase as PackCase
from skillgate_ai.case_pack.models import TrustSuite as TrustSuite
from skillgate_ai.case_pack.models import _reject_missing_seed_cases as _reject_missing_seed_cases
from skillgate_ai.case_pack.models import _reject_removed_seed_cases as _reject_removed_seed_cases
from skillgate_ai.case_pack.pins import _case_from_check as _case_from_check
from skillgate_ai.case_pack.pins import _disk_golden as _disk_golden
from skillgate_ai.case_pack.pins import _file_content as _file_content
from skillgate_ai.case_pack.pins import _file_copies as _file_copies
from skillgate_ai.case_pack.pins import _inline_input_text as _inline_input_text
from skillgate_ai.case_pack.pins import _persist_golden as _persist_golden
from skillgate_ai.case_pack.pins import _persist_input_files as _persist_input_files
from skillgate_ai.case_pack.pins import _skill_name as _skill_name
from skillgate_ai.case_pack.pins import pin_case_ids as pin_case_ids
from skillgate_ai.case_pack.pins import pin_checks as pin_checks
from skillgate_ai.case_pack.store import _dump_pack as _dump_pack
from skillgate_ai.case_pack.store import _validate_pack_on_disk as _validate_pack_on_disk
from skillgate_ai.case_pack.store import cases_path as cases_path
from skillgate_ai.case_pack.store import (
    expected_without_target_warning as expected_without_target_warning,
)
from skillgate_ai.case_pack.store import load_case_pack as load_case_pack
from skillgate_ai.case_pack.store import pack_judge_dict as pack_judge_dict
from skillgate_ai.case_pack.store import reset_pack_judge as reset_pack_judge
from skillgate_ai.case_pack.store import save_case_pack as save_case_pack
from skillgate_ai.case_pack.store import save_pack_judge as save_pack_judge
from skillgate_ai.case_pack.suites import _bundled_suite_trust as _bundled_suite_trust
from skillgate_ai.case_pack.suites import _project_root_for_skill as _project_root_for_skill
from skillgate_ai.case_pack.suites import _template_trust as _template_trust
from skillgate_ai.case_pack.suites import checks_fingerprint as checks_fingerprint
from skillgate_ai.case_pack.suites import checks_from_pack as checks_from_pack
from skillgate_ai.case_pack.suites import expand_from_pack as expand_from_pack
from skillgate_ai.case_pack.suites import pack_fingerprint as pack_fingerprint
from skillgate_ai.case_pack.suites import skill_has_dataset as skill_has_dataset
from skillgate_ai.case_pack.suites import suite_fingerprint as suite_fingerprint
from skillgate_ai.case_pack.suites import suite_from_checks as suite_from_checks
from skillgate_ai.case_pack.suites import suite_from_pack as suite_from_pack
from skillgate_ai.case_pack.suites import trust_suite_for_skill as trust_suite_for_skill
from skillgate_ai.pack_files import GOLDEN_TAIL_CHARS as GOLDEN_TAIL_CHARS
from skillgate_ai.pack_files import read_capped_text as read_capped_text
from skillgate_ai.pack_files import sniff_output_bytes as sniff_output_bytes
from skillgate_ai.pack_schema import ExtraQuestion as ExtraQuestion
from skillgate_ai.pack_schema import JudgeBlock as JudgeBlock
