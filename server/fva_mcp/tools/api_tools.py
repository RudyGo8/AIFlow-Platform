

import re
from pathlib import Path
from typing import Dict, Any

# 获取项目根目录
BASE_DIR = Path(__file__).parent.parent.parent
APIS_DIR = BASE_DIR / "apis"
MODELS_DIR = BASE_DIR / "models"
SCHEMAS_DIR = BASE_DIR / "schemas"


def analyze_model_for_api(model_name: str) -> Dict[str, Any]:
    """分析模型，提取API生成所需信息"""
    # 查找对应的模型文件
    model_file = None
    for file_path in MODELS_DIR.glob("*.py"):
        if file_path.name in ["__init__.py", "common.py"]:
            continue
        
        content = file_path.read_text(encoding="utf-8")
        if f"class {model_name}(BaseModel):" in content:
            model_file = file_path
            break
    
    if not model_file:
        return None
    
    content = model_file.read_text(encoding="utf-8")
    
    # 提取模型信息
    class_match = re.search(rf'class\s+{model_name}\(BaseModel\):(.*?)(?=class\s+\w+|$)', content, re.DOTALL)
    if not class_match:
        return None
    
    class_content = class_match.group(1)
    
    # 提取文档字符串
    doc_match = re.search(r'"""(.*?)"""', class_content, re.DOTALL)
    description = doc_match.group(1).strip().split('\n')[0] if doc_match else f"{model_name}模型"
    
    # 提取表名
    table_match = re.search(r'table\s*=\s*"([^"]*)"', class_content)
    table_name = table_match.group(1) if table_match else model_name.lower()
    
    # 提取字段信息
    fields = []
    field_pattern = r'(\w+)\s*=\s*fields\.(\w+)\((.*?)\)'
    field_matches = re.findall(field_pattern, class_content, re.DOTALL)
    
    for field_name, field_type, field_params in field_matches:
        # 解析字段参数
        field_info = {
            "name": field_name,
            "type": field_type,
            "searchable": field_type in ["CharField", "TextField"],  # 字符串字段可搜索
            "filterable": True,  # 大部分字段都可过滤
        }
        
        # 提取描述
        desc_match = re.search(r'description="([^"]*)"', field_params)
        if desc_match:
            field_info["description"] = desc_match.group(1)
        
        fields.append(field_info)
    
    return {
        "name": model_name,
        "description": description,
        "table_name": table_name,
        "fields": fields,
        "file": model_file.name
    }


