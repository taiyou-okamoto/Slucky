import os
import threading
import sqlite3
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from google import genai
from dotenv import load_dotenv

# 自作モジュール
from calendar_helper import fetch_today_schedule

load_dotenv()

app = Flask(__name__)

slack_client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
gemini_client = genai.Client(api_key=os.environ["SLUCKEY"])
GEMINI_API = "gemini-3.1-flash-lite-preview"

system_instruction = """
    "あなたの名前はSlucky(スラッキー)という犬です。
    由来は「Slack」+「Lucky」から来ています。
    その名の通り、Slackアプリの中でユーザーのお手伝いをします。
    フレンドリーで親しみやすい性格です。絵文字を使って犬らしく、楽しく返信してください。"
    """
chat_sessions = {}

processed_events = set() #無限に増える

def get_user_email(user_id):
    try:
        conn = sqlite3.connect("slucky.db")
        cursor = conn.cursor()

        cursor.execute('''
            SELECT google_calendar_id FROM users
            WHERE slack_user_id = ?
        ''', (user_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return result[0]
        else:
            return os.environ.get("GOOGLE_CALENDAR_ID", "primary")
            
    except Exception as e:
        print(f"DB検索エラー: {e}")
        return os.environ.get("GOOGLE_CALENDAR_ID", "primary") # エラー時もデフォルトを返す

@app.route("/slack/commands", methods=["POST"])
def slack_commands():
    channel_id = request.form.get("channel_id")
    user_id = request.form.get("user_id")
    user_text = request.form.get("text")

    def handle_reset(channel_id):
        chat_sessions[channel_id] = gemini_client.chats.create(
            model=GEMINI_API,
            config={
                "system_instruction": system_instruction
            }
        )
        return "あれっ？ボクって何の話してたんだっけ…？忘れちゃったけどまぁいいか！"

    def handle_mood(channel_id):
        mood_prompt = """
            ご主人様がちょっとお疲れモードみたい。元気づけるような面白い一言か、癒やしのメッセージを短く送って！
            """
        
        response = gemini_client.models.generate_content(
            model=GEMINI_API,
            config={
                "system_instruction": system_instruction
            },
            contents=mood_prompt
        )

        slack_client.chat_postMessage(channel=channel_id, text=response.text)
        return jsonify({"status": "ok"})

    def handle_setCalendar(user_id, user_email):
        if not user_email or "@" not in user_email:
            return "あれっ？💦メールアドレスの形式が変かも？ 正しいメールアドレスをもう一度送ってみて！！"

        try:
            conn = sqlite3.connect('slucky.db')
            cursor = conn.cursor()
    
            # SQLiteでuserテーブルに INSERT OR REPLACE
            cursor.execute('''
                INSERT OR REPLACE INTO users (slack_user_id, google_calendar_id)
                VALUES (?, ?)
            ''', (user_id, user_email))

            conn.commit()
            conn.close()

            return f"わんわんっ！ ご主人様（<@{user_id}>）のカレンダーを `{user_email}` で覚えたよ！🗓️🐶"
        
        except Exception as e:
            return f"ごめんね、データベースに書き込めなかったよ… (エラー: {e})"

    def handle_schedule(channel_id, user_id):
        with app.app_context():
            user_email = get_user_email(user_id)

            raw_schedule = fetch_today_schedule(user_email)

            schedule_prompt = f"以下の予定を、ご主人様に可愛く元気にお知らせしてあげて！\n\n{raw_schedule}"
            response = gemini_client.models.generate_content(
                model=GEMINI_API,
                config={
                    "system_instruction": system_instruction
                },
                contents=schedule_prompt
            )

            slack_client.chat_postMessage(channel=channel_id, text=response.text)
            return jsonify({"status": "ok"})
    
         
    # ディスパッチテーブル
    command = request.form.get("command")
    commands = {
        "/slucky-reset": handle_reset,
        "/slucky-mood": handle_mood,
        "/slucky-schedule": handle_schedule,
        "/slucky-set-calendar": handle_setCalendar
    }

    command_func = commands.get(command)
    if not command_func:
        return jsonify({"text": "えっと…なにをしてほしいのかボクにはよくわかんないや…💦"})

    # 実行
    if command_func in [handle_mood, handle_schedule]:
        # スレッド実行
        thread = threading.Thread(target=command_func, args=(channel_id, user_id,))
        thread.start()

        if command_func == handle_schedule:
            return jsonify({"text": "わんわんっ！カレンダーを見てくるね！🗓️🐾"})
        return jsonify({"text": "わんわんっ！今、癒やしを一生懸命探してくるね！🐶✨"})
    
    else:
        if command_func == handle_setCalendar:
            text = command_func(user_id, user_text)
        else:
            text = command_func(channel_id)

        return jsonify({"text": text})

@app.route("/slack/events", methods=["POST"])
def slack_events():
    # slackからのjsonを表示
    data = request.json
    event_id = data.get("event_id")

    # 重複ガード処理
    if event_id in processed_events:
        return jsonify({"status": "already_processed"})
    
    processed_events.add(event_id)

    # slackURL検証(1度のみ)
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})
    
    # メンションイベントの処理
    if "event" in data and data["event"]["type"] == "app_mention":
        event = data["event"]
        user_text = event.get("text", "")
        channel_id = event.get("channel")

        # 履歴がないなら作成
        if channel_id not in chat_sessions:
            chat_sessions[channel_id] = gemini_client.chats.create(
                model=GEMINI_API,
                config={
                    "system_instruction": system_instruction
                }
            )

        # Geminiに回答してもらう
        response = chat_sessions[channel_id].send_message(user_text)

        # Slackに返信する
        slack_client.chat_postMessage(channel=channel_id, text=response.text)

        history = chat_sessions[channel_id].get_history()
        if len(history) > 20:
            history.pop(0) 
            history.pop(0) 
    
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(port=5000)