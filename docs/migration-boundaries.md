# GameKnife 迁移边界

本文件记录开源核心和商用外壳的边界。Community 仓库只保留无登录本地工作区能力；登录、注册、用户、组织、项目、权限、计费和审计只在商用仓库维护。

公共处理器、公共工作流和公共编辑器只依赖请求上下文、仓储接口和存储接口，不读取真实用户表、项目表、计费表或审计表。

## 公共包边界

- `packages/image-workflows` 承载工具页面、任务轮询、结果展示和保存流程。
- `packages/editor-core` 承载手动编辑画布、选区、画笔和 PNG 导出。
- `services/workflows` 承载后端编排，`services/processors` 承载模型和图像处理适配。
- Community 入口注入匿名主体、本地工作区、SQLite repository 和本地文件存储。
- Commercial 入口注入真实用户、项目工作区、RBAC、MySQL repository 和企业存储。

公共包不能通过隐藏参数读取登录态、组织、项目、计费或审计数据。需要商业差异时，只能通过 `RequestContext`、repository 接口或 storage provider 注入。
