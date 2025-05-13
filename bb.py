#!/usr/bin/env python3

import shutil
import sys
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json
import uuid
import time
import os
import random
import re
import subprocess
import math
import logging
# لا حاجة للاستيراد، استخدم هذه الدالة مباشرة في الملف:
def escape_markdown(text):
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
# Consider loading sensitive data like BOT_TOKEN from environment variables or a config file
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7704039167:AAH7W8fViHZpa-8s7EYyafzUY4j-9URFJHo")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@Sayo_bots")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 2061867832))
BLOCKED_USERS_FILE = "./sayo_bot_data/blocked_users.txt"
UPGRADED_USERS_FILE = "./sayo_bot_data/upgraded_users.txt"
USER_DATA_FILE = "./sayo_bot_data/user_data.json"
VOICES_PER_PAGE = 15
BANNED_WORDS = ["كس", "منيوج", "كحبة", "عير", "عاهرة", "بلاع", "ينيج", "كسمك","كسختك","كس اختك","كس امك","كس أمك","كس أختك","خرب","طيز","طيزك","صرم","صرمك","عاهرة","عاهره", "كحبه", "بلاعة", "بلاعه", "نيج" ,"نيك" ,"انيك" ,"ينيك" ,"أنيك" ,"كوس" ,"زب", "زبي", "عيري", "عيرك", "مشتهي" ,"مشتهية" ,"مشتهيه", "اه" ,"أه", "كسي", "كوسي" ,"عنابة" ,"عنابه", "عنابتي" ,"منيك" ,"عرص", "شرموط" ,"شرموطة" ,"شرموطه" ,"انيج" ,"انيجج", "انيجك"]
MAX_CHARS_FREE = 200
MAX_CHARS_PREMIUM_CHUNK = 200
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "@G35GG")
TEMP_DIR = "./sayo_bot_audio" # Relative path in the current working directory
API_RETRY_DELAY = 5 # Base delay in seconds
API_MAX_RETRIES = 3 # Increased retries
INTER_CHUNK_DELAY = 2 # Reduced delay, rely more on retries
API_TIMEOUT = 30 # General timeout for requests
TTS_API_TIMEOUT = 180 # Longer timeout specifically for TTS generation

# --- Global Variables & Initialization ---
import shutil
import sys
import shutil
import sys
import logging
import telebot


def check_ffmpeg_on_startup():
    """Checks if ffmpeg is installed and accessible in PATH."""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        error_msg = ("CRITICAL: ffmpeg not found. FFmpeg is essential for audio processing. "
                     "Please install ffmpeg and ensure it is in your system PATH. "
                     "On Debian/Ubuntu, you can typically install it using: "
                     "sudo apt update && sudo apt install ffmpeg")
        logging.critical(error_msg)  # Assumes logging is already configured
        print(error_msg, file=sys.stderr)
        sys.exit(1)
    else:
        logging.info(f"ffmpeg found at: {ffmpeg_path}")  # تم تصحيح التنسيق هنا
        print(f"ffmpeg found at: {ffmpeg_path}")

# استدعاء دالة التحقق من ffmpeg

# تهيئة البوت بعد التأكد من ffmpeg
try:
    bot = telebot.TeleBot(BOT_TOKEN)
except Exception as e:
    logging.critical(f"Failed to initialize Telegram Bot: {e}")
    sys.exit(1)
check_ffmpeg_on_startup()

user_last_voice = {} # {user_id: voice_data}
user_speech_speed = {} # {user_id: float_speed, default: 1.0}
user_state = {} # {user_id: state}
admin_actions = {} # {admin_id/key: data}
user_data = {} # {user_id: username}

# --- Utility Functions ---
def safe_int_conversion(value, default=None):
    """Safely converts a value to an integer."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def cleanup_temp_file(file_path):
    """Safely removes a temporary file if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logging.info(f"Cleaned up temporary file: {file_path}")
        except OSError as e:
            logging.error(f"Error removing temporary file {file_path}: {e}")

# --- User Data & State Management ---
def load_users(filename):
    """Loads a set of user IDs from a file, handling potential errors."""
    user_ids = set()
    if not os.path.exists(filename):
        logging.warning(f"User file not found: {filename}. Starting with empty set.")
        return user_ids
    try:
        with open(filename, 'r') as f:
            for line in f:
                user_id = safe_int_conversion(line.strip())
                if user_id is not None:
                    user_ids.add(user_id)
    except IOError as e:
        logging.error(f"Error reading user file {filename}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error loading user file {filename}: {e}")
    return user_ids

def save_users(filename, user_set):
    """Saves a set of user IDs to a file, handling potential errors."""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w') as f:
            for user_id in user_set:
                f.write(f"{user_id}\n")
    except IOError as e:
        logging.error(f"Error writing user file {filename}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error saving user file {filename}: {e}")

def load_user_data():
    """Loads the user ID to username mapping from a JSON file."""
    if not os.path.exists(USER_DATA_FILE):
        logging.warning(f"User data file not found: {USER_DATA_FILE}. Starting with empty data.")
        return {}
    try:
        with open(USER_DATA_FILE, 'r') as f:
            data = json.load(f)
            # Ensure keys are integers
            return {safe_int_conversion(k): v for k, v in data.items() if safe_int_conversion(k) is not None}
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from user data file {USER_DATA_FILE}: {e}")
        return {}
    except IOError as e:
        logging.error(f"Error reading user data file {USER_DATA_FILE}: {e}")
        return {}
    except Exception as e:
        logging.error(f"Unexpected error loading user data file {USER_DATA_FILE}: {e}")
        return {}

def save_user_data():
    """Saves the user ID to username mapping to a JSON file."""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(USER_DATA_FILE), exist_ok=True)
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data, f, indent=4)
    except IOError as e:
        logging.error(f"Error writing user data file {USER_DATA_FILE}: {e}")
    except TypeError as e:
        logging.error(f"Error serializing user data to JSON: {e}")
    except Exception as e:
        logging.error(f"Unexpected error saving user data file {USER_DATA_FILE}: {e}")

def update_user_data(user_id, username):
    """Updates the username for a given user ID and saves."""
    if not isinstance(user_id, int):
        logging.warning(f"Attempted to update user data with non-integer ID: {user_id}")
        return
    # Only update if username is provided and different, or if user_id is new
    # Ensure username is stored as string, handle None case
    current_username = user_data.get(user_id)
    new_username = str(username) if username else None
    if new_username and (user_id not in user_data or current_username != new_username):
        user_data[user_id] = new_username
        save_user_data()

def find_user_id_by_username(username_to_find):
    """Finds a user ID by searching the stored username mapping (case-insensitive)."""
    if not username_to_find:
        return None
    username_lower = username_to_find.lower()
    for user_id, stored_username in user_data.items():
        if stored_username and stored_username.lower() == username_lower:
            return user_id
    return None

# --- Initial Data Loading ---
blocked_users = load_users(BLOCKED_USERS_FILE)
upgraded_users = load_users(UPGRADED_USERS_FILE)
user_data = load_user_data()

def is_blocked(user_id):
    return user_id in blocked_users

def is_upgraded(user_id):
    # Admin is always considered upgraded
    return user_id == ADMIN_ID or user_id in upgraded_users

def set_user_state(user_id, state):
    if state is None:
        user_state.pop(user_id, None)
        logging.debug(f"Cleared state for user {user_id}")
    else:
        user_state[user_id] = state
        logging.debug(f"Set state for user {user_id} to {state}")

def get_user_state(user_id):
    return user_state.get(user_id)

# --- Banned Words Normalization ---
def normalize_text(text):
    if not isinstance(text, str):
        return ""
    # Remove Arabic diacritics (vowels, etc.)
    text = re.sub(r'[\[\u064B-\u065F\]]', '', text)
    # Remove Tatweel (character elongation)
    text = text.replace('\u0640', '')
    # Remove some other potentially problematic Unicode characters and excessive whitespace
    text = re.sub(r'[\[\u0600-\u0605\u061C\u0670\u06D6-\u06ED\uFE00-\uFE0F\r\n\t\f\v\s\]]+', ' ', text).strip()
    # Normalize Arabic letters (Alef variants, Teh Marbuta)
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    text = text.replace('ة', 'ه')
    return text.lower()

normalized_banned_words = {normalize_text(word) for word in BANNED_WORDS if word} # Use a set for faster lookups

def contains_banned_word(text):
    if not text: return False
    normalized_input = normalize_text(text)
    # Check for whole word matches
    for banned_word in normalized_banned_words:
        if re.search(r'\b' + re.escape(banned_word) + r'\b', normalized_input):
            logging.warning(f"Banned word '{banned_word}' detected.")
            return True
    return False

# --- Text Splitting Helper ---
def split_text_into_chunks(text, max_length=MAX_CHARS_PREMIUM_CHUNK):
    """Splits text into chunks <= max_length, respecting word boundaries."""
    chunks = []
    start = 0
    while start < len(text):
        if len(text) - start <= max_length:
            chunks.append(text[start:])
            break
        end = start + max_length
        last_space = text.rfind(' ', start, end + 1)
        if last_space != -1 and last_space > start:
            chunks.append(text[start:last_space])
            start = last_space + 1
        else:
            # No space found or space is at the start, force split
            chunks.append(text[start:end])
            start = end
    return [chunk for chunk in chunks if chunk.strip()]

 # Timeout in seconds for each ffmpeg command

TEMP_DIR = "temp_audio"
FFMPEG_TIMEOUT = 120

class VoiceGenerationError(Exception):
    pass

