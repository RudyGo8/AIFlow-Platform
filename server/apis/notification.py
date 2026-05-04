

import json
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Path, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from models.sa_orm import Q

from annotation.auth import AuthController, Auth
from annotation.log import Log, OperationType
from models import SystemNotification, UserNotification, SystemUser
from models.notification import NotificationScope, NotificationStatus
from schemas.notification import CreateNotificationParams, UpdateNotificationParams
from utils.casbin import DepartmentHelper, UserType
from utils.notification import ws_manager, NotificationService
from utils.response import ResponseUtil

notificationAPI = APIRouter(prefix="/notification")

# WebSocket  # (description)
notificationWsAPI = APIRouter(prefix="/notification")


# ==================== WebSocket  # (description)

@notificationWsAPI.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    """WebSocket """
    user_id = None
    try:
        #  # (description)
        from jose import jwt
        from utils.config import config
        from utils.get_redis import RedisKeyConfig
        
        payload = jwt.decode(
            token=token,
            key=config.jwt().secret_key,
            algorithms=[config.jwt().algorithm],
        )
        user_id = payload.get("id")
        session_id = payload.get("session_id")
        
        if not user_id:
            await websocket.close(code=4001, reason="?token")
            return
        
        #  # (description)
        redis = websocket.app.state.redis
        redis_token = await redis.get(f"{RedisKeyConfig.ACCESS_TOKEN.key}:{session_id}")
        if not redis_token:
            await websocket.close(code=4001, reason="Session expired")
            return
        
        await ws_manager.connect(websocket, user_id)
        
        #  # (description)
        notification_service = NotificationService(redis)
        
        #  # (description)
        await websocket.send_json({
            "type": "connected",
            "data": {"message": "WebSocket "}
        })
        
        #  # (description)
        pending = await notification_service.get_pending_notifications(user_id)
        if pending:
            for notification in pending:
                await websocket.send_json(notification)
        
        #  # (description)
        unread_count = await UserNotification.filter(
            user_id=user_id,
            is_read=False,
            notification__is_del=False,
            notification__status=NotificationStatus.PUBLISHED
        ).count()
        
        await websocket.send_json({
            "type": "unread_count",
            "data": {"count": unread_count}
        })
        
        #  # (description)
        while True:
            data = await websocket.receive_text()
            #  # (description)
            if data == "ping":
                await websocket.send_text("pong")
                continue
            
            #  # (description)
            try:
                message = json.loads(data)
                if message.get("type") == "request":
                    await handle_ws_request(websocket, message, user_id, redis)
            except json.JSONDecodeError:
                pass
    
    except WebSocketDisconnect:
        if user_id:
            ws_manager.disconnect(websocket, user_id)
    except Exception as e:
        if user_id:
            ws_manager.disconnect(websocket, user_id)
        try:
            await websocket.close(code=4001, reason=str(e))
        except Exception:
            pass


async def handle_ws_request(websocket: WebSocket, message: dict, user_id: str, redis):
    """ WebSocket """
    import json
    from utils.get_redis import RedisKeyConfig
    
    action = message.get("action")
    request_id = message.get("requestId")
    
    if not action or not request_id:
        return
    
    try:
        if action == "getUserInfo":
            #  # (description)
            user_info_str = await redis.get(f"{RedisKeyConfig.USER_INFO.key}:{user_id}")
            if user_info_str:
                user_info = json.loads(user_info_str)
                await websocket.send_json({
                    "type": "response",
                    "requestId": request_id,
                    "data": user_info
                })
            else:
                await websocket.send_json({
                    "type": "response",
                    "requestId": request_id,
                    "data": {"success": False, "msg": "User info not found"}
                })
        
        elif action == "getUserRoutes":
            #  # (description)
            routes_str = await redis.get(f"{RedisKeyConfig.USER_ROUTES.key}:{user_id}")
            if routes_str:
                routes = json.loads(routes_str)
                await websocket.send_json({
                    "type": "response",
                    "requestId": request_id,
                    "data": routes
                })
            else:
                #  # (description)
                await websocket.send_json({
                    "type": "response",
                    "requestId": request_id,
                    "data": {"success": False, "msg": "Route cache not found"}
                })
        
        else:
            await websocket.send_json({
                "type": "response",
                "requestId": request_id,
                "data": {"success": False, "msg": f": {action}"}
            })
    
    except Exception as e:
        await websocket.send_json({
            "type": "response",
            "requestId": request_id,
            "data": {"success": False, "msg": str(e)}
        })


