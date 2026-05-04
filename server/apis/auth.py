
import json
import uuid
from datetime import timedelta, datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends
from starlette.responses import JSONResponse
from models.sa_orm import Q

from annotation.auth import CustomOAuth2PasswordRequestForm, AuthController
from annotation.log import Log, OperationType
from models import (
    SystemUser,
    SystemDepartment,
    SystemUserRole,
    SystemLoginLog,
    SystemPermission,
)
from schemas.common import BaseResponse
from schemas.auth import (
    GetCaptchaResponse,
    LoginResponse,
    LoginParams,
    GetEmailCodeParams,
)
from schemas.user import RegisterUserParams, GetUserInfoResponse
from utils.captcha import CaptchaUtil
from utils.get_redis import RedisKeyConfig
from utils.log import logger
from utils.mail import Email
from utils.password import PasswordUtil
from utils.response import ResponseUtil
from annotation.log import _request_meta
from utils.ip2region_util import get_ip_location
from utils.config import config
from utils.notification import NotificationService

authAPI = APIRouter(prefix="/auth")


def get_login_meta(request: Request) -> dict:
    """Build request metadata"""
    meta = _request_meta(request)
    #  # (description)
    meta["location"] = (
        get_ip_location(meta["ip"])
        if config.app().ip_location_enabled
        else "IP"
    )
    return meta


async def safe_create_login_log(**kwargs) -> None:
    """Do not let login-log persistence failures break the login flow."""
    try:
        await SystemLoginLog.create(**kwargs)
    except Exception:
        logger.exception("Failed to persist system login log")


@authAPI.get(
    "/captcha",
    response_class=JSONResponse,
    response_model=GetCaptchaResponse,
    summary="Get captcha",
)
async def get_captcha(request: Request):
    captcha_enabled = (
        True
        if await request.app.state.redis.get(
            f"{RedisKeyConfig.SYSTEM_CONFIG.key}:account_captcha_enabled"
        )
        == "true"
        else False
    )
    register_enabled = (
        True
        if await request.app.state.redis.get(
            f"{RedisKeyConfig.SYSTEM_CONFIG.key}:account_register_enabled"
        )
        == "true"
        else False
    )
    if captcha_enabled:
        captcha_type = (
            await request.app.state.redis.get(
                f"{RedisKeyConfig.SYSTEM_CONFIG.key}:account_captcha_type"
            )
            if await request.app.state.redis.get(
                f"{RedisKeyConfig.SYSTEM_CONFIG.key}:account_captcha_type"
            )
            else "0"  # 
        )
        captcha_result = await CaptchaUtil.create_captcha(captcha_type)
        session_id = str(uuid.uuid4())
        captcha = captcha_result[0]
        result = captcha_result[-1]
        await request.app.state.redis.set(
            f"{RedisKeyConfig.CAPTCHA_CODES.key}:{session_id}",
            result,
            ex=timedelta(minutes=2),
        )
        logger.info(f"Captcha session: {session_id}")

        return ResponseUtil.success(
            data={
                "uuid": session_id,
                "captcha": captcha,
                "captcha_enabled": captcha_enabled,
                "register_enabled": register_enabled,
                "captcha_type": captcha_type,  # 0=1=
            }
        )
    else:
        return ResponseUtil.success(
            data={
                "uuid": None,
                "captcha": None,
                "captcha_enabled": captcha_enabled,
                "register_enabled": register_enabled,
                "captcha_type": "0",  #    
            }
        )


