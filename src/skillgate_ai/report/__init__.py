"""Human-readable reports for CLI and GitHub Actions.

Re-export shim. Code lives in the submodules listed below. Patching a name on this
shim does not affect code inside the package; patch the submodule that defines it.
"""

from __future__ import annotations

from skillgate_ai.report.dicts import _advice_to_dict as _advice_to_dict
from skillgate_ai.report.dicts import _progress_task_to_dict as _progress_task_to_dict
from skillgate_ai.report.dicts import _task_status as _task_status
from skillgate_ai.report.dicts import _task_to_dict as _task_to_dict
from skillgate_ai.report.dicts import hydrate_report_spans as hydrate_report_spans
from skillgate_ai.report.dicts import progress_to_dict as progress_to_dict
from skillgate_ai.report.dicts import report_to_dict as report_to_dict
from skillgate_ai.report.formatting import _cost_line as _cost_line
from skillgate_ai.report.formatting import format_cli as format_cli
from skillgate_ai.report.formatting import format_github as format_github
from skillgate_ai.report.lines import _GENERIC_FAILS as _GENERIC_FAILS
from skillgate_ai.report.lines import _cell_answer as _cell_answer
from skillgate_ai.report.lines import _check_source as _check_source
from skillgate_ai.report.lines import _extra_source_lines as _extra_source_lines
from skillgate_ai.report.lines import _named_builtin_fail as _named_builtin_fail
from skillgate_ai.report.lines import _source_label as _source_label
from skillgate_ai.report.lines import _task_check_answers as _task_check_answers
from skillgate_ai.report.lines import _task_fail_line as _task_fail_line
from skillgate_ai.report.lines import _task_happened as _task_happened
from skillgate_ai.report.lines import _task_warnings as _task_warnings
from skillgate_ai.report.scoring import _has_choice_answers as _has_choice_answers
from skillgate_ai.report.scoring import _judge_stamp as _judge_stamp
from skillgate_ai.report.scoring import _report_gate as _report_gate
from skillgate_ai.report.scoring import _scoring_endpoint as _scoring_endpoint
from skillgate_ai.report.scoring import scored_by_line as scored_by_line