# ====================  # (description)

@notificationAPI.post("/create", response_class=JSONResponse, summary="")
@Log(title="", operation_type=OperationType.INSERT)
@Auth(permission_list=["notification:btn:add", "POST:/notification/create"])
async def create_notification(
    request: Request,
    params: CreateNotificationParams,
    current_user: dict = Depends(AuthController.get_current_user)
):
    """ """
    user_type = current_user.get("user_type", UserType.NORMAL_USER)
    user_id = current_user.get("id")
    sub_departments = current_user.get("sub_departments", [])
    
    #  # (description)
    if user_type == UserType.NORMAL_USER:
        return ResponseUtil.error(msg="")
    
    #  # (description)
    if user_type == UserType.DEPT_ADMIN:
        if params.scope == NotificationScope.ALL:
            return ResponseUtil.error(msg="   $")
        if params.scope == NotificationScope.DEPARTMENT:
            #  # (description)
            for dept_id in params.scope_ids:
                if dept_id not in sub_departments:
                    return ResponseUtil.error(msg="   ")
    
    #  # (description)
    expire_time = None
    if params.expire_time:
        try:
            expire_time = datetime.fromisoformat(params.expire_time.replace("Z", "+00:00"))
        except Exception:
            pass
    
    notification = await SystemNotification.create(
        title=params.title,
        content=params.content,
        type=params.type,
        scope=params.scope,
        scope_ids=params.scope_ids,
        priority=params.priority,
        expire_time=expire_time,
        status=NotificationStatus.DRAFT,
        creator_id=user_id
    )
    
    return ResponseUtil.success(msg="", data={"id": str(notification.id)})


@notificationAPI.put("/update/{id}", response_class=JSONResponse, summary="")
@Log(title="", operation_type=OperationType.UPDATE)
@Auth(permission_list=["notification:btn:update", "PUT:/notification/update/*"])
async def update_notification(
    request: Request,
    params: UpdateNotificationParams,
    id: str = Path(description="ID"),
    current_user: dict = Depends(AuthController.get_current_user)
):
    """Get notification detail"""
    notification = await SystemNotification.get_or_none(id=id, is_del=False)
    if not notification:
        return ResponseUtil.error(msg="Notification not found")
    
    if notification.status != NotificationStatus.DRAFT:
        return ResponseUtil.error(msg="")
    
    #  # (description)
    user_type = current_user.get("user_type", UserType.NORMAL_USER)
    user_id = current_user.get("id")
    department_id = current_user.get("department_id")
    sub_departments = current_user.get("sub_departments", [])
    
    #  # (description)
    if user_type >= UserType.DEPT_ADMIN:
        #  # (description)
        if str(notification.creator_id) != user_id:
            return ResponseUtil.error(msg="   ")
    
    #  # (description)
    if user_type == UserType.DEPT_ADMIN and params.scope is not None:
        if params.scope == NotificationScope.ALL:
            return ResponseUtil.error(msg="   $")
        if params.scope == NotificationScope.DEPARTMENT and params.scope_ids:
            dept_ids = set([department_id] + sub_departments) if department_id else set(sub_departments)
            for dept_id in params.scope_ids:
                if dept_id not in dept_ids:
                    return ResponseUtil.error(msg="   ")
    
    update_data = params.dict(exclude_none=True)
    if "expire_time" in update_data and update_data["expire_time"]:
        try:
            update_data["expire_time"] = datetime.fromisoformat(
                update_data["expire_time"].replace("Z", "+00:00")
            )
        except ValueError:
            del update_data["expire_time"]
    
    if update_data:
        await notification.update_from_dict(update_data)
        await notification.save()
    
    return ResponseUtil.success(msg="")


