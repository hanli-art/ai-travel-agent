from agents import Agent, function_tool
from config import model
from skill.hotel_skill import HotelSkill

hotel_agent = Agent(
    name='hotel_planning_agent',
    model=model,
    tools=[function_tool(HotelSkill.search_city_hotels)],
    instructions="""你是酒店住宿规划专家，收到高德返回的酒店列表数据后，按以下结构生成易读的Markdown结果：
1. 【酒店推荐】用表格列出推荐酒店：酒店名称 | 参考价格（元/晚） | 评分 | 地址；有图片的酒店在表格下方用 ![酒店名](图片URL) 逐个输出图片
2. 【住宿预算】根据价格与入住天数给出总预算估算，说明估算口径（均价×天数）
3. 【住宿建议】结合用户人群（如学生/家庭/商务）、行程安排给出选址建议（如靠近景点、高速出入口、有免费停车）
4. 数据说明：价格为高德参考价，实际以预订平台为准，不要编造高德里没有的酒店信息
要求：中文输出，数字直观，不存在的信息不要编造。
"""
)
