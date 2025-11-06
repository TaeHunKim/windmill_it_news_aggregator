# import wmill
import feedparser
import requests
import traceback

from u.rapaellk.news_parsing_utils import get_content_from_link, process_text_with_gemini, send_long_message_to_telegram, send_to_telegram, remove_html_tags_bs4

def techmeme():
    try:
        message_title = "**Top News on Techmeme:**\n"
        rss_url = 'https://www.techmeme.com/feed.xml'
        feed = feedparser.parse(rss_url)
        message_to_send = ""
        for entry in feed.entries:
            description = remove_html_tags_bs4(entry.description)
            if description:
                ai_processed_descriptions = process_text_with_gemini(remove_html_tags_bs4(description))
                if not ai_processed_descriptions:
                    raise RuntimeError("Failed to retrieve ai summary")
                message_to_send += f"* [{entry.title}]({entry.link})\n{ai_processed_descriptions['english']}\n{ai_processed_descriptions['korean']}\n\n"
            else:
                message_to_send += f"* [{entry.title}]({entry.link})\nCannot find its content...\n\n"
        print(message_to_send)
        send_long_message_to_telegram(message_title + message_to_send)
    except Exception as e:
        print(traceback.format_exc())
        message = f"""Error on handling techmeme: `{e}`"""
        send_to_telegram(message)

HN_TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

def hacker_news(limit=10):
    """
    Hacker News의 현재 Top 스토리를 가져옵니다.
    """
    print("Hacker News Top 스토리를 가져오는 중...")
    try:
        message_title = "**Top News on Hacker News:**\n"
        message_to_send = ""
        top_ids = requests.get(HN_TOP_STORIES_URL).json()
        for item_id in top_ids[:limit]:
            item_details = requests.get(HN_ITEM_URL.format(id=item_id)).json()
            if item_details and 'url' in item_details:
                title = item_details.get('title')
                link = item_details.get('url')
                description = get_content_from_link(link)
                if description:
                    ai_processed_descriptions = process_text_with_gemini(remove_html_tags_bs4(description))
                    if not ai_processed_descriptions:
                        raise RuntimeError("Failed to retrieve ai summary")
                    message_to_send += f"* [{title}]({link})\n{ai_processed_descriptions['english']}\n{ai_processed_descriptions['korean']}\n\n"
                else:
                    message_to_send += f"* [{title}]({link})\nCannot find its content...\n\n"
        print(message_to_send)       
        send_long_message_to_telegram(message_title + message_to_send)
    except Exception as e:
        print(traceback.format_exc())
        message = f"Failed to get news from Hacker News: `{e}`"
        send_to_telegram(message)

def geeknews():
    try:
        message_title = "**Top News on GeekNews:**\n"
        rss_url = 'https://feeds.feedburner.com/geeknews-feed'
        feed = feedparser.parse(rss_url)
        print(feed)
        message_to_send = ""
        for entry in feed.entries:
            description = remove_html_tags_bs4(entry.content[0]['value'])
            message_to_send += f"* [{entry.title}]({entry.link})\n{description}\n\n" # No need to translate as it's Korean
        print(message_to_send)
        send_long_message_to_telegram(message_title + message_to_send)
    except Exception as e:
        print(traceback.format_exc())
        message = f"Failed to get news from GeekNews: {e}"
        send_to_telegram(message)

def main():
    #techmeme()
    #hacker_news()
    #geeknews()
    google_news_tech_kor = 'https://news.google.com/topics/CAAqKAgKIiJDQkFTRXdvSkwyMHZNR1ptZHpWbUVnSnJieG9DUzFJb0FBUAE?ceid=KR:ko&oc=3'
    google_news_tech_us = 'https://news.google.com/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGRqTVhZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US%3Aen'
    google_news_message = "**Top News on Google News**\n"
    google_news_message += f"[Kor]({google_news_tech_kor})\n"
    google_news_message += f"[US]({google_news_tech_us})"
    send_to_telegram(google_news_message)
    return 'done'