import os
import time
import asyncio
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import telegram
from dotenv import load_dotenv
from flask import Flask
import threading

# --- Flask Web Server Setup ---
# This part makes the script act like a web service to satisfy Render's requirements.
app = Flask(__name__)


@app.route('/')
def home():
    # This is the endpoint that UptimeRobot will ping.
    return "Notification service is running."


def run_flask_app():
    # Runs the Flask app in a separate thread.
    # The host '0.0.0.0' is required by Render.
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


# --- Notification Logic (largely the same as before) ---

# Load environment variables from a .env file for local development
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GOOGLE_SHEET_KEY = os.environ.get("GOOGLE_SHEET_KEY")
CREDENTIALS_FILE = "credentials.json"


def check_env_variables():
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GOOGLE_SHEET_KEY]):
        print("❌ FATAL ERROR: One or more environment variables are not set.")
        return False
    return True


def setup_google_sheets_client():
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        return gspread.authorize(creds)
    except FileNotFoundError:
        print(f"❌ ERROR: '{CREDENTIALS_FILE}' not found.")
        return None
    except Exception as e:
        print(f"❌ An error occurred during Google Sheets authentication: {e}")
        return None


def get_todays_schedule(client):
    if not client: return []
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        spreadsheet = client.open_by_key(GOOGLE_SHEET_KEY)
        worksheet = spreadsheet.worksheet(today_str)
        all_data = worksheet.get_all_values()[3:]
        schedule = []
        for row in all_data:
            time_str, activity = row[0], row[1]
            if not time_str or "Flexible" in activity: break
            if activity and activity != "---":
                schedule.append({"time": time_str, "activity": activity})
        print(f"✅ Successfully fetched schedule for today: {today_str}")
        print(f"   Found {len(schedule)} timed tasks.")
        return schedule
    except gspread.exceptions.WorksheetNotFound:
        print(f"⚠️ No worksheet found for today ({today_str}). Will try again later.")
        return []
    except Exception as e:
        print(f"❌ An error occurred fetching the schedule: {e}")
        return []


async def send_telegram_notification(bot, message):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"🚀 Notification sent: {message}")
    except Exception as e:
        print(f"❌ Failed to send Telegram notification: {e}")


async def notification_loop():
    """The main async loop for the notification service."""
    if not check_env_variables(): return

    print("--- Starting Notification Service Logic ---")

    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    gspread_client = setup_google_sheets_client()

    schedule = get_todays_schedule(gspread_client)
    last_day_checked = datetime.now().day
    notified_tasks = set()

    while True:
        current_time = datetime.now()

        if current_time.day != last_day_checked:
            print("\n🌅 New day detected! Fetching new schedule...")
            schedule = get_todays_schedule(gspread_client)
            last_day_checked = current_time.day
            notified_tasks.clear()

        current_time_str_12hr = current_time.strftime("%I:%M %p").upper()

        for task in schedule:
            task_key = f"{task['time']}-{task['activity']}"
            if task['time'].upper() == current_time_str_12hr and task_key not in notified_tasks:
                message = f"🔔 Reminder: It's time for '{task['activity']}'"
                await send_telegram_notification(bot, message)
                notified_tasks.add(task_key)

        await asyncio.sleep(60)


if __name__ == "__main__":
    # 1. Start the Flask web server in a separate thread
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    print("🚀 Flask web server started in a background thread.")

    # 2. Run the main async notification loop
    asyncio.run(notification_loop())