@notificationAPI.post("/publish/{id}", response_class=JSONResponse, summary="")
@Log(title="", operation_type=OperationType.UPDATE)
@Auth(permission_list=["notification:btn:publish", "POST:/notification/publish/*"])
async def publish_notification(
    request: Request,
    id: str = Path(description="ID"),
    current_user: dict = Depends(AuthController.get_current_user)
):
    """ """
    notification = await SystemNotification.get_or_none(id=id, is_del=False)
    if not notification:
        return ResponseUtil.error(msg="Notification not found")
    
    if notification.status != NotificationStatus.DRAFT:
        return ResponseUtil.error(msg="")
    
    #  # (description)
    target_user_ids = await _get_target_users(notification)
    
    if not target_user_ids:
        return ResponseUtil.error(msg="No target users found")
    
    #  # (description)
    notification.status = NotificationStatus.PUBLISHED
    notification.publish_time = datetime.now()
    await notification.save()
    
    #  # (description)
    for user_id in target_user_ids:
        await UserNotification.get_or_create(
            notification_id=notification.id,
            user_id=user_id
        )
    
    #  # (description)
    notification_service = NotificationService(request.app.state.redis)
    creator = await SystemUser.get_or_none(id=notification.creator_id)
    creator_name = creator.nickname if creator else ""
    
    result = await notification_service.push_notification(
        notification_id=str(notification.id),
        title=notification.title,
        content=notification.content,
        notification_type=notification.type,
        priority=notification.priority,
        target_user_ids=target_user_ids,
        creator_name=creator_name
    )
    
    return ResponseUtil.success(
        msg="",
        data={
            "total_users": len(target_user_ids),
            "online_count": result["online_count"],
            "offline_count": result["offline_count"]
        }
    )


@notificationAPI.post("/revoke/{id}", response_class=JSONResponse, summary="   ")
@Log(title="   ", operation_type=OperationType.UPDATE)
@Auth(permission_list=["notification:btn:revoke", "POST:/notification/revoke/*"])
async def revoke_notification(
    request: Request,
    id: str = Path(description="ID"),
    current_user: dict = Depends(AuthController.get_current_user)
):
    """ """
    notification = await SystemNotification.get_or_none(id=id, is_del=False)
    if not notification:
        return ResponseUtil.error(msg="Notification not found")
    
    if notification.status != NotificationStatus.PUBLISHED:
        return ResponseUtil.error(msg="   ")
    
    #  # (description)
    user_type = current_user.get("user_type", UserType.NORMAL_USER)
    user_id = current_user.get("id")
    
    if user_type >= UserType.DEPT_ADMIN:
        #  # (description)
        if str(notification.creator_id) != user_id:
            return ResponseUtil.error(msg="      ")
    
    notification.status = NotificationStatus.REVOKED
    await notification.save()
    
    return ResponseUtil.success(msg="   ")


@notificationAPI.delete("/delete/{id}", response_class=JSONResponse, summary="")
@Log(title="", operation_type=OperationType.DELETE)
@Auth(permission_list=["notification:btn:delete", "DELETE:/notification/delete/*"])
async def delete_notification(
    request: Request,
    id: str = Path(description="ID"),
    current_user: dict = Depends(AuthController.get_current_user)
):
    """ """
    notification = await SystemNotification.get_or_none(id=id, is_del=False)
    if not notification:
        return ResponseUtil.error(msg="Notification not found")
    
    #  # (description)
    user_type = current_user.get("user_type", UserType.NORMAL_USER)
    user_id = current_user.get("id")
    
    if user_type >= UserType.DEPT_ADMIN:
        #  # (description)
        if str(notification.creator_id) != user_id:
            return ResponseUtil.error(msg="   ")
    
    notification.is_del = True
    await notification.save()
    
    return ResponseUtil.success(msg="")


