# 第一个智能体，功能就是给大模型发送一个问题，你是谁？让大模型回答下
# vscode中 同时按下 ctrl +shift +p 选中 选择Python解释器，然后选择自己的创建的虚拟环境
from agents import Agent,OpenAIChatCompletionsModel,Runner,function_tool
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os
import asyncio
from pydantic import BaseModel,Field
import requests
from hook.monitor_hook import MonitorHook
#我们再开发过程中要用到api key  这些关键信息，以及配置薪资。再python工程化的标准中
#会建立.env文件存放这些信息

load_dotenv()
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
DASHSCOPE_BASE_URL =os.getenv("DASHSCOPE_BASE_URL")
MODEL_NAME =os.getenv("MODEL_NAME")
AMAP_KEY =os.getenv("AMAP_KEY")

#下面的类是用来格式化城市天气查询结果的。函数返回的就算这个类的数据
class Weather(BaseModel):
    city:str=Field(description='城市名称')
    weather_info:str=Field(description='天气情况的描述')
    temperature:str=Field(description='温度')

#现在要设计一个函数来查询天气
@function_tool
def SearchWeather(city:str,address="")->Weather:
    """
    通过城市名称和地址查询天气信息。
    Arg:
        city:城市名称，比如：北京、上海
        address:详细地址，北京市朝阳区阜通东大街6号
    returns:
        Weather:返回的包含天气的信息的JSON对象
            - city:城市名称
            - weather_info:天情况描述
            - temperature: 温度信息，比如 24.5°
    """
        #下面我们就要调用高德web服务,我们要发送下面链接https://restapi.amap.com/v3/geocode/geo?parameters
    #通过城市名称获取编码
    url="https://restapi.amap.com/v3/geocode/geo"
    req_params={
        "key":AMAP_KEY,
        "city":address,
        "address":city,
        "output":"json"
    }
    res = requests.get(url,params=req_params,timeout=5).json()
    try:
        if res.get("status")=="1" and res.get("geocodes"):
            adcode =res["geocodes"][0]["adcode"]
        else:
            raise ValueError(f'获取城市地理位置编码失败:{res.get("info","未知错误")}')
    except Exception as e:
        raise ValueError(f'地理API请求失败:{str(e)}')

    #根据地理信息编码，获取天气
    weather_url ="https://restapi.amap.com/v3/weather/weatherInfo"
    params={
        "key":AMAP_KEY,
        "city":adcode,
        "output":"json"
    }
    weather_res=requests.get(weather_url,params=params,timeout=5).json()
    try:
        if weather_res.get("status")=="1" and weather_res.get("lives"):
            live =weather_res["lives"][0]
            return Weather(
                city=city,
                weather_info=live['weather'],
                temperature=live['temperature']
            )
        else:
            raise ValueError(f'天气数据获取失败:{weather_res.get("info","未知错误")}')
    except Exception as e:
        raise ValueError(f'天气API请求失败:{str(e)}')
    

#使用openai-agent框架来创建智能体
client = AsyncOpenAI(api_key=DASHSCOPE_API_KEY,base_url=DASHSCOPE_BASE_URL)
main_agent =Agent(
    name='main_agent',
    model=OpenAIChatCompletionsModel(model=MODEL_NAME,openai_client=client),
    tools=[SearchWeather],
)

async def LLM_Chat():
    hook = MonitorHook()
    print("第一轮对话:你是谁？")
    result = await Runner.run(main_agent,"你是谁？")
    print(result.final_output)
    print("第二轮对话:你对最近的美伊战争有什么看法，你认为美国会输吗？")
    result = await Runner.run(main_agent,"你对最近的美伊战争有什么看法，你认为美国会输吗？")
    print(result.final_output)
    print("第三轮对话:请告诉我江西省南昌市的天气情况？")
    result = await Runner.run(main_agent,"请告诉我江西省南昌市的天气情况？",hooks=hook)
    print(result.final_output)

if __name__=="__main__":
    asyncio.run(LLM_Chat())