def generate_api_code(model_info: Dict[str, Any]) -> str:
    """生成API代码"""
    model_name = model_info["name"]
    description = model_info["description"]
    table_name = model_info["table_name"]
    fields = model_info["fields"]
    
    # 生成基础名称
    base_name = model_name.replace('System', '')
    api_name = base_name.lower()
    router_name = f"{api_name}API"
    
    # 生成可搜索字段
    searchable_fields = [f for f in fields if f.get("searchable", False)]
    
    # 文件头部
    code = f"""# _*_ coding : UTF-8 _*_
# @Time : {__import__('datetime').datetime.now().strftime('%Y/%m/%d %H:%M')}
# @Author : sonder
# @File : {api_name}.py
# @Comment : {description} API - 使用 Casbin 管理权限

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Request, Depends, Path, Query
from starlette.responses import JSONResponse

from models import {model_name}
from schemas.common import BaseResponse, DeleteListParams
from schemas.{api_name} import Add{base_name}Params, Update{base_name}Params, Get{base_name}InfoResponse, Get{base_name}ListResponse
from utils.casbin import CasbinEnforcer, DataScope
from utils.get_redis import RedisKeyConfig
from utils.response import ResponseUtil
from annotation.auth import Auth, AuthController
from annotation.log import Log, OperationType
from exceptions.exception import ServiceException
from utils.log import logger

{router_name} = APIRouter(prefix="/{api_name}")


@{router_name}.post("/add", response_class=JSONResponse, response_model=BaseResponse, summary="新增{description}")
@Log(title="新增{description}", operation_type=OperationType.INSERT)
@Auth(permission_list=["{api_name}:btn:add", "POST:/{api_name}/add"])
async def add_{api_name}(
        request: Request,
        params: Add{base_name}Params,
        current_user: dict = Depends(AuthController.get_current_user)
):
    \"\"\"新增{description}\"\"\"
    try:
        # 检查是否已存在（如果有唯一字段的话）
        # existing = await {model_name}.get_or_none(name=params.name, is_del=False)
        # if existing:
        #     return ResponseUtil.error(msg="添加失败，{description}已存在！")
        
        # 创建记录
        result = await {model_name}.create(**params.dict(exclude_unset=True))
        if result:
            return ResponseUtil.success(msg="添加成功！")
        else:
            return ResponseUtil.error(msg="添加失败！")
    except Exception as e:
        logger.error(f"新增{description}失败: {{str(e)}}")
        return ResponseUtil.error(msg=f"添加失败：{{str(e)}}")


@{router_name}.delete("/delete/{{id}}", response_class=JSONResponse, response_model=BaseResponse, summary="删除{description}")
@{router_name}.post("/delete/{{id}}", response_class=JSONResponse, response_model=BaseResponse, summary="删除{description}")
@Log(title="删除{description}", operation_type=OperationType.DELETE)
@Auth(permission_list=["{api_name}:btn:delete", "DELETE,POST:/{api_name}/delete/*"])
async def delete_{api_name}(
        request: Request,
        id: str = Path(..., description="{description}ID"),
        current_user: dict = Depends(AuthController.get_current_user)
):
    \"\"\"删除{description}\"\"\"
    try:
        record = await {model_name}.get_or_none(id=id, is_del=False)
        if not record:
            return ResponseUtil.error(msg="删除失败，{description}不存在！")
        
        # 软删除
        record.is_del = True
        await record.save()
        
        # 清除相关缓存
        cache_key = f'{{RedisKeyConfig.{model_name.upper()}_INFO.key}}:{{id}}'
        if await request.app.state.redis.get(cache_key):
            await request.app.state.redis.delete(cache_key)
        
        return ResponseUtil.success(msg="删除成功！")
    except Exception as e:
        logger.error(f"删除{description}失败: {{str(e)}}")
        return ResponseUtil.error(msg=f"删除失败：{{str(e)}}")


@{router_name}.delete("/deleteList", response_class=JSONResponse, response_model=BaseResponse, summary="批量删除{description}")
@{router_name}.post("/deleteList", response_class=JSONResponse, response_model=BaseResponse, summary="批量删除{description}")
@Log(title="批量删除{description}", operation_type=OperationType.DELETE)
@Auth(permission_list=["{api_name}:btn:delete", "DELETE,POST:/{api_name}/deleteList"])
async def delete_{api_name}_list(
        request: Request,
        params: DeleteListParams,
        current_user: dict = Depends(AuthController.get_current_user)
):
    \"\"\"批量删除{description}\"\"\"
    try:
        deleted_count = 0
        for record_id in set(params.ids):
            record = await {model_name}.get_or_none(id=record_id, is_del=False)
            if record:
                record.is_del = True
                await record.save()
                deleted_count += 1
        
        return ResponseUtil.success(msg=f"删除成功，共删除 {{deleted_count}} 个{description}！")
    except Exception as e:
        logger.error(f"批量删除{description}失败: {{str(e)}}")
        return ResponseUtil.error(msg=f"批量删除失败：{{str(e)}}")


@{router_name}.put("/update/{{id}}", response_class=JSONResponse, response_model=BaseResponse, summary="更新{description}")
@{router_name}.post("/update/{{id}}", response_class=JSONResponse, response_model=BaseResponse, summary="更新{description}")
@Log(title="更新{description}", operation_type=OperationType.UPDATE)
@Auth(permission_list=["{api_name}:btn:update", "PUT,POST:/{api_name}/update/*"])
async def update_{api_name}(
        request: Request,
        params: Update{base_name}Params,
        id: str = Path(..., description="{description}ID"),
        current_user: dict = Depends(AuthController.get_current_user)
):
    \"\"\"更新{description}\"\"\"
    try:
        record = await {model_name}.get_or_none(id=id, is_del=False)
        if not record:
            return ResponseUtil.error(msg="更新失败，{description}不存在！")
        
        # 更新字段
        update_data = params.dict(exclude_unset=True, exclude_none=True)
        for field, value in update_data.items():
            setattr(record, field, value)
        
        await record.save()
        
        # 清除相关缓存
        cache_key = f'{{RedisKeyConfig.{model_name.upper()}_INFO.key}}:{{id}}'
        if await request.app.state.redis.get(cache_key):
            await request.app.state.redis.delete(cache_key)
        
        return ResponseUtil.success(msg="更新成功！")
    except Exception as e:
        logger.error(f"更新{description}失败: {{str(e)}}")
        return ResponseUtil.error(msg=f"更新失败：{{str(e)}}")


@{router_name}.get("/info/{{id}}", response_class=JSONResponse, response_model=Get{base_name}InfoResponse, summary="获取{description}信息")
@Log(title="获取{description}信息", operation_type=OperationType.SELECT)
@Auth(permission_list=["{api_name}:btn:info", "GET:/{api_name}/info/*"])
async def get_{api_name}_info(
        request: Request,
        id: str = Path(..., description="{description}ID"),
        current_user: dict = Depends(AuthController.get_current_user)
):
    \"\"\"获取{description}信息\"\"\"
    try:
        record = await {model_name}.get_or_none(id=id, is_del=False)
        if record:
            # 转换为字典格式
            data = {{
                "id": str(record.id),
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
"""
    
    # 添加字段到返回数据
    for field in fields:
        field_name = field["name"]
        if field["type"] == "ForeignKeyField":
            code += f'                "{field_name}": str(record.{field_name}.id) if record.{field_name} else None,\n'
        else:
            code += f'                "{field_name}": record.{field_name},\n'
    
    code += f"""            }}
            return ResponseUtil.success(data=data)
        else:
            return ResponseUtil.error(msg="{description}不存在！")
    except Exception as e:
        logger.error(f"获取{description}信息失败: {{str(e)}}")
        return ResponseUtil.error(msg=f"获取{description}信息失败：{{str(e)}}")


@{router_name}.get("/list", response_class=JSONResponse, response_model=Get{base_name}ListResponse, summary="获取{description}列表")
@Log(title="获取{description}列表", operation_type=OperationType.SELECT)
@Auth(permission_list=["{api_name}:btn:list", "GET:/{api_name}/list"])
async def get_{api_name}_list(
        request: Request,
        page: int = Query(default=1, description="当前页码"),
        pageSize: int = Query(default=10, description="每页数量"),"""
    
    # 添加搜索参数
    for field in searchable_fields:
        field_name = field["name"]
        field_desc = field.get("description", field_name)
        code += f'\n        {field_name}: Optional[str] = Query(default=None, description="{field_desc}"),'
    
    code += f"""
        current_user: dict = Depends(AuthController.get_current_user)
):
    \"\"\"获取{description}列表\"\"\"
    try:
        # 构建过滤条件
        filter_args = {{"is_del": False}}
        
        # 添加搜索条件"""
    
    for field in searchable_fields:
        field_name = field["name"]
        code += f"""
        if {field_name}:
            filter_args["{field_name}__contains"] = {field_name}"""
    
    code += f"""
        
        # 查询总数
        total = await {model_name}.filter(**filter_args).count()
        
        # 分页查询
        records = await {model_name}.filter(**filter_args).offset((page - 1) * pageSize).limit(pageSize).all()
        
        # 转换数据格式
        result = []
        for record in records:
            data = {{
                "id": str(record.id),
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,"""
    
    # 添加字段到列表数据
    for field in fields:
        field_name = field["name"]
        if field["type"] == "ForeignKeyField":
            code += f'\n                "{field_name}": str(record.{field_name}.id) if record.{field_name} else None,'
        else:
            code += f'\n                "{field_name}": record.{field_name},'
    
    code += f"""
            }}
            result.append(data)
        
        return ResponseUtil.success(data={{
            "result": result,
            "total": total,
            "page": page,
            "pageSize": pageSize
        }})
    except Exception as e:
        logger.error(f"获取{description}列表失败: {{str(e)}}")
        return ResponseUtil.error(msg=f"获取{description}列表失败：{{str(e)}}")
"""
    
    return code


