"""Skill pack = the skill directory (agentskills spec).

A skill is a folder with SKILL.md plus optional scripts/, references/, assets/,
evals/, and any other files. Progressive disclosure: metadata → SKILL.md body →
resources on demand.

Skill Gate does **not** invent a parallel Artifact blob store. Eval fixtures live
in the skill tree (prefer ``evals/fixtures/`` or ``assets/``). Checks reference
those files with relative paths from the skill root — the same rule as
agentskills file refs.

Re-export shim. Code lives in the submodules listed below. Patching a name on this
shim does not affect code inside the package; patch the submodule that defines it.
"""

from __future__ import annotations

from skillgate_ai.pack.constants import _IMAGE_MAGICS as _IMAGE_MAGICS
from skillgate_ai.pack.constants import _PDF_MAGIC as _PDF_MAGIC
from skillgate_ai.pack.constants import _SAFE_NAME as _SAFE_NAME
from skillgate_ai.pack.constants import _SKIP_DIR_NAMES as _SKIP_DIR_NAMES
from skillgate_ai.pack.constants import _SKIP_FILE_NAMES as _SKIP_FILE_NAMES
from skillgate_ai.pack.constants import _UNSYNTHESIZABLE as _UNSYNTHESIZABLE
from skillgate_ai.pack.constants import ASSET_DIR as ASSET_DIR
from skillgate_ai.pack.constants import CASE_SUFFIXES as CASE_SUFFIXES
from skillgate_ai.pack.constants import DEFAULT_FIXTURE_GLOB as DEFAULT_FIXTURE_GLOB
from skillgate_ai.pack.constants import FIXTURE_DIR as FIXTURE_DIR
from skillgate_ai.pack.constants import GOLDEN_DIR as GOLDEN_DIR
from skillgate_ai.pack.constants import IMAGE_SUFFIXES as IMAGE_SUFFIXES
from skillgate_ai.pack.constants import PDF_DEMO_FIXTURE_NAMES as PDF_DEMO_FIXTURE_NAMES
from skillgate_ai.pack.constants import PREVIEW_TEXT_LIMIT as PREVIEW_TEXT_LIMIT
from skillgate_ai.pack.constants import TEXT_SUFFIXES as TEXT_SUFFIXES
from skillgate_ai.pack.listing import _glob_match as _glob_match
from skillgate_ai.pack.listing import _is_pdf_example_dir as _is_pdf_example_dir
from skillgate_ai.pack.listing import _without_leaked_pdf_demo as _without_leaked_pdf_demo
from skillgate_ai.pack.listing import browser_files as browser_files
from skillgate_ai.pack.listing import fixture_files as fixture_files
from skillgate_ai.pack.listing import list_pack_files as list_pack_files
from skillgate_ai.pack.listing import relevant_eval_fixtures as relevant_eval_fixtures
from skillgate_ai.pack.listing import skill_pack_hash as skill_pack_hash
from skillgate_ai.pack.pathsafe import _path_under_skill as _path_under_skill
from skillgate_ai.pack.pathsafe import _rel_to_skill as _rel_to_skill
from skillgate_ai.pack.pathsafe import _safe_filename as _safe_filename
from skillgate_ai.pack.pathsafe import fixture_src_for as fixture_src_for
from skillgate_ai.pack.pathsafe import implied_fixture_name as implied_fixture_name
from skillgate_ai.pack.pathsafe import is_pack_relative as is_pack_relative
from skillgate_ai.pack.pathsafe import safe_relpath as safe_relpath
from skillgate_ai.pack.resolve import _accept_input_file as _accept_input_file
from skillgate_ai.pack.resolve import _inside_other_skill as _inside_other_skill
from skillgate_ai.pack.resolve import file_copy_from_rel as file_copy_from_rel
from skillgate_ai.pack.resolve import resolve_input_file as resolve_input_file
from skillgate_ai.pack.samples import CannotSynthesizeFixture as CannotSynthesizeFixture
from skillgate_ai.pack.samples import as_fixture_bytes as as_fixture_bytes
from skillgate_ai.pack.samples import cannot_synthesize_sample as cannot_synthesize_sample
from skillgate_ai.pack.samples import generate_sample_bytes as generate_sample_bytes
from skillgate_ai.pack.samples import implies_photo_scan as implies_photo_scan
from skillgate_ai.pack.samples import is_authentic_fixture_bytes as is_authentic_fixture_bytes
from skillgate_ai.pack.tree import _content_type as _content_type
from skillgate_ai.pack.tree import _pack_copy_ignore as _pack_copy_ignore
from skillgate_ai.pack.tree import copy_skill_pack as copy_skill_pack
from skillgate_ai.pack.tree import pack_file_path as pack_file_path
from skillgate_ai.pack.tree import pack_preview as pack_preview
from skillgate_ai.pack.writes import copy_into_pack as copy_into_pack
from skillgate_ai.pack.writes import persist_case_file as persist_case_file
from skillgate_ai.pack.writes import promote_file_into_pack as promote_file_into_pack
from skillgate_ai.pack.writes import write_pack_file as write_pack_file
from skillgate_ai.pack.writes import write_sample_fixture as write_sample_fixture
