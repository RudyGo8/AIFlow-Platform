

import asyncio
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path
from utils.config import config
from utils.database import init_db, close_db
from utils.get_redis import RedisUtil
from utils.casbin import CasbinEnforcer
from utils.dynamic_config import init_dynamic_config
from apis import register_api
from exceptions.handle import handle_exception
from middlewares.handle import handle_middleware

# 创建 FastAPI 实例
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 启动时初始化，关闭时清理"""
    print(f"\n[INIT] {config.app().name} 开始初始化...")

    # 1. 连接 Redis
    print("  - 连接 Redis...")
    app.state.redis = await RedisUtil.create_redis_connection()

    # 2. 初始化数据库
    print("  - 初始化数据库...")
    await init_db()
    await RedisUtil.init_system_config(app.state.redis)

    # 3. 加载动态配置
    print("  - 加载动态配置...")
    dynamic_config = init_dynamic_config(app.state.redis)
    await dynamic_config.init_default_configs()
    await dynamic_config.load_all_to_redis()
    app.state.dynamic_config = dynamic_config

    # 4. 初始化 Casbin 权限
    print("  - 初始化 Casbin 权限...")
    await CasbinEnforcer.init(app.state.redis)

    print(f"\n[OK] {config.app().name} 启动完成!\n")

    yield  # 应用运行中

    # 关闭时清理
    print("\n[SHUTDOWN] 关闭应用中...")
    await close_db()
    await RedisUtil.close_redis_connection(app.state.redis)
    print("[OK] 已关闭")


app = FastAPI(
    title=config.app().name,
    description=f'{config.app().name}接口文档',
    version=config.app().version,
    lifespan=lifespan,
    openapi_url="/openapi.json" if config.app().api_status_enabled else None,
    docs_url=None,
    redoc_url=None,
)

# 注册中间件
handle_middleware(app)

# 注册异常处理
handle_exception(app)

# 注册 API 路由
register_api(app)

# 挂载静态资源
assets_path = Path(__file__).parent / "assets"
if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")
    app.mount("/api/assets", StaticFiles(directory=str(assets_path)), name="api_assets")

if __name__ == "__main__":
    print(f"\n{'=' * 60}")
    print(f"  START: {config.app().name}")
    print(f"  URL:   http://localhost:{config.app().port}")
    print(f"{'=' * 60}\n")

    uvicorn.run(
        app=app,
        host=config.app().host,
        port=config.app().port,
    )
