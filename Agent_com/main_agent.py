from config import model
from agents import Agent, handoff
from Agent_com.route_agent import route_agent
from Agent_com.hotel_agent import hotel_agent
from Agent_com.traffic_agent import traffic_agent
from Agent_com.weather_agent import weather_agent
from Agent_com.food_agent import food_agent
from Agent_com.budget_agent import budget_agent

main_agent = Agent(
    name='agent_manager',
    model=model,
    handoffs=[
        handoff(route_agent, tool_description_override="处理自驾游/驾车路线规划任务，如A城市到B城市几日自驾游路线"),
        handoff(hotel_agent, tool_description_override="处理酒店住宿查询与推荐任务，如某城市酒店推荐、住宿预算规划"),
        handoff(traffic_agent, tool_description_override="处理机票、火车票等交通出行查询与购票建议任务"),
        handoff(weather_agent, tool_description_override="处理城市天气查询任务，如某城市实时天气、未来几天预报、出行穿衣建议"),
        handoff(food_agent, tool_description_override="处理美食推荐任务，如某城市美食/菜系推荐、人均预算觅食建议"),
        handoff(budget_agent, tool_description_override="处理旅行预算估算任务，如交通/住宿/餐饮/门票分项费用的总预算计算"),
    ],
    instructions="""你是一个旅游智能体总指挥（agent_manager），负责协调其它智能体处理任务：
    自驾路线规划（自驾/驾车行程） 调用 route_planning_agent
    酒店住宿 调用 hotel_planning_agent
    机票/火车票/交通出行查询 调用 traffic_query_agent
    城市天气查询（实时天气/未来预报/穿衣建议） 调用 weather_query_agent
    美食推荐（城市美食/菜系/人均觅食） 调用 food_recommend_agent
    旅行预算估算（分项费用汇总/日均/省钱建议） 调用 budget_estimate_agent
    工作要求：
    1. 收到用户请求后，先分析任务（起点、终点、行程天数、出行方式等），说明这个任务涉及哪些智能体；
    2. 说明你准备把任务交给哪个子智能体处理及原因，再进行任务转交；
    3. 一次只转交最匹配当前核心诉求的子智能体，不要同时转交多个；
    4. 如果用户同时提出多个领域需求（如既要路线又要酒店又要美食），先完成第一个，再向用户确认是否继续处理其余需求；
    5. 天气、美食、预算这类有专门专家的任务也要转交对应子智能体处理，不要自己编造实时数据；
    6. 特别注意大模型整个思考过程输出也要显示中文。
    """
)