def convert_and_combine_audio(ogg_files, final_mp3_path, speech_speed=1.0):
    """Combines multiple OGG files into a single MP3 file using ffmpeg with timeouts."""
    if not ogg_files:
        logging.error("No OGG files provided for conversion.")
        return None, []

    # Ensure TEMP_DIR exists
    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
    except OSError as e:
        logging.error(f"Failed to create temporary directory {TEMP_DIR}: {e}")
        raise VoiceGenerationError(f"فشل في إنشاء مجلد مؤقت: {e}") from e

    # Ensure final MP3 path directory exists
    try:
        os.makedirs(os.path.dirname(final_mp3_path), exist_ok=True)
    except OSError as e:
        logging.error(f"Failed to create output directory {os.path.dirname(final_mp3_path)}: {e}")
        raise VoiceGenerationError(f"فشل في إنشاء مجلد الإخراج: {e}") from e

    temp_files_created = []
    final_audio_data = None

    try:
        if len(ogg_files) == 1:
            source_ogg = ogg_files[0]
            temp_files_created.append(source_ogg)
            convert_command = [
                "ffmpeg", "-y", "-i", source_ogg,
                "-vn", "-filter:a", f"atempo={speech_speed}", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                final_mp3_path
            ]
            logging.info(f"Running ffmpeg command (single file): {' '.join(convert_command)}")
            result = subprocess.run(
                convert_command, check=True, capture_output=True,
                text=True, encoding="utf-8", errors="ignore",
                timeout=FFMPEG_TIMEOUT
            )
            logging.info(f"FFmpeg conversion stdout: {result.stdout}")
            logging.info(f"FFmpeg conversion stderr: {result.stderr}")
            temp_files_created.append(final_mp3_path)

        else:
            list_file_path = os.path.join(TEMP_DIR, f"mylist_{uuid.uuid4().hex}.txt")
            merged_ogg_path = os.path.join(TEMP_DIR, f"merged_{uuid.uuid4().hex}.ogg")
            temp_files_created.extend(ogg_files)
            temp_files_created.append(list_file_path)
            temp_files_created.append(merged_ogg_path)

            try:
                with open(list_file_path, "w", encoding="utf-8") as f:
                    for ogg_file in ogg_files:
                        abs_path = os.path.abspath(ogg_file)
                        safe_path = abs_path.replace("'", "'\\''")
                        f.write(f"file '{safe_path}'\n")
            except IOError as e:
                logging.error(f"Failed to create ffmpeg list file {list_file_path}: {e}")
                raise

            # تعديل هنا: إعادة ترميز بدلاً من "-c copy"
            concat_command = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_file_path, "-acodec", "libvorbis", merged_ogg_path
            ]
            logging.info(f"Running ffmpeg command (concat): {' '.join(concat_command)}")
            result_concat = subprocess.run(
                concat_command, check=True, capture_output=True,
                text=True, encoding="utf-8", errors="ignore",
                timeout=FFMPEG_TIMEOUT
            )
            logging.info(f"FFmpeg concat stdout: {result_concat.stdout}")
            logging.info(f"FFmpeg concat stderr: {result_concat.stderr}")

            convert_command = [
                "ffmpeg", "-y", "-i", merged_ogg_path,
                "-vn", "-filter:a", f"atempo={speech_speed}", "-ar", "44100", "-ac", "2", "-b:a", "192k",
                final_mp3_path
            ]
            logging.info(f"Running ffmpeg command (convert merged): {' '.join(convert_command)}")
            result_convert = subprocess.run(
                convert_command, check=True, capture_output=True,
                text=True, encoding="utf-8", errors="ignore",
                timeout=FFMPEG_TIMEOUT
            )
            logging.info(f"FFmpeg conversion stdout: {result_convert.stdout}")
            logging.info(f"FFmpeg conversion stderr: {result_convert.stderr}")
            temp_files_created.append(final_mp3_path)

        if os.path.exists(final_mp3_path):
            try:
                with open(final_mp3_path, "rb") as f:
                    final_audio_data = f.read()
            except IOError as e:
                logging.error(f"Failed to read final MP3 file {final_mp3_path}: {e}")
                final_audio_data = None
        else:
            logging.error(f"Final MP3 file not found after conversion: {final_mp3_path}")

    except subprocess.TimeoutExpired as e:
        logging.error(f"ffmpeg command timed out after {FFMPEG_TIMEOUT} seconds.")
        logging.error(f"Command: {' '.join(e.cmd)}")
        stderr_output = e.stderr
        if isinstance(stderr_output, bytes):
            stderr_output = stderr_output.decode("utf-8", errors="ignore")
        logging.error(f"FFmpeg stderr (last lines): {stderr_output[-500:] if stderr_output else 'N/A'}")
        final_audio_data = None
        raise VoiceGenerationError(f"فشل تحويل الصوت: استغرقت العملية وقتاً طويلاً جداً (تجاوز {FFMPEG_TIMEOUT} ثانية).") from e

    except subprocess.CalledProcessError as e:
        logging.error(f"Error during ffmpeg processing (Return code: {e.returncode})")
        logging.error(f"Command: {' '.join(e.cmd)}")
        stderr_output = e.stderr
        if isinstance(stderr_output, bytes):
            stderr_output = stderr_output.decode("utf-8", errors="ignore")
        logging.error(f"FFmpeg stderr: {stderr_output}")
        final_audio_data = None
        raise VoiceGenerationError(f"فشل تحويل الصوت باستخدام ffmpeg. رمز الخطأ: {e.returncode}. تحقق من سجلات الخادم للمزيد من التفاصيل.") from e

    except Exception as e:
        logging.error(f"An unexpected error occurred during audio processing: {e}", exc_info=True)
        final_audio_data = None
        raise VoiceGenerationError(f"حدث خطأ غير متوقع أثناء معالجة الصوت: {e}") from e

    return final_audio_data, temp_files_created

# --- Telegram API Interaction Helpers ---
def safe_send_message(chat_id, text, **kwargs):
    """Sends a message, catching potential Telegram API errors."""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Telegram API error sending message to {chat_id}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error sending message to {chat_id}: {e}")
    return None

def safe_edit_message(text, chat_id, message_id, **kwargs):
    """Edits a message, catching potential Telegram API errors."""
    try:
        return bot.edit_message_text(text, chat_id, message_id, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is not modified' in str(e):
            logging.debug(f"Message {message_id} in chat {chat_id} was not modified.")        
        else:
            logging.error(f"Telegram API error editing message {message_id} in {chat_id}: {e}")
            # Fallback: Try sending a new message if editing fails critically
            if hasattr(e, "description") and "message to edit not found" not in e.description:
                 safe_send_message(chat_id, text, **kwargs)
    except Exception as e:
        logging.error(f"Unexpected error editing message {message_id} in {chat_id}: {e}")
        # Fallback: Try sending a new message
        safe_send_message(chat_id, text, **kwargs)
    return None
def safe_answer_callback(callback_query_id, text=None, **kwargs):
    """Answers a callback query, catching potential errors."""
    try:
        bot.answer_callback_query(callback_query_id, text=text, **kwargs)
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Telegram API error answering callback query {callback_query_id}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error answering callback query {callback_query_id}: {e}")

def safe_delete_message(chat_id, message_id):
    """Safely deletes a message."""
    try:
        bot.delete_message(chat_id, message_id)
    except telebot.apihelper.ApiTelegramException as e:
        logging.warning(f"Could not delete message {message_id} in chat {chat_id}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error deleting message {message_id} in {chat_id}: {e}")

# --- Subscription & Block Check Decorator ---
def check_access(func):
    def wrapper(message_or_call):
        try:
            user = message_or_call.from_user
            user_id = user.id
            username = user.username

            if isinstance(message_or_call, telebot.types.Message):
                chat_id = message_or_call.chat.id
            elif isinstance(message_or_call, telebot.types.CallbackQuery):
                chat_id = message_or_call.message.chat.id
            else:
                logging.warning("check_access: Could not determine chat_id.")
                return

            update_user_data(user_id, username)

            if is_blocked(user_id):
                logging.info(f"Blocked user {user_id} tried to access.")
                safe_send_message(chat_id, f"🚫 أنت محظور من استخدام البوت. للطعن راسل المبرمج {OWNER_USERNAME}")
                if isinstance(message_or_call, telebot.types.CallbackQuery):
                    safe_answer_callback(message_or_call.id)
                return

            if user_id != ADMIN_ID:
                channels = [
                    {'username': '@S_A_Y_O', 'url': 'https://t.me/S_A_Y_O'},
                    {'username': '@Sayo_Bots', 'url': 'https://t.me/Sayo_Bots'}
                ]

                for channel in channels:
                    try:
                        member = bot.get_chat_member(channel['username'], user_id)
                        if member.status not in ['member', 'administrator', 'creator']:
                            raise Exception(f"User status in {channel['username']}: {member.status}")
                    except Exception as e:
                        logging.info(f"Subscription check failed for user {user_id} in channel {channel['username']}: {e}")
                        markup = InlineKeyboardMarkup()
                        markup.add(InlineKeyboardButton("🔗 الإشتراك في القناة", url=channel['url']))
                        safe_send_message(chat_id, f"⚠️ عذراً، يجب عليك الاشتراك في قناة البوت أولاً: {channel['username']}", reply_markup=markup)
                        if isinstance(message_or_call, telebot.types.CallbackQuery):
                            safe_answer_callback(message_or_call.id)
                        set_user_state(user_id, None)
                        return

            func(message_or_call)

        except Exception as e:
            logging.error(f"Error in access check decorator: {e}", exc_info=True)
            try:
                chat_id_fallback = None
                callback_id_fallback = None
                if isinstance(message_or_call, telebot.types.Message):
                    chat_id_fallback = message_or_call.chat.id
                elif isinstance(message_or_call, telebot.types.CallbackQuery):
                    chat_id_fallback = message_or_call.message.chat.id
                    callback_id_fallback = message_or_call.id

                if chat_id_fallback:
                    safe_send_message(chat_id_fallback, "❌ حدث خطأ داخلي غير متوقع. تم إبلاغ المطور.")
                if callback_id_fallback:
                    safe_answer_callback(callback_id_fallback, "❌ خطأ داخلي")
            except Exception as notify_err:
                logging.error(f"Failed to notify user about decorator error: {notify_err}")

    return wrapper

# --- Voice API Functions ---
# Define custom exceptions for API errors
class VoiceAPIError(Exception):
    """Base exception for voice API errors."""
    pass
class VoiceAuthError(VoiceAPIError):
    """Exception for authentication failures."""
    pass
class VoiceGenerationError(VoiceAPIError):
    """Exception for TTS generation failures."""
    pass
class VoiceListError(VoiceAPIError):
    """Exception for failures fetching voice list."""
    pass

def Fix():
    """Fetches the list of available voices from the API with retry logic."""
    url = "https://ai-voice.nyc3.cdn.digitaloceanspaces.com/data/data.json"
    headers = FOU() # Get headers
    last_error = None

    for attempt in range(API_MAX_RETRIES + 1):
        wait_time = API_RETRY_DELAY * (2 ** attempt) # Exponential backoff
        try:
            response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            data = response.json()
            voices = data.get(	"voices")
            if not isinstance(voices, list):
                logging.error(f"Voice list format unexpected: {type(voices)}")
                last_error = VoiceListError("تنسيق قائمة الأصوات غير متوقع من الخادم.")
                # No retry for format errors
                raise last_error
            logging.info("Successfully fetched voice list.")
            return voices # Success

        except requests.exceptions.Timeout as e:
            logging.warning(f"Timeout fetching voices from {url} (Attempt {attempt + 1}/{API_MAX_RETRIES + 1}): {e}")
            last_error = VoiceListError(f"انتهت مهلة الاتصال بخادم الأصوات: {e}")
        except requests.exceptions.ConnectionError as e:
            logging.warning(f"Connection Error fetching voices from {url} (Attempt {attempt + 1}/{API_MAX_RETRIES + 1}): {e}")
            last_error = VoiceListError(f"خطأ في الاتصال بخادم الأصوات: {e}")
            wait_time *= 1.5 # Wait slightly longer for connection errors
        except requests.exceptions.RequestException as e:
            status_code = e.response.status_code if e.response else None
            logging.warning(f"HTTP Error fetching voices from {url} (Attempt {attempt + 1}/{API_MAX_RETRIES + 1}): Status={status_code}, Error={e}")
            last_error = VoiceListError(f"خطأ HTTP ({status_code}) عند جلب قائمة الأصوات: {e}")
            # Don	 retry client errors (4xx) other than 429
            if status_code and 400 <= status_code < 500 and status_code != 429:
                logging.error(f"Client error {status_code} fetching voices. No retries.")
                raise last_error from e
        except json.JSONDecodeError as e:
            logging.error(f"JSON Decode Error fetching voices from {url}: {e}")
            last_error = VoiceListError("فشل في قراءة قائمة الأصوات من الخادم (تنسيق غير صالح).")
            # No retry for JSON errors
            raise last_error from e
        except Exception as e:
            logging.error(f"Unexpected error fetching voices (Attempt {attempt + 1}/{API_MAX_RETRIES + 1}): {e}", exc_info=True)
            last_error = VoiceListError(f"خطأ غير متوقع أثناء جلب قائمة الأصوات: {e}")
            # Consider whether to retry unexpected errors

        # Wait before retrying if not the last attempt
        if attempt < API_MAX_RETRIES:
            logging.info(f"Waiting {wait_time:.2f} seconds before retrying voice list fetch...")
            time.sleep(wait_time)

    # If loop completes without returning, all retries failed
    logging.error(f"Max retries ({API_MAX_RETRIES}) reached fetching voice list. Last error: {last_error}")
    raise last_error if last_error else VoiceListError(f"فشل جلب قائمة الأصوات بعد {API_MAX_RETRIES + 1} محاولات.")
def Fox():
    """Generates unique IDs and timestamp for API calls."""
    Id_levi1 = uuid.uuid4().hex
    start_time = str(int(time.time() * 1000))
    # Format seems consistent with Firebase Cloud Messaging (FCM) token
    Id_levi9 = f"{uuid.uuid4().hex}:APA91b{uuid.uuid4().hex[:20]}" # Mimic structure
    return Id_levi1, start_time, Id_levi9

def FOU():
    """Returns headers mimicking the mobile app's request."""
    # Headers seem specific to an Android app environment
    # Consider making these configurable or dynamic if they change often
    return {
        'User-Agent': "Mozilla/5.0 (Linux; Android 11; Redmi Note 8 Build/RKQ1.201004.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0.6668.100 Mobile Safari/537.36",
        'Accept-Encoding': "gzip, deflate, br, zstd",
        'Content-Type': "application/json",
        'sec-ch-ua-platform': '"Android"',
        'sec-ch-ua': '"Android WebView";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        'sec-ch-ua-mobile': '?1',
        'origin': "http://localhost",
        'x-requested-with': "com.leonfiedler.voiceaj",
        'sec-fetch-site': "cross-site",
        'sec-fetch-mode': "cors",
        'sec-fetch-dest': "empty",
        'referer': "http://localhost/",
        'accept-language': "ar-EG,ar;q=0.9,en-US;q=0.8,en;q=0.7",
        'priority': 'u=1, i'
    }

def ABC():
    """Handles authentication/signup with Google Identity Toolkit (Firebase Auth)."""
    try:
        # Step 1: Sign up a new anonymous user
        signup_url = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/signupNewUser"
        # API key might be restricted, consider security implications
        api_key = "AIzaSyDk5Vr0fvGX3AF3mNfMghP6Q-ECoBYT7aE"
        params = {'key': api_key}
        signup_payload = json.dumps({"returnSecureToken": True}) # Request secure token
        auth_headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 11; Redmi Note 8 Build/RKQ1.201004.002)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json",
            'X-Android-Package': "com.leonfiedler.voiceaj",
            'X-Android-Cert': "61ED377E85D386A8DFEE6B864BD85B0BFAA5AF81",
            'Accept-Language': "ar-EG, en-US",
            'X-Client-Version': "Android/Fallback/X23000000/FirebaseCore-Android",
            'X-Firebase-GMPID': "1:444011263758:android:acbabc2d1f24666531495f",
            'X-Firebase-Client': "H4sIAAAAAAAAAKtWykhNLCpJSk0sKVayio7VUSpLLSrOzM9TslIyUqoFAFyivEQfAAAA"
        }
        signup_response = requests.post(signup_url, params=params, data=signup_payload, headers=auth_headers, timeout=API_TIMEOUT)
        signup_response.raise_for_status()
        signup_data = signup_response.json()
        id_token = signup_data.get('idToken')
        local_id = signup_data.get('localId') # UID is often returned directly on signup

        if not id_token or not local_id:
            logging.error(f"idToken or localId missing in signup response: {signup_data}")
            raise VoiceAuthError("فشل الحصول على بيانات المصادقة الأولية.")

        # Step 2: Get account info (might not be strictly necessary if signup returns UID, but good validation)
        getinfo_url = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/getAccountInfo"
        getinfo_payload = json.dumps({"idToken": id_token})
        getinfo_response = requests.post(getinfo_url, params=params, data=getinfo_payload, headers=auth_headers, timeout=API_TIMEOUT)
        getinfo_response.raise_for_status()
        getinfo_data = getinfo_response.json()

        users = getinfo_data.get('users')
        if not users or not isinstance(users, list) or len(users) == 0:
            logging.error(f"User info not found in getAccountInfo response: {getinfo_data}")
            raise VoiceAuthError("فشل التحقق من بيانات المصادقة.")

        # Verify localId matches
        if users[0].get('localId') != local_id:
             logging.error(f"Mismatch between signup localId ({local_id}) and getInfo localId ({users[0].get('localId')})")
             raise VoiceAuthError("عدم تطابق في بيانات المصادقة.")

        created_at = users[0].get('createdAt') # Timestamp of user creation
        if not created_at:
            logging.warning("createdAt timestamp missing from user info.")
            # Handle potential issues if C9 is strictly required later

        logging.info(f"Firebase authentication successful. UID: {local_id}")
        return id_token, local_id, created_at

    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP Error during authentication (ABC): {e}")
        status_code = e.response.status_code if e.response else 'N/A'
        response_text = e.response.text if e.response else 'N/A'
        logging.error(f"Response status: {status_code}, Response text: {response_text}")
        raise VoiceAuthError(f"خطأ في الاتصال بخادم المصادقة: {status_code}") from e
    except json.JSONDecodeError as e:
        logging.error(f"JSON Decode Error during authentication (ABC): {e}")
        raise VoiceAuthError("فشل في قراءة استجابة المصادقة.") from e
    except Exception as e:
        logging.error(f"Unexpected error during authentication (ABC): {e}", exc_info=True)
        raise VoiceAuthError("خطأ غير متوقع أثناء المصادقة.") from e

