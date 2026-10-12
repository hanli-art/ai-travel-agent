import json

# 
# 1. 直接把高德返回的JSON写在代码中，作为字符串
# 
amap_weather_json_str = '''
{
    "status": "1",
    "count": "1",
    "info": "OK",
    "infocode": "10000",
    "lives": [
        {
            "province": "福建",
            "city": "福州市",
            "adcode": "350100",
            "weather": "多云",
            "temperature": "28",
            "winddirection": "东南",
            "windpower": "3",
            "humidity": "65",
            "reporttime": "2026-08-27 10:30:00"
        }
    ]
}
'''
data = json.loads(amap_weather_json_str)
print("==================Python解析数据类型===========")
print(f"data的类型是:{type(data)}")
print(f"data[lives]的类型是:{type(data['lives'])}")

if data["status"] =="1":
    lives =data["lives"]
    weather=lives[0]
    print("提取天气信息====================")
    print(f"省份: {weather['province']}")
    print(f"城市:{weather['city']}")
    print(f"天气: {weather['weather']}")
    print(f"温度: {weather['temperature']} ℃")
    print(f"风向: {weather['winddirection']}")
    print(f"风力: {weather['windpower']} 级")
    print(f"湿度: {weather['humidity']} %")
    print(f"更新时间: {weather['reporttime']}")
    print(data["lives"][0]['city'])

#我们可以python对象格式再输出成json字符串，用于打印或者是传给agent大模型
print("================格式化输出json字符串====================")
pretty_json = json.dumps(data, ensure_ascii=False, indent=2)
print(pretty_json)