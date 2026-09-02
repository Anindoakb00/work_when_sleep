import sqlite3
import time
from datetime import datetime
from pathlib import Path

from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By

from Bots.AllPageBot import AllPageBot


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_DIRECTORY / "miracle.db"


def init_message_log_table(connection):
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fb_message_log (
            _pk_fb_message_log INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_name TEXT,
            message_text TEXT NOT NULL,
            captured_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


def save_message(connection, conversation_name, message_text):
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO fb_message_log (conversation_name, message_text, captured_at)
        VALUES (?, ?, ?)
        """,
        (conversation_name, message_text, datetime.utcnow().isoformat(timespec="seconds")),
    )
    connection.commit()


def is_invalid_session_error(error):
    return "invalid session id" in str(error).lower()


def main():
    all_page = AllPageBot()
    connection = None

    try:
        try:
            all_page.test_login()
            input("Press any key: ")
        except (NoSuchElementException, TimeoutException):
            print("Already logged in")
        except WebDriverException as error:
            if is_invalid_session_error(error):
                print("Chrome session ended before the message scan started.")
                return
            raise

        all_page.driver.get("https://www.facebook.com/messages/")
        all_page.driver.implicitly_wait(4)

        connection = sqlite3.connect(str(DATABASE_PATH))
        init_message_log_table(connection)

        input("Press any key: ")
        unread_message = all_page.driver.find_elements(
            By.XPATH, "//div[@data-visualcompletion='ignore-dynamic']/child::a"
        )
        print(f"Found {len(unread_message)} conversations")
        print("=" * 80)
        print("AUTO-REPLY: DISABLED")
        print("All messages will be saved to DB and printed to console")
        print("=" * 80)

        for message in unread_message:
            input("Press any key: ")
            conversation_name = (message.text or "").strip()
            message.click()
            all_page.driver.implicitly_wait(4)
            time.sleep(4)

            last_message_text = all_page.driver.find_elements(
                By.XPATH, "//div[@data-testid='message-container']"
            )
            if not last_message_text:
                continue

            latest_message = (last_message_text[-1].text or "").strip()
            if not latest_message:
                continue

            save_message(connection, conversation_name or None, latest_message)
            timestamp = datetime.utcnow().isoformat(timespec="seconds")
            print(f"\n{'*' * 80}")
            print(f"[{timestamp}] CONVERSATION: {conversation_name}")
            print(f"[MESSAGE]: {latest_message}")
            print(f"[STATUS]: ✓ SAVED TO DB")
            print(f"{'*' * 80}\n")
    except WebDriverException as error:
        if is_invalid_session_error(error):
            print("Chrome session ended unexpectedly. Restart the browser and try again.")
            return
        raise
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
