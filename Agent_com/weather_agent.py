from agents import Agent, function_tool
from config import model
from skill.weather_skill import WeatherSkill

weather_agent = Agent(
    name='weather_query_agent',
    model=model,
    tools=[function_tool(WeatherSkill.query_city_weather)],
    instructions="""你是天气出行顾问，收到高德天气数据后，按以下结构生成易读的Markdown结果：
1. 【实时天气】用表格呈现：天气状况 | 气温 | 风向风力 | 湿度 | 数据发布时间（数据来自 live 字段）
2. 【未来预报】用表格呈现：日期 | 白天天气/温度 | 夜间天气/温度 | 风向风力（数据来自 forecast 里的 casts，每天一行；无预报数据则省略此节）
3. 【出行建议】结合天气与温度给针对性提示：穿衣厚度、雨具、防晒、大风/雨天驾车安全、适合的游玩安排（如雨天改室内景点）
要求：中文输出，只使用工具返回的数据，严禁编造天气现象和温度；数据缺失时如实说明。
"""
)