def create_api_file(model_name: str) -> str:
    """创建API文件"""
    try:
        # 分析模型
        model_info = analyze_model_for_api(model_name)
        if not model_info:
            return f"未找到模型 {model_name} 或无法解析"
        
        # 检查API文件是否已存在
        api_filename = f"{model_name.lower().replace('system', '')}.py"
        api_file = APIS_DIR / api_filename
        
        if api_file.exists():
            return f"⚠️ API文件 {api_filename} 已存在，跳过生成以避免覆盖现有文件。如需强制覆盖，请使用 create_api_from_model_force 工具"
        
        # 生成API代码
        api_code = generate_api_code(model_info)
        
        # 确保apis目录存在
        APIS_DIR.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        api_file.write_text(api_code, encoding="utf-8")
        
        return f"✅ API文件 {api_filename} 创建成功"
        
    except Exception as e:
        return f"创建API文件失败: {str(e)}"


def create_api_file_force(model_name: str) -> str:
    """强制创建API文件（覆盖现有文件）"""
    try:
        # 分析模型
        model_info = analyze_model_for_api(model_name)
        if not model_info:
            return f"未找到模型 {model_name} 或无法解析"
        
        # 生成API代码
        api_code = generate_api_code(model_info)
        
        # 创建API文件
        api_filename = f"{model_name.lower().replace('system', '')}.py"
        api_file = APIS_DIR / api_filename
        
        # 确保apis目录存在
        APIS_DIR.mkdir(parents=True, exist_ok=True)
        
        # 写入文件（强制覆盖）
        api_file.write_text(api_code, encoding="utf-8")
        
        status = "覆盖" if api_file.exists() else "创建"
        return f"✅ API文件 {api_filename} {status}成功"
        
    except Exception as e:
        return f"创建API文件失败: {str(e)}"