@notificationAPI.get("/list", response_class=JSONResponse, summary="")
@Log(title="", operation_type=OperationType.SELECT)
@Auth(permission_list=["notification:btn:list", "GET:/notification/list"])
async def get_notification_list(
    request: Request,
    page: int = Query(default=1, description=""),
    pageSize: int = Query(default=20, description=""),
    type: Optional[int] = Query(default=None, description=""),
    status: Optional[int] = Query(default=None, description="Status"),
    title: Optional[str] = Query(default=None, description="Title"),
    current_user: dict = Depends(AuthController.get_current_user)
):
    """Get notification list"""
    user_type = current_user.get("user_type", UserType.NORMAL_USER)
    user_id = current_user.get("id")
    department_id = current_user.get("department_id")
    sub_departments = current_user.get("sub_departments", [])
    
    #  # (description)
    base_filter = Q(is_del=False)
    
    if type is not None:
        base_filter &= Q(type=type)
    if status is not None:
        base_filter &= Q(status=status)
    if title:
        base_filter &= Q(title__icontains=title)
    
    #  # (description)
    if user_type == UserType.SUPER_ADMIN:
        #  # (description)
        pass
    elif user_type == UserType.ADMIN:
        #  # (description)
        pass
    elif user_type == UserType.DEPT_ADMIN:
        #  # (description)
        dept_ids = set([department_id] + sub_departments) if department_id else set(sub_departments)
        
        #  # (description)
        scope_filter = Q(creator_id=user_id) | Q(scope=NotificationScope.ALL)
        base_filter &= scope_filter
        
        #  # (description)
        #  # (description)
    else:
        #  # (description)
        base_filter &= Q(creator_id=user_id)
    
    #  # (description)
    if user_type == UserType.DEPT_ADMIN:
        #  # (description)
        dept_ids = set([department_id] + sub_departments) if department_id else set(sub_departments)
        managed_user_ids = set()
        if dept_ids:
            users_in_depts = await SystemUser.filter(
                is_del=False, 
                department_id__in=list(dept_ids)
            ).values_list("id", flat=True)
            managed_user_ids = set(str(u) for u in users_in_depts)
        
        #  # (description)
        all_notifications = await SystemNotification.filter(
            Q(is_del=False) & 
            (Q(type=type) if type is not None else Q()) &
            (Q(status=status) if status is not None else Q()) &
            (Q(title__icontains=title) if title else Q())
        ).order_by("-created_at").prefetch_related("creator").values(
            "id", "title", "content", "type", "scope", "scope_ids",
            "status", "priority", "publish_time", "expire_time",
            "created_at", "updated_at",
            creator_id="creator_id",
            creator_name="creator__nickname"
        )
        
        # Python  # (description)
        filtered_result = []
        for n in all_notifications:
            #  # (description)
            if str(n.get("creator_id")) == user_id:
                filtered_result.append(n)
                continue
            #  # (description)
            if n.get("scope") == NotificationScope.ALL:
                filtered_result.append(n)
                continue
            #  # (description)
            if n.get("scope") == NotificationScope.DEPARTMENT:
                n_scope_ids = n.get("scope_ids") or []
                if any(str(dept_id) in [str(s) for s in n_scope_ids] for dept_id in dept_ids):
                    filtered_result.append(n)
                continue
            #  # (description)
            if n.get("scope") == NotificationScope.USER:
                n_scope_ids = n.get("scope_ids") or []
                if any(str(s) in managed_user_ids for s in n_scope_ids):
                    filtered_result.append(n)
                continue
        
        total = len(filtered_result)
        result = filtered_result[(page - 1) * pageSize: page * pageSize]
    else:
        total = await SystemNotification.filter(base_filter).count()
        result = await SystemNotification.filter(base_filter).order_by("-created_at").offset(
            (page - 1) * pageSize
        ).limit(pageSize).prefetch_related("creator").values(
            "id", "title", "content", "type", "scope", "scope_ids",
            "status", "priority", "publish_time", "expire_time",
            "created_at", "updated_at",
            creator_id="creator_id",
            creator_name="creator__nickname"
        )
    
    return ResponseUtil.success(data={
        "result": result,
        "total": total,
        "page": page,
        "pageSize": pageSize
    })


