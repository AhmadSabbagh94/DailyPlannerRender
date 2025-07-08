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
import pytz
import json  # Import the json library

# --- Flask Web Server Setup ---
app = Flask(__name__)


@app.route('/')
def home():
    return "Notification service is running."


def run_flask_app():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


# --- Notification Logic ---
load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GOOGLE_SHEET_KEY = os.environ.get("GOOGLE_SHEET_KEY")
TIMEZONE = os.environ.get("TIMEZONE", "Europe/London")
# Get the credentials from the environment variable if it exists
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")
CREDENTIALS_FILE = "credentials.json"  # Fallback for local development


def check_env_variables():
    # Only check for the main variables, as credentials can be handled in two ways
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GOOGLE_SHEET_KEY]):
        print("❌ FATAL ERROR: One or more environment variables are not set.", flush=True)
        return False
    return True


def setup_google_sheets_client():
    """Authenticates with Google Sheets using credentials from an environment variable or a local file."""
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]

        # ** THE FIX IS HERE **
        # Prioritize environment variable (for Heroku/Render)
        if GOOGLE_CREDENTIALS_JSON:
            print("Found GOOGLE_CREDENTIALS_JSON. Authenticating from environment variable.", flush=True)
            creds_json = json.loads(GOOGLE_CREDENTIALS_JSON)
            creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
        # Fallback to local file (for local testing)
        else:
            print(f"GOOGLE_CREDENTIALS_JSON not found. Authenticating from local file: {CREDENTIALS_FILE}", flush=True)
            creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)

        return gspread.authorize(creds)

    except FileNotFoundError:
        print(
            f"❌ ERROR: Neither GOOGLE_CREDENTIALS_JSON environment variable nor '{CREDENTIALS_FILE}' file were found.",
            flush=True)
        return None
    except Exception as e:
        print(f"❌ An error occurred during Google Sheets authentication: {e}", flush=True)
        return None


def get_todays_schedule(client):
    if not client: return []
    try:
        tz = pytz.timezone(TIMEZONE)
        today_str = datetime.now(tz).strftime("%Y-%m-%d")

        spreadsheet = client.open_by_key(GOOGLE_SHEET_KEY)
        worksheet = spreadsheet.worksheet(today_str)
        all_data = worksheet.get_all_values()[3:]
        schedule = []
        for row in all_data:
            time_str, activity = row[0], row[1]
            if not time_str or "Flexible" in activity: break
            if activity and activity != "---":
                schedule.append({"time": time_str, "activity": activity})
        print(f"✅ Successfully fetched schedule for today: {today_str}", flush=True)
        print(f"   Found {len(schedule)} timed tasks.", flush=True)
        return schedule
    except gspread.exceptions.WorksheetNotFound:
        print(f"⚠️ No worksheet found for today ({today_str}). Will try again later.", flush=True)
        return []
    except Exception as e:
        print(f"❌ An error occurred fetching the schedule: {e}", flush=True)
        return []


async def send_telegram_notification(bot, message):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"🚀 Notification sent: {message}", flush=True)
    except Exception as e:
        print(f"❌ Failed to send Telegram notification: {e}", flush=True)


async def notification_loop():
    if not check_env_variables(): return

    print(f"--- Starting Notification Service in timezone: {TIMEZONE} ---", flush=True)

    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    gspread_client = setup_google_sheets_client()

    schedule = get_todays_schedule(gspread_client)
    last_hour_checked = datetime.now(pytz.timezone(TIMEZONE)).hour
    notified_tasks = set()

    while True:
        tz = pytz.timezone(TIMEZONE)
        current_time = datetime.now(tz)

        if current_time.hour != last_hour_checked:
            print(f"\n🔄 New hour detected! Refreshing schedule...", flush=True)
            schedule = get_todays_schedule(gspread_client)
            last_hour_checked = current_time.hour
            notified_tasks.clear()

        current_time_str_12hr = current_time.strftime("%I:%M %p").upper()

        print(
            f"[{current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}] Checking for tasks. Current time: {current_time_str_12hr}",
            flush=True)

        for task in schedule:
            task_key = f"{task['time']}-{task['activity']}"
            if task['time'].upper() == current_time_str_12hr and task_key not in notified_tasks:
                message = f"🔔 Reminder: It's time for '{task['activity']}'"
                await send_telegram_notification(bot, message)
                notified_tasks.add(task_key)

        await asyncio.sleep(60)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    print("🚀 Flask web server started in a background thread.", flush=True)

    print("--- Preparing to start notification loop... ---", flush=True)
    asyncio.run(notification_loop())