def list_available_models_for_api() -> str:
    """列出可用于生成API的模型"""
    try:
        models = []
        
        if not MODELS_DIR.exists():
            return "模型目录不存在"
        
        for file_path in MODELS_DIR.glob("*.py"):
            if file_path.name in ["__init__.py", "common.py"]:
                continue
            
            content = file_path.read_text(encoding="utf-8")
            
            # 提取模型类名
            class_matches = re.findall(r'class\s+(\w+)\(BaseModel\):', content)
            
            if class_matches:
                models.append({
                    "file": file_path.name,
                    "models": class_matches
                })
        
        if not models:
            return "未找到任何模型"
        
        result = "可用模型列表:\n"
        for model_info in models:
            result += f"\n📁 {model_info['file']}\n"
            for model_name in model_info['models']:
                result += f"   └── {model_name}\n"
        
        return result
        
    except Exception as e:
        return f"获取模型列表失败: {str(e)}"


def list_existing_api_files() -> str:
    """列出现有的API文件"""
    try:
        if not APIS_DIR.exists():
            return "APIs目录不存在"
        
        api_files = []
        for file_path in APIS_DIR.glob("*.py"):
            if file_path.name == "__init__.py":
                continue
            api_files.append(file_path.name)
        
        if not api_files:
            return "未找到任何API文件"
        
        result = "现有API文件:\n"
        for filename in sorted(api_files):
            result += f"  • {filename}\n"
        
        return result
        
    except Exception as e:
        return f"获取API列表失败: {str(e)}"


def register(mcp):
    """注册API工具到 MCP 服务器"""
    
    @mcp.tool()
    def create_api_from_model(model_name: str) -> str:
        """
        根据模型创建API文件（不覆盖现有文件）
        
        Args:
            model_name: 模型类名（如：SystemUser）
        
        Returns:
            创建结果信息
        """
        return create_api_file(model_name)
    
    @mcp.tool()
    def create_api_from_model_force(model_name: str) -> str:
        """
        根据模型强制创建API文件（覆盖现有文件）
        
        Args:
            model_name: 模型类名（如：SystemUser）
        
        Returns:
            创建结果信息
        """
        return create_api_file_force(model_name)
    
    @mcp.tool()
    def list_available_models_for_api() -> str:
        """
        列出可用于生成API的模型
        
        Returns:
            可用模型列表
        """
        return list_available_models_for_api()
    
    @mcp.tool()
    def list_existing_api_files() -> str:
        """
        列出现有的API文件
        
        Returns:
            现有API文件列表
        """
        return list_existing_api_files()
    
    @mcp.tool()
    def analyze_model_for_api_generation(model_name: str) -> str:
        """
        分析模型结构，用于API生成
        
        Args:
            model_name: 模型类名
            
        Returns:
            模型分析结果
        """
        try:
            model_info = analyze_model_for_api(model_name)
            if not model_info:
                return f"未找到模型 {model_name} 或无法解析"
            
            result = f"模型分析: {model_info['name']}\n"
            result += f"描述: {model_info['description']}\n"
            result += f"表名: {model_info['table_name']}\n"
            result += f"文件: {model_info['file']}\n\n"
            result += "字段列表:\n"
            
            for field in model_info['fields']:
                result += f"  • {field['name']}: {field['type']}\n"
                if field.get('description'):
                    result += f"    描述: {field['description']}\n"
                result += f"    可搜索: {'是' if field.get('searchable') else '否'}\n"
                result += f"    可过滤: {'是' if field.get('filterable') else '否'}\n"
                result += "\n"
            
            return result
            
        except Exception as e:
            return f"分析模型失败: {str(e)}"