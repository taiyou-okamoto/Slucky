import sqlite3

def init_db():
    conn = sqlite3.connect('slucky.db')
    cursor = conn.cursor()

    # users というテーブルを作ります。
    # slack_user_id: 誰の設定か（主キー：重複を許さない）
    # google_calendar_id: その人が設定したカレンダーのメアド
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            slack_user_id TEXT PRIMARY KEY,
            google_calendar_id TXET NOT NULL
        )
    ''')

    conn.commit()
    conn.close()
    print("データベースの'slucky.db'の初期化が完了しました")

if __name__ == '__main__':
    init_db()