def EFG(Id_levi2, token2, Id_levi1):
    """Registers the user/device with the voice service backend."""
    try:
        url = "https://connect.getvoices.ai/api/v1/user"
        payload = json.dumps({
            "uid": Id_levi2,
            "isNew": True, # Assume new session/device each time for simplicity
            "uuid": f"android_{Id_levi1}",
            "platform": "android",
            "appVersion": "1.9.1"
        })
        headers = FOU()
        headers['authorization'] = token2 # Firebase ID Token
        response = requests.post(url, data=payload, headers=headers, timeout=API_TIMEOUT)
        logging.info(f"User registration (EFG) call status: {response.status_code}")
        # Log non-2xx responses but don't necessarily raise an error unless critical
        if not response.ok:
             logging.warning(f"User registration (EFG) returned non-OK status {response.status_code}: {response.text}")
        # response.raise_for_status() # Optional: raise error for non-2xx status
    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP Error during user registration (EFG): {e}")
        # Non-critical? Decide if this should raise VoiceAPIError
    except Exception as e:
        logging.error(f"Unexpected error during user registration (EFG): {e}", exc_info=True)
        # Non-critical?

def HIG_with_retry(Id_levi2, token2, C9, Id_levi1, Id_levi9, Id_levi, text, voice_name):
    """Wrapper for HIG function with exponential backoff retry logic."""
    for attempt in range(API_MAX_RETRIES + 1):
        wait_time = API_RETRY_DELAY * (2 ** attempt) # Exponential backoff
        try:
            audio_data = HIG(Id_levi2, token2, C9, Id_levi1, Id_levi9, Id_levi, text, voice_name)
            if audio_data:
                return audio_data # Success            else:
                # Treat empty response as potential transient issue
                logging.warning(f"HIG returned empty data for voice 	'{voice_name}	' (Attempt {attempt + 1}/{API_MAX_RETRIES + 1})")
                error_reason = "API returned empty data"

        except requests.exceptions.Timeout as e:
            logging.warning(f"Timeout during TTS generation (HIG) for voice 	'{voice_name}' (Attempt {attempt + 1}/{API_MAX_RETRIES + 1}): {e}")
            error_reason = "Timeout"
        except requests.exceptions.ConnectionError as e:
            logging.warning(f"Connection Error during TTS generation (HIG) for voice 	'{voice_name}' (Attempt {attempt + 1}/{API_MAX_RETRIES + 1}): {e}")
            error_reason = f"Connection Error: {type(e).__name__}"
            # Wait longer for connection errors before retry
            wait_time *= 1.5
        except requests.exceptions.RequestException as e:
            status_code = e.response.status_code if e.response else None
            response_text = e.response.text if e.response else 'No response body'
            logging.warning(f"HTTP Error during TTS generation (HIG) for voice 	'{voice_name}' (Attempt {attempt + 1}/{API_MAX_RETRIES + 1}): Status={status_code}, Response='	{response_text[:200]}...', Error={e}")
            if status_code:
                error_reason = f"HTTP Error: {status_code}"
                # Don't retry on client errors (4xx) except maybe 429 (Too Many Requests)
                if status_code == 429:
                    logging.warning("Rate limit likely hit. Increasing wait time.")
                    wait_time *= 2 # Increase wait time further for rate limiting
                elif 400 <= status_code < 500 and status_code != 429:
                    logging.error(f"Client error {status_code} during TTS generation. No retries. Response: {response_text}")
                    # Provide more specific user-facing error for common client issues
                    user_error_msg = f"خطأ من جانب الخادم ({status_code}) أثناء إنشاء الصوت. قد يكون النص غير مدعوم، أو هناك مشكلة في الحساب، أو الطلب غير صحيح."
                    if status_code == 400:
                        user_error_msg = f"خطأ في الطلب (400): تأكد من أن النص المرسل صالح ولا يحتوي على رموز غير مدعومة."
                    elif status_code == 401 or status_code == 403:
                        user_error_msg = f"خطأ في المصادقة ({status_code}): مشكلة في الوصول إلى الخدمة. قد تحتاج إلى إعادة المحاولة لاحقاً."
                    raise VoiceGenerationError(user_error_msg) from e
            else:
                # Handle other RequestExceptions that are not ConnectionError or Timeout
                error_reason = f"Network Error: {type(e).__name__}"
                logging.warning(f"Unhandled RequestException during TTS generation: {e}")

        except VoiceGenerationError: # Re-raise specific generation errors immediately
             raise
        except Exception as e:
            logging.error(f"Unexpected error during TTS generation (HIG) for voice 	'{voice_name}	' (Attempt {attempt + 1}/{API_MAX_RETRIES + 1}): {e}", exc_info=True)
            error_reason = f"Unexpected Error: {type(e).__name__}"
        # If not the last attempt, wait before retrying
        if attempt < API_MAX_RETRIES:
            logging.info(f"Waiting {wait_time:.2f} seconds before retrying TTS generation (Reason: {error_reason})...")
            time.sleep(wait_time)
        else:
            logging.error(f"Max retries ({API_MAX_RETRIES}) reached for TTS generation (voice 	'{voice_name}	'). Last error: {error_reason}")
            # Provide a clearer final error message
            final_error_msg = f"فشل إنشاء الصوت بعد {API_MAX_RETRIES + 1} محاولات. السبب الأخير: {error_reason}"
            if error_reason.startswith("HTTP Error:"):
                final_error_msg += ". قد تكون هناك مشكلة مؤقتة في الخدمة أو في الشبكة."
            elif error_reason.startswith("Connection Error:"):
                final_error_msg += ". يرجى التحقق من اتصال الشبكة والمحاولة مرة أخرى."
            elif error_reason == "Timeout":
                final_error_msg += ". استغرقت العملية وقتاً طويلاً جداً للرد."
            raise VoiceGenerationError(final_error_msg)

def HIG(Id_levi2, token2, C9, Id_levi1, Id_levi9, Id_levi, text, voice_name):
    """Sends text to the API to generate speech audio stream."""
    url = "https://connect.getvoices.ai/api/v1/text2speech/stream"
    payload = json.dumps({
        "voiceId": Id_levi,
        "text": text,
        "deviceId": Id_levi1,
        "uid": Id_levi2,
        "startTime": C9, # Might be optional or less critical
        "translate": None,
        "fcmToken": Id_levi9,
        "appVersion": "1.9.1"
    })
    headers = FOU()
    headers['authorization'] = token2

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=TTS_API_TIMEOUT)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        if response.content:
            # Check content type? Might be audio/ogg
            # logging.debug(f"Received {len(response.content)} bytes of audio data.")
            return response.content
        else:
            # Log warning if content is empty despite 2xx status
            logging.warning(f"HIG received empty content for voice '{voice_name}' despite status {response.status_code}.")
            return None # Handled by retry wrapper
    except requests.exceptions.RequestException as e:
        # Let the retry wrapper handle logging and retries for RequestExceptions
        raise
    except Exception as e:
        # Catch unexpected errors here
        logging.error(f"Unexpected error in HIG function: {e}", exc_info=True)
        raise VoiceGenerationError("حدث خطأ غير متوقع داخل وظيفة إنشاء الصوت.") from e