@authAPI.post("/login", response_class=JSONResponse, summary="")
@Log(operation_type=OperationType.GRANT, title="", log_type="login")
async def login(request: Request, params: CustomOAuth2PasswordRequestForm = Depends()):
    user = LoginParams(
        username=params.username,
        password=params.password,
        loginDays=params.login_days,
        code=params.code,
        uuid=params.uuid,
    )
    captcha_enabled = (
        True
        if await request.app.state.redis.get(
            f"{RedisKeyConfig.SYSTEM_CONFIG.key}:account_captcha_enabled"
        )
        == "true"
        else False
    )
    #  # (description)
    request_from_swagger = (
        request.headers.get("referer").endswith("docs")
        if request.headers.get("referer")
        else False
    )
    request_from_redoc = (
        request.headers.get("referer").endswith("redoc")
        if request.headers.get("referer")
        else False
    )

    #  # (description)
    if captcha_enabled and not request_from_redoc and not request_from_swagger:
        result = await CaptchaUtil.verify_code(
            request, code=user.code, session_id=user.uuid
        )
        if not result["status"]:
            return ResponseUtil.error(msg=result["msg"])
    if user := await SystemUser.get_or_none(
        Q(username=params.username)
        | Q(email=params.username)
        | Q(phone=params.username),
        is_del=False,
    ):
        if await PasswordUtil.verify_password(
            plain_password=params.password, hashed_password=user.password
        ):
            userInfo = await AuthController.get_user_info(user.id)
            logger.info(f"   {user.username}")
            session_id = uuid.uuid4().__str__()
            
            #  # (description)
            request_meta = get_login_meta(request)
            await safe_create_login_log(
                user_id=user,
                login_ip=request_meta["ip"],
                login_location=request_meta["location"],
                browser=request_meta["browser"],
                os=request_meta["os"],
                status=1,  # 
                session_id=session_id
            )
            # JWT Token  # (description)
            token_data = {
                "id": user.id.__str__(),
                "username": user.username,
                "session_id": session_id,
            }
            accessToken = await AuthController.create_token(
                data=token_data,
                expires_delta=timedelta(minutes=params.login_days * 24 * 60),
            )
            expiresTime = (
                datetime.now() + timedelta(minutes=params.login_days * 24 * 60)
            ).timestamp()
            refreshToken = await AuthController.create_token(
                data=token_data,
                expires_delta=timedelta(minutes=(params.login_days * 24 + 2) * 60),
            )
            await request.app.state.redis.set(
                f"{RedisKeyConfig.ACCESS_TOKEN.key}:{session_id}",
                accessToken,
                ex=timedelta(minutes=params.login_days * 24 * 60),
            )
            #  # (description)

            userInfoStr = json.dumps(userInfo, ensure_ascii=False, default=str)
            await request.app.state.redis.set(
                f"{RedisKeyConfig.USER_INFO.key}:{user.id.__str__()}",
                userInfoStr,
                ex=timedelta(
                    minutes=params.login_days * 24 * 60
                ),  # oken?
            )
            
            #  # (description)
            notification_service = NotificationService(request.app.state.redis)
            await notification_service.send_login_notification(
                user_id=user.id.__str__(),
                username=user.username,
                login_ip=request_meta["ip"],
                login_location=request_meta["location"],
                browser=request_meta["browser"],
                os=request_meta["os"]
            )
            
            if request_from_swagger or request_from_redoc:
                return {
                    "access_token": accessToken,
                    "token_type": "Bearer",
                    "expires_in": expiresTime,
                }
            else:
                return ResponseUtil.success(
                    data={"accessToken": accessToken, "refreshToken": refreshToken}
                )
        else:
            #  # (description)
            request_meta = get_login_meta(request)
            await safe_create_login_log(
                user_id=user,
                login_ip=request_meta["ip"],
                login_location=request_meta["location"],
                browser=request_meta["browser"],
                os=request_meta["os"],
                status=0,  # 
                session_id=None
            )
            return ResponseUtil.error(msg="   ")
    else:
        #  # (description)
        logger.warning(f"Login failed for nonexistent user: {params.username}")
        return ResponseUtil.error(msg="Invalid username or password!")
        request_meta = get_login_meta(request)
        await safe_create_login_log(
            user_id=None,
            login_ip=request_meta["ip"],
            login_location=request_meta["location"],
            browser=request_meta["browser"],
            os=request_meta["os"],
            status=0,  # 
            session_id=None
        )
        return ResponseUtil.error(msg="   ")


