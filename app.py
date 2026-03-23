import os
import threading
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from google import genai
from dotenv import load_dotenv

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

@app.route("/slack/commands", methods=["POST"])
def slack_commands():
    channel_id = request.form.get("channel_id")

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
        
    # ディスパッチテーブル
    command = request.form.get("command")
    commands = {
        "/slucky-reset": handle_reset,
        "/slucky-mood": handle_mood
    }

    command_func = commands.get(command)
    if not command_func:
        return jsonify({"text": "えっと…なにをしてほしいのかボクにはよくわかんないや…💦"})

    # 実行
    if command_func == handle_mood:
        # スレッド実行
        thread = threading.Thread(target=handle_mood, args=(channel_id,))
        thread.start()
        return jsonify({"text": "わんわんっ！今、癒やしを一生懸命探してくるね！🐶✨"})
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