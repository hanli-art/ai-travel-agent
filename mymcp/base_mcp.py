from typing import Any


class BaseMCP:
    """MCP 工具基类，子类可通过类属性设置 name/description"""
    name: str = "base_mcp"
    description: str = "基础MCP工具"
    def __init__(self):
        pass

    async def execute(self, **kwargs) -> Any:
        """工具执行方法，子类实现具体逻辑"""
        raise NotImplementedError