# GameKnife 贡献说明

## 基本原则

- Community 保持无登录本地工作区。
- 公共处理器、公共工作流和公共编辑器不能导入商用 auth、users、organizations、projects、rbac、billing、audit 模块。
- 新增工具能力先确认 `packages/image-workflows`、`services/workflows`、`services/processors` 是否已有可复用实现。
- 依赖模型的任务必须在创建阶段检查安装状态，推理阶段只能读取本地缓存。
- 数据库和文件删除以数据库记录为准，磁盘清理按尽力执行。

## 提交

提交信息使用 Conventional Commits。

## 验证

后端改动运行：

```powershell
conda run -n codex python -m pytest -q apps\community-api\tests services-extra\stable-audio-sfx\tests
```

前端改动运行：

```powershell
npm run build
```
