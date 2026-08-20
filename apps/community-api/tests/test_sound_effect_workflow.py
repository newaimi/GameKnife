from __future__ import annotations

import json
from pathlib import Path

import pytest
from gameknife_core import AllowAllPermissionChecker, CapabilitySet, JobRecord, Principal, RequestContext, Workspace
from gameknife_jobs import (
    AssetWriteInProgressError,
    JobSubmissionResult,
    SQLiteGameKnifeRepository,
    TaskSubmission,
    init_sqlite_schema,
)
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


class ReplaySoundEffectRepository(SQLiteGameKnifeRepository):
    def __init__(self, database_path: Path) -> None:
        super().__init__(database_path)
        self._accepted_by_key: dict[str, JobRecord] = {}

    def create_job(
        self,
        job: JobRecord,
        submission: TaskSubmission | None = None,
    ) -> JobSubmissionResult:
        key = submission.idempotency_key if submission is not None else None
        if key is not None and key in self._accepted_by_key:
            return JobSubmissionResult(job=self._accepted_by_key[key], replayed=True)
        result = super().create_job(job, submission)
        if key is not None:
            self._accepted_by_key[key] = result.job
        return result


class FencedPromptRepository(SQLiteGameKnifeRepository):
    def create_pending_asset(
        self,
        asset,
        *,
        reserved_bytes: int,
        reservation_job_id: str | None = None,
    ):
        del reserved_bytes, reservation_job_id
        raise AssetWriteInProgressError(asset.id)


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
        assert str(exc) == "请输入声效提示词。"
    else:
        raise AssertionError("空声效提示词必须阻止创建任务。")


def test_sound_effect_workflow_rejects_unavailable_service(tmp_path: Path) -> None:
    repository, context = _make_repository_and_context(tmp_path)

    try:
        create_sound_effect_workflow(
            repository,
            context,
            FakeSoundEffectService({"status": "unconfigured", "installed": False, "message": "Stable Audio 声效服务未配置。"}),
            parameters={"prompt": "coin pickup", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        )
    except WorkflowServiceUnavailableError as exc:
        assert str(exc) == "Stable Audio 声效服务未配置。"
    else:
        raise AssertionError("声效服务不可用时必须阻止创建任务。")


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
        assert str(exc) == "Stable Audio Open 模型尚未安装，请先到设置页下载安装模型文件。"
    else:
        raise AssertionError("Stable Audio 模型未安装时必须阻止创建任务。")


def test_sound_effect_workflow_creates_prompt_and_wav_assets(tmp_path: Path) -> None:
    repository, context = _make_repository_and_context(tmp_path)
    service = FakeSoundEffectService()

    submitted, runner = create_sound_effect_workflow(
        repository,
        context,
        service,
        parameters={"prompt": " coin pickup ", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
    )
    job = submitted.job
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
    output_path = context.storage.local_path(output_asset.path)
    assert output_path is not None
    assert output_path.read_bytes().startswith(b"RIFF")
    assert service.generate_calls == 1


def test_sound_effect_replay_reuses_input_and_removes_unaccepted_prompt(tmp_path: Path) -> None:
    repository, context = _make_repository_and_context(tmp_path, ReplaySoundEffectRepository)
    service = FakeSoundEffectService()
    submission = TaskSubmission(idempotency_key="sound-request-1", quote_id="quote-1")

    first, _first_runner = create_sound_effect_workflow(
        repository,
        context,
        service,
        parameters={"prompt": "coin pickup", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        submission=submission,
    )
    replay, _replay_runner = create_sound_effect_workflow(
        repository,
        context,
        service,
        parameters={"prompt": "coin pickup", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        submission=submission,
    )
    changed_prompt_replay, _changed_runner = create_sound_effect_workflow(
        repository,
        context,
        service,
        parameters={"prompt": "sword impact", "duration_seconds": 1, "steps": 20, "cfg_scale": 5},
        submission=submission,
    )

    prompt_assets = [
        asset
        for asset in repository.list_assets_for_workspace(context.workspace.id)
        if asset.kind == "sound_prompt"
    ]
    assert first.replayed is False
    assert replay.replayed is True
    assert changed_prompt_replay.replayed is True
    assert replay.job.id == first.job.id
    assert replay.job.input_asset_id == first.job.input_asset_id
    assert changed_prompt_replay.job.id == first.job.id
    assert [asset.id for asset in prompt_assets] == [first.job.input_asset_id]
    assert len(list((tmp_path / "storage" / "assets").glob("*.txt"))) == 1


def test_sound_effect_prompt_delete_fence_returns_service_unavailable(
    tmp_path: Path,
) -> None:
    repository, context = _make_repository_and_context(
        tmp_path,
        FencedPromptRepository,
    )

    with pytest.raises(
        WorkflowServiceUnavailableError,
        match="相同声效任务正在提交",
    ):
        create_sound_effect_workflow(
            repository,
            context,
            FakeSoundEffectService(),
            parameters={
                "prompt": "coin pickup",
                "duration_seconds": 1,
                "steps": 20,
                "cfg_scale": 5,
            },
            submission=TaskSubmission(
                idempotency_key="sound-fenced",
                quote_id="quote-fenced",
            ),
        )


def _make_repository_and_context(
    tmp_path: Path,
    repository_type: type[SQLiteGameKnifeRepository] = SQLiteGameKnifeRepository,
) -> tuple[SQLiteGameKnifeRepository, RequestContext]:
    storage = LocalStorageProvider(tmp_path / "storage")
    database_path = tmp_path / "storage" / "gameknife.sqlite3"
    init_sqlite_schema(database_path)
    repository = repository_type(database_path)
    context = RequestContext(
        principal=Principal(id="anonymous", kind="anonymous", display_name="本地用户"),
        workspace=Workspace(id="local", kind="local", name="本地工作区"),
        permissions=AllowAllPermissionChecker(),
        capabilities=CapabilitySet(edition="community", features=frozenset({"sound-effect"})),
        storage=storage,
    )
    return repository, context