@authAPI.post(
    "/register",
    response_class=JSONResponse,
    response_model=LoginResponse,
    summary="      ",
)
async def register(request: Request, params: RegisterUserParams):
    async def _create_user(
        params: RegisterUserParams,
        department: Optional[SystemDepartment],
    ) -> Optional[SystemUser]:
        """Create user"""
        hashed_pwd = await PasswordUtil.get_password_hash(
            input_password=params.password
        )
        return await SystemUser.create(
            username=params.username,
            password=hashed_pwd,
            nickname=params.nickname,
            phone=params.phone,
            email=params.email,
            gender=params.gender,
            department=department,
            status=params.status,
        )

    redis = request.app.state.redis
    key = f"{RedisKeyConfig.SYSTEM_CONFIG.key}"

    #  # (description)
    (
        captcha_enabled,
        register_enabled,
        default_dept_id,
        default_role_id,
    ) = await redis.mget(
        f"{key}:account_captcha_enabled",
        f"{key}:account_register_enabled",
        f"{key}:default_department_id",
        f"{key}:default_role_id",
    )
    captcha_enabled = captcha_enabled == "true"
    register_enabled = register_enabled == "true"

    if not register_enabled:
        return ResponseUtil.error(msg="   ")

    #  # (description)
    if captcha_enabled:
        result = await Email.verify_code(
            request, username=params.username, mail=params.email, code=params.code
        )
        if not result["status"]:
            return ResponseUtil.error(msg=result["msg"])

    #  # (description)
    if await SystemUser.get_or_none(username=params.username, is_del=False):
        return ResponseUtil.error(msg="Registration failed, user already exists")

    #  # (description)
    dept_id = params.department_id or default_dept_id
    department: Optional[SystemDepartment] = None
    if dept_id and (
        department := await SystemDepartment.get_or_none(id=dept_id, is_del=False)
    ):
        pass  # ?
    #  # (description)

    #  # (description)
    user = await _create_user(params, department)
    if not user:
        return ResponseUtil.error(msg="Registration failed")

    #  # (description)
    if default_role_id:
        await SystemUserRole.create(user_id=user.id, role_id=default_role_id)

    return ResponseUtil.success(msg="Registration successful")


@authAPI.post(
    "/code",
    response_class=JSONResponse,
    response_model=BaseResponse,
    summary="Get email verification code",
)
async def get_code(request: Request, params: GetEmailCodeParams):
    result = await Email.send_email(
        request, username=params.username, title=params.title, mail=params.mail
    )
    if result:
        return ResponseUtil.success(msg="")
    return ResponseUtil.error(msg="      ")


@authAPI.get(
    "/info",
    response_class=JSONResponse,
    response_model=GetUserInfoResponse,
    summary="   ",
)
@Log(title="   ", operation_type=OperationType.SELECT)
async def info(
    request: Request, current_user: dict = Depends(AuthController.get_current_user)
):
 
    return ResponseUtil.success(data=current_user)


