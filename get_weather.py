import wmill
import requests
import pprint
from typing import Dict, Any
import traceback
from holidayskr import today_is_holiday
import telegramify_markdown
import json
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderUnavailable, GeocoderTimedOut

from u.admin.news_parsing_utils import get_content_from_link, process_weather_info_with_gemini, send_long_message_to_telegram, send_to_telegram

API_KEY = wmill.get_variable("u/admin/open_weather_map_api_key")

URL_WEATHER = "https://api.openweathermap.org/data/3.0/onecall"
URL_POLLUTION = "https://api.openweathermap.org/data/2.5/air_pollution"
URL_GEO_REVERSE = "http://api.openweathermap.org/geo/1.0/reverse"

def get_location_name(lat: float, lon: float, api_key: str) -> str:
    """
    One Call API 3.0을 호출하여 현재 위치 이름을 가져옵니다.
    """
    print(f"위치 정보 요청 중... (lat: {lat}, lon: {lon})")
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "limit": 1,
    }
    response = requests.get(URL_GEO_REVERSE, params=params)
    response.raise_for_status() # 오류 발생 시 예외 처리
    city_info = response.json()[0]
    return city_info["local_names"]["kr"] if "kr" in city_info["local_names"] else city_info["name"]

def get_weather_data(lat: float, lon: float, api_key: str) -> Dict[str, Any]:
    """
    One Call API 3.0을 호출하여 날씨 정보를 가져옵니다.
    """
    print(f"날씨 정보 요청 중... (lat: {lat}, lon: {lon})")
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric",  # 섭씨(Celsius)
        "lang": "kr",       # 한국어
        "exclude": "minutely,hourly"
    }
    response = requests.get(URL_WEATHER, params=params)
    response.raise_for_status() # 오류 발생 시 예외 처리
    return response.json()

def get_air_pollution_data(lat: float, lon: float, api_key: str) -> Dict[str, Any]:
    """
    Air Pollution API를 호출하여 대기 오염 정보를 가져옵니다.
    """
    print(f"대기 오염 정보 요청 중... (lat: {lat}, lon: {lon})")
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key
    }
    response = requests.get(URL_POLLUTION, params=params)
    response.raise_for_status() # 오류 발생 시 예외 처리
    return response.json()

# OWM 대기질 등급 (1~5)과 사용자 요청 (좋음~매우나쁨) 매핑
POLLUTANT_LEVEL_MAP = {1: "좋음", 2: "보통", 3: "경계", 4: "나쁨", 5: "매우 나쁨"}

def get_pm2_5_level(value: float) -> str:
    """PM2.5 (미세먼지) μg/m³ 기준 등급 반환"""
    if value < 10: return POLLUTANT_LEVEL_MAP[1]
    if value < 25: return POLLUTANT_LEVEL_MAP[2]
    if value < 50: return POLLUTANT_LEVEL_MAP[3]
    if value < 75: return POLLUTANT_LEVEL_MAP[4]
    return POLLUTANT_LEVEL_MAP[5]

def get_pm10_level(value: float) -> str:
    """PM10 (초미세먼지) μg/m³ 기준 등급 반환"""
    if value < 20: return POLLUTANT_LEVEL_MAP[1]
    if value < 50: return POLLUTANT_LEVEL_MAP[2]
    if value < 100: return POLLUTANT_LEVEL_MAP[3]
    if value < 200: return POLLUTANT_LEVEL_MAP[4]
    return POLLUTANT_LEVEL_MAP[5]

def get_so2_level(value: float) -> str:
    """SO2 (이산화황) μg/m³ 기준 등급 반환"""
    if value < 20: return POLLUTANT_LEVEL_MAP[1]
    if value < 80: return POLLUTANT_LEVEL_MAP[2]
    if value < 250: return POLLUTANT_LEVEL_MAP[3]
    if value < 350: return POLLUTANT_LEVEL_MAP[4]
    return POLLUTANT_LEVEL_MAP[5]

def get_no2_level(value: float) -> str:
    """NO2 (이산화질소) μg/m³ 기준 등급 반환"""
    if value < 40: return POLLUTANT_LEVEL_MAP[1]
    if value < 70: return POLLUTANT_LEVEL_MAP[2]
    if value < 150: return POLLUTANT_LEVEL_MAP[3]
    if value < 200: return POLLUTANT_LEVEL_MAP[4]
    return POLLUTANT_LEVEL_MAP[5]

