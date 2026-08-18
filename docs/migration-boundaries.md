# GameKnife Public Code Boundaries

This document defines the responsibilities of public code in the open source repository. The Community applications assemble a login-free local workspace backed by SQLite and local file storage. Accounts, organizations, projects, billing, and auditing are outside the Community application scope.

The separate commercial repository is a downstream consumer of these public packages. Public processors, workflows, and editors depend only on request-context, repository, and storage interfaces. They do not read downstream application tables or implementation modules.

## Public Package Boundaries

- `packages/image-workflows` owns tool pages, job polling, result presentation, and save flows.
- `packages/editor-core` owns the manual-edit canvas, selections, brushes, and PNG export.
- `services/workflows` owns backend orchestration, while `services/processors` owns model and image-processing adapters.
- `apps/community-web` and `apps/community-api` inject the anonymous principal, local workspace, SQLite repository, and local file storage.
- Community model caches default to `storage/models/*`. Installation state is isolated by local workspace and does not read the machine-wide Hugging Face cache.
- Other application entry points may inject their own principal, workspace, permission, repository, and storage provider implementations through the public interfaces.

Downstream differences must be injected explicitly through `RequestContext`, repository interfaces, or storage providers. Public packages must not read a caller's authentication state or business data through hidden parameters.
