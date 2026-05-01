

import re
from pathlib import Path
from typing import Dict, List, Any

# 获取项目根目录
BASE_DIR = Path(__file__).parent.parent.parent
MODELS_DIR = BASE_DIR / "models"

# 字段类型映射
FIELD_TYPE_MAPPING = {
    "CharField": {
        "import": "fields.CharField",
        "params": ["max_length", "null", "default", "description", "source_field"],
        "required": ["max_length"]
    },
    "TextField": {
        "import": "fields.TextField",
        "params": ["null", "default", "description", "source_field"],
        "required": []
    },
    "IntField": {
        "import": "fields.IntField",
        "params": ["null", "default", "description", "source_field"],
        "required": []
    },
    "SmallIntField": {
        "import": "fields.SmallIntField",
        "params": ["null", "default", "description", "source_field"],
        "required": []
    },
    "BigIntField": {
        "import": "fields.BigIntField",
        "params": ["null", "default", "description", "source_field"],
        "required": []
    },
    "FloatField": {
        "import": "fields.FloatField",
        "params": ["null", "default", "description", "source_field"],
        "required": []
    },
    "DecimalField": {
        "import": "fields.DecimalField",
        "params": ["max_digits", "decimal_places", "null", "default", "description", "source_field"],
        "required": ["max_digits", "decimal_places"]
    },
    "BooleanField": {
        "import": "fields.BooleanField",
        "params": ["null", "default", "description", "source_field"],
        "required": []
    },
    "DateField": {
        "import": "fields.DateField",
        "params": ["null", "default", "auto_now", "auto_now_add", "description", "source_field"],
        "required": []
    },
    "DatetimeField": {
        "import": "fields.DatetimeField",
        "params": ["null", "default", "auto_now", "auto_now_add", "description", "source_field"],
        "required": []
    },
    "TimeField": {
        "import": "fields.TimeField",
        "params": ["null", "default", "auto_now", "auto_now_add", "description", "source_field"],
        "required": []
    },
    "JSONField": {
        "import": "fields.JSONField",
        "params": ["null", "default", "description", "source_field"],
        "required": []
    },
    "UUIDField": {
        "import": "fields.UUIDField",
        "params": ["pk", "null", "default", "description", "source_field"],
        "required": []
    },
    "ForeignKeyField": {
        "import": "fields.ForeignKeyField",
        "params": ["model", "related_name", "null", "on_delete", "description", "source_field"],
        "required": ["model"]
    },
    "OneToOneField": {
        "import": "fields.OneToOneField",
        "params": ["model", "related_name", "null", "on_delete", "description", "source_field"],
        "required": ["model"]
    },
    "ManyToManyField": {
        "import": "fields.ManyToManyField",
        "params": ["model", "related_name", "through", "description"],
        "required": ["model"]
    }
}


def create_model(model_name: str, table_name: str, table_description: str, field_definitions: List[Dict]) -> str:
    """
    创建数据库模型
    
    Args:
        model_name: 模型类名
        table_name: 数据库表名
        table_description: 表描述
        field_definitions: 字段定义列表
        
    Returns:
        创建结果信息
    """
    try:
        # 验证输入参数
        if not model_name or not table_name:
            return "模型名和表名不能为空"
        
        if not field_definitions:
            return "字段定义不能为空"
        
        # 生成模型代码
        model_code = generate_model_code(model_name, table_name, table_description, field_definitions)
        
        # 创建模型文件
        file_name = f"{table_name}.py"
        model_file = MODELS_DIR / file_name
        
        if model_file.exists():
            return f"模型文件 {file_name} 已存在"
        
        # 确保models目录存在
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        
        # 写入模型文件
        model_file.write_text(model_code, encoding="utf-8")
        
        # 更新__init__.py
        update_models_init(model_name, file_name)
        
        return f"✅ 模型 {model_name} 创建成功，文件: {file_name}"
        
    except Exception as e:
        return f"创建模型失败: {str(e)}"


def generate_model_code(model_name: str, table_name: str, table_description: str, field_definitions: List[Dict]) -> str:
    """生成模型代码"""
    
    # 文件头部
    code = f"""# _*_ coding : UTF-8 _*_
# @Time : {__import__('datetime').datetime.now().strftime('%Y/%m/%d %H:%M')}
# @Author : sonder
# @File : {table_name}.py
# @Comment : {table_description}

from tortoise import fields
from models.common import BaseModel


class {model_name}(BaseModel):
    \"\"\"
    {table_description}
    \"\"\"

"""
    
    # 生成字段定义
    for field_def in field_definitions:
        field_code = generate_field_code(field_def["name"], field_def["type"], field_def)
        code += field_code + "\n"
    
    # 添加Meta类
    code += f"""
    class Meta:
        table = "{table_name}"
        table_description = "{table_description}"
        ordering = ["-created_at"]
"""
    
    return code


