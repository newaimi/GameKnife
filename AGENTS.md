# AGENTS.md

This file defines how automated coding agents should work in the GameKnife open source repository.

GameKnife Community is a local, no-login toolbox for game art asset processing. It uses React, TypeScript, Vite, FastAPI, SQLite, local file storage, local model caches, and an optional standalone Stable Audio SFX service.

## Working Principles

- Read the relevant code before changing behavior.
- Prefer existing modules, services, hooks, components, and utilities over new parallel implementations.
- Search the repository before adding a new helper, API, component, type, workflow, or processor.
- Keep changes scoped to the requested behavior.
- Avoid broad refactors unless they are required to complete the request safely.
- Add comments only where they explain why a boundary, safety check, coordinate conversion, model-loading rule, or cleanup path exists.
- Code comments should be written in Chinese when comments are needed.
- User-facing UI copy should stay short and clear.
- Do not add visible UI text that explains implementation details, architecture, shortcuts, or internal behavior.
- Do not write local absolute paths, personal environment names, private tokens, or machine-specific commands into documentation or scripts.
- Do not commit generated runtime data, local storage, model caches, or secrets.

## Repository Scope

This repository contains the Community edition and the public reusable code needed by it.

The Community edition must stay no-login:

- No login, registration, logout, user management, account roles, organizations, billing, or audit features.
- No Authorization header, login cookie, or localStorage token requirement for Community API calls.
- The fixed Community request context is `principal.id = "anonymous"`, `workspace.id = "local"`, and `edition = "community"`.
- Community data is stored in SQLite and local files by default.
- Assets, jobs, sequences, rigs, and manual edits use `workspace_id = "local"` and `created_by = "anonymous"`.

Public packages and services must not depend on real users, organizations, projects, billing, audit, or commercial storage.

## Directory Responsibilities

- `apps/community-web`: Community React shell, routing, theme, no-login startup context, and public page composition.
- `apps/community-api`: Community FastAPI entry point and runtime assembly.
- `packages/api-client`: Frontend API client. It must not read login tokens.
- `packages/app-context`: Frontend Principal, Workspace, Permission, and Capability abstractions.
- `packages/editor-core`: Manual editor core logic.
- `packages/feature-registry`: Tool route and menu registration.
- `packages/image-workflows`: Public workflow pages and tool workbenches.
- `packages/shared-types`: Shared frontend response and domain types.
- `packages/ui-kit`: Cross-tool UI components.
- `services/core`: Domain records such as Asset, Job, WorkflowRun, Layer, Mask, and BBox.
- `services/jobs`: Repository interface and SQLite implementation.
- `services/storage`: Local file storage interface and implementation.
- `services/processors`: Model and media processor adapters.
- `services/workflows`: Backend workflow orchestration.
- `services/api`: FastAPI routes, request context dependencies, settings endpoints, and response assembly.
- `services-extra/stable-audio-sfx`: Standalone Stable Audio SFX service.
- `docker`: Community and Stable Audio SFX Docker files.
- `docs`: Architecture and deployment documentation.
- `scripts`: Build, deploy, and environment helper scripts.

## Frontend Rules

- `apps/community-web` composes routes and shell behavior. Keep individual tool logic inside package modules.
- Tool pages should depend on `api-client`, `app-context`, `ui-kit`, and workflow-specific package code.
- Tool pages must not read edition, login state, real user roles, or billing state.
- Use `packages/feature-registry` for tool menus and routes.
- Use shared workflow pages from `packages/image-workflows` instead of duplicating tool UI.
- Use shared editor logic from `packages/editor-core` for manual edit behavior.
- Use `WorkbenchPreview` and existing preview helpers for image preview, zoom, pan, fit-to-screen, bbox editing, and comparison views.
- Keep the three-column workbench structure consistent where the tool uses that layout: left tool navigation, center preview, right parameters.
- Long parameter panels should scroll internally. The main workbench row should not be stretched by one side panel.
- Result lists, task history, thumbnails, diagnostics, and secondary outputs belong below the main workbench.
- Manual edit is a dedicated route. It should keep its focused editor layout.
- Use `gameknife-*` localStorage and sessionStorage keys.
- Protected asset loading should use blob requests through the API client helpers. Do not add token-based file preview logic.
- Keep UI style aligned with the existing Community shell and shared CSS variables.
- Avoid text overflow, hidden labels, overlapping controls, and unstable button dimensions on mobile and desktop widths.