# --- Bot Handlers ---
def display_start_menu(chat_id, user_id, first_name, username, edit_message_id=None):
    status = "مرقى ✨" if is_upgraded(user_id) else "غير مرقى"
    # Use HTML parsing for better formatting control if needed, but Markdown is simpler
    welcome_text = f"""
—————————————————————————•
👋 مرحباً بك: {escape_markdown(first_name)}
🆔 الآي دي: `{user_id}`
👤 اليوزر: @{escape_markdown(username) if username else 'لا يوجد'}
📊 الحالة: {status}
—————————————————————————•
اختر أحد الخيارات:
"""
    markup = InlineKeyboardMarkup(row_width=2) # Changed row_width for better layout
    markup.add(
        InlineKeyboardButton("🎤 تحويل كلام لصوت", callback_data="action_tts"),
        InlineKeyboardButton("⚙️ سرعة التكلم", callback_data="action_set_speed")
    )
    markup.add(
        InlineKeyboardButton("❓ مساعدة", callback_data="action_help"),
        InlineKeyboardButton(f"👑 المالك ({OWNER_USERNAME})", url=f"https://t.me/{OWNER_USERNAME.lstrip('@')}")
    )

    if edit_message_id:
        safe_edit_message(welcome_text, chat_id, edit_message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        safe_send_message(chat_id, welcome_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
@check_access
def handle_start(message):
    user = message.from_user
    logging.info(f"Received /start from user {user.id} (@{user.username})")
    set_user_state(user.id, None) # Clear any previous state
    update_user_data(user.id, user.username) # Ensure user data is updated
    display_start_menu(message.chat.id, user.id, user.first_name, user.username)

def display_voice_options(message_or_call, page=1, edit_message_id=None):
    """Displays available voices with pagination."""
    chat_id = message_or_call.message.chat.id if isinstance(message_or_call, telebot.types.CallbackQuery) else message_or_call.chat.id
    user_id = message_or_call.from_user.id
    callback_id = message_or_call.id if isinstance(message_or_call, telebot.types.CallbackQuery) else None

    set_user_state(user_id, None)

    try:
        voices = Fix() # Fetch voices
    except VoiceListError as e:
        logging.error(f"Failed to fetch voice list for user {user_id}: {e}")
        # Provide a more user-friendly message, especially for connection issues
        error_msg = f"⚠️ فشل في جلب قائمة الأصوات. قد تكون هناك مشكلة في الاتصال بالخادم. يرجى المحاولة لاحقاً.\n(السبب: {e})"
        if edit_message_id:
            safe_edit_message(error_msg, chat_id, edit_message_id)
        else:
            safe_send_message(chat_id, error_msg)
        if callback_id:
            safe_answer_callback(callback_id)
        return
    except Exception as e:
        logging.error(f"Unexpected error fetching voices in display_voice_options: {e}", exc_info=True)
        error_msg = "⚠️ حدث خطأ غير متوقع أثناء جلب الأصوات."
        if edit_message_id:
            safe_edit_message(error_msg, chat_id, edit_message_id)
        else:
            safe_send_message(chat_id, error_msg)
        if callback_id:
            safe_answer_callback(callback_id)
        return

    if not voices:
        error_msg = "⚠️ لا توجد أصوات متاحة حالياً. يرجى المحاولة لاحقاً."
        if edit_message_id:
            safe_edit_message(error_msg, chat_id, edit_message_id)
        else:
            safe_send_message(chat_id, error_msg)
        if callback_id:
            safe_answer_callback(callback_id)
        return

    total_voices = len(voices)
    total_pages = math.ceil(total_voices / VOICES_PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * VOICES_PER_PAGE
    end_idx = start_idx + VOICES_PER_PAGE
    current_voices = voices[start_idx:end_idx]

    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for i, voice in enumerate(current_voices):
        actual_index = start_idx + i
        voice_name = voice.get('name', f'Voice {actual_index+1}')
        # Escape potential markdown issues in voice names if using Markdown parse mode
        # button_text = escape_markdown(voice_name)
        button_text = voice_name # Assuming names are safe
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"voice_{actual_index}"))

    # Add voice buttons row by row
    for i in range(0, len(buttons), 3):
        markup.row(*buttons[i:i+3])

    # Pagination buttons
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"page_{page-1}"))
    if page < total_pages:
        pagination_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"page_{page+1}"))
    if pagination_buttons:
        markup.row(*pagination_buttons)

    markup.row(InlineKeyboardButton("رجوع للقائمة 🔙", callback_data="action_back_to_start"))

    message_text = f"🎙️ اختر صوتاً (صفحة {page} من {total_pages}):"

    if edit_message_id:
        safe_edit_message(message_text, chat_id, edit_message_id, reply_markup=markup)
    else:
        safe_send_message(chat_id, message_text, reply_markup=markup)

    if callback_id:
        safe_answer_callback(callback_id)