@notificationAPI.get("/info/{id}", response_class=JSONResponse, summary="")
@Log(title="", operation_type=OperationType.SELECT)
async def get_notification_info(
    request: Request,
    id: str = Path(description="ID"),
    current_user: dict = Depends(AuthController.get_current_user)
):
    """ """
    notification = await SystemNotification.get_or_none(
        id=id, is_del=False
    ).prefetch_related("creator")
    
    if not notification:
        return ResponseUtil.error(msg="Notification not found")
    
    #  # (description)
    user_type = current_user.get("user_type", UserType.NORMAL_USER)
    user_id = current_user.get("id")
    department_id = current_user.get("department_id")
    sub_departments = current_user.get("sub_departments", [])
    
    #  # (description)
    can_view = False
    if user_type <= UserType.ADMIN:
        #  # (description)
        can_view = True
    elif user_type == UserType.DEPT_ADMIN:
        #  # (description)
        if str(notification.creator_id) == user_id:
            can_view = True
        elif notification.scope == NotificationScope.ALL:
            can_view = True
        elif notification.scope == NotificationScope.DEPARTMENT:
            dept_ids = set([department_id] + sub_departments) if department_id else set(sub_departments)
            n_scope_ids = notification.scope_ids or []
            if any(str(dept_id) in [str(s) for s in n_scope_ids] for dept_id in dept_ids):
                can_view = True
        elif notification.scope == NotificationScope.USER:
            #  # (description)
            dept_ids = set([department_id] + sub_departments) if department_id else set(sub_departments)
            if dept_ids:
                users_in_depts = await SystemUser.filter(
                    is_del=False, 
                    department_id__in=list(dept_ids)
                ).values_list("id", flat=True)
                managed_user_ids = set(str(u) for u in users_in_depts)
                n_scope_ids = notification.scope_ids or []
                if any(str(s) in managed_user_ids for s in n_scope_ids):
                    can_view = True
    else:
        #  # (description)
        if str(notification.creator_id) == user_id:
            can_view = True
    
    if not can_view:
        return ResponseUtil.error(msg="      ")
    
    #  # (description)
    total_count = await UserNotification.filter(notification_id=id).count()
    read_count = await UserNotification.filter(notification_id=id, is_read=True).count()
    
    return ResponseUtil.success(data={
        "id": str(notification.id),
        "title": notification.title,
        "content": notification.content,
        "type": notification.type,
        "scope": notification.scope,
        "scope_ids": notification.scope_ids,
        "status": notification.status,
        "priority": notification.priority,
        "publish_time": notification.publish_time,
        "expire_time": notification.expire_time,
        "created_at": notification.created_at,
        "updated_at": notification.updated_at,
        "creator_id": str(notification.creator_id) if notification.creator_id else None,
        "creator_name": notification.creator.nickname if notification.creator else None,
        "statistics": {
            "total": total_count,
            "read": read_count,
            "unread": total_count - read_count
        }
    })


# ====================  # (description)

@notificationAPI.get("/my/list", response_class=JSONResponse, summary="")
async def get_my_notifications(
    request: Request,
    page: int = Query(default=1, description=""),
    pageSize: int = Query(default=20, description=""),
    is_read: Optional[bool] = Query(default=None, description=""),
    type: Optional[int] = Query(default=None, description=""),
    current_user: dict = Depends(AuthController.get_current_user)
):
    """   """
    user_id = current_user.get("id")
    
    #  # (description)
    base_filter = Q(user_id=user_id) & Q(notification__is_del=False) & Q(notification__status=NotificationStatus.PUBLISHED)
    
    if is_read is not None:
        base_filter &= Q(is_read=is_read)
    if type is not None:
        base_filter &= Q(notification__type=type)
    
    #  # (description)
    expire_filter = Q(notification__expire_time__isnull=True) | Q(notification__expire_time__gt=datetime.now())
    
    final_filter = base_filter & expire_filter
    
    total = await UserNotification.filter(final_filter).count()
    
    result = await UserNotification.filter(final_filter).order_by(
        "-created_at"
    ).offset((page - 1) * pageSize).limit(pageSize).prefetch_related(
        "notification", "notification__creator"
    ).values(
        "id", "is_read", "read_time", "created_at",
        notification_id="notification_id",
        title="notification__title",
        content="notification__content",
        notification_type="notification__type",
        priority="notification__priority",
        publish_time="notification__publish_time",
        creator_name="notification__creator__nickname"
    )
    
    return ResponseUtil.success(data={
        "result": result,
        "total": total,
        "page": page,
        "pageSize": pageSize
    })


