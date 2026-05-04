

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from models.sa_orm import Count

from annotation.auth import AuthController
from annotation.log import Log, OperationType
from models import SystemLoginLog, SystemOperationLog, UserNotification
from models.notification import NotificationStatus
from schemas.common import BaseResponse
from utils.response import ResponseUtil

dashboardAPI = APIRouter(prefix="/dashboard")


@dashboardAPI.get("/statistics", response_class=JSONResponse, response_model=BaseResponse, summary="Get dashboard statistics")
@Log(title="Get dashboard statistics", operation_type=OperationType.SELECT)
# @Auth(permission_list=["dashboard:btn:statistics", "GET:/dashboard/statistics"])
async def get_dashboard_statistics(
    request: Request,
    current_user: dict = Depends(AuthController.get_current_user)
):
    """
       ?
          ?
    """
    user_type = current_user.get("user_type", 3)
    user_id = current_user.get("id")
    sub_departments = current_user.get("sub_departments", [])
    
    #  # (description)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    
    #  # (description)
    unread_notifications = await UserNotification.filter(
        user_id=user_id,
        is_read=False,
        notification__is_del=False,
        notification__status=NotificationStatus.PUBLISHED
    ).count()
    
    total_notifications = await UserNotification.filter(
        user_id=user_id,
        notification__is_del=False,
        notification__status=NotificationStatus.PUBLISHED
    ).count()
    
    #  # (description)
    if user_type in [0, 1]:
        #  # (description)
        today_logins = await SystemLoginLog.filter(
            is_del=False,
            created_at__range=[today_start, today_end],
            status=1  # 
        ).count()
        
        today_operations = await SystemOperationLog.filter(
            is_del=False,
            created_at__range=[today_start, today_end]
        ).count()
        
    elif user_type == 2:
        #  # (description)
        today_logins = await SystemLoginLog.filter(
            is_del=False,
            user_id__department__id__in=sub_departments,
            created_at__range=[today_start, today_end],
            status=1
        ).count()
        
        today_operations = await SystemOperationLog.filter(
            is_del=False,
            operator__department__id__in=sub_departments,
            created_at__range=[today_start, today_end]
        ).count()
        
    else:
        #  # (description)
        today_logins = await SystemLoginLog.filter(
            is_del=False,
            user_id=user_id,
            created_at__range=[today_start, today_end],
            status=1
        ).count()
        
        today_operations = await SystemOperationLog.filter(
            is_del=False,
            operator_id=user_id,
            created_at__range=[today_start, today_end]
        ).count()

    
    return ResponseUtil.success(data={
        "unreadNotifications": unread_notifications,
        "totalNotifications": total_notifications,
        "todayLogins": today_logins,
        "todayOperations": today_operations
    })


@dashboardAPI.get("/login-statistics", response_class=JSONResponse, response_model=BaseResponse, summary="")
@Log(title="", operation_type=OperationType.SELECT)
# @Auth(permission_list=["dashboard:btn:statistics", "GET:/dashboard/login-statistics"])
async def get_login_statistics(
    request: Request,
    current_user: dict = Depends(AuthController.get_current_user)
):
    """
    
    - 
    -    ?
    - 
    """
    user_type = current_user.get("user_type", 3)
    user_id = current_user.get("id")
    sub_departments = current_user.get("sub_departments", [])
    
    #  # (description)
    if user_type in [0, 1]:
        #  # (description)
        login_logs = SystemLoginLog.filter(is_del=False, status=1)
    elif user_type == 2:
        #  # (description)
        login_logs = SystemLoginLog.filter(
            is_del=False,
            status=1,
            user_id__department__id__in=sub_departments
        )
    else:
        #  # (description)
        login_logs = SystemLoginLog.filter(
            is_del=False,
            status=1,
            user_id=user_id
        )
    
    #  # (description)
    os_stats = await login_logs.annotate(count=Count('id')).group_by('os').values('os', 'count')
    os_distribution = []
    for stat in os_stats:
        if stat['os']:
            os_distribution.append({
                "name": stat['os'],
                "value": stat['count']
            })
    
    #  # (description)
    browser_stats = await login_logs.annotate(count=Count('id')).group_by('browser').values('browser', 'count')
    browser_distribution = []
    for stat in browser_stats:
        if stat['browser']:
            browser_distribution.append({
                "name": stat['browser'],
                "value": stat['count']
            })
    
    #  # (description)
    location_stats = await login_logs.annotate(count=Count('id')).group_by('login_location').values('login_location', 'count')
    location_distribution = []
    for stat in location_stats:
        if stat['login_location']:
            location_distribution.append({
                "name": stat['login_location'],
                "value": stat['count']
            })
    #  # (description)
    location_distribution.sort(key=lambda x: x['value'], reverse=True)
    location_distribution = location_distribution[:10]
    
    return ResponseUtil.success(data={
        "osDistribution": os_distribution,
        "browserDistribution": browser_distribution,
        "locationDistribution": location_distribution
    })


