
from fastapi import FastAPI

from middlewares.cors import add_cors_middleware
from middlewares.gzip import add_gzip_middleware
from middlewares.casbin import add_casbin_middleware


def handle_middleware(app: FastAPI):
    """
    全局中间件处理
    """
    # 加载跨域中间件
    add_cors_middleware(app)
    # 加载gzip压缩中间件
    add_gzip_middleware(app)
    # 加载Casbin权限中间件
    add_casbin_middleware(app)