@notificationAPI.post("/my/read/{id}", response_class=JSONResponse, summary="")
async def mark_notification_read(
    request: Request,
    id: str = Path(description="   ID"),
    current_user: dict = Depends(AuthController.get_current_user)
):
    """Mark notification as read"""
    user_id = current_user.get("id")
    
    user_notification = await UserNotification.get_or_none(
        id=id, user_id=user_id
    )
    
    if not user_notification:
        return ResponseUtil.error(msg="Notification not found")
    
    if not user_notification.is_read:
        user_notification.is_read = True
        user_notification.read_time = datetime.now()
        await user_notification.save()
        
        #  # (description)
        notification_service = NotificationService(request.app.state.redis)
        await notification_service.decrement_unread_count(user_id)
    
    return ResponseUtil.success(msg="")


@notificationAPI.post("/my/read-all", response_class=JSONResponse, summary="   ")
async def mark_all_read(
    request: Request,
    current_user: dict = Depends(AuthController.get_current_user)
):
    """Mark all notifications as read"""
    user_id = current_user.get("id")
    
    count = await UserNotification.filter(
        user_id=user_id, is_read=False
    ).update(is_read=True, read_time=datetime.now())
    
    #  # (description)
    notification_service = NotificationService(request.app.state.redis)
    await notification_service.reset_unread_count(user_id)
    
    return ResponseUtil.success(msg=f"Marked {count} notifications as read")


@notificationAPI.get("/my/unread-count", response_class=JSONResponse, summary="")
async def get_unread_count(
    request: Request,
    current_user: dict = Depends(AuthController.get_current_user)
):
    """ """
    user_id = current_user.get("id")
    
    #  # (description)
    count = await UserNotification.filter(
        user_id=user_id,
        is_read=False,
        notification__is_del=False,
        notification__status=NotificationStatus.PUBLISHED
    ).count()
    
    #  # (description)
    notification_service = NotificationService(request.app.state.redis)
    if count > 0:
        await request.app.state.redis.set(
            f"{notification_service.UNREAD_COUNT_KEY}:{user_id}",
            count
        )
    else:
        await request.app.state.redis.delete(
            f"{notification_service.UNREAD_COUNT_KEY}:{user_id}"
        )
    
    return ResponseUtil.success(data={"count": count})


@notificationAPI.get("/my/pending", response_class=JSONResponse, summary="Get pending notifications (HTTP)")
async def get_pending_notifications(
    request: Request,
    current_user: dict = Depends(AuthController.get_current_user)
):
    """Get pending notifications (HTTP fallback)"""
    user_id = current_user.get("id")
    
    notification_service = NotificationService(request.app.state.redis)
    notifications = await notification_service.get_pending_notifications(user_id)
    
    return ResponseUtil.success(data={"notifications": notifications})


# ====================  # (description)

async def _get_target_users(notification: SystemNotification) -> List[str]:
    """Get target user list for notification"""
    if notification.scope == NotificationScope.ALL:
        #  # (description)
        users = await SystemUser.filter(is_del=False, status=1).values_list("id", flat=True)
        return [str(u) for u in users]
    
    elif notification.scope == NotificationScope.DEPARTMENT:
        #  # (description)
        all_dept_ids = set()
        for dept_id in notification.scope_ids:
            child_ids = await DepartmentHelper.get_child_department_ids(dept_id)
            all_dept_ids.update(child_ids)
        
        users = await SystemUser.filter(
            is_del=False, status=1, department_id__in=list(all_dept_ids)
        ).values_list("id", flat=True)
        return [str(u) for u in users]
    
    elif notification.scope == NotificationScope.USER:
        #  # (description)
        return notification.scope_ids
    
    return []