@authAPI.get(
    "/routes",
    response_class=JSONResponse,
    response_model=BaseResponse,
    summary="   ",
)
@Log(title="   ", operation_type=OperationType.SELECT)
async def get_user_routes(
    request: Request, current_user: dict = Depends(AuthController.get_current_user)
):
    permission_cache = await request.app.state.redis.get(
        f"{RedisKeyConfig.USER_ROUTES.key}:{current_user['id']}"
    )
    if permission_cache:
        return ResponseUtil.success(data=json.loads(permission_cache))
    uid = current_user.get("id")
    user_type = current_user.get("user_type", 3)

    from utils.casbin import CasbinEnforcer, UserType

    # 超级管理员和管理员直接获取所有菜单/按钮权限
    if user_type in (UserType.SUPER_ADMIN, UserType.ADMIN):
        rolePermissions = await SystemPermission.filter(
            menu_type=0,
            is_del=False
        ).values(
            id="id",
            created_at="created_at",
            updated_at="updated_at",
            menu_type="menu_type",
            parent_id="parent_id",
            component="component",
            name="name",
            title="title",
            path="path",
            icon="icon",
            showBadge="showBadge",
            showTextBadge="showTextBadge",
            isHide="isHide",
            isHideTab="isHideTab",
            link="link",
            isIframe="isIframe",
            keepAlive="keepAlive",
            isFirstLevel="isFirstLevel",
            fixedTab="fixedTab",
            activePath="activePath",
            isFullPage="isFullPage",
            order="order",
            authTitle="authTitle",
            authMark="authMark",
            min_user_type="min_user_type",
        )
        buttonPermissions = await SystemPermission.filter(
            menu_type=1,
            is_del=False
        ).values(
            id="id",
            parent_id="parent_id",
            authTitle="authTitle",
            authMark="authMark",
            min_user_type="min_user_type",
        )
    else:
        user_permissions = await CasbinEnforcer.get_user_permissions(str(uid))
        menu_ids = user_permissions["menus"]

        rolePermissions = []
        if menu_ids:
            rolePermissions = await SystemPermission.filter(
                id__in=menu_ids,
                menu_type=0,
                min_user_type__gte=user_type,
                is_del=False
            ).values(
                id="id",
                created_at="created_at",
                updated_at="updated_at",
                menu_type="menu_type",
                parent_id="parent_id",
                component="component",
                name="name",
                title="title",
                path="path",
                icon="icon",
                showBadge="showBadge",
                showTextBadge="showTextBadge",
                isHide="isHide",
                isHideTab="isHideTab",
                link="link",
                isIframe="isIframe",
                keepAlive="keepAlive",
                isFirstLevel="isFirstLevel",
                fixedTab="fixedTab",
                activePath="activePath",
                isFullPage="isFullPage",
                order="order",
                authTitle="authTitle",
                authMark="authMark",
                min_user_type="min_user_type",
            )

        button_ids = user_permissions["buttons"]
        buttonPermissions = []
        if button_ids:
            buttonPermissions = await SystemPermission.filter(
                id__in=button_ids,
                menu_type=1,
                min_user_type__gte=user_type,
                is_del=False
            ).values(
                id="id",
                parent_id="parent_id",
                authTitle="authTitle",
                authMark="authMark",
                min_user_type="min_user_type",
            )

    async def find_node_recursive(node_id: str, data: list) -> dict:
        """Find node recursively by ID"""
        result = {}
        data = list(filter(lambda x: x.get("menu_type") == 0, data))
        for item in data:
            if item["id"] == node_id:
                children = []
                for child_item in data:
                    if child_item["parent_id"] == node_id:
                        child_node = await find_node_recursive(child_item["id"], data)
                        if child_node:
                            children.append(child_node)
                meta = {
                    k: v
                    for k, v in {
                        "title": item["title"],
                        "order": item["order"],
                        "icon": item["icon"],
                        "showBadge": item["showBadge"],
                        "showTextBadge": item["showTextBadge"],
                        "keepAlive": item["keepAlive"],
                        "isHide": item["isHide"],
                        "isHideTab": item["isHideTab"],
                        "link": item["link"],
                        "isIframe": item["isIframe"],
                        "isFullPage": item["isFullPage"],
                        "fixedTab": item["fixedTab"],
                        "isFirstLevel": item["isFirstLevel"],
                        "minUserType": item.get("min_user_type", 3),
                        "authList": await get_menu_auth_list(
                            item["id"], buttonPermissions, user_type
                        ),
                    }.items()
                    if v is not None
                }
                result = {
                    "name": item["name"],
                    "path": item["path"],
                    "meta": meta,
                    "children": children,
                }
                if item["component"]:
                    result["component"] = (
                        item["component"]
                        .replace(".vue", "")
                        .replace(".ts", "")
                        .replace(".tsx", "")
                        .replace(".js", "")
                        .replace(".jsx", "")
                        .strip()
                    )
                if result["name"] == "":
                    result.pop("name")
                if result["children"] == []:
                    result.pop("children")
                else:
                    result["children"] = sorted(
                        result["children"], key=lambda x: x["meta"]["order"]
                    )
                break
        return result

    async def find_complete_data(data: list) -> list:
        """
           
        :param data: 
        """
        complete_data = []
        root_ids = [item["id"] for item in data if not item["parent_id"]]
        for root_id in root_ids:
            complete_data.append(await find_node_recursive(root_id, data))
        return complete_data

    permissions = await find_complete_data(rolePermissions)

    #  # (description)
    base_routes = await get_base_public_routes()
    all_routes = base_routes + permissions
    
    await request.app.state.redis.set(
        f"{RedisKeyConfig.USER_ROUTES.key}:{current_user['id']}",
        json.dumps(all_routes,ensure_ascii=False,default=str),
        ex=timedelta(minutes=30),
    )
    return ResponseUtil.success(code=200, data=all_routes)


