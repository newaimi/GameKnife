# GameKnife Community

GameKnife Community 是无登录的本地游戏素材处理工具箱。当前仓库承载开源核心、Community Web、Community API、公共前端包和公共后端包。

## 开发命令

```powershell
npm install
npm run build
```

```powershell
conda run -n codex python -m pip install -e ".[dev]"
conda run -n codex python -m uvicorn community_api.main:app --host 0.0.0.0 --port 8000
```

## Community 默认上下文

- 主体：`anonymous`
- 工作区：`local`
- 数据库：`storage/gameknife.sqlite3`
- 文件存储：`storage/assets`

Community API 不读取 Authorization header、登录 Cookie 或本地 token。
