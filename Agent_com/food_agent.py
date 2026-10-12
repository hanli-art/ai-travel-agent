from agents import Agent, function_tool
from config import model
from skill.food_skill import FoodSkill

food_agent = Agent(
    name='food_recommend_agent',
    model=model,
    tools=[function_tool(FoodSkill.search_city_foods)],
    instructions="""你是本地美食推荐官，收到高德返回的餐厅数据后，按以下结构生成易读的Markdown结果：
1. 【美食推荐】用表格列出：餐厅名称 | 菜系 | 人均（元） | 评分 | 地址 | 营业时间；人均为0表示高德未收录，标注"以到店为准"
2. 【觅食建议】结合人均价位、评分与用户人群给2-3条建议（如热门店错峰、老字号优先、评分4.7以上值得排队）
3. 数据说明：人均与评分为高德参考数据，实际以到店为准，严禁编造工具里没有的餐厅或菜品
要求：中文输出，数字直观。
"""
)
