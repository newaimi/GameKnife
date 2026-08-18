# Contributing to GameKnife

## Core Principles

- Keep the Community edition local and login-free.
- Public processors, workflows, and editors must not import concrete account, organization, project, permission, billing, or audit implementations.
- Before adding a tool capability, check `packages/image-workflows`, `services/workflows`, and `services/processors` for an existing reusable implementation.
- Model-dependent jobs must check installation status before creation and may read only local model caches during inference.
- Database records are the source of truth for deletions. Disk cleanup remains a best-effort follow-up.

## Commits

Write commit messages in English and follow Conventional Commits.

## Verification

For backend changes, run:

```powershell
python -m pytest -q apps\community-api\tests services-extra\stable-audio-sfx\tests
```

For frontend changes, run:

```powershell
npm run build
```
