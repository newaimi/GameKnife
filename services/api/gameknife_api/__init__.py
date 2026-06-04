from __future__ import annotations


__all__ = ["create_community_app"]


def create_community_app(*args, **kwargs):
    # 包初始化阶段不能提前导入 app 和 routes，原因是 services/workflows 会复用 API 内已有的 job 执行函数。
    # 这里延迟到真正创建应用时再导入，避免工作流测试导入包时触发路由和工作流互相加载。
    from .app import create_community_app as factory

    return factory(*args, **kwargs)