async def get_base_public_routes() -> list:
    """
    
     src/router/routes/modules/base.ts 
    """
    return [
        {
            "name": "Dashboard",
            "path": "/dashboard",
            "component": "/index/index",
            "meta": {
                "title": "menus.dashboard.title",
                "icon": "&#xe721;",
                "order": 1
            },
            "children": [
                {
                    "name": "Console",
                    "path": "/dashboard/console",
                    "component": "/dashboard/console",
                    "meta": {
                        "title": "menus.dashboard.console",
                        "icon": "&#xe721;",
                        "keepAlive": False,
                        "fixedTab": True
                    }
                }
            ]
        },
        {
            "name": "UserCenter_",
            "path": "/user-center",
            "component": "/index/index",
            "meta": {
                "title": "menus.system.userCenter",
                "icon": "&#xe6bd;",
                "order": 999
            },
            "children": [
                {
                    "name": "UserCenter",
                    "path": "/user-center",
                    "component": "/user-center",
                    "meta": {
                        "title": "menus.system.userCenter",
                        "keepAlive": False,
                        "isHide": True
                    }
                }
            ]
        },
        {
            "name": "PersonalLoginRecord_",
            "path": "/personal-login-record",
            "component": "/index/index",
            "meta": {
                "title": "menus.personalLoginRecord.title",
                "icon": "&#xe6ce;",
                "order": 999
            },
            "children": [
                {
                    "name": "PersonalLoginRecord",
                    "path": "/personal-login-record",
                    "component": "/personal-login-record/index",
                    "meta": {
                        "title": "menus.personalLoginRecord.title",
                        "icon": "&#xe6ce;",
                        "keepAlive": False,
                        "isHide": True
                    }
                }
            ]
        },
        {
            "name": "PersonalOperationRecord_",
            "path": "/personal-operation-record",
            "component": "/index/index",
            "meta": {
                "title": "menus.personalOperationRecord.title",
                "icon": "&#xe6df;",
                "order": 999
            },
            "children": [
                {
                    "name": "PersonalOperationRecord",
                    "path": "/personal-operation-record",
                    "component": "/personal-operation-record/index",
                    "meta": {
                        "title": "menus.personalOperationRecord.title",
                        "icon": "&#xe6df;",
                        "keepAlive": False,
                        "isHide": True
                    }
                }
            ]
        },
        {
            "name": "MyNotification_",
            "path": "/my-notification",
            "component": "/index/index",
            "meta": {
                "title": "menus.myNotification.title",
                "icon": "&#xe6c2;",
                "order": 999
            },
            "children": [
                {
                    "name": "MyNotification",
                    "path": "/my-notification",
                    "component": "/my-notification/index",
                    "meta": {
                        "title": "menus.myNotification.title",
                        "icon": "&#xe6c2;",
                        "keepAlive": False,
                        "isHide": True
                    }
                }
            ]
        },
        {
            "name": "Rag",
        "path": "/rag",
        "component": "/index/index",
        "meta": {
            "title": "menus.rag.title",
            "icon": "🤖",
            "order": 10
        },
        "children": [
            {
                "name": "RagChat",
                "path": "/rag/chat",
                "component": "/rag/chat/index",
                "meta": {
                    "title": "menus.rag.chat",
                    "icon": "&#xe6c2;",
                    "keepAlive": True
                }
            },
            {
                "name": "RagDocuments",
                "path": "/rag/documents",
                "component": "/rag/documents/index",
                "meta": {
                    "title": "menus.rag.documents",
                    "icon": "&#xe727;",
                    "keepAlive": False
                }
            }
        ]
    }
]


async def get_menu_auth_list(menu_id: str, button_permissions: list, user_type: int = 3) -> list:
    """
       
    :param menu_id: ID
    :param button_permissions: ?
    :param user_type:    
    :return: 
    """
    auth_list = []
    for perm in button_permissions:
        if str(perm.get("parent_id")) == str(menu_id):
            #  # (description)
            min_required = perm.get("min_user_type", 3)
            if user_type <= min_required:  #    ?
                if perm.get("authTitle") and perm.get("authMark"):
                    auth_list.append({
                        "title": perm["authTitle"], 
                        "authMark": perm["authMark"],
                        "minUserType": min_required
                    })
    return auth_list


@authAPI.post(
    "/logout",
    response_class=JSONResponse,
    response_model=BaseResponse,
    summary="   ",
)
@Log(title="Logout", operation_type=OperationType.GRANT)
async def logout(request: Request, status: bool = Depends(AuthController.logout)):
    if status:
        return ResponseUtil.success(data="")
    return ResponseUtil.error(data="Logout failed")


@authAPI.post(
    "/refreshToken",
    response_class=JSONResponse,
    response_model=LoginResponse,
    summary="token",
)
@Log(title="token", operation_type=OperationType.GRANT)
async def refresh_token(
    request: Request, current_user: dict = Depends(AuthController.get_current_user)
):
    session_id = uuid.uuid4().__str__()
    accessToken = await AuthController.create_token(
        data={
            "user": current_user,
            "id": current_user.get("id"),
            "session_id": session_id,
        },
        expires_delta=timedelta(minutes=2 * 24 * 60),
    )
    expiresTime = (datetime.now() + timedelta(minutes=2 * 24 * 60)).timestamp()
    refreshToken = await AuthController.create_token(
        data={
            "user": current_user,
            "id": current_user.get("id"),
            "session_id": session_id,
        },
        expires_delta=timedelta(minutes=(4 * 24 + 2) * 60),
    )
    return ResponseUtil.success(
        data={
            "accessToken": accessToken,
            "refreshToken": refreshToken,
            "expiresTime": expiresTime,
        }
    )