@dashboardAPI.get("/login-trend", response_class=JSONResponse, response_model=BaseResponse, summary="")
@Log(title="", operation_type=OperationType.SELECT)
# @Auth(permission_list=["dashboard:btn:statistics", "GET:/dashboard/login-trend"])
async def get_login_trend(
    request: Request,
    current_user: dict = Depends(AuthController.get_current_user)
):
    """
    ?   ?
    - 
    - 
    - 
    """
    user_type = current_user.get("user_type", 3)
    user_id = current_user.get("id")
    sub_departments = current_user.get("sub_departments", [])
    
    #  # (description)
    today = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    seven_days_ago = today - timedelta(days=6)
    seven_days_ago = seven_days_ago.replace(hour=0, minute=0, second=0, microsecond=0)
    
    #  # (description)
    if user_type in [0, 1]:
        #  # (description)
        login_logs = SystemLoginLog.filter(
            is_del=False,
            status=1,
            created_at__range=[seven_days_ago, today]
        )
    elif user_type == 2:
        #  # (description)
        login_logs = SystemLoginLog.filter(
            is_del=False,
            status=1,
            user_id__department__id__in=sub_departments,
            created_at__range=[seven_days_ago, today]
        )
    else:
        #  # (description)
        login_logs = SystemLoginLog.filter(
            is_del=False,
            status=1,
            user_id=user_id,
            created_at__range=[seven_days_ago, today]
        )
    
    #  # (description)
    all_logs = await login_logs.all()
    
    #  # (description)
    date_dict = {}
    for i in range(7):
        date = seven_days_ago + timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        date_dict[date_str] = {
            "date": date_str,
            "count": 0,
            "locations": {}
        }
    
    #  # (description)
    for log in all_logs:
        date_str = log.created_at.strftime('%Y-%m-%d')
        if date_str in date_dict:
            date_dict[date_str]["count"] += 1
            location = log.login_location or ""
            if location in date_dict[date_str]["locations"]:
                date_dict[date_str]["locations"][location] += 1
            else:
                date_dict[date_str]["locations"][location] = 1
    
    #  # (description)
    dates = []
    login_counts = []
    location_trend = {}
    
    for date_str in sorted(date_dict.keys()):
        data = date_dict[date_str]
        dates.append(date_str)
        login_counts.append(data["count"])
        
        #  # (description)
        for location, count in data["locations"].items():
            if location not in location_trend:
                location_trend[location] = [0] * 7
            day_index = dates.index(date_str)
            location_trend[location][day_index] = count
    
    #  # (description)
    top_locations = sorted(location_trend.items(), key=lambda x: sum(x[1]), reverse=True)[:5]
    location_series = []
    for location, values in top_locations:
        location_series.append({
            "name": location,
            "data": values
        })
    
    return ResponseUtil.success(data={
        "dates": dates,
        "loginCounts": login_counts,
        "locationSeries": location_series
    })


@dashboardAPI.get("/operation-statistics", response_class=JSONResponse, response_model=BaseResponse, summary="")
@Log(title="", operation_type=OperationType.SELECT)
# @Auth(permission_list=["dashboard:btn:statistics", "GET:/dashboard/operation-statistics"])
async def get_operation_statistics(
    request: Request,
    current_user: dict = Depends(AuthController.get_current_user)
):
    """
    
    - 
    - 
    - ?   ?
    """
    user_type = current_user.get("user_type", 3)
    user_id = current_user.get("id")
    sub_departments = current_user.get("sub_departments", [])
    
    #  # (description)
    today = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    seven_days_ago = today - timedelta(days=6)
    seven_days_ago = seven_days_ago.replace(hour=0, minute=0, second=0, microsecond=0)
    
    #  # (description)
    if user_type in [0, 1]:
        #  # (description)
        operation_logs = SystemOperationLog.filter(
            is_del=False,
            created_at__range=[seven_days_ago, today]
        )
    elif user_type == 2:
        #  # (description)
        operation_logs = SystemOperationLog.filter(
            is_del=False,
            operator__department__id__in=sub_departments,
            created_at__range=[seven_days_ago, today]
        )
    else:
        #  # (description)
        operation_logs = SystemOperationLog.filter(
            is_del=False,
            operator_id=user_id,
            created_at__range=[seven_days_ago, today]
        )
    
    #  # (description)
    type_stats = await operation_logs.annotate(count=Count('id')).group_by('operation_type').values('operation_type', 'count')
    type_distribution = []
    #  # (description)
    type_names = {
        0: "",
        1: "",
        2: "",
        3: "",
        4: "   ",
        5: "",
        6: "",
        7: ""
    }
    for stat in type_stats:
        if stat['operation_type'] is not None:
            type_distribution.append({
                "name": type_names.get(stat['operation_type'], f"{stat['operation_type']}"),
                "value": stat['count']
            })
    
    #  # (description)
    module_stats = await operation_logs.annotate(count=Count('id')).group_by('operation_name').values('operation_name', 'count')
    module_distribution = []
    for stat in module_stats:
        if stat['operation_name']:
            module_distribution.append({
                "name": stat['operation_name'],
                "value": stat['count']
            })
    #  # (description)
    module_distribution.sort(key=lambda x: x['value'], reverse=True)
    module_distribution = module_distribution[:10]
    
    #  # (description)
    raw_logs = SystemOperationLog.filter(
        is_del=False,
        created_at__range=[seven_days_ago, today]
    )
    if user_type == 2:
        raw_logs = SystemOperationLog.filter(
            is_del=False,
            operator__department__id__in=sub_departments,
            created_at__range=[seven_days_ago, today]
        )
    elif user_type > 2:
        raw_logs = SystemOperationLog.filter(
            is_del=False,
            operator_id=user_id,
            created_at__range=[seven_days_ago, today]
        )
    all_logs = await raw_logs.all()
    
    #  # (description)
    date_dict = {}
    for i in range(7):
        date = seven_days_ago + timedelta(days=i)
        date_str = date.strftime('%Y-%m-%d')
        date_dict[date_str] = 0
    
    #  # (description)
    for log in all_logs:
        date_str = log.created_at.strftime('%Y-%m-%d')
        if date_str in date_dict:
            date_dict[date_str] += 1
    
    #  # (description)
    dates = sorted(date_dict.keys())
    daily_trend = [date_dict[d] for d in dates]
    
    return ResponseUtil.success(data={
        "dates": dates,
        "typeDistribution": type_distribution,
        "dailyTrend": daily_trend,
        "moduleDistribution": module_distribution
    })
