import wmill
import feedparser
from datetime import datetime, timedelta, timezone
import calendar # For converting struct_time to UTC timestamp
import ssl
import traceback
from typing import Set, Dict, Any, Optional, List, TypedDict
import json

from u.admin.news_parsing_utils import get_content_from_link, process_text_with_gemini, send_long_message_to_telegram, send_to_telegram

def get_item_id(item) -> Optional[str]:
    """
    RSS 항목에서 고유 ID를 추출합니다.
    RSS 표준에 따라 'guid'가 가장 신뢰할 수 있는 고유 식별자입니다.
    'guid'가 없으면 'link' (URL)를, 그것도 없으면 'title'을 사용합니다.
    """
    if 'guid' in item:
        return item.guid
    if 'link' in item:
        return item.link
    if 'title' in item:
        # 제목은 변경되거나 중복될 수 있어 신뢰성이 가장 낮습니다.
        return item.title
    return None  # 고유 ID로 사용할 만한 키가 없음

def main():
    now_utc = datetime.now(timezone.utc)
    cutoff_time_utc = now_utc - timedelta(hours=24)
    rss_feed_dict = {
        "OpenAI News": "https://openai.com/news/rss.xml",
        "Google Developers Blog": "https://developers.googleblog.com/rss/", # no pub date so need to store yesterday and compare with today
        "Google DeepMind Blog": "https://blog.google/technology/google-deepmind/rss/",
        "Google Research Blog": "https://research.google/blog/rss/",
        "Meta Engineering Blog": "https://engineering.fb.com/feed/",
        "Slack Engineering Blog": "https://slack.engineering/feed/",
        "Netflix Tech Blog": "https://netflixtechblog.com/feed/"
    }
    for blog_name, feedurl in rss_feed_dict.items():
        try:
            if blog_name == "Netflix Tech Blog":
                if hasattr(ssl, '_create_unverified_context'):
                    ssl._create_default_https_context = ssl._create_unverified_context
            feed = feedparser.parse(feedurl)
            message_title = f"**Recent updates on {blog_name}**\n"
            message_to_send = ""
            if blog_name == "Google Developers Blog":
                yesterday_list = json.loads(wmill.get_variable("u/admin/google_developer_yesterday_rss"))
                yesterday_set = set(yesterday_list)
                today_set = set()
            for index, entry in enumerate(feed.entries):
                if hasattr(entry, 'published_parsed'):
                    pub_struct_time = entry.published_parsed
                    pub_timestamp_utc = calendar.timegm(pub_struct_time)
                    pub_datetime_utc = datetime.fromtimestamp(pub_timestamp_utc, timezone.utc)
                    if pub_datetime_utc < cutoff_time_utc:
                        break
                elif blog_name == "Google Developers Blog":
                    item_id = get_item_id(entry)
                    today_set.add(item_id)
                    if item_id in yesterday_set:
                        continue
                else:
                    if index > 2:
                        break
                if blog_name == "Netflix Tech Blog":
                    description = entry.content[0]['value']
                elif blog_name == "Google Research Blog" or "Google DeepMind Blog":
                    description = get_content_from_link(entry.link)
                else:
                    description = entry.description
                if description:
                    ai_processed_descriptions = process_text_with_gemini(description)
                    if not ai_processed_descriptions:
                        raise RuntimeError("Failed to retrieve ai summary")
                    message_to_send += f"* [{entry.title}]({entry.link})\n{ai_processed_descriptions['english']}\n{ai_processed_descriptions['korean']}\n\n"
                else:
                    message_to_send += f"* [{entry.title}]({entry.link})\nCannot find its content...\n\n"
            if not message_to_send:
                message_to_send += "no update today"
            print(message_to_send)
            send_long_message_to_telegram(message_title + message_to_send)
            if blog_name == "Google Developers Blog":
                today_list = list(today_set)
                wmill.set_variable("u/admin/google_developer_yesterday_rss", json.dumps(today_list))
        except Exception as e:
            print(traceback.format_exc())
            message = f"""Error on handling blog {blog_name}: `{e}`"""
            send_to_telegram(message)
    return "done"