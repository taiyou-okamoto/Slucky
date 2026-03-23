# calendar_helper.py
import datetime
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# .envは app.py 側で load_dotenv() されていれば、ここでも os.environ が使えます！
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
SERVICE_ACCOUNT_FILE = 'slucky-491106-c57b81d197ad.json'

def fetch_today_schedule():
    """
    Googleカレンダーから直近10件の予定を取得し、
    Geminiに渡しやすい文字列（プレーンテキスト）にして返す。
    """
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now = now_utc.isoformat().replace('+00:00', 'Z')

        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return "直近の予定は何も入っていないみたいだよ！"

        # 予定を箇条書きにまとめる
        schedule_text = "【直近の予定リスト】\n"
        for event in events:
            # 開始時間を取得
            start = event['start'].get('dateTime', event['start'].get('date'))
            
            # 見やすくするために"2024-10-25T14:00:00+09:00"などを少し整形
            summary = event['summary']
            schedule_text += f"・ {start} : {summary}\n"

        return schedule_text

    except Exception as e:
        return f"カレンダーの取得に失敗しちゃった💦 エラー: {e}"