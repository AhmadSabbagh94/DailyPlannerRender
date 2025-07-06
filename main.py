import os
import time
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import telegram

# --- CONFIGURATION ---
# These should be set as environment variables on your hosting service (Render)
# For local testing, you can temporarily hardcode them.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7630172063:AAH5oN5PdB46eFZK1dwQG1MGsNNHiilh4_g")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5411991305")
GOOGLE_SHEET_KEY = os.environ.get("GOOGLE_SHEET_KEY", "1PPCkmnGxajOP27sxJZkrzbnOlSTQ_Dy5ZGulXJOXLpI")

# Path to your Google credentials file
# On Render, you will need to add your credentials.json as a secret file.
CREDENTIALS_FILE = "credentials.json"


def setup_google_sheets_client():
    """Authenticates with Google Sheets and returns a client object."""
    try:
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file"
        ]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        return gspread.authorize(creds)
    except FileNotFoundError:
        print(f"❌ ERROR: '{CREDENTIALS_FILE}' not found.")
        return None
    except Exception as e:
        print(f"❌ An error occurred during Google Sheets authentication: {e}")
        return None


def get_todays_schedule(client):
    """Fetches and parses today's schedule from the Google Sheet."""
    if not client:
        return []

    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        spreadsheet = client.open_by_key(GOOGLE_SHEET_KEY)
        worksheet = spreadsheet.worksheet(today_str)

        # Get all data, skipping the header rows
        all_data = worksheet.get_all_values()[3:]

        schedule = []
        for row in all_data:
            time_str, activity = row[0], row[1]
            # Stop parsing when we reach the flexible tasks section or an empty row
            if not time_str or "Flexible" in activity:
                break
            # Skip empty placeholder activities
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


def send_telegram_notification(bot, message):
    """Sends a message to your Telegram chat."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"🚀 Notification sent: {message}")
    except Exception as e:
        print(f"❌ Failed to send Telegram notification: {e}")


def main():
    """The main loop for the notification service."""
    print("--- Starting Notification Service ---")

    # Initialize the clients
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    gspread_client = setup_google_sheets_client()

    # Get the initial schedule
    schedule = get_todays_schedule(gspread_client)
    last_day_checked = datetime.now().day
    notified_tasks = set()  # To avoid sending duplicate notifications

    while True:
        current_time = datetime.now()

        # Check if it's a new day to fetch a new schedule
        if current_time.day != last_day_checked:
            print("\n🌅 New day detected! Fetching new schedule...")
            schedule = get_todays_schedule(gspread_client)
            last_day_checked = current_time.day
            notified_tasks.clear()  # Reset the notified tasks for the new day

        # Check for tasks to notify
        current_time_str_12hr = current_time.strftime("%I:%M %p").upper()

        for task in schedule:
            task_key = f"{task['time']}-{task['activity']}"
            if task['time'].upper() == current_time_str_12hr and task_key not in notified_tasks:
                message = f"🔔 Reminder: It's time for '{task['activity']}'"
                send_telegram_notification(bot, message)
                notified_tasks.add(task_key)

        # Wait for 60 seconds before checking again
        time.sleep(60)


if __name__ == "__main__":
    main()
