from __future__ import annotations

import json
from pathlib import Path

from gameknife_core import AllowAllPermissionChecker, CapabilitySet, Principal, RequestContext, Workspace
from gameknife_jobs import SQLiteGameKnifeRepository, init_sqlite_schema
from gameknife_storage import LocalStorageProvider
from gameknife_workflows import (
    WorkflowModelNotInstalledError,
    WorkflowServiceUnavailableError,
    WorkflowValidationError,
    create_sound_effect_workflow,
)


class FakeSoundEffectService:
    def __init__(self, status: dict[str, object] | None = None) -> None:
        self.status = status or {"status": "success", "installed": True, "message": "ok", "error": None}
        self.generate_calls = 0

    def install_status(self) -> dict[str, object]:
        return self.status

    def generate_sound_effect(self, prompt: str, output_path: Path, parameters: dict[str, object]) -> dict[str, object]:
        self.generate_calls += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
        return {
            "model": "fake-stable-audio",
            "device": "cpu",
            "sample_rate": 44100,
            "queue_wait_ms": 0,
            "duration_ms": 5,
        }


def test_sound_effect_workflow_rejects_blank_prompt(tmp_path: Path) -> None:
    repository, context = _make_repository_and_context(tmp_path)

    try:
        create_sound_effect_workflow(
            repository,
            context,
            FakeSoundEffectService(),
            parameters={"prompt": "   ", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        )
    except WorkflowValidationError as exc:
        assert str(exc) == "Enter an SFX prompt."
    else:
        raise AssertionError("An empty SFX prompt must prevent job creation.")


def test_sound_effect_workflow_rejects_unavailable_service(tmp_path: Path) -> None:
    repository, context = _make_repository_and_context(tmp_path)

    try:
        create_sound_effect_workflow(
            repository,
            context,
            FakeSoundEffectService({"status": "unconfigured", "installed": False, "message": "The Stable Audio SFX service is not configured."}),
            parameters={"prompt": "coin pickup", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        )
    except WorkflowServiceUnavailableError as exc:
        assert str(exc) == "The Stable Audio SFX service is not configured."
    else:
        raise AssertionError("An unavailable SFX service must prevent job creation.")


def test_sound_effect_workflow_rejects_missing_model(tmp_path: Path) -> None:
    repository, context = _make_repository_and_context(tmp_path)

    try:
        create_sound_effect_workflow(
            repository,
            context,
            FakeSoundEffectService({"status": "idle", "installed": False, "message": "not installed"}),
            parameters={"prompt": "coin pickup", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        )
    except WorkflowModelNotInstalledError as exc:
        assert str(exc) == "Stable Audio Open is not installed. Install the model files from Settings first."
    else:
        raise AssertionError("A missing Stable Audio model must prevent job creation.")


def test_sound_effect_workflow_creates_prompt_and_wav_assets(tmp_path: Path) -> None:
    repository, context = _make_repository_and_context(tmp_path)
    service = FakeSoundEffectService()

    job, runner = create_sound_effect_workflow(
        repository,
        context,
        service,
        parameters={"prompt": " coin pickup ", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
    )
    runner()

    stored = repository.get_job_for_workspace(job.id, context.workspace.id)
    assert stored is not None
    result = json.loads(stored.result_json)
    prompt_asset = repository.get_asset_for_workspace(stored.input_asset_id, context.workspace.id)
    output_asset = repository.get_asset_for_workspace(result["output_assets"][0]["id"], context.workspace.id)
    assert stored.status == "success"
    assert stored.job_type == "sound_effect_generate"
    assert result["prompt"] == "coin pickup"
    assert prompt_asset is not None
    assert prompt_asset.kind == "sound_prompt"
    assert output_asset is not None
    assert output_asset.kind == "sound_effect"
    assert output_asset.mime_type == "audio/wav"
    assert context.storage.resolve_asset_path(output_asset.path).read_bytes().startswith(b"RIFF")
    assert service.generate_calls == 1


def _make_repository_and_context(tmp_path: Path) -> tuple[SQLiteGameKnifeRepository, RequestContext]:
    storage = LocalStorageProvider(tmp_path / "storage")
    database_path = tmp_path / "storage" / "gameknife.sqlite3"
    init_sqlite_schema(database_path)
    repository = SQLiteGameKnifeRepository(database_path)
    context = RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="Local user"),
        workspace=Workspace(id="local", kind="local", name="Local workspace"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=frozenset({"sound-effect"})),
        storage=storage,
    )
    return repository, context