## Backend Rules

- FastAPI routes should validate input, resolve context, call services or workflows, and assemble responses.
- Repository and storage access should go through the established repository and provider layers.
- Use `RequestContext` for principal, workspace, permissions, capabilities, storage, and edition.
- Community permission checks use the allow-all local implementation.
- New Community tables must use `workspace_id` and `created_by`; do not add `user_id` fields to Community data models.
- Database writes should be explicit and parameterized.
- File deletion keeps the existing policy: delete database records first, then clean disk files as a best-effort operation.
- Upload endpoints must validate actual file contents, not only MIME headers.
- Job responses should use Asset and Job terminology.
- Keep Chinese error messages for end users.
- Background removal, Real-ESRGAN, character rig model workflows, and Stable Audio generation must check installation status before job creation.
- Inference code must load from local model caches during task execution.
- Do not add implicit model downloads in processors or workflow execution.
- If a required model is installed and inference fails, the job should fail explicitly.
- Asset board region detection should stay a fast local image-analysis step. It should not call BiRefNet.
- BiRefNet and Real-ESRGAN inference should remain serialized in-process.
- Stable Audio generation should stay in the standalone service queue.

## Stable Audio SFX

- Keep the SFX service independent from the Community API process.
- The Community API creates the job, calls the internal SFX service, and stores output assets.
- The SFX service owns model installation, worker state, queueing, runtime dependency checks, WAV encoding, and generation errors.
- Requests to the SFX service use `X-Gameknife-Token` when `GAMEKNIFE_STABLE_AUDIO_TOKEN` is configured.
- Stable Audio local development must respect the pinned dependency set described in the README.

## Docker And Environment

- Environment variables must use the `GAMEKNIFE_*` prefix unless the upstream tool requires another name such as `HF_TOKEN`.
- Keep `.env.example` generic and safe.
- Docker volumes in compose files should be relative to the compose file directory when local bind mounts are intended.
- Community Docker should expose the web app and `/api/health` from the same service port.
- Docker GPU support should be explicit in compose files and documented as requiring NVIDIA driver and NVIDIA Container Toolkit.

## Documentation Rules

- README and docs should describe the open source Community edition from the developer's point of view.
- Do not include private local paths, personal environment names, or local-only commands.
- Mention external or commercial extension points only when needed to explain public boundaries.
- Keep product naming consistent: `GameKnife`, `gameknife`, and `GAMEKNIFE`.
- Avoid legacy `ImageKnife` naming except in migration history documents.

## Testing And Verification

Run the smallest reliable verification set for the files changed.

Backend tests:

```powershell
python -m pytest -q apps\community-api\tests services-extra\stable-audio-sfx\tests
```

Frontend build:

```powershell
npm run build
```

Type checks:

```powershell
npm run typecheck
```

Docker validation:

```powershell
docker compose --env-file .env -f docker\compose.community.yml config
```

For preview, zoom, drag comparison, upload, download, manual edit, or responsive layout changes, run the app and verify the affected page in a browser.

## Git Rules

- Do not commit unless the user explicitly asks for a commit.
- When committing, use Conventional Commits.
- Write commit messages in English.
- Keep unrelated user changes intact.
- Do not revert files that are outside the requested work.
- Before reporting completion, check `git status --short`.

## Common Pitfalls

- Do not reintroduce login checks into Community API or frontend.
- Do not add old route compatibility aliases unless the user explicitly requests them.
- Do not add aggregate legacy settings endpoints after they have been removed.
- Do not place all tool logic into one shell file.
- Do not duplicate workflow pages between packages and apps.
- Do not leave temporary prompt assets or partially created records after a failed job creation path.
- Do not let frontend polling become the only source of truth for long-running jobs.
- Do not treat a local browser preview as proof that model inference works. Model-dependent features need backend behavior checks as well.
