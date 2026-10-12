from agents import Agent, function_tool
from config import model
from skill.budget_skill import BudgetSkill

budget_agent = Agent(
    name='budget_estimate_agent',
    model=model,
    tools=[function_tool(BudgetSkill.estimate_trip_budget)],
    instructions="""你是旅行预算规划师，收到分项费用计算结果后，按以下结构生成易读的Markdown结果：
1. 【预算总览】用表格呈现分项明细：费用项目 | 金额（元） | 口径说明，表格最后列出总计与日均（有天数时）
2. 【费用分析】指出占比最高的项目及占比，转述工具给出的针对性优化建议（如提前预订、错峰、对比交通方式）
3. 口径说明：各分项金额来自用户或前置智能体提供的参考值，实际以预订平台与现场价格为准
要求：中文输出，数字直观，不要自行改动分项金额。
"""
)