def get_o3_level(value: float) -> str:
    """O3 (오존) μg/m³ 기준 등급 반환"""
    if value < 60: return POLLUTANT_LEVEL_MAP[1]
    if value < 100: return POLLUTANT_LEVEL_MAP[2]
    if value < 140: return POLLUTANT_LEVEL_MAP[3]
    if value < 180: return POLLUTANT_LEVEL_MAP[4]
    return POLLUTANT_LEVEL_MAP[5]

def get_co_level(value: float) -> str:
    """CO (일산화탄소) μg/m³ 기준 등급 반환"""
    if value < 4400: return POLLUTANT_LEVEL_MAP[1]
    if value < 9400: return POLLUTANT_LEVEL_MAP[2]
    if value < 12400: return POLLUTANT_LEVEL_MAP[3]
    if value < 15400: return POLLUTANT_LEVEL_MAP[4]
    return POLLUTANT_LEVEL_MAP[5]

def parse_combined_data(current_location: str, weather_data: Dict[str, Any], pollution_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    두 API의 응답을 파싱하여 사용자가 요청한 형식의 딕셔너리로 조합합니다.
    """
    # 'daily' 배열의 첫 번째 항목(오늘)을 사용합니다.
    today_forecast = weather_data["daily"][0]
    current_weather = weather_data["current"]

    # 대기 오염 데이터의 첫 번째 항목을 사용합니다.
    air_quality = pollution_data["list"][0]

    # 개별 오염물질 값 추출 (API 응답에 따라 'no', 'nh3'는 없을 수 있음)
    components = air_quality["components"] # 편의를 위해 변수 할당
    val_pm2_5 = components.get("pm2_5", 0.0)
    val_pm10 = components.get("pm10", 0.0)
    val_co = components.get("co", 0.0)
    val_o3 = components.get("o3", 0.0)
    val_no2 = components.get("no2", 0.0)
    val_so2 = components.get("so2", 0.0)
    val_no = components.get("no", 0.0)
    val_nh3 = components.get("nh3", 0.0)

    # 강우량, 강설량 (없을 경우 0)
    rainfall_mm = today_forecast.get("rain", 0.0)
    snowfall_mm = today_forecast.get("snow", 0.0)

    # OWM의 AQI는 1~5의 값을 가집니다. (1=좋음, 5=매우나쁨)
    aqi_map = {1: "좋음", 2: "보통", 3: "경계", 4: "나쁨", 5: "매우 나쁨"}

    combined_data = {
        "위치": current_location,
        "요약": today_forecast["summary"],
        "오늘 날씨": today_forecast["weather"][0]['description'],
        "현재 체감기온 (°C)": current_weather["feels_like"],
        "현재 가시거리 (m)": current_weather["visibility"],
        "최고 기온 (°C)": today_forecast["temp"]["max"],
        "최저 기온 (°C)": today_forecast["temp"]["min"],
        "오늘 습도 (%)": today_forecast["humidity"],
        "오늘 풍속 (m/s)" : str(today_forecast['wind_speed']) + f" (최대 {today_forecast['wind_gust']})" if 'wind_gust' in today_forecast else "",
        "오늘 체감기온 (°C)": f"낮: {today_forecast['feels_like']['day']}, 저녁: {today_forecast['feels_like']['eve']}, 밤: {today_forecast['feels_like']['night']}", 
        "오늘 강우량 (mm)": rainfall_mm,
        "오늘 강설량 (mm)": snowfall_mm,
        "오늘 강수 확률 (%)": today_forecast["pop"] * 100,
        "오늘 자외선 지수 (UVI)": today_forecast["uvi"],
        "경보": ", ".join([x["event"] for x in weather_data.get("alerts", [])]),

        "대기질 지수 (AQI)": f"{air_quality['main']['aqi']} ({aqi_map.get(air_quality['main']['aqi'])})",
        # 등급표(이미지) 기준이 있는 항목들
        "미세먼지 (PM2.5)": f"{val_pm2_5:.2f} μg/m³ ({get_pm2_5_level(val_pm2_5)})",
        "초미세먼지 (PM10)": f"{val_pm10:.2f} μg/m³ ({get_pm10_level(val_pm10)})",
        "일산화탄소 (CO)": f"{val_co:.2f} μg/m³ ({get_co_level(val_co)})",
        "오존 (O3)": f"{val_o3:.2f} μg/m³ ({get_o3_level(val_o3)})",
        "이산화질소 (NO2)": f"{val_no2:.2f} μg/m³ ({get_no2_level(val_no2)})",
        "이산화황 (SO2)": f"{val_so2:.2f} μg/m³ ({get_so2_level(val_so2)})",
        
        # 참고: NO, NH3는 OWM 등급표에 기준이 없습니다.
        "일산화질소 (NO, μg/m³)": f"{val_no:.2f}", 
        "암모니아 (NH3, μg/m³)": f"{val_nh3:.2f}",
    }
    
    return combined_data

def get_and_parse_data(lat: float, lon: float,):
    print(f"{lat}, {lon}")
    try:
        current_location = get_location_name(lat, lon, API_KEY)

        # 1. 날씨 정보 API 호출
        weather_json = get_weather_data(lat, lon, API_KEY)
        
        # 2. 대기 오염 API 호출
        pollution_json = get_air_pollution_data(lat, lon, API_KEY)
        
        # 3. 두 데이터 조합 및 파싱
        final_data = parse_combined_data(current_location, weather_json, pollution_json)

        processed_weather = process_weather_info_with_gemini(final_data)
        final_data["위치"] = processed_weather["location_ko"]
        final_data["요약"] = processed_weather["summary_ko"]
        final_data["경보"] = processed_weather["alert_ko"]
        final_data["제안"] = processed_weather["suggestion"]

        # 4. 결과 출력
        print("\n--- 최종 날씨 및 대기 질 정보 ---")
        pprint.pprint(final_data)

        return final_data
    except Exception:
        raise

def escape_mdv2(text):
    return telegramify_markdown.markdownify(str(text)).strip()

def format_weather_for_telegram(data: dict) -> str:
    """날씨 딕셔너리를 텔레그램 MarkdownV2 문자열로 변환합니다."""
    
    # --- 데이터 추출 및 이스케이프 ---
    
    # .get()을 사용하여 키가 없어도 오류가 나지 않도록 처리
    def get_escaped(key, default="N/A"):
        return escape_mdv2(data.get(key, default))

    # 섹션 1: 핵심 요약
    location = get_escaped('위치')
    summary = get_escaped('요약')
    suggestion = get_escaped('제안')

    # 섹션 2: 경보 (내용이 있을 때만 표시)
    alert = data.get('경보', '')
    alert_message = ""
    if alert:
        alert_message = (
            f"\n\n*🚨 경보 🚨*\n"
            f"_{escape_mdv2(alert)}_\n"
        )

    # 섹션 3: 주요 날씨
    weather = get_escaped('오늘 날씨')
    temp_max = get_escaped('최고 기온 (°C)')
    temp_min = get_escaped('최저 기온 (°C)')
    feels_now = get_escaped('현재 체감기온 (°C)')
    rain_prob = get_escaped('오늘 강수 확률 (%)')
    
    # 0.0이 아닌 강수/강설량만 표시
    rain_amount = data.get('오늘 강우량 (mm)', 0.0)
    snow_amount = data.get('오늘 강설량 (mm)', 0.0)

    # 섹션 4: 대기 질
    aqi = get_escaped('대기질 지수 (AQI)')
    # 키 이름에 '.'이 있으므로 수동으로 이스케이프
    pm25_key = '미세먼지 (PM2.5)'
    pm10_key = '초미세먼지 (PM10)'
    pm25 = get_escaped(pm25_key)
    pm10 = get_escaped(pm10_key)
    o3 = get_escaped('오존 (O3)')

    # 섹션 5: 세부 정보 (스포일러 처리)
    uvi = get_escaped('오늘 자외선 지수 (UVI)')
    humidity = get_escaped('오늘 습도 (%)')
    wind = get_escaped('오늘 풍속 (m/s)')
    feels_today = get_escaped('오늘 체감기온 (°C)')
    visibility = get_escaped('현재 가시거리 (m)')
    
    # 나머지 오염물질
    co = get_escaped('일산화탄소 (CO)')
    no2 = get_escaped('이산화질소 (NO2)')
    so2 = get_escaped('이산화황 (SO2)')
    no = get_escaped('일산화질소 (NO, μg/m³)')
    nh3 = get_escaped('암모니아 (NH3, μg/m³)')

    # --- MarkdownV2 문자열 조합 ---
    
    message_parts = []
    
    # 헤더
    message_parts.append(f"*{location.strip()} 날씨 브리핑* 🌦")
    message_parts.append(f"*{summary}*")
    
    # 제안 (가장 중요)
    message_parts.append(f"\n{suggestion}")
    
    # 경보 (있을 경우)
    if alert_message:
        message_parts.append(alert_message)

    # 구분선
    separator = r'\-' * 25  # 이스케이프된 하이픈 25개
    message_parts.append(f"\n{separator}\n")

    # 주요 날씨
    message_parts.append(f"*오늘의 날씨* 🌡️")
    message_parts.append(f"• *날씨*: {weather}")
    message_parts.append(f"• *기온*: {temp_min}°C / {temp_max}°C")
    message_parts.append(f"• *현재 체감*: {feels_now}°C")
    message_parts.append(f"• *강수 확률*: {rain_prob}%")
    if rain_amount > 0:
        message_parts.append(f"• *강우량*: {escape_mdv2(rain_amount)}mm")
    if snow_amount > 0:
        message_parts.append(f"• *강설량*: {escape_mdv2(snow_amount)}mm")

    # 대기 질
    message_parts.append(f"\n*대기 질* 🍃")
    message_parts.append(f"• *종합*: {aqi}")
    # 키 이름의 특수문자(., 2.5)는 직접 이스케이프 처리
    message_parts.append(f"• *미세\(PM2\.5\)*: {pm25}")
    message_parts.append(f"• *초미세\(PM10\)*: {pm10}")
    message_parts.append(f"• *오존\(O3\)*: {o3}")

    # 세부 정보 (스포일러)
    message_parts.append(f"\n{separator}\n")
    message_parts.append(f"||") # 스포일러 시작
    message_parts.append(f"*세부 정보 \(날씨\)*")
    message_parts.append(f"• 자외선 \(UVI\): {uvi}")
    message_parts.append(f"• 습도: {humidity}%")
    message_parts.append(f"• 바람: {wind}")
    message_parts.append(f"• 오늘 체감: {feels_today}")
    message_parts.append(f"• 가시거리: {visibility}m")
    
    message_parts.append(f"\n*세부 정보 \(대기\)*")
    message_parts.append(f"• CO: {co}")
    message_parts.append(f"• NO2: {no2}")
    message_parts.append(f"• SO2: {so2}")
    message_parts.append(f"• NO: {no}")
    message_parts.append(f"• NH3: {nh3}")
    message_parts.append(f"||") # 스포일러 끝

    # 모든 부분을 개행 문자로 연결
    return "\n".join(message_parts)

def get_weather_message(lat: float, lon: float, with_send_to_telegram: bool = True):
    try:
        location_data = get_and_parse_data(lat, lon)
        message = format_weather_for_telegram(location_data)
    except Exception as e:
        print(traceback.format_exc())
        message = f"Failed to get weather: {e}"
    finally:
        if with_send_to_telegram:
            send_to_telegram(message, escaped=True, token=wmill.get_resource("u/admin/telegram_token_resource_2"))
        return message

def get_home_weather(with_send_to_telegram: bool = True):
    locations = json.loads(wmill.get_variable("u/admin/important_locations"))
    location = locations.get("home")
    return get_weather_message(*location, with_send_to_telegram=with_send_to_telegram)

def get_office_weather(with_send_to_telegram: bool = True):
    locations = json.loads(wmill.get_variable("u/admin/important_locations"))
    location = locations.get("office")
    return get_weather_message(*location, with_send_to_telegram=with_send_to_telegram)

def get_parent_home_weather(with_send_to_telegram: bool = True):
    locations = json.loads(wmill.get_variable("u/admin/important_locations"))
    location = locations.get("parent_home")
    return get_weather_message(*location, with_send_to_telegram=with_send_to_telegram)

def _get_location_from_name(location_name:str):
    try:
        geolocator = Nominatim(user_agent="admin-weather-bot-v1")
        location = geolocator.geocode(location_name)

        # 3. 결과 확인
        if location:
            print(f"입력: {location_name}")
            print(f"주소: {location.address}")
            print(f"위도: {location.latitude}")
            print(f"경도: {location.longitude}")
            return location.latitude, location.longitude
        else:
            raise RuntimeError("Cannot find location")

    except Exception:
        raise

def get_weather_message_from_location_name(location_name:str, with_send_to_telegram: bool = False):
    try:
        lat, lon = _get_location_from_name(location_name)
        message = get_weather_message(lat, lon, with_send_to_telegram=with_send_to_telegram)
        return message
    except Exception as e:
        print(traceback.format_exc())
        message = f"Failed to get weather: {e}"
        return message

def main(lat: float, lon: float):
    print(f"{lat}, {lon}")
    try:
        current_location_data = get_weather_message(lat, lon, with_send_to_telegram=True)

        if not today_is_holiday() and wmill.get_variable("u/admin/home_location") in current_location_data:
            get_office_weather(with_send_to_telegram=True)

        response = {
            "windmill_status_code":200,
            "result":{
                "lat": lat,
                "lon": lon,
            }
        }

        return response
    except Exception as e:
        print(traceback.format_exc())
        message = f"Failed to get weather: {e}"
        send_to_telegram(message, token=wmill.get_resource("u/admin/telegram_token_resource_2"))
