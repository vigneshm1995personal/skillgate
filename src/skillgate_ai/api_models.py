"""Pydantic v2 request bodies for FastAPI routes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Compare arm payloads accept arbitrary JSON objects from the UI.
_CompareArm = str | dict[str, object]


class SetKeyBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str = ""


class JudgeSettingsBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str | None = None
    region: str | None = None
    model: str | None = None
    base_url: str | None = None
    decisions_path: str | None = None
    account_id: str | None = None
    key_env: str | None = None


class InstallExamplesBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    names: list[str] | None = None
    name: str | None = None


class ImportSkillsBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    folder: str | None = None
    path: str | None = None
    git_url: str | None = None
    git: str | None = None
    sources: list[str] | None = None


class PackFileWriteBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill: str = ""
    path: str | None = None
    filename: str | None = None
    content: str | None = None
    generate: bool = False
    prompt: str = ""


class PasteSkillBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    markdown: str = ""


class ApplyFixBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill: str = ""
    paste: str = ""
    restore_scripts_from: str = ""


class DeployBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target: str = ""
    mode: str = "local"
    skill: str = ""
    force: bool = False


class EvalGenerateBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill: str = ""
    yaml: str | None = None


class EvalPinBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    skill: str = ""
    checks: list[dict[str, object]] | None = None
    case_ids: list[str] | None = None
    pack_judge: dict[str, object] | None = None


class EvalFixtureBindBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill: str = ""
    checks: list[dict[str, object]] = Field(default_factory=list)
    inherit: bool = True
    glob: str | None = None
    action: str = "inherit"


class StartRunBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    skill: str = ""
    tryout: bool = False
    checks: list[dict[str, object]] | None = None
    config: dict[str, object] = Field(default_factory=dict)
    harness: str = "auto"
    no_judge: bool = False


class CompareModelsBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    skill: str = ""
    arms: list[_CompareArm] | None = None
    max_spend_usd: float | None = None
    case_ids: list[str] | None = None


class CompareVersionsBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    skill: str = ""
    run_ids: list[str] | None = None
    git_refs: list[str] | None = None
    rerun: bool = False


class EvalBaselineBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill: str = ""
    run_id: str | None = None


class PromoteDraftBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    skill: str | None = None
    task: dict[str, object] = Field(default_factory=dict)


class CheckPreviewBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    question: dict[str, object] | None = None