def generate_field_code(field_name: str, field_type: str, params: Dict[str, Any]) -> str:
    """生成字段代码"""
    
    if field_type not in FIELD_TYPE_MAPPING:
        raise ValueError(f"不支持的字段类型: {field_type}")
    
    field_info = FIELD_TYPE_MAPPING[field_type]
    
    # 构建参数列表
    param_parts = []
    
    for param_name in field_info["params"]:
        if param_name in params:
            value = params[param_name]
            
            # 特殊处理不同类型的参数
            if isinstance(value, str):
                if param_name == "model":
                    param_parts.append(f'{param_name}="{value}"')
                else:
                    param_parts.append(f'{param_name}="{value}"')
            elif isinstance(value, bool):
                param_parts.append(f'{param_name}={str(value)}')
            elif value is None:
                param_parts.append(f'{param_name}=None')
            else:
                param_parts.append(f'{param_name}={value}')
    
    # 确保source_field参数存在
    if "source_field" not in params:
        param_parts.append(f'source_field="{field_name}"')
    
    param_str = ",\n        ".join(param_parts)
    
    # 生成字段定义
    field_code = f"""    {field_name} = fields.{field_type}(
        {param_str}
    )"""
    
    # 添加字段文档
    description = params.get("description", "")
    if description:
        field_code += f'''
    """
    {description}
    """'''
    
    return field_code


def update_models_init(model_name: str, file_name: str) -> None:
    """更新models/__init__.py文件"""
    
    init_file = MODELS_DIR / "__init__.py"
    
    if not init_file.exists():
        return
    
    content = init_file.read_text(encoding="utf-8")
    
    # 添加导入语句
    module_name = file_name.replace(".py", "")
    import_line = f"from models.{module_name} import {model_name}"
    
    # 查找导入部分的结束位置
    import_match = re.search(r'(from models\.\w+ import [^\n]+\n)', content)
    if import_match:
        # 在最后一个导入语句后添加
        last_import_end = import_match.end()
        new_content = content[:last_import_end] + f"{import_line}\n" + content[last_import_end:]
    else:
        # 如果没有找到导入语句，在文件开头添加
        new_content = f"{import_line}\n" + content
    
    # 更新__all__列表
    all_match = re.search(r'__all__ = \[(.*?)\]', new_content, re.DOTALL)
    if all_match:
        all_content = all_match.group(1)
        if f"'{model_name}'" not in all_content:
            # 在最后一个元素后添加
            new_all_content = all_content.rstrip() + f",\n    '{model_name}'"
            new_content = new_content.replace(all_match.group(1), new_all_content)
    
    init_file.write_text(new_content, encoding="utf-8")


def list_models():
    """
    列出所有已定义的数据库模型
    
    Returns:
        模型列表信息
    """
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
                    "classes": class_matches
                })
        
        if not models:
            return "未找到任何模型"
        
        result = "数据库模型列表:\n"
        for model in models:
            result += f"\n📁 {model['file']}\n"
            for class_name in model['classes']:
                result += f"   └── {class_name}\n"
        
        return result
        
    except Exception as e:
        return f"获取模型列表失败: {str(e)}"


def get_model_info(model_name: str) -> str:
    """
    获取指定模型的详细信息
    
    Args:
        model_name: 模型类名
        
    Returns:
        模型详细信息
    """
    try:
        if not MODELS_DIR.exists():
            return "模型目录不存在"
        
        for file_path in MODELS_DIR.glob("*.py"):
            if file_path.name in ["__init__.py", "common.py"]:
                continue
            
            content = file_path.read_text(encoding="utf-8")
            
            # 查找指定的模型类
            class_pattern = rf'class\s+{model_name}\(BaseModel\):(.*?)(?=class\s+\w+|$)'
            class_match = re.search(class_pattern, content, re.DOTALL)
            
            if class_match:
                class_content = class_match.group(1)
                
                # 提取字段信息
                field_matches = re.findall(r'(\w+)\s*=\s*fields\.(\w+)\((.*?)\)', class_content, re.DOTALL)
                
                result = f"模型信息: {model_name}\n"
                result += f"文件: {file_path.name}\n\n"
                result += "字段列表:\n"
                
                for field_name, field_type, field_params in field_matches:
                    result += f"  • {field_name}: {field_type}\n"
                    if field_params.strip():
                        result += f"    参数: {field_params.strip()}\n"
                
                return result
        
        return f"未找到模型: {model_name}"
        
    except Exception as e:
        return f"获取模型信息失败: {str(e)}"


if __name__ == "__main__":
    # 测试代码
    print("模型工具测试")


def register(mcp):
    """注册模型工具到 MCP 服务器"""
    
    @mcp.tool()
    def create_database_model(
        model_name: str,
        table_name: str,
        table_description: str,
        field_definitions: list
    ) -> str:
        """
        创建数据库模型
        
        Args:
            model_name: 模型类名
            table_name: 数据库表名
            table_description: 表描述
            field_definitions: 字段定义列表，每个字段包含name、type和其他参数
            
        Returns:
            创建结果信息
        """
        return create_model(model_name, table_name, table_description, field_definitions)
    
    @mcp.tool()
    def list_database_models() -> str:
        """
        列出所有已定义的数据库模型
        
        Returns:
            模型列表信息
        """
        return list_models()
    
    @mcp.tool()
    def get_database_model_info(model_name: str) -> str:
        """
        获取指定模型的详细信息
        
        Args:
            model_name: 模型类名
            
        Returns:
            模型详细信息
        """
        return get_model_info(model_name)