@bot.callback_query_handler(func=lambda call: True)
@check_access
def handle_callback_query(call):
    user = call.from_user
    user_id = user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    query_data = call.data
    callback_id = call.id

    logging.info(f"Callback query received: User={user_id}, Chat={chat_id}, Data='{query_data}'")

    try:
        if query_data == "action_tts":
            display_voice_options(call, page=1, edit_message_id=message_id)
        elif query_data == "action_set_speed": # New speed setting callback
            markup = InlineKeyboardMarkup(row_width=3)
            speeds = [ 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.75, 1.8, 1.85, 1.9, 2.0 ]
            buttons = [InlineKeyboardButton(f"{s}x", callback_data=f"set_speed_{s}") for s in speeds]
            
            markup.row(*buttons[0:3])
            if len(buttons) > 3:
                markup.row(*buttons[3:6])
            if len(buttons) > 6:
                markup.row(*buttons[6:9])
            if len(buttons) > 9:
                markup.row(*buttons[9:12])
            if len(buttons) > 12:
                markup.row(*buttons[12:15])
            if len(buttons) > 15:
                markup.row(*buttons[15:18])
            if len(buttons) > 18:
                markup.row(*buttons[18:21])
            if len(buttons) > 21:
                markup.row(*buttons[21:24])

            markup.row(InlineKeyboardButton("رجوع للقائمة 🔙", callback_data="action_back_to_start"))
            
            current_speed = user_speech_speed.get(user_id, 1.0) # Get current or default
            text_to_send = f"⚙️ اختر سرعة التكلم المطلوبة (الحالية: {current_speed}x):"
            try:
                # Attempt to edit the existing message
                safe_edit_message(text_to_send, chat_id, message_id, reply_markup=markup)
            except Exception as e_edit_speed_options: 
                # Fallback if editing fails (e.g., message too old, or other Telegram API errors)
                logging.warning(f"Failed to edit message for speed selection (user: {user_id}, msg: {message_id}), sending new: {e_edit_speed_options}")
                safe_send_message(chat_id, text_to_send, reply_markup=markup)
            safe_answer_callback(callback_id)

        elif query_data.startswith("set_speed_"): # New callback for actual speed selection
            try:
                speed_str = query_data.split("_")[2] # e.g., "set_speed_0.5" -> "0.5"
                selected_speed = float(speed_str)
                
                # Validate if the selected speed is one of the allowed values
                if selected_speed not in [ 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.75, 1.8, 1.85, 1.9, 2.0 ]:
                    logging.warning(f"User {user_id} selected an invalid speed: {selected_speed}")
                    safe_answer_callback(callback_id, "❌ سرعة غير صالحة.")
                else:
                    user_speech_speed[user_id] = selected_speed
                    logging.info(f"User {user_id} set speech speed to {selected_speed}x")
                    safe_answer_callback(callback_id, f"✅ تم ضبط السرعة إلى {selected_speed}x")
                    # Go back to main menu after setting speed
                    display_start_menu(chat_id, user_id, user.first_name, user.username, edit_message_id=message_id)

            except (ValueError, IndexError) as e_parse_speed:
                logging.error(f"Error parsing speed selection callback '{query_data}' for user {user_id}: {e_parse_speed}")
                safe_answer_callback(callback_id, "❌ خطأ في بيانات اختيار السرعة.")
            except Exception as e_set_speed_generic:
                logging.error(f"Unexpected error in handle_speed_selection for user {user_id} (data: {query_data}): {e_set_speed_generic}", exc_info=True)
                safe_answer_callback(callback_id, "❌ حدث خطأ أثناء ضبط السرعة.")
        
        elif query_data == "action_help":
            help_text = f"""
❓ **مساعدة**

- اضغط على "🎤 تحويل كلام لصوت" لاختيار شخصية صوتية.
- اضغط على "⚙️ سرعة التكلم" لضبط سرعة الصوت
- بعد اختيار الصوت والسرعة (اختياري)، أرسل النص الذي تريد تحويله.
- الأعضاء المرقون ✨ يمكنهم إرسال نصوص أطول (سيتم تقسيمها ومعالجتها تلقائياً بحد أقصى {MAX_CHARS_PREMIUM_CHUNK} حرف لكل جزء).
- الأعضاء غير المرقين محدودون بـ {MAX_CHARS_FREE} حرف.
- استخدم أمر /again لإعادة استخدام آخر صوت تم اختياره مع نص جديد (سيتم استخدام آخر سرعة تم ضبطها).
- استخدم أمر /new لاختيار صوت جديد من البداية.
- للمشاكل أو الاستفسارات، تواصل مع المالك ({OWNER_USERNAME}).
            """
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("رجوع 🔙", callback_data="action_back_to_start"))
            safe_edit_message(help_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
            safe_answer_callback(callback_id)
        elif query_data == "action_back_to_start":
            set_user_state(user_id, None)
            display_start_menu(chat_id, user_id, user.first_name, user.username, edit_message_id=message_id)
            safe_answer_callback(callback_id)
        elif query_data.startswith("voice_"):
            handle_voice_selection(call)
        elif query_data.startswith("page_"):
            try:
                page = int(query_data.split("_")[1])
                if page > 0:
                    display_voice_options(call, page=page, edit_message_id=message_id)
                else:
                    safe_answer_callback(callback_id, "⚠️ رقم الصفحة غير صالح.")
            except (ValueError, IndexError):
                 logging.warning(f"Invalid page data in callback: {query_data}")
                 safe_answer_callback(callback_id, "⚠️ خطأ في بيانات الصفحة.")
        elif query_data.startswith('confirm_broadcast_') or query_data == 'cancel_broadcast':
            handle_broadcast_confirmation(call)
        else:
            logging.warning(f"Unhandled callback query data: {query_data}")
            safe_answer_callback(callback_id, "⚠️ أمر غير معروف.")
    except Exception as e:
        logging.error(f"Error handling callback query '{query_data}': {e}", exc_info=True)
        safe_answer_callback(callback_id, "❌ حدث خطأ أثناء معالجة طلبك.")

def handle_voice_selection(call):
    """Handles the selection of a voice from the inline keyboard."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    callback_id = call.id
    message_id = call.message.message_id

    try:
        voice_index_str = call.data.split("_")[1]
        voice_index = safe_int_conversion(voice_index_str)

        if voice_index is None:
            raise ValueError("Invalid voice index format")

        # Fetch voices again to ensure index is valid and data is fresh
        try:
            voices = Fix()
        except VoiceListError as e:
            logging.error(f"Failed to fetch voice list during selection: {e}")
            safe_answer_callback(callback_id, f"❌ خطأ في جلب قائمة الأصوات: {e}")
            set_user_state(user_id, None)
            return

        if not voices or not (0 <= voice_index < len(voices)):
             logging.warning(f"Invalid voice index {voice_index} selected by user {user_id}. Total voices: {len(voices)}")
             safe_answer_callback(callback_id, "❌ خطأ: الصوت المحدد غير صالح أو لم يعد متاحاً.")
             set_user_state(user_id, None)
             # Redisplay first page of voice options
             display_voice_options(call, page=1, edit_message_id=message_id)
             return

        selected_voice = voices[voice_index]
        user_last_voice[user_id] = selected_voice
        voice_name = selected_voice.get('name', f'Voice {voice_index+1}')
        logging.info(f"User {user_id} selected voice: {voice_name} (Index: {voice_index})")

        safe_answer_callback(callback_id) # Acknowledge selection

        prompt_text = f"🎉 رائع! الآن أرسل النص الذي ترغب بتحويله إلى صوت بواسطة شخصية **{escape_markdown(voice_name)}**."
        safe_edit_message(prompt_text, chat_id, message_id, reply_markup=None, parse_mode="Markdown")
        set_user_state(user_id, 'awaiting_tts_text')

    except (ValueError, IndexError) as e:
        logging.error(f"Error parsing voice selection callback '{call.data}': {e}")
        safe_answer_callback(callback_id, "❌ خطأ في بيانات اختيار الصوت.")
        set_user_state(user_id, None)
    except Exception as e:
        logging.error(f"Error in handle_voice_selection: {e}", exc_info=True)
        safe_answer_callback(callback_id, "❌ حدث خطأ أثناء اختيار الصوت.")
        set_user_state(user_id, None)


# Inserted function for handling long messages from subscribed users
import telebot # Ensure telebot is available for util.escape
import time
import os
import uuid
import logging

# Assuming these are defined globally in the main So.py or passed if not
# TEMP_DIR, MAX_CHARS_PREMIUM_CHUNK, INTER_CHUNK_DELAY, OWNER_USERNAME
# Also functions: Fox, ABC, EFG, HIG_with_retry, convert_and_combine_audio, cleanup_temp_file
# safe_send_message, safe_edit_message, safe_delete_message, set_user_state
# Exceptions: VoiceAuthError, VoiceAPIError, VoiceGenerationError

# Constants from the main script (ensure they are accessible or redefine/pass them)
# These should ideally be sourced from the main script's context if possible
# For the helper, we might need to assume they are available or pass them explicitly.
# For now, let's assume they are accessible via global scope of So.py

def _handle_subscriber_long_message(message, text_to_process, selected_voice_details, status_msg_main_scope):
    """Handles long text for subscribed users: splits, TTS per chunk, combines, sends."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    original_message_id = message.message_id # For replying

    voice_id = selected_voice_details.get(	"voiceId"	)
    voice_name = selected_voice_details.get(	"name"	, "Unknown Voice")

    if not voice_id:
        logging.error(f"[_handle_subscriber_long_message] VoiceId missing for user {user_id}")
        # Use status_msg_main_scope if available, otherwise send new
        err_msg = "❌ خطأ: بيانات الصوت المحددة غير كاملة للمعالجة المقسمة."
        if status_msg_main_scope:
            safe_edit_message(err_msg, chat_id, status_msg_main_scope.message_id)
        else:
            safe_send_message(chat_id, err_msg)
        set_user_state(user_id, None)
        return

    logging.info(f"[_handle_subscriber_long_message] Processing long text for upgraded user {user_id}. Voice: {voice_name}")

    # This local status_msg will be used by the helper internally.
    # If status_msg_main_scope is passed, we can update it.
    current_status_msg = status_msg_main_scope 

    temp_ogg_files_helper = []
    all_temp_files_helper = [] # To track files created by this helper for its own cleanup

    try:

        # --- Text Splitting --- #
        text_chunks = split_text_into_chunks(text_to_process, MAX_CHARS_PREMIUM_CHUNK)
        total_chunks = len(text_chunks)
        logging.info(f"[_handle_subscriber_long_message] Text split into {total_chunks} chunks for user {user_id}.")

        if current_status_msg:
            safe_edit_message(f"⏳ النص طويل ({len(text_to_process)} حرف)، سيتم تقسيمه إلى {total_chunks} أجزاء صوتية...", chat_id, current_status_msg.message_id)
        elif not current_status_msg: # If main function didn't create one, create it now.
             current_status_msg = safe_send_message(chat_id, f"⏳ النص طويل ({len(text_to_process)} حرف)، سيتم تقسيمه إلى {total_chunks} أجزاء صوتية...", parse_mode="Markdown")
        if current_status_msg:
            bot.send_chat_action(chat_id, 	"record_voice"	)

        for i, chunk in enumerate(text_chunks):
            chunk_num = i + 1
            logging.info(f"[_handle_subscriber_long_message] Processing chunk {chunk_num}/{total_chunks} for user {user_id}")
            if current_status_msg:
                safe_edit_message(f"⏳ جارٍ معالجة الجزء الصوتي {chunk_num} من {total_chunks}...", chat_id, current_status_msg.message_id)
                bot.send_chat_action(chat_id, 	"record_voice"	)
            
            # --- Authentication (copied from process_text_input) --- #
            # Authenticating per chunk.
            logging.info(f"[_handle_subscriber_long_message] Authenticating for TTS for chunk {chunk_num}/{total_chunks} (User: {user_id})...")
            Id_levi1_helper, start_time_id_helper, Id_levi9_helper = Fox()
            try:
                token2_helper, Id_levi2_helper, C9_helper = ABC()
            except VoiceAuthError as auth_err_helper:
                logging.error(f"[_handle_subscriber_long_message] Auth failed for chunk {chunk_num} (User: {user_id}): {auth_err_helper}")
                raise VoiceAPIError(f"خطأ في المصادقة مع خدمة الصوت للجزء {chunk_num}: {auth_err_helper}") from auth_err_helper
            EFG(Id_levi2_helper, token2_helper, Id_levi1_helper)
            try:
                audio_chunk_data = HIG_with_retry(Id_levi2_helper, token2_helper, C9_helper, Id_levi1_helper, Id_levi9_helper, voice_id, chunk, voice_name)
            except VoiceGenerationError as gen_err_chunk:
                logging.error(f"[_handle_subscriber_long_message] Failed to generate audio for chunk {chunk_num} (User {user_id}): {gen_err_chunk}")
                raise VoiceGenerationError(f"فشل إنشاء الصوت للجزء {chunk_num} من {total_chunks}. {gen_err_chunk}") from gen_err_chunk

            chunk_filename = os.path.join(TEMP_DIR, f"chunk_helper_{user_id}_{uuid.uuid4().hex}.ogg")
            try:
                with open(chunk_filename, 	"wb"	) as f:
                    f.write(audio_chunk_data)
                temp_ogg_files_helper.append(chunk_filename)
                all_temp_files_helper.append(chunk_filename) # Track for cleanup
                logging.info(f"[_handle_subscriber_long_message] Saved chunk {chunk_num} to {chunk_filename}")
            except IOError as e_io:
                logging.error(f"[_handle_subscriber_long_message] Failed to write audio chunk {chunk_num} to {chunk_filename}: {e_io}")
                raise VoiceGenerationError(f"فشل حفظ الملف الصوتي للجزء {chunk_num}.") from e_io

            if chunk_num < total_chunks:
                logging.debug(f"[_handle_subscriber_long_message] Waiting {INTER_CHUNK_DELAY}s before next chunk...")
                time.sleep(INTER_CHUNK_DELAY)

        if not temp_ogg_files_helper:
            raise VoiceGenerationError("لم يتم إنشاء أي ملفات صوتية بنجاح للمعالجة المقسمة.")

        # --- Combine/Convert Audio --- #
        if current_status_msg:
            safe_edit_message(f"⏳ جارٍ دمج {len(temp_ogg_files_helper)} أجزاء صوتية وتحويلها إلى MP3...", chat_id, current_status_msg.message_id)
            bot.send_chat_action(chat_id, 	"record_voice"	)

        final_mp3_path_helper = os.path.join(TEMP_DIR, f"final_helper_{user_id}_{uuid.uuid4().hex}.mp3")
        all_temp_files_helper.append(final_mp3_path_helper) # Track for cleanup
        current_speech_speed = user_speech_speed.get(user_id, 1.0) # Get user's speed or default
        logging.info(f"[_handle_subscriber_long_message] Using speech speed: {current_speech_speed}x for user {user_id}")
        final_audio_data, temp_files_to_clean_combined = convert_and_combine_audio(temp_ogg_files_helper, final_mp3_path_helper, speech_speed=current_speech_speed)
        all_temp_files_helper.extend(temp_files_to_clean_combined)

        if not final_audio_data:
            raise VoiceGenerationError("فشل دمج أو تحويل الملفات الصوتية النهائية (معالجة مقسمة).")

        # --- Send Final Audio --- #
        if current_status_msg: # Delete the status message as we are about to send the final audio
            safe_delete_message(chat_id, current_status_msg.message_id)
            current_status_msg = None # Avoid trying to edit/delete again in finally

        random_suffix_helper = str(random.randint(1000000, 9999999))
        audio_filename_display_helper = f"sayo-bot-long-{random_suffix_helper}.mp3"
        current_speech_speed_helper = user_speech_speed.get(user_id, 1.0) # Get user's speed or default
        caption_text_helper = f"""🎙️ هذه هي رسالتك الطويلة بصوت *{escape_markdown(voice_name)}* (تم دمج {total_chunks} أجزاء)
⏱️ سرعة الصوت: {current_speech_speed_helper}x

🔄 أرسل /again لإعادة استخدام هذا الصوت مع نص جديد
✨ أرسل /new لاختيار شخصية صوتية مختلفة"""

        logging.info(f"[_handle_subscriber_long_message] Sending final combined MP3 audio ({len(final_audio_data)} bytes) to user {user_id} with speed {current_speech_speed_helper}x")
        bot.send_chat_action(chat_id, 	"upload_voice"	)
        try:
            bot.send_audio(chat_id, final_audio_data,
                           title=audio_filename_display_helper,
                           caption=caption_text_helper,
                           performer="Sayo Bot",
                           parse_mode="MarkdownV2",
                           reply_to_message_id=original_message_id)
            set_user_state(user_id, 	"can_use_again"	) # Set state for /again command
        except telebot.apihelper.ApiTelegramException as send_err_helper:
            logging.error(f"[_handle_subscriber_long_message] Failed to send combined audio to user {user_id}: {send_err_helper}")
            # If sending fails, try to inform user via a new message if status_msg was deleted
            safe_send_message(chat_id, "❌ حدث خطأ أثناء إرسال الملف الصوتي المدمج. يرجى المحاولة مرة أخرى.")
            # No specific error re-raise here, as the main task (TTS and combine) was done.
            # The user just didn't get the file.

    except (VoiceAPIError, VoiceGenerationError) as e_helper:
        # These errors are caught and include user-friendly Arabic messages
        logging.error(f"[_handle_subscriber_long_message] Voice Processing Error for user {user_id}: {e_helper}")
        if current_status_msg:
            safe_edit_message(f"❌ خطأ في المعالجة المقسمة: {e_helper}", chat_id, current_status_msg.message_id)
        else: # If status_msg wasn't set or was deleted before error
            safe_send_message(chat_id, f"❌ خطأ في المعالجة المقسمة: {e_helper}")
        set_user_state(user_id, None)
        raise # Re-raise so process_text_input can also log it if needed / handle its own status_msg

    except Exception as e_unhandled_helper:
        logging.error(f"[_handle_subscriber_long_message] Unexpected Error for user {user_id}: {e_unhandled_helper}", exc_info=True)
        err_msg_unhandled = "❌ حدث خطأ غير متوقع أثناء معالجة رسالتك الطويلة. تم إبلاغ المطور."
        if current_status_msg:
            safe_edit_message(err_msg_unhandled, chat_id, current_status_msg.message_id)
        else:
            safe_send_message(chat_id, err_msg_unhandled)
        set_user_state(user_id, None)
        # Re-raise as a generic VoiceGenerationError to be caught by the caller if needed
        raise VoiceGenerationError(err_msg_unhandled) from e_unhandled_helper

    finally:
        # Cleanup temporary files created *by this helper function*
        logging.debug(f"[_handle_subscriber_long_message] Cleaning up its temporary files for user {user_id}: {all_temp_files_helper}")
        for temp_file in all_temp_files_helper:
            cleanup_temp_file(temp_file) # cleanup_temp_file is from main So.py
        
        # Ensure state is cleared if not already set to can_use_again
        if get_user_state(user_id) != 'can_use_again':
             set_user_state(user_id, None)
    return # Indicate completion to the caller (process_text_input)

@bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'awaiting_tts_text')
@check_access
def process_text_input(message):
    """Processes the text message received after a voice was selected."""
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    message_id = message.message_id

    logging.info(f"Received text for TTS from user {user_id}. Length: {len(text)}")
    set_user_state(user_id, None) # Clear state

    if user_id not in user_last_voice:
        logging.warning(f"User {user_id} sent text but no voice selected.")
        safe_send_message(chat_id, "⚠️ لم تختر صوتاً بعد أو انتهت جلستك. الرجاء استخدام /start واختيار صوت أولاً.")
        return

    selected_voice = user_last_voice[user_id]
    voice_id = selected_voice.get('voiceId')
    voice_name = selected_voice.get('name', 'Unknown Voice')

    if not voice_id:
        logging.error(f"Selected voice for user {user_id} has no voiceId: {selected_voice}")
        safe_send_message(chat_id, "❌ خطأ: بيانات الصوت غير كاملة. حاول اختيار صوت آخر.")
        return

    text_to_process = text.strip()
    if not text_to_process:
        safe_send_message(chat_id, "⚠️ النص فارغ. يرجى إرسال نص لتحويله.")
        return

    is_premium = is_upgraded(user_id)
    temp_ogg_files = [] # Holds paths of temporary OGG chunks created in this request
    all_temp_files = [] # Holds all temp files (ogg, mp3, list) for final cleanup
    final_audio_data = None
    processing_error = None
    status_msg = None

    # New logic for message length and subscriber status
    if is_premium and len(text) > MAX_CHARS_PREMIUM_CHUNK:
        logging.info(f"User {user_id} is upgraded, message length {len(text)} > 200. Routing to _handle_subscriber_long_message.")
        # selected_voice is user_last_voice[user_id], status_msg is None at this point (or passed if defined earlier by main func)
        _handle_subscriber_long_message(message, text, selected_voice, status_msg)
        return  # IMPORTANT: Return after helper handles it.
    elif not is_premium and len(text) > MAX_CHARS_FREE:
        logging.info(f"User {user_id} (non-upgraded) sent message longer than 200 chars: {len(text)}.")
        error_msg_free_limit = f"❌ لا يمكنك إرسال أكثر من 200 حرف إلا إذا كنت مشتركاً. للاشتراك: {OWNER_USERNAME}"
        safe_send_message(chat_id, error_msg_free_limit)
        set_user_state(user_id, None)
        return
    # If execution reaches here, it's a short message for either user type OR premium user with short message.    # The original logic for these cases (which includes the main try-except) will follow.

    try:
        status_msg = safe_send_message(chat_id, "⏳ جارٍ تحضير الصوت...", parse_mode="Markdown")
        if status_msg:
            bot.send_chat_action(chat_id, 'record_voice')
        else:
            logging.warning(f"Could not send initial status message to chat {chat_id}")

        # --- Authentication (Once per request) --- #
        logging.info(f"Authenticating for TTS request (User: {user_id})...")
        Id_levi1, start_time_id, Id_levi9 = Fox()
        try:
            token2, Id_levi2, C9 = ABC()
        except VoiceAuthError as auth_err:
            logging.error(f"Authentication failed for user {user_id}: {auth_err}")
            raise VoiceAPIError(f"خطأ في المصادقة مع خدمة الصوت: {auth_err}") from auth_err
        EFG(Id_levi2, token2, Id_levi1) # Register device/user (best effort)

        # --- Text Splitting and Audio Generation --- #
        text_chunks = []
        is_long_text = False
        if is_premium:
            if len(text_to_process) > MAX_CHARS_PREMIUM_CHUNK:
                is_long_text = True
                text_chunks = split_text_into_chunks(text_to_process, MAX_CHARS_PREMIUM_CHUNK)
                logging.info(f"Premium user {user_id}: Splitting text into {len(text_chunks)} chunks.")
                if status_msg:
                    safe_edit_message(f"⏳ النص طويل، سيتم تقسيمه إلى {len(text_chunks)} أجزاء...", chat_id, status_msg.message_id)
            else:
                # Premium user, short text
                text_chunks = [text_to_process]
                if contains_banned_word(text_to_process):
                     logging.warning(f"Upgraded user {user_id} used a potentially banned word.")
                     # Continue processing for premium users
        else:
            # Free user
            if contains_banned_word(text_to_process):
                raise VoiceGenerationError(f"🚫 الرسالة تحتوي على كلمات محظورة. لرفع الحظر راسل المالك {OWNER_USERNAME}")
            if len(text_to_process) > MAX_CHARS_FREE:
                raise VoiceGenerationError(f"❌ لا يمكنك إرسال أكثر من {MAX_CHARS_FREE} حرف إلا إذا كنت مشتركاً. للاشتراك: {OWNER_USERNAME}")
            text_chunks = [text_to_process]

        total_chunks = len(text_chunks)
        for i, chunk in enumerate(text_chunks):
            chunk_num = i + 1
            if is_long_text and status_msg:
                safe_edit_message(f"⏳ جارٍ معالجة الجزء {chunk_num} من {total_chunks}...", chat_id, status_msg.message_id)
                bot.send_chat_action(chat_id, 'record_voice')
            elif status_msg: # Single chunk
                 safe_edit_message("⏳ جارٍ إنشاء الصوت...", chat_id, status_msg.message_id)
                 bot.send_chat_action(chat_id, 'record_voice')

            logging.info(f"Processing chunk {chunk_num}/{total_chunks} for user {user_id}")
            try:
                # Call HIG with retry logic
                audio_chunk_data = HIG_with_retry(Id_levi2, token2, C9, Id_levi1, Id_levi9, voice_id, chunk, voice_name)
            except VoiceGenerationError as gen_err:
                # Catch generation errors (including max retries reached)
                logging.error(f"Failed to generate audio for chunk {chunk_num} (User {user_id}): {gen_err}")
                # Add chunk number to the error message for clarity
                raise VoiceGenerationError(f"فشل إنشاء الصوت للجزء {chunk_num}. {gen_err}") from gen_err

            # Save successful chunk
            chunk_filename = os.path.join(TEMP_DIR, f"chunk_{user_id}_{uuid.uuid4().hex}.ogg")
            try:
                with open(chunk_filename, 'wb') as f:
                    f.write(audio_chunk_data)
                temp_ogg_files.append(chunk_filename)
                logging.info(f"Saved chunk {chunk_num} to {chunk_filename}")
            except IOError as e:
                logging.error(f"Failed to write audio chunk {chunk_num} to {chunk_filename}: {e}")
                raise VoiceGenerationError(f"فشل حفظ الملف الصوتي للجزء {chunk_num}.") from e

            # Wait between chunks if processing multiple
            if total_chunks > 1 and chunk_num < total_chunks:
                logging.debug(f"Waiting {INTER_CHUNK_DELAY} seconds before next chunk...")
                time.sleep(INTER_CHUNK_DELAY)

        if not temp_ogg_files:
             # This should ideally be caught earlier, but as a safeguard
             raise VoiceGenerationError("لم يتم إنشاء أي ملفات صوتية بنجاح.")

        # --- Combine/Convert Audio --- #
        if status_msg:
            action_desc = f"دمج {len(temp_ogg_files)} أجزاء" if len(temp_ogg_files) > 1 else "تحويل الصوت"
            safe_edit_message(f"⏳ جارٍ {action_desc} وتحويله إلى MP3...", chat_id, status_msg.message_id)

        final_mp3_path = os.path.join(TEMP_DIR, f"final_{user_id}_{uuid.uuid4().hex}.mp3")
        current_speech_speed = user_speech_speed.get(user_id, 1.0)  # Get user's speed or default
        logging.info(f"[process_text_input] Using speech speed: {current_speech_speed}x for user {user_id} for audio conversion.")
        final_audio_data, ffmpeg_temp_files = convert_and_combine_audio(temp_ogg_files, final_mp3_path, speech_speed=current_speech_speed)
        all_temp_files.extend(ffmpeg_temp_files) # Add files used by ffmpeg for cleanup

        if not final_audio_data:
            raise VoiceGenerationError("فشل دمج أو تحويل الملفات الصوتية النهائية.")

        # --- Send Final Audio --- #
        if status_msg:
            safe_delete_message(chat_id, status_msg.message_id)
            status_msg = None # Avoid trying to edit deleted message in finally block

        random_suffix = str(random.randint(1000000, 9999999))
        audio_filename_display = f"{voice_name.replace(' ', '_')}_{user_id}.mp3"
        # current_speech_speed is already defined a few lines above where convert_and_combine_audio is called
        caption_text = f"""🎤 الصوت بواسطة: {escape_markdown(voice_name)}
⏱️ سرعة الصوت: {current_speech_speed}x

🔄 أرسل /again لإعادة استخدام هذا الصوت مع نص جديد
✨ أرسل /new لاختيار شخصية صوتية مختلفة"""

        logging.info(f"Sending final MP3 audio ({len(final_audio_data)} bytes) to user {user_id} with speed {current_speech_speed}x")
        bot.send_chat_action(chat_id, 'upload_voice')
        try:
            bot.send_audio(chat_id, final_audio_data,
                           title=audio_filename_display,
                           caption=caption_text,
                           performer="Sayo Bot",
                           parse_mode="Markdown",
                           reply_to_message_id=message_id) # Reply to original text message
            set_user_state(user_id, 'can_use_again')
        except telebot.apihelper.ApiTelegramException as send_err:
             logging.error(f"Failed to send audio to user {user_id}: {send_err}")
             safe_send_message(chat_id, "❌ حدث خطأ أثناء إرسال الملف الصوتي. يرجى المحاولة مرة أخرى.")

    except (VoiceAPIError, VoiceGenerationError) as e:
        processing_error = str(e)
        logging.error(f"Voice Processing Error for user {user_id}: {processing_error}")
        if status_msg:
            safe_edit_message(f"❌ خطأ: {processing_error}", chat_id, status_msg.message_id)
        else:
            safe_send_message(chat_id, f"❌ حدث خطأ: {processing_error}")
        set_user_state(user_id, None)
    except Exception as e:
        processing_error = str(e)
        logging.error(f"Unexpected Error in process_text_input (user {user_id}): {e}", exc_info=True)
        error_message_user = "❌ حدث خطأ غير متوقع أثناء معالجة طلبك. تم إبلاغ المطور."
        if status_msg:
            safe_edit_message(error_message_user, chat_id, status_msg.message_id)
        else:
            safe_send_message(chat_id, error_message_user)
        set_user_state(user_id, None)
    finally:
        # Ensure all temporary files created during this request are cleaned up
        logging.debug(f"Cleaning up temporary files for user {user_id}: {all_temp_files}")
        for temp_file in all_temp_files:
            cleanup_temp_file(temp_file)
        # Also clean any ogg files directly tracked if not already in all_temp_files
        for temp_file in temp_ogg_files:
             if temp_file not in all_temp_files:
                 cleanup_temp_file(temp_file)

