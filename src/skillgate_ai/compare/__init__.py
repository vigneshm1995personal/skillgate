"""Compare runs: models (live arms) and versions (history / git).

Patching ``skillgate_ai.compare.run_check`` has no effect on compare internals;
monkeypatch ``skillgate_ai.compare.models.run_check`` instead.
"""

from __future__ import annotations

from skillgate_ai.compare.core import ALLOWED_COMPARE_HARNESS as ALLOWED_COMPARE_HARNESS
from skillgate_ai.compare.core import DEFAULT_MAX_SPEND_USD as DEFAULT_MAX_SPEND_USD
from skillgate_ai.compare.core import MAX_ARMS as MAX_ARMS
from skillgate_ai.compare.core import MIN_ARMS as MIN_ARMS
from skillgate_ai.compare.core import CompareArmSpec as CompareArmSpec
from skillgate_ai.compare.core import CompareError as CompareError
from skillgate_ai.compare.core import CompareResult as CompareResult
from skillgate_ai.compare.core import _arm_ids as _arm_ids
from skillgate_ai.compare.core import _as_float as _as_float
from skillgate_ai.compare.core import _as_int as _as_int
from skillgate_ai.compare.core import _blank as _blank
from skillgate_ai.compare.core import _resolve_compare_case_ids as _resolve_compare_case_ids
from skillgate_ai.compare.core import _resolved_arm_model as _resolved_arm_model
from skillgate_ai.compare.core import arm_id_for_index as arm_id_for_index
from skillgate_ai.compare.core import arm_label_defaults as arm_label_defaults
from skillgate_ai.compare.core import checks_for_case_ids as checks_for_case_ids
from skillgate_ai.compare.core import parse_arm_file as parse_arm_file
from skillgate_ai.compare.core import parse_arm_spec as parse_arm_spec
from skillgate_ai.compare.core import validate_compare_plan as validate_compare_plan
from skillgate_ai.compare.models import _append_compare_failure as _append_compare_failure
from skillgate_ai.compare.models import _run_models_compare as _run_models_compare
from skillgate_ai.compare.models import run_check as run_check
from skillgate_ai.compare.models import run_models_compare as run_models_compare
from skillgate_ai.compare.payload import _arm_stats_from_report as _arm_stats_from_report
from skillgate_ai.compare.payload import _build_cases as _build_cases
from skillgate_ai.compare.payload import _case_ids_from_report as _case_ids_from_report
from skillgate_ai.compare.payload import _dry_run_payload as _dry_run_payload
from skillgate_ai.compare.payload import _plan_subtitle as _plan_subtitle
from skillgate_ai.compare.payload import (
    _skill_pack_hash_from_report as _skill_pack_hash_from_report,
)
from skillgate_ai.compare.payload import _subtitle_for_arm as _subtitle_for_arm
from skillgate_ai.compare.payload import _task_map as _task_map
from skillgate_ai.compare.payload import _usage_for_task_ids as _usage_for_task_ids
from skillgate_ai.compare.payload import _usage_from_report as _usage_from_report
from skillgate_ai.compare.payload import scrub_compare_payload as scrub_compare_payload
from skillgate_ai.compare.payload import (
    scrub_customer_compare_payload as scrub_customer_compare_payload,
)
from skillgate_ai.compare.store import find_compare as find_compare
from skillgate_ai.compare.store import find_compare_anywhere as find_compare_anywhere
from skillgate_ai.compare.store import list_compares as list_compares
from skillgate_ai.compare.store import list_compares_merged as list_compares_merged
from skillgate_ai.compare.store import strip_compare_list_meta as strip_compare_list_meta
from skillgate_ai.compare.versions import _git_ref_picker_suggestions as _git_ref_picker_suggestions
from skillgate_ai.compare.versions import _history_report as _history_report
from skillgate_ai.compare.versions import _normalize_compare_harness as _normalize_compare_harness
from skillgate_ai.compare.versions import _run_versions_compare as _run_versions_compare
from skillgate_ai.compare.versions import _versions_dry_run_payload as _versions_dry_run_payload
from skillgate_ai.compare.versions import harness_from_history as harness_from_history
from skillgate_ai.compare.versions import preflight_versions_compare as preflight_versions_compare
from skillgate_ai.compare.versions import run_versions_compare as run_versions_compare