@bot.message_handler(commands=['again'])
@check_access
def handle_again(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if get_user_state(user_id) != 'can_use_again':
        safe_send_message(chat_id, "⚠️ لا يمكن استخدام /again حالياً. يرجى استخدامه مباشرة بعد تلقي الصوت السابق أو اختيار صوت أولاً.")
        return

    if user_id in user_last_voice:
        selected_voice = user_last_voice[user_id]
        voice_name = selected_voice.get('name', 'Unknown Voice')
        logging.info(f"User {user_id} using /again with voice '{voice_name}'")
        safe_send_message(chat_id, f"🔄 ستستخدم صوت **{escape_markdown(voice_name)}** مرة أخرى.\n📝 أرسل النص الجديد:", parse_mode="Markdown")
        set_user_state(user_id, 'awaiting_tts_text')
    else:
        logging.warning(f"User {user_id} used /again but no last voice found.")
        safe_send_message(chat_id, "⚠️ لم تستخدم أي صوت مؤخراً أو انتهت الجلسة. استخدم /start لاختيار صوت أولاً.")
        set_user_state(user_id, None)

@bot.message_handler(commands=['new'])
@check_access
def handle_new(message):
    """Allows user to select a new voice."""
    logging.info(f"User {message.from_user.id} using /new")
    set_user_state(message.from_user.id, None)
    display_voice_options(message, page=1)

# --- Admin Commands ---
@bot.message_handler(commands=['admin'])
@check_access
def handle_admin(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if user_id == ADMIN_ID:
        logging.info(f"Admin {user_id} accessed admin panel.")
        admin_text = f"""
🛠️ **لوحة تحكم الأدمن**

أهلاً بك أيها المدير!

**الأوامر المتاحة:**
- `/block_user` : حظر مستخدم (تفاعلي).
- `/unblock_user` : إلغاء حظر مستخدم (تفاعلي).
- `/upgrade_user` : ترقية مستخدم (تفاعلي).
- `/downgrade_user` : إلغاء ترقية مستخدم (تفاعلي).
- `/list_blocked` : عرض قائمة المحظورين.
- `/list_upgraded` : عرض قائمة المرقين.
- `/broadcast` : إرسال رسالة جماعية للمستخدمين (تفاعلي).
- `/stats` : عرض إحصائيات بسيطة.
        """
        safe_send_message(chat_id, admin_text, parse_mode="Markdown")
    else:
        logging.warning(f"Non-admin user {user_id} tried to access /admin.")
        safe_send_message(chat_id, "🚫 هذا الأمر مخصص للأدمن فقط.")
    set_user_state(user_id, None)

def setup_interactive_admin_command(message, action_type):
    """Generic function to start an interactive admin command requiring a target user."""
    admin_id = message.from_user.id
    if admin_id != ADMIN_ID:
        safe_send_message(message.chat.id, "🚫 هذا الأمر مخصص للأدمن فقط.")
        return

    prompt_text_map = {
        'block': "📝 الرجاء إدخال اسم المستخدم (مع @) أو المعرف الرقمي (ID) للشخص الذي تريد **حظره**.",
        'unblock': "📝 الرجاء إدخال اسم المستخدم (مع @) أو المعرف الرقمي (ID) للشخص الذي تريد **إلغاء حظره**.",
        'upgrade': "📝 الرجاء إدخال اسم المستخدم (مع @) أو المعرف الرقمي (ID) للشخص الذي تريد **ترقيته**.",
        'downgrade': "📝 الرجاء إدخال اسم المستخدم (مع @) أو المعرف الرقمي (ID) للشخص الذي تريد **إلغاء ترقيته**."
    }
    prompt_text = prompt_text_map.get(action_type, "📝 الرجاء إدخال اسم المستخدم (مع @) أو المعرف الرقمي (ID) للهدف.")

    try:
        prompt = bot.reply_to(message, prompt_text)
        state_key = f'awaiting_admin_target_{action_type}'
        set_user_state(admin_id, state_key)
        admin_actions[admin_id] = {'action': action_type} # Store action type
        logging.info(f"Admin {admin_id} initiated {action_type} action.")
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Failed to send admin prompt for {action_type}: {e}")
        safe_send_message(message.chat.id, "❌ حدث خطأ أثناء بدء الأمر الإداري.")

@bot.message_handler(commands=['block_user'])
@check_access
def handle_block_user_setup(message):
    setup_interactive_admin_command(message, 'block')

@bot.message_handler(commands=['unblock_user'])
@check_access
def handle_unblock_user_setup(message):
    setup_interactive_admin_command(message, 'unblock')

@bot.message_handler(commands=['upgrade_user'])
@check_access
def handle_upgrade_user_setup(message):
    setup_interactive_admin_command(message, 'upgrade')

@bot.message_handler(commands=['downgrade_user'])
@check_access
def handle_downgrade_user_setup(message):
    setup_interactive_admin_command(message, 'downgrade')

@bot.message_handler(func=lambda message: get_user_state(message.from_user.id) and get_user_state(message.from_user.id).startswith('awaiting_admin_target_'))
@check_access
def process_admin_target_input(message):
    """Handles the message containing the target user ID or username for an admin action."""
    admin_id = message.from_user.id
    chat_id = message.chat.id
    target_input = message.text.strip()

    current_state = get_user_state(admin_id)
    if not current_state: return # Should not happen based on handler func, but safety check

    action_type = current_state.replace('awaiting_admin_target_', '')
    set_user_state(admin_id, None)
    admin_action_info = admin_actions.pop(admin_id, None)

    if not admin_action_info or admin_action_info.get('action') != action_type:
        logging.error(f"Admin action state mismatch for admin {admin_id}. State: {current_state}, Action info: {admin_action_info}")
        safe_send_message(chat_id, "❌ حدث خطأ داخلي في تتبع الإجراء الإداري. يرجى المحاولة مرة أخرى.")
        return

    target_user_id = None
    target_username = None

    try:
        if target_input.isdigit():
            target_user_id = int(target_input)
            target_username = user_data.get(target_user_id)
        elif target_input.startswith('@'):
            username_to_find = target_input[1:]
            found_id = find_user_id_by_username(username_to_find)
            if found_id:
                target_user_id = found_id
                target_username = username_to_find # Use the provided username
                safe_send_message(chat_id, f"ℹ️ تم العثور على المستخدم `{target_input}` بالمعرف `{target_user_id}`.", parse_mode="Markdown")
            else:
                safe_send_message(chat_id, f"⚠️ لم يتم العثور على المستخدم بالاسم `{target_input}` في سجلات البوت. قد يحتاج المستخدم للتفاعل مع البوت أولاً أو أن الاسم غير صحيح. يرجى استخدام المعرف الرقمي (ID) إذا كنت متأكداً.", parse_mode="Markdown")
                return
        else:
            safe_send_message(chat_id, "⚠️ الإدخال غير صالح. يرجى إدخال معرف رقمي (ID) صحيح أو اسم مستخدم يبدأ بـ @.")
            return

        if target_user_id == ADMIN_ID and action_type in ['block', 'downgrade']:
             safe_send_message(chat_id, "🛡️ لا يمكنك حظر أو إلغاء ترقية نفسك.")
             return

        # Execute the corresponding admin action
        action_func_map = {
            'block': execute_block_user,
            'unblock': execute_unblock_user,
            'upgrade': execute_upgrade_user,
            'downgrade': execute_downgrade_user
        }
        action_func = action_func_map.get(action_type)
        if action_func:
            action_func(message, target_user_id, target_username)
        else:
            logging.error(f"Unknown admin action type resolved: {action_type}")
            safe_send_message(chat_id, "❌ نوع الإجراء الإداري غير معروف.")

    except Exception as e:
        logging.error(f"Error processing admin target input for action {action_type}, target '{target_input}': {e}", exc_info=True)
        safe_send_message(chat_id, "❌ حدث خطأ أثناء معالجة الإدخال.")

# --- Admin Action Execution Functions ---
def execute_block_user(message, target_user_id, target_username=None):
    display_target = f"`{target_user_id}`{f' (@{escape_markdown(target_username)})' if target_username else ''}"
    if target_user_id in blocked_users:
        safe_send_message(message.chat.id, f"ℹ️ المستخدم {display_target} محظور بالفعل.", parse_mode="Markdown")
    else:
        blocked_users.add(target_user_id)
        save_users(BLOCKED_USERS_FILE, blocked_users)
        logging.info(f"Admin {message.from_user.id} blocked user {target_user_id}.")
        safe_send_message(message.chat.id, f"✅ تم حظر المستخدم {display_target} بنجاح.", parse_mode="Markdown")
        # Notify the user
        notify_msg = safe_send_message(target_user_id, f"🚫 تم حظرك من استخدام هذا البوت بواسطة الإدارة. للطعن راسل المبرمج {OWNER_USERNAME}")
        if not notify_msg:
            safe_send_message(message.chat.id, "⚠️ لم أتمكن من إرسال إشعار للمستخدم المحظور (قد يكون قد حظر البوت).", parse_mode="Markdown")

def execute_unblock_user(message, target_user_id, target_username=None):
    display_target = f"`{target_user_id}`{f' (@{escape_markdown(target_username)})' if target_username else ''}"
    if target_user_id in blocked_users:
        blocked_users.discard(target_user_id)
        save_users(BLOCKED_USERS_FILE, blocked_users)
        logging.info(f"Admin {message.from_user.id} unblocked user {target_user_id}.")
        safe_send_message(message.chat.id, f"✅ تم إلغاء حظر المستخدم {display_target}.", parse_mode="Markdown")
        notify_msg = safe_send_message(target_user_id, "✅ تم إلغاء حظرك. يمكنك الآن استخدام البوت مجدداً.")
        if not notify_msg:
            safe_send_message(message.chat.id, "⚠️ لم أتمكن من إرسال إشعار للمستخدم الذي تم إلغاء حظره.", parse_mode="Markdown")
    else:
        safe_send_message(message.chat.id, f"⚠️ المستخدم {display_target} ليس محظوراً أصلاً.", parse_mode="Markdown")

def execute_upgrade_user(message, target_user_id, target_username=None):
    display_target = f"`{target_user_id}`{f' (@{escape_markdown(target_username)})' if target_username else ''}"
    if is_upgraded(target_user_id): # Check includes admin
         safe_send_message(message.chat.id, f"ℹ️ المستخدم {display_target} مرقى بالفعل.", parse_mode="Markdown")
    else:
        upgraded_users.add(target_user_id)
        save_users(UPGRADED_USERS_FILE, upgraded_users)
        logging.info(f"Admin {message.from_user.id} upgraded user {target_user_id}.")
        safe_send_message(message.chat.id, f"✅ تم ترقية المستخدم {display_target} بنجاح.", parse_mode="Markdown")
        notify_msg = safe_send_message(target_user_id, "✨ تمت ترقية حسابك! يمكنك الآن إرسال نصوص أطول وبدون قيود على الكلمات.")
        if not notify_msg:
            safe_send_message(message.chat.id, "⚠️ لم أتمكن من إرسال إشعار للمستخدم الذي تمت ترقيته.", parse_mode="Markdown")

def execute_downgrade_user(message, target_user_id, target_username=None):
    display_target = f"`{target_user_id}`{f' (@{escape_markdown(target_username)})' if target_username else ''}"
    if target_user_id == ADMIN_ID:
        safe_send_message(message.chat.id, "🛡️ لا يمكن إلغاء ترقية الأدمن الرئيسي.")
        return
    if target_user_id in upgraded_users:
        upgraded_users.discard(target_user_id)
        save_users(UPGRADED_USERS_FILE, upgraded_users)
        logging.info(f"Admin {message.from_user.id} downgraded user {target_user_id}.")
        safe_send_message(message.chat.id, f"✅ تم إلغاء ترقية المستخدم {display_target}.", parse_mode="Markdown")
        notify_msg = safe_send_message(target_user_id, "ℹ️ تم إرجاع حسابك إلى الحالة العادية. ستطبق عليك قيود الأحرف والكلمات المحظورة.")
        if not notify_msg:
            safe_send_message(message.chat.id, "⚠️ لم أتمكن من إرسال إشعار للمستخدم الذي تم إلغاء ترقيته.", parse_mode="Markdown")
    else:
        safe_send_message(message.chat.id, f"⚠️ المستخدم {display_target} ليس مرقى أصلاً.", parse_mode="Markdown")

# --- List Commands & Stats ---
def admin_list_command(func):
    """Decorator to ensure only admin can run list/stats commands."""
    def wrapper(message):
        if message.from_user.id != ADMIN_ID:
            safe_send_message(message.chat.id, "🚫 هذا الأمر مخصص للأدمن فقط.")
            return
        try:
            func(message)
        except Exception as e:
            logging.error(f"Error executing admin list/stats command {func.__name__}: {e}", exc_info=True)
            safe_send_message(message.chat.id, "❌ حدث خطأ أثناء عرض المعلومات.")
    return wrapper

def send_long_message(chat_id, text, **kwargs):
    """Sends a long message by splitting it into parts if necessary."""
    max_len = 4096 # Telegram message length limit
    if len(text) <= max_len:
        safe_send_message(chat_id, text, **kwargs)
    else:
        parts = telebot.util.split_string(text, max_len)
        for part in parts:
            safe_send_message(chat_id, part, **kwargs)
            time.sleep(0.5) # Small delay between parts

@bot.message_handler(commands=['list_blocked'])
@check_access
@admin_list_command
def handle_list_blocked(message):
    if not blocked_users:
        safe_send_message(message.chat.id, "🚫 لا يوجد مستخدمون محظورون حالياً.")
        return
    user_list_items = []
    for user_id in sorted(list(blocked_users)):
        username = user_data.get(user_id)
        user_list_items.append(f"- `{user_id}`{f' (@{escape_markdown(username)})' if username else ''}")
    header = f"🔒 **قائمة المستخدمين المحظورين ({len(blocked_users)}):**\n"
    full_message = header + "\n".join(user_list_items)
    send_long_message(message.chat.id, full_message, parse_mode="Markdown")

@bot.message_handler(commands=['list_upgraded'])
@check_access
@admin_list_command
def handle_list_upgraded(message):
    display_users = upgraded_users - {ADMIN_ID} # Exclude admin unless explicitly added
    if not display_users:
        safe_send_message(message.chat.id, "✨ لا يوجد مستخدمون مرقون حالياً (باستثناء الأدمن).")
        return
    user_list_items = []
    for user_id in sorted(list(display_users)):
        username = user_data.get(user_id)
        user_list_items.append(f"- `{user_id}`{f' (@{escape_markdown(username)})' if username else ''}")
    header = f"🌟 **قائمة المستخدمين المرقين ({len(display_users)}):**\n"
    full_message = header + "\n".join(user_list_items)
    send_long_message(message.chat.id, full_message, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
@check_access
@admin_list_command
def handle_stats(message):
    total_known_users = len(user_data)
    total_blocked = len(blocked_users)
    total_upgraded = len(upgraded_users - {ADMIN_ID}) # Exclude admin
    stats_text = f"""
📊 **إحصائيات البوت**

- إجمالي المستخدمين المعروفين: {total_known_users}
- المستخدمون المحظورون: {total_blocked}
- المستخدمون المرقون (غير الأدمن): {total_upgraded}
    """
    safe_send_message(message.chat.id, stats_text, parse_mode="Markdown")

# --- Broadcast Command (Admin Only) ---
@bot.message_handler(commands=['broadcast'])
@check_access
@admin_list_command
def handle_broadcast_setup(message):
    try:
        prompt = bot.reply_to(message, "📝 أرسل الرسالة التي تريد بثها لجميع المستخدمين المعروفين للبوت. يمكنك استخدام تنسيق Markdown.")
        set_user_state(message.from_user.id, 'awaiting_broadcast_message')
        logging.info(f"Admin {message.from_user.id} initiated broadcast.")
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Failed to send broadcast prompt: {e}")
        safe_send_message(message.chat.id, "❌ حدث خطأ أثناء بدء أمر البث.")

@bot.message_handler(func=lambda message: get_user_state(message.from_user.id) == 'awaiting_broadcast_message')
@check_access
@admin_list_command
def process_broadcast_message(message):
    admin_id = message.from_user.id
    chat_id = message.chat.id
    # Use message.text for plain text, or message.html_text/markdown_text if using entities
    broadcast_text = message.text # Assuming plain text or Markdown

    set_user_state(admin_id, None)

    if not broadcast_text:
        safe_send_message(chat_id, "⚠️ تم إلغاء البث لأن الرسالة فارغة.")
        return

    known_user_ids = set(user_data.keys()) # All users who ever interacted
    active_user_ids = known_user_ids - blocked_users # Exclude blocked users

    if not active_user_ids:
        safe_send_message(chat_id, "⚠️ لا يوجد مستخدمون نشطون (غير محظورين) لإرسال البث إليهم.")
        return

    confirm_markup = InlineKeyboardMarkup()
    # Use message_id in callback data to link confirmation to the specific broadcast message
    confirm_key = f"broadcast_confirm_{message.message_id}"
    cancel_key = f"broadcast_cancel_{message.message_id}"
    confirm_markup.add(
        InlineKeyboardButton(f"✅ نعم، أرسل إلى {len(active_user_ids)} مستخدم نشط", callback_data=confirm_key),
        InlineKeyboardButton("❌ إلغاء", callback_data=cancel_key)
    )
    # Store the broadcast message temporarily, associated with the confirmation key
    admin_actions[confirm_key] = broadcast_text
    try:
        bot.reply_to(message, f"**معاينة الرسالة:**\n\n{broadcast_text}\n\nهل أنت متأكد أنك تريد إرسال هذه الرسالة إلى **{len(active_user_ids)}** مستخدم نشط؟ (سيتم تخطي المحظورين)", reply_markup=confirm_markup, parse_mode="Markdown")
    except telebot.apihelper.ApiTelegramException as e:
         logging.error(f"Failed to send broadcast confirmation: {e}")
         safe_send_message(chat_id, "❌ حدث خطأ أثناء عرض معاينة البث.")
         admin_actions.pop(confirm_key, None) # Clean up stored message if confirmation failed

# Handler for broadcast confirmation/cancellation callbacks
@bot.callback_query_handler(func=lambda call: call.data.startswith('broadcast_confirm_') or call.data.startswith('broadcast_cancel_'))
@check_access
@admin_list_command # Ensure only admin can confirm/cancel
def handle_broadcast_confirmation(call):
    admin_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id # ID of the confirmation message
    callback_id = call.id
    query_data = call.data

    confirm_key = None
    cancel_key = None
    original_message_id_str = query_data.split('_')[-1]

    if query_data.startswith('broadcast_confirm_'):
        confirm_key = query_data
    elif query_data.startswith('broadcast_cancel_'):
        cancel_key = query_data
        # Try to find the corresponding confirm key to remove the stored message
        confirm_key = f"broadcast_confirm_{original_message_id_str}"

    # Clean up stored message text
    broadcast_text = admin_actions.pop(confirm_key, None)

    if cancel_key:
        logging.info(f"Admin {admin_id} cancelled broadcast {original_message_id_str}.")
        safe_edit_message("🚫 تم إلغاء البث.", chat_id, message_id, reply_markup=None)
        safe_answer_callback(callback_id, "تم الإلغاء")
        return

    # If it's a confirmation and we found the text
    if confirm_key and broadcast_text:
        logging.info(f"Admin {admin_id} confirmed broadcast {original_message_id_str}.")
        safe_edit_message("⏳ جارٍ إرسال البث...", chat_id, message_id, reply_markup=None)
        safe_answer_callback(callback_id, "بدء الإرسال")

        known_user_ids = set(user_data.keys())
        active_user_ids = sorted(list(known_user_ids - blocked_users))
        success_count = 0
        fail_count = 0
        total_users_to_send = len(active_user_ids)

        start_time = time.time()
        for i, user_id in enumerate(active_user_ids):
            try:
                # Send with Markdown enabled, assuming admin composed with Markdown
                safe_send_message(user_id, broadcast_text, parse_mode="Markdown")
                success_count += 1
                logging.debug(f"Broadcast sent to {user_id}")
            except Exception as e:
                # safe_send_message handles logging, just count failure
                fail_count += 1
                logging.warning(f"Failed to send broadcast to {user_id}: {e}")
                # Consider removing user if blocked/deactivated? Needs careful thought.

            # Update status periodically
            if (i + 1) % 25 == 0 or (i + 1) == total_users_to_send:
                elapsed_time = time.time() - start_time
                try:
                    safe_edit_message(f"⏳ جارٍ إرسال البث... ({i+1}/{total_users_to_send})\nنجح: {success_count}, فشل: {fail_count}\nالوقت المنقضي: {elapsed_time:.1f} ثانية", chat_id, message_id)
                except Exception as edit_e:
                    logging.warning(f"Error updating broadcast status: {edit_e}")
            # Rate limiting delay
            time.sleep(0.1) # Adjust as needed based on Telegram limits

        end_time = time.time()
        total_time = end_time - start_time
        final_status_text = f"✅ اكتمل البث! ({total_time:.1f} ثانية)\nتم الإرسال بنجاح إلى: {success_count} مستخدم\nفشل الإرسال إلى: {fail_count} مستخدم"
        logging.info(final_status_text)
        safe_edit_message(final_status_text, chat_id, message_id)

    elif confirm_key and not broadcast_text:
        # Confirmation pressed, but text was already removed (e.g., double-click, race condition)
        logging.warning(f"Broadcast text for {confirm_key} not found in admin_actions.")
        safe_edit_message("❌ خطأ: لم يتم العثور على رسالة البث الأصلية. ربما تم تأكيدها أو إلغاؤها بالفعل.", chat_id, message_id, reply_markup=None)
        safe_answer_callback(callback_id, "خطأ")
    else:
        # Should not happen if logic is correct
        logging.error(f"Unhandled broadcast confirmation state: {query_data}")
        safe_answer_callback(callback_id, "خطأ غير معروف")

# --- Catch-all for unhandled text messages ---
@bot.message_handler(func=lambda message: get_user_state(message.from_user.id) is None, content_types=['text'])
@check_access
def handle_other_text(message):
    """Handles any text message when the user is not in a specific state."""
    logging.info(f"Received unhandled text from user {message.from_user.id}: '{message.text[:50]}...'" )
    update_user_data(message.from_user.id, message.from_user.username)
    safe_send_message(message.chat.id, "🤔 لم أفهم طلبك. يرجى استخدام الأمر /start للبدء أو أحد الأوامر المتاحة.")
    set_user_state(message.from_user.id, None)

# --- Main Execution Loop ---
if __name__ == "__main__":
    logging.info("Bot starting...")
    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        logging.info(f"Using temporary directory: {TEMP_DIR}")
    except OSError as e:
        logging.critical(f"Failed to create temporary directory {TEMP_DIR}: {e}. Exiting.")
        exit(1)

    logging.info(f"Admin ID: {ADMIN_ID}")
    logging.info(f"Channel ID: {CHANNEL_ID}")
    logging.info(f"Loaded {len(blocked_users)} blocked users.")
    logging.info(f"Loaded {len(upgraded_users)} upgraded users (Admin always upgraded)." )
    logging.info(f"Loaded {len(user_data)} users from user data file.")
    logging.info(f"Normalized {len(normalized_banned_words)} banned words.")
    logging.info(f"Max chars free: {MAX_CHARS_FREE}, Premium chunk size: {MAX_CHARS_PREMIUM_CHUNK}")
    logging.info(f"API Retries: {API_MAX_RETRIES}, Base Retry Delay: {API_RETRY_DELAY}s, Inter-Chunk Delay: {INTER_CHUNK_DELAY}s")
    logging.info("Bot is initializing polling...")

    polling_interval = 0
    polling_timeout = 30
    consecutive_errors = 0
    max_consecutive_errors = 5 # Limit before longer sleep

    while True:
        try:
            logging.info(f"Starting polling (interval={polling_interval}s, timeout={polling_timeout}s)...")
            # skip_pending=True ignores messages sent while bot was offline
            bot.polling(non_stop=True, interval=polling_interval, timeout=polling_timeout, skip_pending=True)
            # If polling stops gracefully (e.g., non_stop=False), this loop will exit.
            # Since non_stop=True, it should only exit on critical unhandled exceptions.
            logging.warning("Polling loop exited unexpectedly without error.")
            break # Exit loop if polling stops for some reason
        except requests.exceptions.ReadTimeout as e:
            logging.warning(f"Polling timeout error: {e}. Restarting polling...")
            consecutive_errors += 1
            time.sleep(1) # Short sleep on timeout
        except requests.exceptions.ConnectionError as e:
             logging.warning(f"Polling connection error: {e}. Retrying in 15 seconds...")
             consecutive_errors += 1
             time.sleep(15)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Telegram API error during polling: {e}")
            consecutive_errors += 1
            # Handle specific API errors if needed (e.g., authorization issues)
            if "Unauthorized" in str(e):
                 logging.critical("Bot token seems invalid or revoked. Exiting.")
                 exit(1)
            time.sleep(10) # Wait before retrying after API error
        except Exception as e:
            logging.critical(f"CRITICAL UNHANDLED ERROR in polling loop: {e}", exc_info=True)
            consecutive_errors += 1
            wait_time = 30 * consecutive_errors # Increase wait time on repeated critical errors
            logging.critical(f"Waiting {wait_time} seconds before restarting polling...")
            time.sleep(wait_time)
        else:
             # Reset error count if polling runs without exception for a cycle (though non_stop=True makes this unlikely)
             consecutive_errors = 0

        # Safety break if too many consecutive errors
        if consecutive_errors >= max_consecutive_errors:
             logging.critical(f"Too many ({consecutive_errors}) consecutive polling errors. Waiting 5 minutes before retrying.")
             time.sleep(300)
             consecutive_errors = 0 # Reset count after long wait

    logging.info("Bot script finished.")

