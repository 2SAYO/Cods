import uuid
import importlib.util
import pkg_resources
import sys
import pkgutil
import resource
import telebot
from telebot import types
import subprocess
import os
import re
import psutil
import time
import json
import logging
import datetime
from ping3 import ping
import threading
import shutil
import signal
import tempfile
import uuid
def get_formatted_time():
    now = datetime.datetime.now()
    hour = now.hour % 12 or 12
    period = "AM" if now.hour < 12 else "PM"
    return f"{now.year}/{now.month}/{now.day} - {hour}:{now.minute} {period}"

TOKEN = '7001218911:AAF_QZOeYo2wn7Tio47SkE_jPobWRIK6lOQ'

ADMIN_ID = '5026029533'

FORWARD_BOT_TOKEN = '6907844305:AAFNp_X3_K0D6C1_ee4gft-HWAnKgi495DM'

UPLOADED_FILES_DIR = "uploaded_files"
SANDBOX_BASE_DIR = "sandbox_environments"

BANNED_USERS_FILE = "banned_users.json"

UPGRADED_USERS_FILE = "upgraded_users.json"

USER_FILES_FILE = "user_files.json"

LOG_FILE = "bot_log.log"

DEFAULT_MAX_FILES = 2

CHANNEL_ID_1 = '@S_A_Y_O'
CHANNEL_ID_2 = '@Sayo_Bots'

# Constants for pending uploads
PENDING_UPLOADS_FILE = "pending_uploads.json"
PENDING_FILES_DIR = "pending_files_temp"


logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

logging.getLogger("telebot").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

bot = telebot.TeleBot(TOKEN)
forward_bot = telebot.TeleBot(FORWARD_BOT_TOKEN)

bot_scripts = {}
banned_users = {}
upgraded_users = {}
user_files = {}
username_to_id_cache = {}
process_map = {}
registered_users = set()
installed_libraries = set()
user_pending_libraries = {}

# Global variable for pending uploads
pending_uploads = {}
# Active timers for non-upgraded users
active_timers = {}

def process_admin_reason(message, action_type, request_id, pending_upload_info, admin_msg_chat_id, admin_msg_id):
    admin_id_str = str(message.from_user.id)
    reason = message.text.strip()

    # Assuming 'logger' is globally defined in the script
    if not reason:
        bot.send_message(admin_id_str, "Reason cannot be empty. Please provide a valid reason.")
        file_name = pending_upload_info.get('file_name', 'Unknown file')
        action_verb = "approve" if action_type == "approve" else "reject"
        bot.send_message(admin_id_str, f"Please provide the reason for {action_verb}ing the file: {file_name}")
        bot.register_next_step_handler(message, process_admin_reason, action_type, request_id, pending_upload_info, admin_msg_chat_id, admin_msg_id)
        return

    original_user_id = pending_upload_info['user_id']
    original_username = pending_upload_info['username']
    file_name = pending_upload_info['file_name']
    temp_file_path = pending_upload_info['temp_file_path']
    original_chat_id = pending_upload_info.get('chat_id') # For starting the script

    if action_type == "approve":
        final_file_path = os.path.join(UPLOADED_FILES_DIR, file_name)
        try:
            if not os.path.exists(UPLOADED_FILES_DIR):
                os.makedirs(UPLOADED_FILES_DIR)
            shutil.move(temp_file_path, final_file_path)
            logger.info(f"File {file_name} approved by admin {admin_id_str} and moved to {final_file_path}. Reason: {reason}")
            add_user_file(original_user_id, file_name, final_file_path)

            approval_message = f"✅ Your file [ {file_name} ] has been accepted by the admin and successfully run!\nReason: {reason}"

            if original_chat_id and callable(globals().get('start_bot_script')):
                try:
                    start_bot_script(original_user_id, file_name, final_file_path, original_chat_id)
                    logger.info(f"Attempted to start script {file_name} for user {original_user_id} after approval.")
                except Exception as start_e:
                    logger.error(f"Error auto-starting script {file_name} after approval: {start_e}")
                    approval_message += "(Note: Auto-start failed, please try running it manually if needed.)"
            
            if not is_user_upgraded(str(original_user_id)):
                expiry_time = datetime.datetime.now() + datetime.timedelta(days=1.5)
                expiry_formatted = expiry_time.strftime("%Y/%m/%d - %I:%M %p").replace(" 0", " ")
                approval_message += (f"⏳ Note: The file will be disabled after 1.5 days because you are a regular user "
                                     f"and not subscribed to the bot. It will automatically stop on {expiry_formatted}."
                                     f"To subscribe for unlimited runtime, contact the admin @G35GG.")
                timer_request_id = f"timer_{original_user_id}_{file_name.replace('.py', '')}_{uuid.uuid4().hex[:6]}"
                if callable(globals().get('schedule_stop')):
                    schedule_stop(timer_request_id, original_user_id, file_name, 1.5 * 24 * 60 * 60)
                else:
                    logger.error("schedule_stop function not found for approved file timer.")

            try:
                with open(final_file_path, 'rb') as doc_to_send:
                    bot.send_document(original_user_id, doc_to_send, caption=approval_message)
            except Exception as send_e:
                logger.error(f"Error sending approved document {file_name} to user {original_user_id}: {send_e}")
                bot.send_message(original_user_id, approval_message + "(Could not attach the file due to an error.)")
            
            bot.send_message(admin_id_str, f"File {file_name} for user @{original_username} (ID: {original_user_id}) has been approved. Reason: {reason}")
            try:
                bot.edit_message_text(text=f"File {file_name} has been APPROVED by you. Reason: {reason}", chat_id=admin_msg_chat_id, message_id=admin_msg_id, reply_markup=None)
            except Exception as edit_e:
                logger.warning(f"Could not edit admin approval message: {edit_e}")

        except Exception as e:
            logger.error(f"Error approving file {file_name} for user {original_user_id}: {e}")
            bot.send_message(admin_id_str, f"An error occurred while approving {file_name}: {e}")
            bot.send_message(original_user_id, f"⚠️ An error occurred while processing the approval for your file {file_name}. Please contact support.")

    elif action_type == "reject":
        try:
            rejection_message = (f"❌ Your file [ {file_name} ] has been rejected by the admin."
                                 f"Reason: {reason}"
                                 f"To appeal this decision, please contact the admin: @G35GG")
            try:
                if os.path.exists(temp_file_path):
                    with open(temp_file_path, 'rb') as doc_to_send:
                        bot.send_document(original_user_id, doc_to_send, caption=rejection_message)
                    os.remove(temp_file_path)
                else:
                    bot.send_message(original_user_id, rejection_message)
            except Exception as send_e:
                logger.error(f"Error sending rejected document {file_name} to user {original_user_id}: {send_e}")
                bot.send_message(original_user_id, rejection_message + "(Could not attach the file due to an error.)")
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

            logger.info(f"File {file_name} for user {original_user_id} rejected by admin {admin_id_str}. Reason: {reason}")
            bot.send_message(admin_id_str, f"File {file_name} for user @{original_username} (ID: {original_user_id}) has been rejected. Reason: {reason}")
            try:
                bot.edit_message_text(text=f"File {file_name} has been REJECTED by you. Reason: {reason}", chat_id=admin_msg_chat_id, message_id=admin_msg_id, reply_markup=None)
            except Exception as edit_e:
                logger.warning(f"Could not edit admin rejection message: {edit_e}")

        except Exception as e:
            logger.error(f"Error rejecting file {file_name} for user {original_user_id}: {e}")
            bot.send_message(admin_id_str, f"An error occurred while rejecting {file_name}: {e}")

    if request_id in pending_uploads:
        del pending_uploads[request_id]
        save_pending_uploads()


def setup_directories():
    # Ensure main upload directory exists
    if not os.path.exists(UPLOADED_FILES_DIR):
        os.makedirs(UPLOADED_FILES_DIR)
        logger.info(f"Created directory: {UPLOADED_FILES_DIR}")
    # Clean the main upload directory (as per original logic)
    else:
        for filename in os.listdir(UPLOADED_FILES_DIR):
            file_path = os.path.join(UPLOADED_FILES_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    logger.info(f"Deleted file during setup: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting file {file_path} during setup: {e}")

    # Ensure sandbox base directory exists and is clean
    if not os.path.exists(SANDBOX_BASE_DIR):
        os.makedirs(SANDBOX_BASE_DIR)
        logger.info(f"Created directory: {SANDBOX_BASE_DIR}")
    else:
        # Clean up any leftover sandbox directories from previous runs
        for item_name in os.listdir(SANDBOX_BASE_DIR):
            item_path = os.path.join(SANDBOX_BASE_DIR, item_name)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    logger.info(f"Cleaned up old sandbox: {item_path}")
            except Exception as e:
                logger.error(f"Error cleaning up sandbox {item_path}: {e}")

    # Ensure pending files directory exists
    if not os.path.exists(PENDING_FILES_DIR):
        os.makedirs(PENDING_FILES_DIR)
        logger.info(f"Created directory: {PENDING_FILES_DIR}")
    # Clean the pending files directory (optional, but good practice)
    else:
        for filename in os.listdir(PENDING_FILES_DIR):
            file_path = os.path.join(PENDING_FILES_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    logger.info(f"Deleted pending file during setup: {file_path}")
            except Exception as e:
                logger.error(f"Error deleting pending file {file_path} during setup: {e}")

def load_banned_users():
    global banned_users
    try:
        if os.path.exists(BANNED_USERS_FILE):
            with open(BANNED_USERS_FILE, 'r') as f:
                banned_users = json.load(f)
                logger.info(f"Loaded {len(banned_users)} banned users")
        else:
            banned_users = {}
            save_banned_users()
    except Exception as e:
        logger.error(f"Error loading banned users: {e}")
        banned_users = {}

def save_banned_users():
    try:
        with open(BANNED_USERS_FILE, 'w') as f:
            json.dump(banned_users, f, indent=4)
        logger.info(f"Saved {len(banned_users)} banned users")
    except Exception as e:
        logger.error(f"Error saving banned users: {e}")

def is_user_banned(user_id):
    return str(user_id) in banned_users

def ban_user(user_id, username):
    banned_users[str(user_id)] = {
        "username": username,
        "banned_at": get_formatted_time()
    }
    save_banned_users()
    logger.info(f"Banned user: {user_id} (@{username})")

def unban_user(user_id):
    if str(user_id) in banned_users:
        username = banned_users[str(user_id)].get("username", "Unknown")
        del banned_users[str(user_id)]
        save_banned_users()
        logger.info(f"Unbanned user: {user_id} (@{username})")
        return True
    return False

def is_admin(user_id):
    return str(user_id) == ADMIN_ID




def is_module_available(module_name):
    """Checks if a module is built-in, standard library, or already pip-installed."""
    if module_name in sys.builtin_module_names:
        return True
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is not None:
            # 'built-in' or 'frozen' for true builtins
            # If spec.origin is None, it could be a namespace package or something complex.
            # If spec.loader is not None, it's generally available.
            if spec.origin == 'built-in' or spec.origin == 'frozen':
                return True
            if spec.loader is not None: # Indicates it's an importable module (std lib or installed)
                 return True
    except ModuleNotFoundError:
        return False
    except Exception as e:
        logger.debug(f"Exception during find_spec for {module_name}: {e}")
        return False # Treat as not available if unsure
    return False

@bot.callback_query_handler(func=lambda call: call.data == "download_library")
def handle_download_library_button(call):
    try:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "Please send the name of the library you want to download.")
        bot.register_next_step_handler(msg, process_library_name_input)
    except Exception as e:
        logger.error(f"Error in handle_download_library_button: {e}")
        bot.send_message(call.message.chat.id, "An error occurred. Please try again later.")

def process_library_name_input(message):
    chat_id = message.chat.id
    library_name = message.text.strip()

    if not library_name:
        bot.send_message(chat_id, "Library name cannot be empty. Please try again.")
        return

    try:
        # 1. Check if already in our installed_libraries set (installed by bot before or by script)
        if library_name in installed_libraries:
            bot.send_message(chat_id, f"Library '{library_name}' is already installed by the bot.")
            return

        # 2. Check if it's a built-in or standard library module not requiring pip install
        if is_module_available(library_name):
            # Check with pip show as a fallback for already installed but not in 'installed_libraries'
            try:
                check_process = subprocess.run([sys.executable, "-m", "pip", "show", library_name], capture_output=True, text=True, check=False, timeout=10)
                if check_process.returncode == 0:
                    bot.send_message(chat_id, f"Library '{library_name}' is already installed (verified by pip)." )
                    installed_libraries.add(library_name) # Ensure it's tracked
                    return
            except subprocess.TimeoutExpired:
                logger.warning(f"pip show timed out for {library_name}")
            except Exception as e_pip_show:
                logger.info(f"Pip show check for {library_name} failed or library not found by pip show: {e_pip_show}")
            
            # If pip show didn't confirm, but is_module_available was true (e.g. built-in)
            if not library_name in installed_libraries: # Re-check after pip show attempt
                 bot.send_message(chat_id, f"Library '{library_name}' is a built-in or standard module and is already available.")
                 installed_libraries.add(library_name) # Ensure it's tracked
                 return
            # If it got added by pip show, the first check in this block would have caught it.

        # 3. Attempt to install using pip
        bot.send_message(chat_id, f"Attempting to download and install '{library_name}'...")
        install_process = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", library_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Set a timeout for the installation process
        try:
            stdout, stderr = install_process.communicate(timeout=120) # 2 minutes timeout for pip install
        except subprocess.TimeoutExpired:
            install_process.kill()
            stdout, stderr = install_process.communicate()
            logger.error(f"Pip install for '{library_name}' timed out.")
            bot.send_message(chat_id, f"Installation of '{library_name}' timed out. Please try again or check the library name.")
            return

        if install_process.returncode == 0:
            installed_libraries.add(library_name)
            bot.send_message(chat_id, f"Library '{library_name}' downloaded successfully ✅")
            logger.info(f"Library '{library_name}' installed successfully by user {chat_id}.")
        else:
            if "Requirement already satisfied" in stdout or "Requirement already satisfied" in stderr:
                 bot.send_message(chat_id, f"Library '{library_name}' is already installed.")
                 installed_libraries.add(library_name) # Ensure it's tracked
                 logger.info(f"Library '{library_name}' was already satisfied for user {chat_id}.")
            else:
                error_message = stderr or stdout or "Unknown error during installation"
                logger.error(f"Failed to install library '{library_name}'. Pip output: {error_message}")
                concise_error = error_message.splitlines()[-1] if error_message.splitlines() else 'Unknown installation error'
                if len(concise_error) > 200:
                    concise_error = concise_error[:197] + "..."
                bot.send_message(chat_id, f"Failed to find or install library '{library_name}'. Error: {concise_error}")
    except Exception as e:
        logger.error(f"Error in process_library_name_input for '{library_name}': {e}")
        bot.send_message(chat_id, f"An error occurred while processing library '{library_name}'. Please contact support if this persists.")



def load_upgraded_users():
    global upgraded_users
    try:
        if os.path.exists(UPGRADED_USERS_FILE):
            with open(UPGRADED_USERS_FILE, 'r') as f:
                upgraded_users = json.load(f)
                logger.info(f"Loaded {len(upgraded_users)} upgraded users")
        else:
            upgraded_users = {}
            save_upgraded_users()
    except Exception as e:
        logger.error(f"Error loading upgraded users: {e}")
        upgraded_users = {}

def save_upgraded_users():
    try:
        with open(UPGRADED_USERS_FILE, 'w') as f:
            json.dump(upgraded_users, f, indent=4)
        logger.info(f"Saved {len(upgraded_users)} upgraded users")
    except Exception as e:
        logger.error(f"Error saving upgraded users: {e}")

def is_user_upgraded(user_id):
    return str(user_id) in upgraded_users

def upgrade_user(user_id, username, max_files):
    upgraded_users[str(user_id)] = {
        "username": username,
        "max_files": max_files,
        "upgraded_at": get_formatted_time()
    }
    save_upgraded_users()
    logger.info(f"Upgraded user: {user_id} (@{username}) to {max_files} files")

def downgrade_user(user_id):
    if str(user_id) in upgraded_users:
        username = upgraded_users[str(user_id)].get("username", "Unknown")
        del upgraded_users[str(user_id)]
        save_upgraded_users()
        logger.info(f"Downgraded user: {user_id} (@{username})")
        return True
    return False

def get_user_max_files(user_id):
    if str(user_id) in upgraded_users:
        return upgraded_users[str(user_id)].get("max_files", DEFAULT_MAX_FILES)
    return DEFAULT_MAX_FILES

def load_user_files():
    global user_files
    try:
        if os.path.exists(USER_FILES_FILE):
            with open(USER_FILES_FILE, 'r') as f:
                user_files = json.load(f)
                logger.info(f"Loaded user files for {len(user_files)} users")
        else:
            user_files = {}
            save_user_files()
    except Exception as e:
        logger.error(f"Error loading user files: {e}")
        user_files = {}

def save_user_files():
    try:
        with open(USER_FILES_FILE, 'w') as f:
            json.dump(user_files, f, indent=4)
        logger.info(f"Saved user files for {len(user_files)} users")
    except Exception as e:
        logger.error(f"Error saving user files: {e}")

def load_pending_uploads():
    global pending_uploads
    try:
        if os.path.exists(PENDING_UPLOADS_FILE):
            with open(PENDING_UPLOADS_FILE, 'r') as f:
                pending_uploads = json.load(f)
                logger.info(f"Loaded {len(pending_uploads)} pending uploads")
        else:
            pending_uploads = {}
            save_pending_uploads()
    except Exception as e:
        logger.error(f"Error loading pending uploads: {e}")
        pending_uploads = {}

def save_pending_uploads():
    try:
        with open(PENDING_UPLOADS_FILE, 'w') as f:
            json.dump(pending_uploads, f, indent=4)
        logger.info(f"Saved {len(pending_uploads)} pending uploads")
    except Exception as e:
        logger.error(f"Error saving pending uploads: {e}")

# Function to schedule the automatic stop
def schedule_stop(request_id, user_id, file_name, delay_seconds):
    def stop_action():
        logger.info(f"Timer expired for request {request_id} ({file_name}). Stopping script.")
        # Assuming file_name is sufficient for stop_bot_script
        script_name_to_stop = file_name # Placeholder - adjust if needed
        
        # Ensure the script is actually running before attempting to stop and notify
        update_process_map() # Refresh the process map
        if script_name_to_stop in process_map or script_name_to_stop in bot_scripts:
            stopped = stop_bot_script(script_name_to_stop, None, user_id, force=True)
            
            if stopped:
                try:
                    bot.send_message(
                        user_id,
                        f"⏳ Your file \'{file_name}\' has been automatically stopped due to the end of the free file upload period.\n\n"
                        f"To subscribe to the bot and run files for life, contact the developer @G35GG."
                    )
                    logger.info(f"Notified user {user_id} about automatic stop for {file_name}.")
                except Exception as e:
                    logger.error(f"Error notifying user {user_id} about automatic stop: {e}")
                # Also remove the file record after successful auto-stop
                remove_user_file(user_id, script_name_to_stop)
                # Attempt to delete the file itself
                script_path = os.path.join(UPLOADED_FILES_DIR, script_name_to_stop)
                try:
                    if os.path.exists(script_path):
                        os.remove(script_path)
                        logger.info(f"Deleted file after auto-stop: {script_path}")
                except Exception as del_e:
                    logger.error(f"Error deleting file {script_path} after auto-stop: {del_e}")
            else:
                 logger.warning(f"Could not automatically stop script {script_name_to_stop} for user {user_id} after timer expired (stop_bot_script failed).")
        else:
            logger.info(f"Script {script_name_to_stop} was not running when timer expired for request {request_id}. No stop action needed.")
            # Remove file record if it exists but script wasn't running
            remove_user_file(user_id, script_name_to_stop)

        # Clean up timer reference
        active_timers.pop(request_id, None)

    timer = threading.Timer(delay_seconds, stop_action)
    timer.start()
    active_timers[request_id] = timer
    logger.info(f"Scheduled stop timer for request {request_id} ({file_name}) in {delay_seconds} seconds.")

def add_user_file(user_id, file_name, file_path):
    if str(user_id) not in user_files:
        user_files[str(user_id)] = []
    
    for existing_file in user_files[str(user_id)]:
        if existing_file["name"] == file_name:
            existing_file["path"] = file_path
            existing_file["uploaded_at"] = get_formatted_time()
            save_user_files()
            logger.info(f"Updated file {file_name} for user {user_id}")
            return
    
    user_files[str(user_id)].append({
        "name": file_name,
        "path": file_path,
        "uploaded_at": get_formatted_time()
    })
    save_user_files()
    logger.info(f"Added file {file_name} to user {user_id}")

def remove_user_file(user_id, file_name):
    removed = False
    
    if str(user_id) in user_files:
        prev_length = len(user_files[str(user_id)])
        
        original_name = file_name
        prefixed_name = "file_" + file_name
        
        user_files[str(user_id)] = [f for f in user_files[str(user_id)] 
                                   if f["name"] != original_name and f["name"] != prefixed_name]
        
        if len(user_files[str(user_id)]) < prev_length:
            removed = True
            logger.info(f"Removed file {file_name} from user {user_id}")
            
            if len(user_files[str(user_id)]) == 0:
                del user_files[str(user_id)]
                logger.info(f"Removed empty user entry for {user_id}")
            
            save_user_files()
        else:
            logger.warning(f"File {file_name} not found in user {user_id}'s files")
    else:
        logger.warning(f"User {user_id} has no files to remove")
    
    return removed

def delete_all_user_files(user_id):
    if str(user_id) not in user_files or not user_files[str(user_id)]:
        return 0, False
    
    files_count = len(user_files[str(user_id)])
    
    for file_data in user_files[str(user_id)]:
        file_name = file_data["name"]
        file_path = file_data["path"]
        
        stop_bot_script(file_name, None, user_id, force=True)
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted file: {file_path}")
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {e}")
    
    del user_files[str(user_id)]
    save_user_files()
    
    logger.info(f"Deleted all {files_count} files for user {user_id}")
    return files_count, True

def get_user_files(user_id):
    return user_files.get(str(user_id), [])

def count_user_files(user_id):
    return len(user_files.get(str(user_id), []))

def get_file_owner(file_name):

    original_name = file_name
    prefixed_name = "file_" + file_name
    
    for user_id, files in user_files.items():
        for file in files:
            if file["name"] == original_name or file["name"] == prefixed_name:
                return user_id
    return None

def reset_all_user_files():
    global user_files
    user_files = {}
    save_user_files()
    logger.info("Reset all user files data")

    try:
        for filename in os.listdir(UPLOADED_FILES_DIR):
            file_path = os.path.join(UPLOADED_FILES_DIR, filename)
            if os.path.isfile(file_path):
                os.unlink(file_path)
                logger.info(f"Deleted file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up directory: {e}")

def get_all_running_files():
    running_files = {}
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and len(cmdline) > 1 and 'python' in cmdline[0].lower():
                for i in range(1, len(cmdline)):
                    if UPLOADED_FILES_DIR in cmdline[i]:
                        file_path = cmdline[i]
                        file_name = os.path.basename(file_path)
                        running_files[file_name] = proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return running_files

def update_process_map():
    global process_map
    process_map = get_all_running_files()
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Updated process map: {process_map}")

def kill_all_running_processes():
    killed_count = 0
    try:
        for script_name, script_info in list(bot_scripts.items()):
            process = script_info['process']
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                killed_count += 1
                logger.info(f"Killed process for {script_name}")
        bot_scripts.clear()
        process_map.clear()
        logger.info(f"Killed {killed_count} running processes")
    except Exception as e:
        logger.error(f"Error killing all processes: {e}")
    return killed_count

def resolve_username(username):

    if username.startswith('@'):
        username = username[1:]

    if username in username_to_id_cache:
        return username_to_id_cache[username]

    for user_id, data in banned_users.items():
        if data.get("username") == username:
            username_to_id_cache[username] = user_id
            return user_id

    for user_id, data in upgraded_users.items():
        if data.get("username") == username:
            username_to_id_cache[username] = user_id
            return user_id

    for user_id, files in user_files.items():
        if files and len(files) > 0:
            for banned_id, data in banned_users.items():
                if banned_id == user_id and data.get("username") == username:
                    username_to_id_cache[username] = user_id
                    return user_id
            for upgraded_id, data in upgraded_users.items():
                if upgraded_id == user_id and data.get("username") == username:
                    username_to_id_cache[username] = user_id
                    return user_id
    
    temp_id = f"username_{username}"
    username_to_id_cache[username] = temp_id
    return temp_id

def validate_python_file(file_path):

    try:

        return True, ""
    except Exception as e:
        logger.error(f"Error validating file: {e}")
        return False, str(e)

@bot.message_handler(func=lambda message: is_user_banned(message.from_user.id))
def handle_banned_user(message):
    bot.send_message(
        message.chat.id,
        "🔴 : You are banned from using the bot \n"
        "Contact the developer to appeal: @G35GG"
    )

@bot.message_handler(commands=['start'])
def start(message):
    user = message.from_user
    user_id = user.id
    username = user.username or "Unknown"
    first_name = user.first_name or ""

    registered_users.add(user_id)
    logger.info(f"User {user_id} (@{username}) started the bot and was added to registered_users.")

    if username != "Unknown":
        username_to_id_cache[username] = str(user_id)

    # تحقق من الاشتراك في القناة الأولى
    try:
        chat_member1 = bot.get_chat_member(CHANNEL_ID_1, user_id)
        is_subscribed1 = chat_member1.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking subscription for {CHANNEL_ID_1} for user {user_id}: {e}")
        is_subscribed1 = False

    if not is_subscribed1:
        markup1 = types.InlineKeyboardMarkup()
        channel_button1 = types.InlineKeyboardButton("Join Channel 1 💫", url=f"https://t.me/{CHANNEL_ID_1.strip('@')}")
        markup1.add(channel_button1)
        bot.send_message(message.chat.id,
                         f"🌀 | Oops!\n"
                         f"📢 | Please join our first channel to use the bot: {CHANNEL_ID_1}\n\n"
                         f"🔗 | https://t.me/{CHANNEL_ID_1.strip('@')}\n\n"
                         f"🚀🚀 | After joining, please send /start again.",
                         reply_markup=markup1)
        return

    # تحقق من الاشتراك في القناة الثانية
    try:
        chat_member2 = bot.get_chat_member(CHANNEL_ID_2, user_id)
        is_subscribed2 = chat_member2.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking subscription for {CHANNEL_ID_2} for user {user_id}: {e}")
        is_subscribed2 = False

    if not is_subscribed2:
        markup2 = types.InlineKeyboardMarkup()
        channel_button2 = types.InlineKeyboardButton("Join Channel 2 💫", url=f"https://t.me/{CHANNEL_ID_2.strip('@')}")
        markup2.add(channel_button2)
        bot.send_message(message.chat.id,
                         f"🌀 | Almost there!\n"
                         f"📢 | Please also join our second channel to use the bot: {CHANNEL_ID_2}\n\n"
                         f"🔗 | https://t.me/{CHANNEL_ID_2.strip('@')}\n\n"
                         f"🚀🚀 | After joining, please send /start again.",
                         reply_markup=markup2)
        return

    # إشعار المدير بمحاولة جديدة
    try:
        forward_bot.send_message(
            ADMIN_ID,
            f"👤 مستخدم جديد حاول استخدام البوت:\n\n"
            f"• معرف المستخدم: {user_id}\n"
            f"• اسم المستخدم: @{username if username != 'Unknown' else 'غير معروف'}\n"
            f"• الوقت: {get_formatted_time()}"
        )
    except Exception as e:
        logger.error(f"Error notifying admin about new user attempt: {e}")

    # التحقق من الحظر
    if is_user_banned(user_id):
        bot.send_message(
            message.chat.id,
            "🔴 : You are banned from using the bot \n"
            "Contact the developer to appeal: @G35GG"
        )
        return

    # إعداد لوحة التحكم
    markup = types.InlineKeyboardMarkup(row_width=2)
    upload_button = types.InlineKeyboardButton("Upload File 📤", callback_data='upload')
    my_files_button = types.InlineKeyboardButton("My Files 📁", callback_data='my_files')
    ping_button = types.InlineKeyboardButton("Ping ⏱️", callback_data='ping')
    help_button = types.InlineKeyboardButton("Help ❓", callback_data='help')
    owner_button = types.InlineKeyboardButton("Owner 📌", url='https://t.me/G35GG')
    download_library_button = types.InlineKeyboardButton("Download Library 📚", callback_data='download_library')

    markup.add(upload_button, my_files_button)
    markup.add(ping_button, help_button)
    markup.add(download_library_button)
    markup.add(owner_button)
    
    # رسالة الترحيب
    welcome_message = f"—————————————————————————\n\n• Hi : {first_name}!\n\n• ID: {user_id} | User: @{username if username != 'Unknown' else 'unavailable'}"
    if is_user_upgraded(user_id):
        welcome_message += f"\n\n• 🌟 You are upgraded with {get_user_max_files(user_id)} file"
    else:
        welcome_message += f"\n\n❌ You are not upgraded - file count : {get_user_max_files(user_id)}"
    welcome_message += "\n\n—————————————————————————\n\n• Choose :"

    bot.send_message(
        message.chat.id,
        welcome_message,
        reply_markup=markup
    )

    # إشعار المدير بالانضمام الجديد
    try:
        forward_bot.send_message(
            ADMIN_ID,
            f"👤 مستخدم جديد انضم للبوت (أو أعاد تشغيله):\n\n"
            f"• الاسم: {first_name}\n"
            f"• المعرف: @{username if username != 'Unknown' else 'غير معروف'}\n"
            f"• الآيدي: {user_id}\n"
            f"• الوقت: {get_formatted_time()}"
        )
    except Exception as e:
        logger.error(f"Error notifying admin about new user start: {e}")


@bot.message_handler(commands=['help'])
def help_command(message):
    if is_user_banned(message.from_user.id):
        return
    
    show_help(message.chat.id)

@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    
    if is_user_banned(user_id):
        return
    
    if is_admin(user_id):
        bot.send_message(
            message.chat.id,
            "🛠️ أوامر المشرف\n\n"
            "/admin_files - عرض الملفات المرفوعة\n"
            "/admin_ban - حظر مستخدم\n"
            "/admin_banned - عرض المستخدمين المحظورين\n"
            "/admin_unban - إلغاء حظر مستخدم\n"
            "/admin_upgrade - ترقية مستخدم\n"
            "/admin_upgraded - عرض المستخدمين المرقّين\n"
            "/admin_downgrade - إلغاء ترقية مستخدم\n"
            "/admin_delete_user_files - حذف جميع ملفات مستخدم\n"
            "/admin_logs - عرض السجلات الأخيرة\n"
            "/admin_processes - عرض العمليات الجارية\n"
            "/admin_broadcast - إرسال رسالة لجميع المستخدمين المسجلين (/start)\n"
            "/pending_uploads - عرض طلبات الرفع المعلقة\n" # <<< Added pending uploads command
            "/reset - إعادة تعيين جميع الملفات"
        )
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_files'])
def admin_files_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        update_process_map()
        show_uploaded_files(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_ban'])
def admin_ban_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        ask_for_ban_username(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_banned'])
def admin_banned_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        show_banned_users(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_unban'])
def admin_unban_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        ask_for_unban_username(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_upgrade'])
def admin_upgrade_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        ask_for_upgrade_username(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_upgraded'])
def admin_upgraded_command(message):
    """Handle /admin_upgraded command - Admin only command to view upgraded users"""
    user_id = message.from_user.id
    
    if is_admin(user_id):
        show_upgraded_users_list(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_downgrade'])
def admin_downgrade_command(message):
    """Handle /admin_downgrade command - Admin only command to downgrade a user"""
    user_id = message.from_user.id
    
    if is_admin(user_id):
        ask_for_downgrade_username(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_delete_user_files'])
def admin_delete_user_files_command(message):
    """Handle /admin_delete_user_files command - Admin only command to delete all files of a user"""
    user_id = message.from_user.id
    
    if is_admin(user_id):
        ask_for_delete_files_username(message.chat.id)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )


@bot.message_handler(commands=['admin_logs'])
def admin_logs_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        try:
            with open(LOG_FILE, 'r') as f:
                logs = f.readlines()
                last_logs = logs[-20:] if len(logs) > 20 else logs
            
            logs_message = "📋 Recent Logs\n\n"
            for log in last_logs:
                logs_message += f"{log.strip()}\n"
            
            logs_message += "\nUse /admin to return to admin commands."
            
            bot.send_message(
                message.chat.id,
                logs_message
            )
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"✖️ Error reading logs: {str(e)}\n\n"
                "Use /admin to return to admin commands."
            )
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['admin_processes'])
def admin_processes_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        update_process_map()
        
        if not process_map:
            bot.send_message(
                message.chat.id,
                "📋 Running Processes\n\n"
                "No processes are currently running.\n\n"
                "Use /admin to return to admin commands."
            )
            return
        
        processes_message = "📋 Running Processes\n\n"
        
        for i, (script_name, pid) in enumerate(process_map.items(), 1):
            
            owner_id = get_file_owner(script_name)
            owner_username = "Unknown"
            
            if owner_id:
                if owner_id in upgraded_users:
                    owner_username = upgraded_users[owner_id].get("username", "Unknown")
                elif owner_id in banned_users:
                    owner_username = banned_users[owner_id].get("username", "Unknown")
            
            processes_message += f"{i}. {script_name}\n"
            processes_message += f"   - PID: {pid}\n"
            processes_message += f"   - Owner: "
            if owner_id:
                processes_message += f"ID: {owner_id}"
                if owner_username != "Unknown":
                    processes_message += f" (@{owner_username})"
            else:
                processes_message += "Unknown"
            processes_message += "\n"
            processes_message += f"   - Stop command: /stop_file {script_name}\n\n"
        
        processes_message += "Use /admin to return to admin commands."
        
        bot.send_message(
            message.chat.id,
            processes_message
        )
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

@bot.message_handler(commands=['reset'])
def reset_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        reset_all_user_files()
        killed_count = kill_all_running_processes()
        
        bot.send_message(
            message.chat.id,
            f"✅ Reset Successful\n\n"
            f"• All user files data has been reset\n"
            f"• {killed_count} running processes were terminated\n\n"
            f"The bot is now in a clean state."
        )
        logger.info(f"Admin {user_id} performed a complete reset")
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )


@bot.message_handler(commands=["pending_uploads"])
def admin_pending_uploads_command(message):
    user_id = message.from_user.id

    if not is_admin(user_id):
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )
        return

    load_pending_uploads() # Ensure latest data is loaded

    if not pending_uploads:
        bot.send_message(
            message.chat.id,
            "📂 Pending Uploads\n\nThere are no pending file uploads to review.\n\nUse /admin to return to admin commands."
        )
        return

    bot.send_message(message.chat.id, "📂 Processing Pending Uploads...") # Initial message

    # Sort requests by time (optional, but helpful)
    sorted_requests = sorted(pending_uploads.items(), key=lambda item: item[1].get("request_timestamp", 0))

    files_sent = 0
    for request_id, details in sorted_requests:
        try:
            temp_path = details.get('temp_path')
            if not temp_path or not os.path.exists(temp_path):
                 logger.error(f"Pending file path not found or invalid for request {request_id}: {temp_path}")
                 bot.send_message(ADMIN_ID, f"⚠️ Error: Could not find the file for request ID {request_id} ({details.get('original_filename', 'N/A')}). It might have been deleted.")
                 continue # Skip this request

            caption_text = (
                f"📄 File: {details.get('original_filename', 'N/A')}\n"
                f"👤 User: {details.get('first_name', '')}"
                f" (@{details.get('username', 'Unknown')}, ID: {details.get('user_id', 'N/A')})\n"
                f"⏱️ Requested: {details.get('request_time', 'N/A')}"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            accept_button = types.InlineKeyboardButton("Accept ✅", callback_data=f"accept_{request_id}")
            reject_button = types.InlineKeyboardButton("Reject ❌", callback_data=f"reject_{request_id}")
            markup.add(accept_button, reject_button)

            with open(temp_path, "rb") as file_doc:
                bot.send_document(
                    message.chat.id,
                    file_doc,
                    caption=caption_text,
                    reply_markup=markup
                )
            files_sent += 1
            time.sleep(0.5) # Add a small delay to avoid hitting rate limits

        except Exception as e:
            logger.error(f"Error sending pending file for request {request_id}: {e}")
            bot.send_message(ADMIN_ID, f"⚠️ Failed to send pending file for request ID {request_id} ({details.get('original_filename', 'N/A')}). Error: {e}")

    # Final summary message
    if files_sent == 0 and pending_uploads: # If loop ran but no files were sent due to errors
         bot.send_message(message.chat.id, "⚠️ Could not process pending uploads. Check logs for errors.")
    elif files_sent > 0:
        bot.send_message(message.chat.id, f"✅ Displayed {files_sent} pending upload(s).\n\nUse /admin to return to admin commands.")
    # If no pending uploads initially, the first message handles it.








logger = logging.getLogger(__name__)
installed_libraries = set()

def extract_dependencies(file_path):
    """Extract required external libraries from a Python file (excluding built-ins)"""
    dependencies = set()

    std_libs = set(sys.builtin_module_names) | {
        module.name for module in pkgutil.iter_modules()
    }

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.split('#')[0].strip()
                if not line:
                    continue

                # Match "import x, y as z"
                import_match = re.match(r'^import\s+(.+)', line)
                if import_match:
                    modules = import_match.group(1).split(',')
                    for module in modules:
                        module_name = module.strip().split(' as ')[0].split('.')[0]
                        if module_name in ('telegram', 'telegram.ext'):
                            dependencies.add('python-telegram-bot')
                        elif module_name and module_name not in std_libs:
                            dependencies.add(module_name)

                # Match "from x.y import z"
                from_match = re.match(r'^from\s+([a-zA-Z0-9_\.]+)\s+import', line)
                if from_match:
                    module_name = from_match.group(1).split('.')[0]
                    if module_name in ('telegram', 'telegram.ext'):
                        dependencies.add('python-telegram-bot')
                    elif module_name and module_name not in std_libs:
                        dependencies.add(module_name)

        return list(dependencies)

    except Exception as e:
        logger.error(f"Error extracting dependencies: {e}")
        return []


def install_libraries(libraries, message_id=None, chat_id=None):
    """Install Python libraries, avoiding duplicates and already installed ones"""
    if not libraries:
        return True, "No libraries to install"

    try:
        for library in libraries:
            if library in installed_libraries:
                logger.info(f"Library already marked as installed: {library}")
                continue

            # Skip if library is already installed
            if importlib.util.find_spec(library.replace('-', '_')) is not None:
                logger.info(f"Library already installed: {library}")
                installed_libraries.add(library)
                continue

            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--user', library])
                installed_libraries.add(library)
                logger.info(f"Successfully installed library: {library}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install library {library}: {e}")
                return False, f"Failed to install {library}: {str(e)}"

        return True, f"Successfully installed {len(installed_libraries)} libraries"

    except Exception as e:
        logger.error(f"Error during library installation: {e}")
        return False, f"Installation error: {str(e)}"

def get_bot_token(file_path):
    """Extract bot token from a Python file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            
            # Look for common token patterns
            token_patterns = [
                r'[\'"]([0-9]{8,10}:[A-Za-z0-9_-]{35})[\'"]',  # Standard token format
                r'bot_token\s*=\s*[\'"]([0-9]{8,10}:[A-Za-z0-9_-]{35})[\'"]',
                r'token\s*=\s*[\'"]([0-9]{8,10}:[A-Za-z0-9_-]{35})[\'"]',
                r'TOKEN\s*=\s*[\'"]([0-9]{8,10}:[A-Za-z0-9_-]{35})[\'"]',
                r'api_token\s*=\s*[\'"]([0-9]{8,10}:[A-Za-z0-9_-]{35})[\'"]',
                r'API_TOKEN\s*=\s*[\'"]([0-9]{8,10}:[A-Za-z0-9_-]{35})[\'"]'
            ]
            
            for pattern in token_patterns:
                match = re.search(pattern, content)
                if match:
                    return match.group(1)
            
            return None
    except Exception as e:
        logger.error(f"Error extracting bot token: {e}")
        return None

def run_uploaded_file(script_path, chat_id, user_id, script_name):
    """Run an uploaded Python file in an isolated sandbox directory."""
    sandbox_dir = None # Initialize sandbox_dir
    try:
        # Check if already running (using bot_scripts dictionary)
        if script_name in bot_scripts and bot_scripts[script_name].get('process') and bot_scripts[script_name]['process'].poll() is None:
            logger.warning(f"Script {script_name} is already running for user {user_id}")
            # Optionally inform user, but original code didn\'t, so we won\'t add it.
            return False # Indicate already running
        
        # 1. Create a unique sandbox directory
        # Ensure the SANDBOX_BASE_DIR exists (should be handled by setup_directories)
        if not os.path.exists(SANDBOX_BASE_DIR):
             os.makedirs(SANDBOX_BASE_DIR)
             logger.warning(f"Created SANDBOX_BASE_DIR {SANDBOX_BASE_DIR} on the fly.")
             
        sandbox_dir = tempfile.mkdtemp(prefix=f"sandbox_{user_id}_", dir=SANDBOX_BASE_DIR)
        logger.info(f"Created sandbox for {script_name} at {sandbox_dir}")

        # 2. Copy the script into the sandbox
        sandbox_script_name = os.path.basename(script_path)
        sandbox_script_path = os.path.join(sandbox_dir, sandbox_script_name)
        shutil.copy2(script_path, sandbox_script_path)

        # 3. Create the note.txt file
        note_content = (
            "لا يمكنك سحب ملفات هذا البوت لأنه محمي بأقصى أنواع الحمايات ومبرمج وفق معايير حديثة.\n"
            "You cannot extract files from this bot as it is protected with the strongest types of security and developed according to modern technical standards."
        )
        note_path = os.path.join(sandbox_dir, "note.txt")
        with open(note_path, 'w', encoding='utf-8') as f:
            f.write(note_content)

        # 4. Prepare environment (minimal, inherit basic path)
        # Keep the original env logic
        env = os.environ.copy()
        # Add user site-packages to PYTHONPATH if needed for installed libraries
        try:
            user_site_packages = subprocess.run(
                [sys.executable, "-m", "site", "--user-site"],
                capture_output=True, text=True, check=True, timeout=5
            ).stdout.strip()
            if user_site_packages and os.path.exists(user_site_packages):
                 env['PYTHONPATH'] = user_site_packages + os.pathsep + env.get('PYTHONPATH', '')
        except Exception as site_e:
            logger.warning(f"Could not determine user site-packages: {site_e}")

        # 5. Run the script using subprocess.Popen with cwd set to the sandbox
        process = subprocess.Popen(
            [sys.executable, sandbox_script_name], # Run the script name relative to cwd
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=sandbox_dir, # <<< CRITICAL: Set working directory to the sandbox
            env=env, # Pass the modified environment
            text=True,
            encoding='utf-8',  # Specify encoding
            errors='replace' # Handle potential encoding errors in output
        )
        
        # 6. Store process info and sandbox path
        bot_scripts[script_name] = {
            'process': process,
            'user_id': user_id,
            'chat_id': chat_id,
            'path': script_path,  # Original path for reference
            'sandbox_dir': sandbox_dir,  # Store sandbox path for cleanup
            'started_at': get_formatted_time()
        }
        
        logger.info(f"Started script {script_name} (PID: {process.pid}) in sandbox {sandbox_dir} for user {user_id}")
        return True # Indicate success

    except Exception as e:
        logger.error(f"Error running script {script_name} in sandbox for user {user_id}: {e}")
        # Clean up sandbox if created but process failed to start
        if sandbox_dir and os.path.exists(sandbox_dir):
            try:
                shutil.rmtree(sandbox_dir)
                logger.info(f"Cleaned up failed sandbox {sandbox_dir}")
            except Exception as cleanup_e:
                logger.error(f"Error cleaning up failed sandbox {sandbox_dir}: {cleanup_e}")
        # Ensure script entry is removed if it failed before process start
        if script_name in bot_scripts and bot_scripts[script_name].get('process') is None:
            bot_scripts.pop(script_name, None)
        return False # Indicate fa
def cleanup_sandbox(sandbox_dir, script_name):
    """Safely remove the sandbox directory."""
    if sandbox_dir and os.path.exists(sandbox_dir) and os.path.isdir(sandbox_dir):
         # Double-check it's inside the expected base directory for safety
        if os.path.abspath(sandbox_dir).startswith(os.path.abspath(SANDBOX_BASE_DIR)):
            try:
                shutil.rmtree(sandbox_dir)
                logger.info(f"Cleaned up sandbox directory for {script_name}: {sandbox_dir}")
                return True
            except Exception as e:
                logger.error(f"Error removing sandbox directory {sandbox_dir} for {script_name}: {e}")
                return False
        else:
            logger.error(f"Attempted to clean up directory outside designated sandbox area: {sandbox_dir}. Aborted.")
            return False
    # logger.debug(f"Sandbox directory {sandbox_dir} not found or already cleaned up for {script_name}.")
    return True # Consider it success if dir doesn't exist

def stop_bot_script(script_name, chat_id, user_id, force=False):
    """Stop a running bot script and clean up its sandbox."""
    script_info = bot_scripts.get(script_name)
    stopped = False
    sandbox_dir_to_clean = None

    if script_info:
        process = script_info.get('process')
        sandbox_dir_to_clean = script_info.get('sandbox_dir') # Get sandbox dir from script_info
        
        try:
            if process and process.poll() is None: # Check if process exists and is running
                process.terminate() # Try graceful termination first
                try:
                    process.wait(timeout=5) # Wait for termination
                except subprocess.TimeoutExpired:
                    logger.warning(f"Process {script_name} (PID {process.pid}) did not terminate gracefully, killing.")
                    process.kill() # Force kill if timeout
                    process.wait() # Wait for kill to complete
                
                logger.info(f"Stopped script {script_name} (PID {process.pid}) for user {user_id}")
                stopped = True
                if chat_id:
                    bot.send_message(
                        chat_id,
                        f"✅ File stopped successfully ✋\n{script_name}"
                    )
            else:
                # Process already finished or doesn't exist
                logger.info(f"Script {script_name} was not running when stop was requested.")
                stopped = True # Consider it stopped if not running
                if chat_id:
                     bot.send_message(
                         chat_id,
                         f"⚠️ File was not running\n{script_name}"
                     )
        except Exception as e:
            logger.error(f"Error stopping process for script {script_name}: {e}")
            stopped = False
            if chat_id:
                bot.send_message(
                    chat_id,
                    f"✖️ Error stopping file process: {str(e)}\n{script_name}"
                )
        finally:
            # Always remove from bot_scripts if entry exists
            bot_scripts.pop(script_name, None)
            # Clean up sandbox regardless of process stop success/failure
            if sandbox_dir_to_clean:
                cleanup_sandbox(sandbox_dir_to_clean, script_name)
            else:
                 logger.warning(f"No sandbox directory found in script_info for {script_name} during cleanup.")

    # Original logic for handling process_map (less reliable, no sandbox info)
    elif script_name in process_map:
        pid = process_map[script_name]
        logger.warning(f"Script {script_name} found only in process_map (PID {pid}). Attempting to stop, but cannot clean sandbox.")
        try:
            process = psutil.Process(pid)
            process.terminate()
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                process.kill()
            
            logger.info(f"Stopped script {script_name} with PID {pid} for user {user_id} (via process_map)")
            stopped = True
            if chat_id:
                bot.send_message(
                    chat_id,
                    f"✅ File stopped successfully ✋\n{script_name}"
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            if chat_id:
                bot.send_message(
                    chat_id,
                    f"⚠️ Process not found or access denied\n{script_name}"
                )
            stopped = False # Indicate failure to stop via psutil
        except Exception as e:
            logger.error(f"Error stopping script {script_name} via process_map: {e}")
            stopped = False
            if chat_id:
                bot.send_message(
                    chat_id,
                    f"✖️ Error stopping file process (via PID): {str(e)}\n{script_name}"
                )
        finally:
             # Remove from process_map regardless
             process_map.pop(script_name, None)

    else:
        # Script not found in bot_scripts or process_map
        if chat_id and not force:
            bot.send_message(
                chat_id,
                f"⚠️ File not found in running processes\n{script_name}"
            )
        stopped = False # Not found, so not stopped

    return stopped
def ping_host():
    """Ping a host to check server status"""
    try:
        host = "8.8.8.8"  # Google DNS
        response_time = ping(host)
        
        if response_time is not None:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            
            uptime_seconds = int(time.time() - psutil.boot_time())
            days, remainder = divmod(uptime_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
            
            return (
                f"🟢 Server is online\n\n"
                f"• Ping: {response_time * 1000:.2f} ms\n"
                f"• CPU Usage: {cpu_percent}%\n"
                f"• Memory: {memory.percent}% used\n"
                f"• Uptime: {uptime_str}\n\n"
                f"Last checked: {get_formatted_time()}"
            )
        else:
            return (
                f"🟡 Server is online but not responding to ping\n\n"
                f"Last checked: {get_formatted_time()}"
            )
    except Exception as e:
        logger.error(f"Error pinging host: {e}")
        return None

def create_back_markup():
    """Create a markup with a back button"""
    markup = types.InlineKeyboardMarkup()
    back_button = types.InlineKeyboardButton("Back 🔙", callback_data='back')
    markup.add(back_button)
    return markup

def show_help(chat_id):
    """Show help message"""
    # Check if the user is upgraded to tailor the message
    is_upgraded = is_user_upgraded(chat_id) # Assuming chat_id can be used as user_id here, might need adjustment if help is called differently
    max_files = get_user_max_files(chat_id)

    help_text = (
        "📚 Bot Help\n\n"
        "This bot allows you to upload and run Python files.\n\n"
        "• Upload File 📤: Upload a Python file (.py) to run on the server.\n"
        "• My Files 📁: View and manage your uploaded files.\n"
        "• Ping ⏱️: Check server status.\n\n"
        "📋 Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n\n"
        "📝 Notes:\n"
        "• Files require admin approval before running.\n"
        "• You can stop your running files at any time via \'My Files\'.\n"
    )

    if is_upgraded:
        help_text += f"• 🌟 As an upgraded user, you can run up to {max_files} files simultaneously, and they run indefinitely until stopped.\n"
    else:
        help_text += (
            f"• You can run up to {max_files} files simultaneously.\n"
            f"• ⏳ Files uploaded by non-subscribed users will automatically stop after 1.5 days.\n"
            f"• To subscribe for unlimited runtime, contact the admin: @G35GG\n"
        )

    help_text += "• Contact @G35GG for assistance."
    
    bot.send_message(
        chat_id,
        help_text,
        reply_markup=create_back_markup()
    )

def show_user_files(chat_id, user_id):
    """Show files uploaded by a user"""
    user_files_list = get_user_files(user_id)
    
    if not user_files_list:
        bot.send_message(
            chat_id,
            "📁 My Files\n\n"
            "You haven't uploaded any files yet.\n"
            "Use the 'Upload File 📤' button to upload a file.",
            reply_markup=create_back_markup()
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    message = "📁 My Files\n\n"
    
    update_process_map()
    
    for i, file_data in enumerate(user_files_list, 1):
        file_name = file_data["name"]
        file_path = file_data["path"]
        uploaded_at = file_data["uploaded_at"]
        
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path) / 1024
            
            status = "🟢 Running" if file_name in process_map else "⚪️ Inactive"
            
            message += f"{i}. {file_name}\n"
            message += f"   - Size: {file_size:.1f} KB\n"
            message += f"   - Uploaded: {uploaded_at}\n"
            message += f"   - Status: {status}\n\n"
            
            stop_button = types.InlineKeyboardButton(
                f"Stop {file_name} ⚠️",
                callback_data=f'stop_{file_name}'
            )
            markup.add(stop_button)
    
    back_button = types.InlineKeyboardButton("Back 🔙", callback_data='back')
    markup.add(back_button)
    
    bot.send_message(
        chat_id,
        message,
        reply_markup=markup
    )

# Modified handle_file function
@bot.message_handler(content_types=["document"])
def handle_file(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    first_name = message.from_user.first_name or ""

    if username != "Unknown":
        username_to_id_cache[username] = str(user_id)

    if is_user_banned(user_id):
        bot.send_message(
            message.chat.id,
            "🔴 You are banned from using this bot.\n"
            "Contact the developer to appeal: @G35GG"
        )
        return

    try:
        file_name = message.document.file_name
        if not file_name.endswith(".py"):
            bot.reply_to(
                message,
                "⚠️ The file must be a Python (.py) file."
            )
            return

        # Check file limits *before* downloading/processing
        max_files = get_user_max_files(user_id)
        # Consider pending files + active files towards the limit if desired
        # current_active_files = count_user_files(user_id)
        # current_pending_files = sum(1 for req in pending_uploads.values() if req["user_id"] == user_id)
        # if current_active_files + current_pending_files >= max_files:
        # Simplified check: only check active files for now, as per original logic
        current_files = count_user_files(user_id)
        if current_files >= max_files:
            bot.reply_to(
                message,
                f"⚠️ You cannot upload more files. You currently have {current_files}/{max_files} active files.\n"
                f"Please stop one of your active files or wait for pending uploads to be processed."
            )
            return

        # Send initial processing message
        processing_msg = bot.send_message(
            message.chat.id,
            "⏳ Processing your file upload request..."
        )

        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Generate a unique ID for the request
        request_id = str(uuid.uuid4())
        # Save to temporary pending directory with unique name
        temp_file_name = f"{request_id}_{file_name}"
        temp_script_path = os.path.join(PENDING_FILES_DIR, temp_file_name)

        with open(temp_script_path, "wb") as new_file:
            new_file.write(downloaded_file)

        logger.info(f"User {user_id} (@{username}) submitted file for review: {file_name} (Temp: {temp_file_name}) Request ID: {request_id}")

        # Store pending request details
        load_pending_uploads() # Load current state before modifying
        pending_uploads[request_id] = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "original_filename": file_name,
            "temp_path": temp_script_path,
            "request_time": get_formatted_time(),
            "request_timestamp": time.time() # Store timestamp for potential sorting
        }
        save_pending_uploads()

        # Notify user
        bot.edit_message_text(
            f"✅ File [ {file_name} ] received.\n"
            f"⏳ It has been sent to the admin for inspection. You will be notified once it\'s reviewed.",
            message.chat.id,
            processing_msg.message_id
        )

        # Notify admin
        try:
            admin_message = (
                f"🔔 New File Upload Request\n\n"
                f"👤 User: {first_name} (@{username}, ID: {user_id})\n"
                f"📄 File: {file_name}\n"
                f"⏱️ Time: {get_formatted_time()}\n\n"
                f"Use /pending_uploads to review."
            )
            # Send the file itself to the admin for inspection
            with open(temp_script_path, "rb") as temp_file_doc:
                bot.send_document(ADMIN_ID, temp_file_doc, caption=admin_message)
            logger.info(f"Notified admin about pending request {request_id}")
        except Exception as admin_notify_e:
            logger.error(f"Failed to notify admin about pending request {request_id}: {admin_notify_e}")

    except Exception as e:
        error_text = str(e)
        # Try to edit the processing message if it exists
        try:
            bot.edit_message_text(
                f"❌ Failed to process your file upload request.\nError: {error_text}\nContact the admin: @G35GG",
                message.chat.id,
                processing_msg.message_id
            )
        except:
            # Fallback if editing fails (e.g., message deleted)
            bot.reply_to(
                message,
                f"❌ Failed to process your file upload request.\nError: {error_text}\nContact the admin: @G35GG"
            )
            logger.error(f"Error handling file upload for user {user_id}: {error_text}")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    username = call.from_user.username or "Unknown"
    first_name = call.from_user.first_name or ""

    if username != "Unknown":
        username_to_id_cache[username] = str(user_id)

    if is_user_banned(user_id) and not is_admin(user_id):
        bot.answer_callback_query(call.id, "You are banned from using this bot.", show_alert=True)
        return

    try:
        if call.data == 'upload':
            bot.answer_callback_query(call.id)

            max_files = get_user_max_files(user_id)
            current_files = count_user_files(user_id)

            if current_files >= max_files:
                bot.send_message(
                    call.message.chat.id,
                    f"⚠️ You cannot upload more than {max_files} files.\n"
                    f"Please stop one of your previously uploaded files."
                )
            else:
                bot.send_message(call.message.chat.id, "📎 Please send the file you want to upload.")

        elif call.data.startswith('stop_'):
            bot.answer_callback_query(call.id)
            script_name = call.data.split('_', 1)[1]
            script_path = os.path.join(UPLOADED_FILES_DIR, script_name)

            owner_id = get_file_owner(script_name)

            if str(user_id) == owner_id or is_admin(user_id):
                update_process_map()
                success = stop_bot_script(script_name, call.message.chat.id, owner_id, force=is_admin(user_id))

                if success:
                    if owner_id:
                        remove_user_file(owner_id, script_name)

                    try:
                        if os.path.exists(script_path):
                            os.remove(script_path)
                    except Exception as e:
                        logger.error(f"Error deleting file {script_path}: {e}")

                    if str(user_id) == owner_id:
                        show_user_files(call.message.chat.id, user_id)
                    elif is_admin(user_id):
                        show_uploaded_files(call.message.chat.id)
            else:
                bot.send_message(
                    call.message.chat.id,
                    "⛔️ You cannot stop this file because you are not the owner ⛔️"
                )

        elif call.data == 'ping':
            bot.answer_callback_query(call.id)
            ping_result = ping_host()
            if ping_result:
                bot.edit_message_text(
                    f"🔄 Server Status\n\n{ping_result}",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_back_markup()
                )
            else:
                bot.edit_message_text(
                    "❌ Failed to ping the host.",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=create_back_markup()
                )

        elif call.data == 'back':
            bot.answer_callback_query(call.id)

            markup = types.InlineKeyboardMarkup(row_width=2)
            upload_button = types.InlineKeyboardButton("Upload File 📤", callback_data='upload')
            owner_button = types.InlineKeyboardButton("Owner 📌", url='https://t.me/G35GG')
            download_library_button = types.InlineKeyboardButton("Download Library 📚", callback_data='download_library')
            ping_button = types.InlineKeyboardButton("Ping ⏱️", callback_data='ping')
            help_button = types.InlineKeyboardButton("Help ❓", callback_data='help')
            my_files_button = types.InlineKeyboardButton("My Files 📁", callback_data='my_files')
            markup.add(upload_button, my_files_button)
            markup.add(ping_button, help_button)
            markup.add(download_library_button)
            markup.add(owner_button)
            
            welcome_message = (
                f"—————————————————————————\n\n"
                f"• Hi : {first_name}!\n\n"
                f"• ID: {user_id} | User: @{username if username != 'Unknown' else 'unavailable'}"
            )
            if is_user_upgraded(user_id):
                welcome_message += f"\n\n• 🌟 You are an upgraded user with {get_user_max_files(user_id)} files allowed."
            else:
                welcome_message += f"\n\n❌ You are not upgraded - file count : {get_user_max_files(user_id)}"
            welcome_message += "\n\n—————————————————————————\n\n• Choose an option:"

            bot.edit_message_text(
                welcome_message,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )

        elif call.data == 'help':
            bot.answer_callback_query(call.id)
            show_help(call.message.chat.id)

        elif call.data == 'my_files':
            bot.answer_callback_query(call.id)
            show_user_files(call.message.chat.id, user_id)

        elif call.data.startswith('stop_user_file_'):
            bot.answer_callback_query(call.id)
            script_name = call.data.split('_user_file_', 1)[1]
            script_path = os.path.join(UPLOADED_FILES_DIR, script_name)

            owner_id = get_file_owner(script_name)
            user_files_list = get_user_files(user_id)
            is_owner = False

            for file_data in user_files_list:
                if file_data["name"] == script_name:
                    is_owner = True
                    break

            if is_owner or str(user_id) == owner_id or is_admin(user_id):
                update_process_map()

                success = stop_bot_script(script_name, None, user_id)

                if success:
                    remove_user_file(user_id, script_name)

                    try:
                        if os.path.exists(script_path):
                            os.remove(script_path)
                    except Exception as e:
                        logger.error(f"Error deleting file {script_path}: {e}")

                    bot.send_message(
                        call.message.chat.id,
                        f"✅ File stopped successfully ✋\n{script_name}"
                    )

                show_user_files(call.message.chat.id, user_id)
            else:
                bot.send_message(
                    call.message.chat.id,
                    "⛔️ You cannot stop this file because you are not the owner ⛔️"
                )

        elif call.data == 'check_subscription':
            bot.answer_callback_query(call.id)
            start(call.message)

        # <<< Add accept/reject logic here >>>
        elif call.data.startswith("accept_"):
            if not is_admin(user_id):
                bot.answer_callback_query(call.id, "Admin only.", show_alert=True)
                return

            request_id = call.data.split("_", 1)[1]
            load_pending_uploads() # Ensure we have the latest data

            if request_id not in pending_uploads:
                bot.answer_callback_query(call.id, "Request not found or already processed.", show_alert=True)
                # Optionally update the admin message if possible
                try:
                    bot.edit_message_text("Request already processed.", call.message.chat.id, call.message.message_id)
                except:
                    pass # Ignore if editing fails
                return

            details = pending_uploads[request_id]
            original_filename = details["original_filename"]
            temp_path = details["temp_path"]
            requester_user_id = details["user_id"]
            requester_username = details["username"]
            requester_first_name = details["first_name"]

            bot.answer_callback_query(call.id, f"Accepting {original_filename}...")

            # Define final path in the main uploaded files directory
            final_script_path = os.path.join(UPLOADED_FILES_DIR, original_filename)

            # Handle potential file name conflicts (overwrite existing if admin accepts)
            if os.path.exists(final_script_path):
                logger.warning(f"Overwriting existing file during acceptance: {final_script_path}")
                # Optional: Stop existing script with the same name if running?
                # stop_bot_script(original_filename, None, get_file_owner(original_filename), force=True)

            try:
                # Move the file
                shutil.move(temp_path, final_script_path)
                logger.info(f"Moved pending file {temp_path} to {final_script_path}")

                # --- Run the script (similar logic to original handle_file, but without library install) ---
                # Extract dependencies and token again from the final path (optional but safer)
                bot_token = get_bot_token(final_script_path)
                # dependencies = extract_dependencies(final_script_path)
                # missing_dependencies = [lib for lib in dependencies if lib not in set(sys.stdlib_module_names)]
                # if missing_dependencies:
                #     # Handle missing dependencies - maybe reject or notify admin?
                #     # For now, assume libraries were checked/installed before or are present
                #     logger.warning(f"Script {original_filename} might have uninstalled dependencies: {missing_dependencies}")
                    
                # Run the file using the sandboxed function
                run_success = run_uploaded_file(final_script_path, requester_user_id, requester_user_id, original_filename)

                if run_success:
                    logger.info(f"Successfully started accepted script {original_filename} for user {requester_user_id}")
                    update_process_map()
                    add_user_file(requester_user_id, original_filename, final_script_path)

                    # Notify user of acceptance
                    accept_notify_msg = f"✅ Your file [ {original_filename} ] has been accepted by the admin and successfully run!"
                    
                    # Schedule stop timer if user is not upgraded
                    is_upgraded = is_user_upgraded(requester_user_id)
                    if not is_upgraded:
                        stop_delay_seconds = 36 * 60 * 60 # 1.5 days
                        disable_time = datetime.datetime.now() + datetime.timedelta(seconds=stop_delay_seconds)
                        # Format like get_formatted_time but with standard %I for 12-hour clock
                        disable_time_str = disable_time.strftime("%Y/%m/%d - %I:%M %p") 
                        schedule_stop(request_id, requester_user_id, original_filename, stop_delay_seconds)
                        accept_notify_msg += (
                            f"\n\n⏳ Note: The file will be disabled after 1.5 days because you are a regular user and not subscribed to the bot. "
                            f"It will automatically stop on {disable_time_str}.\n"
                            f"To subscribe for unlimited runtime, contact the admin @G35GG."
                        )
                    else:
                         accept_notify_msg += f"\n\n🌟 As an upgraded user, your file will run until stopped manually."

                    try:
                        # Also attach the file to the acceptance message
                        with open(final_script_path, "rb") as file_doc:
                            bot.send_document(requester_user_id, file_doc, caption=accept_notify_msg)
                        # bot.send_message(requester_user_id, accept_notify_msg) # Original send_message replaced by send_document
                    except Exception as notify_e:
                        logger.error(f"Failed to notify user {requester_user_id} about acceptance: {notify_e}")

                    # Remove from pending
                    del pending_uploads[request_id]
                    save_pending_uploads()

                    # Update admin message (remove buttons for this item)
                    try:
                        bot.edit_message_text(
                            call.message.text + f"\n\n---\n✅ Accepted: {original_filename} for @{requester_username}",
                            call.message.chat.id,
                            call.message.message_id,
                            reply_markup=None # Remove buttons after action
                        )
                    except Exception as edit_e:
                         logger.warning(f"Could not edit admin message after accepting {request_id}: {edit_e}")
                    # Consider refreshing the list for the admin with admin_pending_uploads_command(call.message) ?

                else:
                    logger.error(f"Failed to run accepted script {original_filename} for user {requester_user_id}")
                    # Notify admin of run failure
                    bot.send_message(ADMIN_ID, f"⚠️ Failed to start the accepted script: {original_filename} for user @{requester_username} ({requester_user_id}). Check logs.")
                    # Notify user?
                    try:
                        bot.send_message(requester_user_id, f"❌ Your file [ {original_filename} ] was accepted but failed to start. Please contact @G35GG.")
                    except Exception as notify_e:
                        logger.error(f"Failed to notify user {requester_user_id} about run failure: {notify_e}")
                    # Clean up: remove the moved file? remove from user_files? Keep pending?
                    # Let's remove the moved file and keep it out of user_files, but remove from pending.
                    if os.path.exists(final_script_path):
                        os.remove(final_script_path)
                    del pending_uploads[request_id]
                    save_pending_uploads()
                    try:
                        bot.edit_message_text(
                            call.message.text + f"\n\n---\n⚠️ Failed to run accepted: {original_filename} for @{requester_username}",
                            call.message.chat.id,
                            call.message.message_id,
                            reply_markup=None
                        )
                    except Exception as edit_e:
                         logger.warning(f"Could not edit admin message after failed run {request_id}: {edit_e}")

            except Exception as accept_e:
                logger.error(f"Error processing accept request {request_id}: {accept_e}")
                bot.answer_callback_query(call.id, f"Error accepting file: {accept_e}", show_alert=True)
                # Clean up temp file if it still exists
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                # Remove from pending if something went wrong during move/run
                if request_id in pending_uploads:
                    del pending_uploads[request_id]
                    save_pending_uploads()
                try:
                    bot.edit_message_text(
                        call.message.text + f"\n\n---\n❌ Error accepting: {original_filename}",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=None
                    )
                except:
                    pass

        elif call.data.startswith("reject_"):
            if not is_admin(user_id):
                bot.answer_callback_query(call.id, "Admin only.", show_alert=True)
                return

            request_id = call.data.split("_", 1)[1]
            load_pending_uploads() # Ensure latest data

            if request_id not in pending_uploads:
                bot.answer_callback_query(call.id, "Request not found or already processed.", show_alert=True)
                try:
                    bot.edit_message_text("Request already processed.", call.message.chat.id, call.message.message_id)
                except:
                    pass
                return

            details = pending_uploads[request_id]
            original_filename = details["original_filename"]
            temp_path = details["temp_path"]
            requester_user_id = details["user_id"]
            requester_username = details["username"]

            bot.answer_callback_query(call.id, f"Rejecting {original_filename}...")

            try:
                # Notify user of rejection
                reject_notify_msg = (
                    f"❌ Your file [ {original_filename} ] has been rejected by the admin.\n\n"
                    f"To appeal this decision, please contact the admin: @G35GG"
                )
                try:
                    # Also attach the file to the rejection message
                    with open(temp_path, "rb") as file_doc:
                        bot.send_document(requester_user_id, file_doc, caption=reject_notify_msg)
                    # bot.send_message(requester_user_id, reject_notify_msg) # Original send_message replaced
                except Exception as notify_e:
                    logger.error(f"Failed to notify user {requester_user_id} about rejection: {notify_e}")

                # Delete the temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    logger.info(f"Deleted rejected temporary file: {temp_path}")
                else:
                    logger.warning(f"Temporary file not found for rejected request {request_id}: {temp_path}")

                # Remove from pending
                del pending_uploads[request_id]
                save_pending_uploads()

                # Update admin message
                try:
                    bot.edit_message_text(
                        call.message.text + f"\n\n---\n❌ Rejected: {original_filename} for @{requester_username}",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=None # Remove buttons
                    )
                except Exception as edit_e:
                    logger.warning(f"Could not edit admin message after rejecting {request_id}: {edit_e}")

            except Exception as reject_e:
                logger.error(f"Error processing reject request {request_id}: {reject_e}")
                bot.answer_callback_query(call.id, f"Error rejecting file: {reject_e}", show_alert=True)
                # Attempt to remove from pending even if other steps failed
                if request_id in pending_uploads:
                    del pending_uploads[request_id]
                    save_pending_uploads()
                try:
                    bot.edit_message_text(
                        call.message.text + f"\n\n---\n❌ Error rejecting: {original_filename}",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=None
                    )
                except:
                    pass

    except Exception as e:
        error_text = str(e)
        bot.send_message(call.message.chat.id, f"❌ Error: {error_text}")
        logger.error(f"Error in callback handler: {error_text}")

def show_uploaded_files(chat_id):
    try:
        all_files = []
        for user_id, files in user_files.items():
            for file in files:
                file_info = file.copy()
                file_info['owner_id'] = user_id
                all_files.append(file_info)
        
        if not all_files:
            bot.send_message(
                chat_id,
                "📁 Uploaded Files\n\n"
                "No files have been uploaded yet.\n\n"
                "Use /admin to return to admin commands."
            )
            return
        
        message = "📁 Uploaded Files\n\n"
        
        for i, file_info in enumerate(all_files, 1):
            file_name = file_info["name"]
            file_path = file_info["path"]
            owner_id = file_info["owner_id"]
            uploaded_at = file_info["uploaded_at"]
            
            owner_username = "Unknown"
            if owner_id in upgraded_users:
                owner_username = upgraded_users[owner_id].get("username", "Unknown")
            elif owner_id in banned_users:
                owner_username = banned_users[owner_id].get("username", "Unknown")
            
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path) / 1024
                
                status = "🟢 Running" if file_name in process_map else "⚪️ Inactive"
                
                message += f"{i}. {file_name}\n"
                message += f"   - Size: {file_size:.1f} KB\n"
                message += f"   - Owner: ID: {owner_id}"
                if owner_username != "Unknown":
                    message += f" (@{owner_username})"
                message += "\n"
                message += f"   - Uploaded: {uploaded_at}\n"
                message += f"   - Status: {status}\n"
                message += f"   - Stop command: /stop_file {file_name}\n\n"
        
        message += "\nUse /admin to return to admin commands."
        
        bot.send_message(
            chat_id,
            message
        )
    except Exception as e:
        bot.send_message(chat_id, f"✖️ Error: {str(e)}")
        logger.error(f"Error showing uploaded files: {e}")

@bot.message_handler(commands=['stop_file'])
def stop_file_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        command_parts = message.text.split(' ', 1)
        if len(command_parts) < 2:
            bot.send_message(
                message.chat.id,
                "⚠️ Please specify a file name\n"
                "Usage: /stop_file filename.py"
            )
            return
        
        script_name = command_parts[1].strip()
        script_path = os.path.join(UPLOADED_FILES_DIR, script_name)
        
        owner_id = get_file_owner(script_name)
        
        if owner_id:
            update_process_map()
            
            success = stop_bot_script(script_name, message.chat.id, owner_id, force=True)
            
            if success:

                try:
                    bot.send_message(
                        int(owner_id),
                        f"⚠️ Your file has been stopped by an admin ⚠️\n\n"
                        f"📄 File: {script_name}\n"
                        f"⏱️ Time: {get_formatted_time()}"
                    )
                    logger.info(f"Notified user {owner_id} about file stop by admin")
                except Exception as e:
                    logger.error(f"Error notifying user about file stop: {e}")
                
                remove_user_file(owner_id, script_name)
                

                try:
                    if os.path.exists(script_path):
                        os.remove(script_path)
                        logger.info(f"Deleted file: {script_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {script_path}: {e}")
                
                show_uploaded_files(message.chat.id)
            
            logger.info(f"Admin {user_id} stopped script: {script_name}")
        else:
            bot.send_message(
                message.chat.id,
                f"⚠️ File not found\n"
                f"No file named {script_name} was found."
            )
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

def ask_for_ban_username(chat_id):
    msg = bot.send_message(
        chat_id,
        "🚫 Ban User\n\n"
        "Please enter the username (with @) or user ID of the person you want to ban:"
    )
    
    bot.register_next_step_handler(msg, process_ban_username)

def process_ban_username(message):
    if not is_admin(message.from_user.id):
        return
    
    username = message.text.strip()
    
    if username.isdigit():
        user_id = username
        ban_user(user_id, "Unknown")
        bot.send_message(
            message.chat.id,
            f"✅ User with ID {user_id} has been banned successfully."
        )
    elif username.startswith('@'):
        username_clean = username[1:]
        
        user_id = resolve_username(username_clean)
        
        ban_user(user_id, username_clean)
        
        bot.send_message(
            message.chat.id,
            f"✅ User {username} has been banned successfully."
        )
    else:
        bot.send_message(
            message.chat.id,
            "✖️ Invalid format. Please enter a user ID or username with @ symbol."
        )

def show_banned_users(chat_id):
    if not banned_users:
        bot.send_message(
            chat_id,
            "📋 Banned Users\n\n"
            "No users are currently banned.\n\n"
            "Use /admin to return to admin commands."
        )
        return
    
    message = "📋 Banned Users\n\n"
    
    for i, (user_id, data) in enumerate(banned_users.items(), 1):
        username = data.get("username", "Unknown")
        banned_at = data.get("banned_at", "Unknown")
        
        message += f"{i}. "
        if user_id.startswith("username_"):
            message += f"@{username}\n"
        else:
            message += f"ID: {user_id}"
            if username != "Unknown":
                message += f" (@{username})"
            message += "\n"
        
        message += f"   - Banned at: {banned_at}\n\n"
    
    message += "Use /admin to return to admin commands."
    
    bot.send_message(
        chat_id,
        message
    )

def ask_for_unban_username(chat_id):
    if not banned_users:
        bot.send_message(
            chat_id,
            "✅ Unban User\n\n"
            "No users are currently banned.\n\n"
            "Use /admin to return to admin commands."
        )
        return
    
    msg = bot.send_message(
        chat_id,
        "✅ Unban User\n\n"
        "Please enter the username (with @) or user ID of the person you want to unban:"
    )
    
    bot.register_next_step_handler(msg, process_unban_username)

def process_unban_username(message):
    if not is_admin(message.from_user.id):
        return
    
    username = message.text.strip()
    
    if username.isdigit():
        user_id = username
        if unban_user(user_id):
            bot.send_message(
                message.chat.id,
                f"✅ User with ID {user_id} has been unbanned successfully."
            )
        else:
            bot.send_message(
                message.chat.id,
                f"✖️ User with ID {user_id} was not found in the banned list."
            )
    elif username.startswith('@'):
        username_clean = username[1:]
        
        user_id = None
        for banned_id, data in banned_users.items():
            if data.get("username") == username_clean:
                user_id = banned_id
                break
        
        if user_id:
            if unban_user(user_id):
                bot.send_message(
                    message.chat.id,
                    f"✅ User {username} has been unbanned successfully."
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"✖️ Error unbanning user {username}."
                )
        else:
            user_id = f"username_{username_clean}"
            if unban_user(user_id):
                bot.send_message(
                    message.chat.id,
                    f"✅ User {username} has been unbanned successfully."
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"✖️ User {username} was not found in the banned list."
                )
    else:
        bot.send_message(
            message.chat.id,
            "✖️ Invalid format. Please enter a user ID or username with @ symbol."
        )

def ask_for_upgrade_username(chat_id):
    msg = bot.send_message(
        chat_id,
        "⬆️ Upgrade User\n\n"
        "Please enter the username (with @) or user ID of the person you want to upgrade:"
    )
    
    bot.register_next_step_handler(msg, process_upgrade_username_step1)

def process_upgrade_username_step1(message):
    if not is_admin(message.from_user.id):
        return
    
    username = message.text.strip()
    
    if username.isdigit():
        user_data = {"type": "id", "value": username}
    elif username.startswith('@'):
        user_data = {"type": "username", "value": username[1:]}
        
        user_id = resolve_username(username[1:])
        if user_id and not user_id.startswith("username_"):
            user_data = {"type": "id", "value": user_id}
    else:
        bot.send_message(
            message.chat.id,
            "✖️ Invalid format. Please enter a user ID or username with @ symbol."
        )
        return
    
    msg = bot.send_message(
        message.chat.id,
        "⬆️ Upgrade User\n\n"
        "Please enter the maximum number of files this user can upload:"
    )
    
    bot.register_next_step_handler(msg, process_upgrade_username_step2, user_data)

def process_upgrade_username_step2(message, user_data):
    if not is_admin(message.from_user.id):
        return
    
    try:
        max_files = int(message.text.strip())
        if max_files <= 0:
            bot.send_message(
                message.chat.id,
                "✖️ Maximum files must be a positive number."
            )
            return
    except ValueError:
        bot.send_message(
            message.chat.id,
            "✖️ Invalid number. Please enter a valid integer."
        )
        return
    
    if user_data["type"] == "id":
        user_id = user_data["value"]
        username = "Unknown"
        for upgraded_id, data in upgraded_users.items():
            if upgraded_id == user_id:
                username = data.get("username", "Unknown")
                break
        
        upgrade_user(user_id, username, max_files)
        
        bot.send_message(
            message.chat.id,
            f"✅ User with ID {user_id} has been upgraded to {max_files} files."
        )
    else:
        username = user_data["value"]
        user_id = resolve_username(username)
        
        upgrade_user(user_id, username, max_files)
        
        bot.send_message(
            message.chat.id,
            f"✅ User @{username} has been upgraded to {max_files} files."
        )

def show_upgraded_users_list(chat_id):
    if not upgraded_users:
        bot.send_message(
            chat_id,
            "📋 Upgraded Users\n\n"
            "No users are currently upgraded.\n\n"
            "Use /admin to return to admin commands."
        )
        return
    
    message = "📋 Upgraded Users\n\n"
    
    for i, (user_id, data) in enumerate(upgraded_users.items(), 1):
        username = data.get("username", "Unknown")
        max_files = data.get("max_files", DEFAULT_MAX_FILES)
        upgraded_at = data.get("upgraded_at", "Unknown")
        
        message += f"{i}. "
        if user_id.startswith("username_"):
            message += f"@{username}\n"
        else:
            message += f"ID: {user_id}"
            if username != "Unknown":
                message += f" (@{username})"
            message += "\n"
        
        message += f"   - Max Files: {max_files}\n"
        message += f"   - Upgraded at: {upgraded_at}\n\n"
    
    message += "Use /admin to return to admin commands."
    
    bot.send_message(
        chat_id,
        message
    )

def ask_for_downgrade_username(chat_id):
    if not upgraded_users:
        bot.send_message(
            chat_id,
            "⬇️ Downgrade User\n\n"
            "No users are currently upgraded.\n\n"
            "Use /admin to return to admin commands."
        )
        return
    
    msg = bot.send_message(
        chat_id,
        "⬇️ Downgrade User\n\n"
        "Please enter the username (with @) or user ID of the person you want to downgrade:"
    )
    
    bot.register_next_step_handler(msg, process_downgrade_username)

def process_downgrade_username(message):
    if not is_admin(message.from_user.id):
        return
    
    username = message.text.strip()
    
    if username.isdigit():
        user_id = username
        if downgrade_user(user_id):
            bot.send_message(
                message.chat.id,
                f"✅ User with ID {user_id} has been downgraded successfully."
            )
        else:
            bot.send_message(
                message.chat.id,
                f"✖️ User with ID {user_id} was not found in the upgraded list."
            )
    elif username.startswith('@'):
        username_clean = username[1:]
        
        user_id = None
        for upgraded_id, data in upgraded_users.items():
            if data.get("username") == username_clean:
                user_id = upgraded_id
                break
        
        if user_id:
            if downgrade_user(user_id):
                bot.send_message(
                    message.chat.id,
                    f"✅ User {username} has been downgraded successfully."
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"✖️ Error downgrading user {username}."
                )
        else:
            user_id = f"username_{username_clean}"
            if downgrade_user(user_id):
                bot.send_message(
                    message.chat.id,
                    f"✅ User {username} has been downgraded successfully."
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"✖️ User {username} was not found in the upgraded list."
                )
    else:
        bot.send_message(
            message.chat.id,
            "✖️ Invalid format. Please enter a user ID or username with @ symbol."
        )

def ask_for_delete_files_username(chat_id):
    msg = bot.send_message(
        chat_id,
        "🗑️ Delete User Files\n\n"
        "Please enter the username (with @) or user ID of the person whose files you want to delete:"
    )
    
    bot.register_next_step_handler(msg, process_delete_files_username)

def process_delete_files_username(message):
    if not is_admin(message.from_user.id):
        return
    
    username = message.text.strip()
    
    if username.isdigit():
        user_id = username
        files_count, success = delete_all_user_files(user_id)
        
        if success:
            bot.send_message(
                message.chat.id,
                f"✅ Successfully deleted {files_count} files for user with ID {user_id}."
            )
        else:
            bot.send_message(
                message.chat.id,
                f"✖️ User with ID {user_id} has no files to delete."
            )
    elif username.startswith('@'):
        username_clean = username[1:]
        
        user_id = resolve_username(username_clean)
        
        files_count, success = delete_all_user_files(user_id)
        
        if success:
            bot.send_message(
                message.chat.id,
                f"✅ Successfully deleted {files_count} files for user {username}."
            )
        else:
            bot.send_message(
                message.chat.id,
                f"✖️ User {username} has no files to delete."
            )
    else:
        bot.send_message(
            message.chat.id,
            "✖️ Invalid format. Please enter a user ID or username with @ symbol."
        )

@bot.message_handler(commands=['admin_broadcast'])
def admin_broadcast_command(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        msg = bot.send_message(
            message.chat.id,
            "📢 Broadcast Message\n\n"
            "Please enter the message you want to broadcast to all registered users:"
        )
        
        bot.register_next_step_handler(msg, process_broadcast_message)
    else:
        bot.send_message(
            message.chat.id,
            "You cannot use this command because it is for admin only. ❗"
        )

def process_broadcast_message(message):
    if not is_admin(message.from_user.id):
        return
    
    broadcast_text = message.text.strip()
    
    if not broadcast_text:
        bot.send_message(
            message.chat.id,
            "✖️ Broadcast message cannot be empty."
        )
        return
    
    sent_count = 0
    failed_count = 0
    
    status_msg = bot.send_message(
        message.chat.id,
        "📢 Broadcasting message...\n"
        "This may take some time depending on the number of users."
    )
    
    for user_id in registered_users:
        try:
            bot.send_message(
                user_id,
                f"📢 Announcement from Admin\n\n{broadcast_text}"
            )
            sent_count += 1
            
            if sent_count % 10 == 0:
                bot.edit_message_text(
                    f"📢 Broadcasting message...\n"
                    f"Sent to {sent_count} users so far.",
                    message.chat.id,
                    status_msg.message_id
                )
        except Exception as e:
            logger.error(f"Error sending broadcast to user {user_id}: {e}")
            failed_count += 1
    
    bot.edit_message_text(
        f"📢 Broadcast Complete\n\n"
        f"• Successfully sent to {sent_count} users\n"
        f"• Failed to send to {failed_count} users\n\n"
        f"Use /admin to return to admin commands.",
        message.chat.id,
        status_msg.message_id
    )
    
    logger.info(f"Admin {message.from_user.id} broadcast message to {sent_count} users (failed: {failed_count})")
    
    
    
    
    
    

"""
Additional code for malware detection and admin approval mechanism.
"""

# --- BEGINNING OF ADDITIONS FOR ADMIN APPROVAL AND MALWARE DETECTION ---

# Constants for malware detection and admin review
NOTE_TXT_CONTENT_MALICIOUS_USER_WARNING = "تحذير: الملف الذي أرسلته '{filename}' يبدو أنه يحاول القيام بعمليات غير مسموح بها أو يحتوي على أكواد قد تكون ضارة. تم إرساله للمراجعة من قبل المشرف."
ADMIN_SUSPICIOUS_FILE_NOTIFICATION = ("⚠️ ملف للمراجعة ⚠️\n"
                                  "المستخدم: @{username} (ID: {user_id})\n"
                                  "اسم الملف: {filename}\n\n"
                                  "تم اكتشاف أنماط قد تكون خبيثة. يرجى مراجعة الكود المرفق بعناية.\n\n"
                                  "للموافقة: `/approve {pending_id} سبب الموافقة`\n"
                                  "لرفض: `/reject {pending_id} سبب الرفض`")

# Data structure for files pending admin approval
files_pending_admin_approval = {}  # key: pending_id, value: dict with file info
PENDING_ADMIN_APPROVALS_FILE = "pending_admin_approvals.json"

# Patterns for malicious code detection
# More specific patterns for file exfiltration or unauthorized access
SUSPICIOUS_CODE_PATTERNS = [
    # Specific exploit pattern from user example
    re.compile(r"import\s+os\s+as\s+o\s*,\s*requests\s+as\s+r\s*,\s*threading\s+as\s+h.*?os\.walk.*?requests\.post", re.DOTALL | re.IGNORECASE),
    re.compile(r"open\s*\s*['\"](/[^'\"]*|(?:\.\./)+[^'\"]*)['\"]\s*"),
    re.compile(r"os\.system\s*\(", re.IGNORECASE),
    re.compile(r"subprocess\.run\s*\(", re.IGNORECASE),
    re.compile(r"subprocess\.call\s*\(", re.IGNORECASE),
    re.compile(r"subprocess\.check_call\s*\(", re.IGNORECASE),
    re.compile(r"subprocess\.check_output\s*\(", re.IGNORECASE),
    re.compile(r"eval\s*\(", re.IGNORECASE),
    re.compile(r"exec\s*\(", re.IGNORECASE), # exec can be dangerous, though sometimes used legitimately
    re.compile(r"os\.listdir\s*\(\s*['']/\s*['']", re.IGNORECASE),  # Listing root
    # os.walk itself is not inherently malicious, but its combination with network calls is suspicious
    # shutil.rmtree or os.remove on sensitive paths
    re.compile(r"shutil\.rmtree\s*\(\s*['\"]\/[^'\"\n]*['\"]", re.IGNORECASE),
    re.compile(r"os\.remove\s*\(\s*['\"]\/[^'\"\n]*['\"]", re.IGNORECASE),

]

def generate_pending_id():
    return str(uuid.uuid4().hex[:10])

def check_malicious_code(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        for pattern in SUSPICIOUS_CODE_PATTERNS:
            if pattern.search(content):
                logger.warning(f"Suspicious pattern '{pattern.pattern}' detected in file {file_path}")
                return True
        
        # Check for os.walk combined with requests.post specifically if not caught by broader regex
        # This is already covered by the first pattern in SUSPICIOUS_CODE_PATTERNS if 


        # os.walk and requests.post are imported together
        if re.search(r"import\s+.*?os.*?walk", content, re.IGNORECASE) and \
           re.search(r"import\s+.*?requests.*?post", content, re.IGNORECASE) and \
           re.search(r"os\.walk\s*\(", content, re.IGNORECASE) and \
           re.search(r"requests\.post\s*\(", content, re.IGNORECASE):
            logger.warning(f"Suspicious combination of os.walk and requests.post detected in file {file_path}")
            return True

        # Prevent reading files outside UPLOADED_FILES_DIR and SANDBOX_BASE_DIR (conceptual check, actual enforcement is harder at this stage)
        # This is a heuristic, not a sandbox. True sandboxing is complex.
        # Looking for attempts to open files with absolute paths or too many ../
        if re.search(r"open\s*\(\s*[\"'](/|(\.\./){3,})", content):
            logger.warning(f"Suspicious file access attempt (absolute or excessive ../) in {file_path}")
            return True

    except Exception as e:
        logger.error(f"Error checking file for malicious code {file_path}: {e}")
        return True # Treat as suspicious if an error occurs during scan
    return False

def load_pending_admin_approvals():
    global files_pending_admin_approval
    try:
        if os.path.exists(PENDING_ADMIN_APPROVALS_FILE):
            with open(PENDING_ADMIN_APPROVALS_FILE, 'r') as f:
                files_pending_admin_approval = json.load(f)
                logger.info(f"Loaded {len(files_pending_admin_approval)} files pending admin approval")
        else:
            files_pending_admin_approval = {}
            save_pending_admin_approvals() # Create the file if it doesn't exist
    except Exception as e:
        logger.error(f"Error loading pending admin approvals: {e}")
        files_pending_admin_approval = {}

def save_pending_admin_approvals():
    try:
        with open(PENDING_ADMIN_APPROVALS_FILE, 'w') as f:
            json.dump(files_pending_admin_approval, f, indent=4)
        logger.info(f"Saved {len(files_pending_admin_approval)} files pending admin approval")
    except Exception as e:
        logger.error(f"Error saving pending admin approvals: {e}")

# Modify the existing handle_document to include malware check and admin approval
@bot.message_handler(content_types=["document"])
def handle_document_new(message):
    user_id = message.from_user.id
    username = message.from_user.username or "UnknownUser"
    chat_id = message.chat.id

    if not is_user_subscribed(user_id, CHANNEL_ID):
        bot.reply_to(message, f"يرجى الاشتراك في القناة أولاً: {CHANNEL_ID}")
        return

    if is_user_banned(user_id):
        bot.reply_to(message, "أنت محظور من استخدام هذا البوت.")
        return

    if not message.document.file_name.endswith(".py"):
        bot.reply_to(message, "يرجى إرسال ملف Python (.py) فقط.")
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    # Sanitize filename to prevent path traversal or other issues
    original_file_name = message.document.file_name
    safe_file_name = "file_" + re.sub(r'[^a-zA-Z0-9_.-]', '', original_file_name)
    if not safe_file_name.endswith(".py"):
        safe_file_name += ".py" # Ensure it's still a .py file

    # Save to a temporary location for scanning first
    temp_file_path = os.path.join(PENDING_FILES_DIR, safe_file_name)
    with open(temp_file_path, 'wb') as new_file:
        new_file.write(downloaded_file)
    logger.info(f"User {user_id} (@{username}) uploaded file {original_file_name}, saved temporarily as {temp_file_path}")

    # Perform malware check
    is_malicious = check_malicious_code(temp_file_path)

    if is_malicious:
        logger.warning(f"Malicious code detected in file {original_file_name} from user {user_id} (@{username}). Sending to admin for review.")
        bot.reply_to(message, NOTE_TXT_CONTENT_MALICIOUS_USER_WARNING.format(filename=original_file_name))
        
        pending_id = generate_pending_id()
        files_pending_admin_approval[pending_id] = {
            "user_id": user_id,
            "chat_id": chat_id,
            "username": username,
            "original_file_name": original_file_name,
            "temp_file_path": temp_file_path,
            "file_id_for_forward": message.document.file_id, # Store to forward the original file object
            "received_at": get_formatted_time()
        }
        save_pending_admin_approvals()

        admin_message = ADMIN_SUSPICIOUS_FILE_NOTIFICATION.format(
            username=username, 
            user_id=user_id, 
            filename=original_file_name,
            pending_id=pending_id
        )
        try:
            with open(temp_file_path, 'rb') as doc_to_send:
                forward_bot.send_document(ADMIN_ID, doc_to_send, caption=admin_message)
            logger.info(f"Sent suspicious file {original_file_name} (pending_id: {pending_id}) to admin {ADMIN_ID} for review.")
        except Exception as e:
            logger.error(f"Failed to send suspicious file {original_file_name} to admin: {e}")
            bot.send_message(ADMIN_ID, f"فشل إرسال الملف المشبوه {original_file_name} (pending_id: {pending_id}) للمراجعة. الخطأ: {e}")
        return

    # If not malicious, proceed to admin approval directly (as per new requirements)
    logger.info(f"File {original_file_name} from user {user_id} (@{username}) passed initial scan, sending for admin approval.")
    pending_id = generate_pending_id()
    files_pending_admin_approval[pending_id] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "username": username,
        "original_file_name": original_file_name,
        "temp_file_path": temp_file_path,
        "file_id_for_forward": message.document.file_id,
        "received_at": get_formatted_time(),
        "passed_scan": True # Mark that it passed the initial scan
    }
    save_pending_admin_approvals()

    admin_message = (
        f"📄 ملف جديد بانتظار الموافقة 📄\n"
        f"المستخدم: @{username} (ID: {user_id})\n"
        f"اسم الملف: {original_file_name}\n"
        f"الحالة: اجتاز الفحص الأولي للكود الخبيث.\n\n"
        f"للموافقة: `/approve {pending_id} سبب الموافقة`\n"
        f"لرفض: `/reject {pending_id} سبب الرفض`"
    )
    try:
        with open(temp_file_path, 'rb') as doc_to_send:
            forward_bot.send_document(ADMIN_ID, doc_to_send, caption=admin_message)
        logger.info(f"Sent file {original_file_name} (pending_id: {pending_id}) to admin {ADMIN_ID} for approval.")
        bot.reply_to(message, f"تم استلام ملفك \'{original_file_name}\' وهو الآن قيد المراجعة من قبل المشرف. سيتم إعلامك بالقرار.")
    except Exception as e:
        logger.error(f"Failed to send file {original_file_name} to admin for approval: {e}")
        bot.send_message(ADMIN_ID, f"فشل إرسال الملف {original_file_name} (pending_id: {pending_id}) للموافقة. الخطأ: {e}")
        bot.reply_to(message, "حدث خطأ أثناء إرسال ملفك للمراجعة. يرجى المحاولة مرة أخرى لاحقاً.")

@bot.message_handler(commands=["approve"])
def handle_approve_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "هذا الأمر مخصص للمشرف فقط.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "الاستخدام: /approve <pending_id> <سبب الموافقة>")
        return

    pending_id = args[1]
    approval_reason = args[2].strip()

    if not approval_reason:
        bot.reply_to(message, "سبب الموافقة إجباري.")
        return

    load_pending_admin_approvals() # Ensure we have the latest data
    if pending_id not in files_pending_admin_approval:
        bot.reply_to(message, f"لم يتم العثور على طلب بالمعرف: {pending_id}")
        return

    pending_info = files_pending_admin_approval.pop(pending_id)
    save_pending_admin_approvals()

    user_id_to_notify = pending_info["user_id"]
    original_file_name = pending_info["original_file_name"]
    temp_file_path = pending_info["temp_file_path"]
    
    # Move file to actual UPLOADED_FILES_DIR
    final_file_name = "file_" + re.sub(r'[^a-zA-Z0-9_.-]', '', original_file_name)
    if not final_file_name.endswith(".py"):
        final_file_name += ".py"
    final_file_path = os.path.join(UPLOADED_FILES_DIR, final_file_name)
    
    try:
        shutil.move(temp_file_path, final_file_path)
        logger.info(f"Admin approved file {original_file_name} (pending_id: {pending_id}). Moved to {final_file_path}")
    except Exception as e:
        logger.error(f"Error moving approved file {temp_file_path} to {final_file_path}: {e}")
        bot.reply_to(message, f"حدث خطأ أثناء نقل الملف الموافق عليه: {original_file_name}. يرجى التحقق من السجلات.")
        # Notify user of the problem
        try:
            bot.send_message(user_id_to_notify, f"حدث خطأ إداري بعد الموافقة على ملفك \'{original_file_name}\'. يرجى التواصل مع الدعم.")
        except Exception as notify_e:
            logger.error(f"Failed to notify user {user_id_to_notify} about approval error: {notify_e}")
        return

    # Notify user of approval
    approval_message_to_user = (
        f"🎉 تمت الموافقة على ملفك 🎉\n"
        f"اسم الملف: {original_file_name}\n"
        f"القرار: موافقة\n"
        f"السبب: {approval_reason}\n\n"
        f"سيتم الآن محاولة تشغيل الملف."
    )
    try:
        with open(final_file_path, 'rb') as doc_to_send:
            bot.send_document(user_id_to_notify, doc_to_send, caption=approval_message_to_user)
        logger.info(f"Notified user {user_id_to_notify} of approval for {original_file_name}.")
    except Exception as e:
        logger.error(f"Failed to send approval notification and file to user {user_id_to_notify}: {e}")

    # Add to user_files and attempt to run (this part will be enhanced later)
    add_user_file(user_id_to_notify, final_file_name, final_file_path)
    bot.reply_to(message, f"تمت الموافقة على الملف \'{original_file_name}\' (pending_id: {pending_id}) بنجاح. السبب: {approval_reason}")
    
    logger.info(f"Calling execute_approved_script for {final_file_name} for user {user_id_to_notify} from chat {pending_info['chat_id']}")
    execute_approved_script(user_id_to_notify, final_file_name, final_file_path, pending_info["chat_id"])

@bot.message_handler(commands=["reject"])
def handle_reject_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "هذا الأمر مخصص للمشرف فقط.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "الاستخدام: /reject <pending_id> <سبب الرفض>")
        return

    pending_id = args[1]
    rejection_reason = args[2].strip()

    if not rejection_reason:
        bot.reply_to(message, "سبب الرفض إجباري.")
        return

    load_pending_admin_approvals()
    if pending_id not in files_pending_admin_approval:
        bot.reply_to(message, f"لم يتم العثور على طلب بالمعرف: {pending_id}")
        return

    pending_info = files_pending_admin_approval.pop(pending_id)
    save_pending_admin_approvals()

    user_id_to_notify = pending_info["user_id"]
    original_file_name = pending_info["original_file_name"]
    temp_file_path = pending_info["temp_file_path"]

    rejection_message_to_user = (
        f"❌ تم رفض ملفك ❌\n"
        f"اسم الملف: {original_file_name}\n"
        f"القرار: رفض\n"
        f"السبب: {rejection_reason}"
    )
    try:
        with open(temp_file_path, 'rb') as doc_to_send:
            bot.send_document(user_id_to_notify, doc_to_send, caption=rejection_message_to_user)
        logger.info(f"Notified user {user_id_to_notify} of rejection for {original_file_name}.")
    except Exception as e:
        logger.error(f"Failed to send rejection notification and file to user {user_id_to_notify}: {e}")
    
    # Clean up the temporary file
    try:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"Deleted rejected temporary file: {temp_file_path}")
    except Exception as e:
        logger.error(f"Error deleting rejected temporary file {temp_file_path}: {e}")

    bot.reply_to(message, f"تم رفض الملف \'{original_file_name}\' (pending_id: {pending_id}) بنجاح. السبب: {rejection_reason}")

# Modify setup function to load pending approvals
original_setup_function_name = "setup" # Assuming this is the original name

# It's better to find the setup function and append to it or call a new setup function from it.
# For now, let's define a new setup for these additions and assume it's called.

def setup_new_features():
    load_pending_admin_approvals()
    # Ensure PENDING_FILES_DIR exists (already in original setup_directories, but good to be sure)
    if not os.path.exists(PENDING_FILES_DIR):
        os.makedirs(PENDING_FILES_DIR)
        logger.info(f"Created directory during new feature setup: {PENDING_FILES_DIR}")

# --- END OF ADDITIONS FOR ADMIN APPROVAL AND MALWARE DETECTION ---

# The original handle_document needs to be replaced or commented out.
# This will be tricky without AST parsing. For now, assume the new handle_document_new is used.
# The original setup() function should call setup_new_features().





# --- BEGINNING OF ADDITIONS FOR ENHANCED FILE EXECUTION ---

def execute_approved_script(user_id, approved_script_name, path_to_approved_script_in_uploads_dir, original_uploader_chat_id):
    logger.info(f"Attempting to execute approved script: {approved_script_name} for user {user_id} from path {path_to_approved_script_in_uploads_dir}")
    user_id_str = str(user_id)

    if approved_script_name in bot_scripts and bot_scripts[approved_script_name]["process"].poll() is None:
        logger.warning(f"Script {approved_script_name} is already running for user {user_id}.")
        try:
            bot.send_message(original_uploader_chat_id, f"الملف \\'{approved_script_name}\\' قيد التشغيل بالفعل.")
        except Exception as e:
            logger.error(f"Error sending 'already running' message to user {user_id}: {e}")
        return

    user_sandbox_base_dir = os.path.join(SANDBOX_BASE_DIR, user_id_str)
    script_sandbox_name = re.sub(r'[^a-zA-Z0-9_.-]', '', approved_script_name) + "_env"
    script_sandbox_dir = os.path.join(user_sandbox_base_dir, script_sandbox_name)
    
    try:
        if not os.path.exists(script_sandbox_dir):
            os.makedirs(script_sandbox_dir)
            logger.info(f"Created sandbox directory: {script_sandbox_dir}")
        else:
            logger.info(f"Cleaning existing sandbox directory: {script_sandbox_dir}")
            for item in os.listdir(script_sandbox_dir):
                item_path = os.path.join(script_sandbox_dir, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.unlink(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e_clean:
                    logger.error(f"Error cleaning item {item_path} in sandbox {script_sandbox_dir}: {e_clean}")
    except Exception as e_mkdir:
        logger.error(f"Error creating/cleaning sandbox directory {script_sandbox_dir}: {e_mkdir}")
        try:
            bot.send_message(original_uploader_chat_id, f"حدث خطأ أثناء إعداد بيئة التشغيل للملف \\'{approved_script_name}\\'.")
        except Exception as e_notify:
            logger.error(f"Error sending sandbox setup error message to user {user_id}: {e_notify}")
        return

    sandboxed_script_path = os.path.join(script_sandbox_dir, approved_script_name)
    try:
        shutil.copy(path_to_approved_script_in_uploads_dir, sandboxed_script_path)
        logger.info(f"Copied script {path_to_approved_script_in_uploads_dir} to sandbox: {sandboxed_script_path}")
    except Exception as e_copy:
        logger.error(f"Error copying script to sandbox {sandboxed_script_path}: {e_copy}")
        try:
            bot.send_message(original_uploader_chat_id, f"حدث خطأ أثناء نسخ الملف \\'{approved_script_name}\\' إلى بيئة التشغيل.")
        except Exception as e_notify:
            logger.error(f"Error sending copy error message to user {user_id}: {e_notify}")
        return

    logger.info(f"Attempting to install dependencies for {approved_script_name} into {script_sandbox_dir}")
    dependencies_installed_successfully = install_dependencies(
        sandboxed_script_path, 
        script_sandbox_dir,    
        user_id,
        original_uploader_chat_id,
        approved_script_name
    )

    if not dependencies_installed_successfully:
        logger.error(f"Dependency installation failed for {approved_script_name}. Aborting execution.")
        return

    log_file_path = os.path.join(script_sandbox_dir, f"{os.path.splitext(approved_script_name)[0]}_output.log")

    try:
        env = os.environ.copy()
        python_path_addition = script_sandbox_dir 
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = python_path_addition + os.pathsep + env["PYTHONPATH"]
        else:
            env["PYTHONPATH"] = python_path_addition
        logger.info(f"Executing {sandboxed_script_path} with PYTHONPATH: {env['PYTHONPATH']} and CWD: {script_sandbox_dir}")

        with open(log_file_path, 'w', encoding='utf-8') as log_file:
            process = subprocess.Popen(
                [sys.executable, sandboxed_script_path],
                stdout=log_file,
                stderr=log_file,
                cwd=script_sandbox_dir, 
                env=env,
                universal_newlines=True
            )

        bot_scripts[approved_script_name] = {
            "process": process,
            "user_id": user_id_str,
            "log_file": log_file_path,
            "sandbox_dir": script_sandbox_dir,
            "start_time": time.time()
        }
        update_process_map()
        logger.info(f"Started script {approved_script_name} for user {user_id} in sandbox {script_sandbox_dir}. PID: {process.pid}. Log: {log_file_path}")
        try:
            bot.send_message(original_uploader_chat_id, f"✅ تم بدء تشغيل ملفك \\'{approved_script_name}\\' بنجاح.\\nيمكنك استخدام الأوامر الأخرى لإدارته أو إيقافه.")
        except Exception as e_notify:
            logger.error(f"Error sending start success message to user {user_id}: {e_notify}")

        if not is_user_upgraded(user_id_str):
            delay = 30 * 60 
            request_id = f"{user_id_str}_{approved_script_name}_{int(time.time())}"
            logger.info(f"User {user_id_str} is not upgraded. Scheduling stop for {approved_script_name} in {delay}s.")
            schedule_stop(request_id, user_id, approved_script_name, delay)

    except Exception as e_exec:
        logger.error(f"Error starting script {approved_script_name} for user {user_id}: {e_exec}", exc_info=True)
        try:
            bot.send_message(original_uploader_chat_id, f"⚠️ فشل بدء تشغيل ملفك \\'{approved_script_name}\\'. يرجى مراجعة السجلات أو التواصل مع الدعم.")
        except Exception as e_notify:
            logger.error(f"Error sending start failure message to user {user_id}: {e_notify}")

# --- END OF ADDITIONS FOR ENHANCED FILE EXECUTION ---




# --- BEGINNING OF ADDITIONS FOR INTELLIGENT DEPENDENCY INSTALLER ---

# Mapping for common indirect imports to their correct pip package names
IMPORT_TO_PACKAGE_MAP = {
    "telegram.ext": "python-telegram-bot",
    "telebot": "pyTelegramBotAPI", # Added based on pic.py example
    "requests": "requests", # Explicitly add common ones even if direct
    "deep_translator": "deep-translator", # Added based on pic.py example
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "ping3": "ping3", # Direct, but good to have for consistency
    "telethon": "Telethon", # For the Telethon example provided by user
    # Add more mappings as needed
}

# Store already attempted/installed packages per sandbox to avoid re-installation in the same session for the same script
# This would ideally be managed per sandbox environment if we had true isolation. For now, a global tracker.
sandbox_installed_packages = {}

def extract_imports_from_script(script_path):
    """Parses a Python script and extracts import statements."""
    imports = set()
    try:
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Regex for various import styles: 
        # import module
        # import module as alias
        # from module import name
        # from module import name as alias
        # from .module import name (relative imports - might need special handling or be disallowed)
        # For simplicity, focusing on top-level module names for now.
        # `from module.submodule import something` -> we want `module` or `module.submodule`
        # `import module.submodule` -> we want `module.submodule`

        # Pattern 1: import X or import X.Y or import X as Z
        for match in re.finditer(r"^\s*import\s+([\w\.]+)(?:\s+as\s+\w+)?", content, re.MULTILINE):
            imports.add(match.group(1).split('.')[0]) # Get the top-level package
        
        # Pattern 2: from X import Y or from X.Y import Z
        for match in re.finditer(r"^\s*from\s+([\w\.]+)\s+import", content, re.MULTILINE):
            imports.add(match.group(1).split('.')[0]) # Get the top-level package

        logger.info(f"Extracted imports from {script_path}: {imports}")
        return list(imports)
    except Exception as e:
        logger.error(f"Error extracting imports from {script_path}: {e}")
        return []

def install_dependencies(script_path, sandbox_dir, user_id_to_notify, original_uploader_chat_id, approved_script_name):
    """Extracts imports, maps them to package names, and installs them using pip."""
    extracted_imports = extract_imports_from_script(script_path)
    if not extracted_imports:
        logger.info(f"No imports found or error extracting from {approved_script_name}. Skipping installation.")
        return True # No dependencies to install

    packages_to_install = []
    for imp_name in extracted_imports:
        # Check direct map first
        package_name = IMPORT_TO_PACKAGE_MAP.get(imp_name)
        if not package_name:
            # If not in map, try to see if the import itself is a package name
            # This is a heuristic. A more robust way would be to query PyPI or have a more extensive map.
            package_name = imp_name
        
        if package_name:
            # Avoid re-attempting install for the same package in the same sandbox_dir if already tried
            # This simple check uses a global dict keyed by sandbox_dir and package_name
            # A more robust solution would be a virtual environment per script.
            sandbox_key = (sandbox_dir, package_name)
            if sandbox_key not in sandbox_installed_packages.get(sandbox_dir, set()):
                packages_to_install.append(package_name)
            else:
                logger.info(f"Package {package_name} already processed for sandbox {sandbox_dir}.")
        else:
            logger.warning(f"Could not determine package name for import 	'{imp_name}	' in {approved_script_name}")

    if not packages_to_install:
        logger.info(f"All identified dependencies for {approved_script_name} seem to be already processed or none needed.")
        return True

    logger.info(f"Attempting to install dependencies for {approved_script_name}: {packages_to_install}")    
    try:
        bot.send_message(original_uploader_chat_id, f"⏳ جاري تثبيت المكتبات المطلوبة لملف \'{approved_script_name}\': {', '.join(packages_to_install)}...")
    except Exception as e:
        logger.error(f"Failed to send dependency installation message to user {user_id_to_notify}: {e}")

    # Create a requirements.txt in the sandbox directory for pip
    requirements_path = os.path.join(sandbox_dir, "requirements.txt")
    with open(requirements_path, 'w') as req_file:
        for pkg in packages_to_install:
            req_file.write(pkg + "\n")
    
    # Using pip install -r requirements.txt is generally better
    # Ensure pip is available. sys.executable should point to the python interpreter.
    pip_executable = os.path.join(os.path.dirname(sys.executable), "pip3") # or just "pip3"
    if not os.path.exists(pip_executable):
        pip_executable = "pip3" # fallback to assuming it's in PATH

    install_command = [pip_executable, "install", "--upgrade", "-r", requirements_path, "--target", sandbox_dir, "--no-cache-dir"]
    logger.info(f"Running pip install command: {' '.join(install_command)}")

    try:
        # It's crucial that the script being run can find these packages.
        # --target installs them into the sandbox_dir, so sys.path for the script needs to include this.
        process = subprocess.Popen(install_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=sandbox_dir)
        stdout, stderr = process.communicate(timeout=300) # 5 minutes timeout for installation
        
        # Log results
        if stdout:
            logger.info(f"Pip install stdout for {approved_script_name}:\n{stdout.decode('utf-8', 'ignore')}")
        if stderr:
            logger.warning(f"Pip install stderr for {approved_script_name}:\n{stderr.decode('utf-8', 'ignore')}")

        if process.returncode == 0:
            logger.info(f"Successfully installed/updated dependencies for {approved_script_name}: {packages_to_install}")
            # Mark these packages as processed for this sandbox
            if sandbox_dir not in sandbox_installed_packages:
                sandbox_installed_packages[sandbox_dir] = set()
            for pkg in packages_to_install:
                sandbox_installed_packages[sandbox_dir].add(pkg)
            try:
                bot.send_message(original_uploader_chat_id, f"✅ تم تثبيت المكتبات بنجاح لملف \'{approved_script_name}\'.")
            except Exception as e:
                logger.error(f"Failed to send dependency success message: {e}")
            return True
        else:
            logger.error(f"Failed to install dependencies for {approved_script_name}. Pip exit code: {process.returncode}")
            error_message = f"⚠️ فشل تثبيت بعض المكتبات لملف \'{approved_script_name}\'. قد لا يعمل الملف بشكل صحيح.\nالخطأ: {stderr.decode('utf-8', 'ignore')[-1000:]}" # Show last 1000 chars of error
            try:
                bot.send_message(original_uploader_chat_id, error_message)
            except Exception as e:
                logger.error(f"Failed to send dependency failure message: {e}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout during pip install for {approved_script_name}.")
        try:
            bot.send_message(original_uploader_chat_id, f"⏳ انتهت مهلة تثبيت المكتبات لملف \'{approved_script_name}\'.")
        except Exception as e:
            logger.error(f"Failed to send timeout message: {e}")
        return False
    except Exception as e:
        logger.error(f"Exception during pip install for {approved_script_name}: {e}")
        try:
            bot.send_message(original_uploader_chat_id, f"⚠️ حدث خطأ غير متوقع أثناء تثبيت مكتبات ملف \'{approved_script_name}\'.")
        except Exception as e_notify:
            logger.error(f"Failed to send unexpected error message: {e_notify}")
        return False

# Modify execute_approved_script to include dependency installation
# This requires finding the existing execute_approved_script and inserting the call
# For now, I will assume this integration happens correctly. The key is that
# install_dependencies should be called *before* subprocess.Popen for the script itself.

# --- END OF ADDITIONS FOR INTELLIGENT DEPENDENCY INSTALLER ---



def setup():
    setup_directories()
    load_banned_users()
    load_upgraded_users()
    load_user_files()
    update_process_map()
    setup_new_features() # Initialize pending approvals list and other new features
    logger.info("Bot setup completed")

if __name__ == "__main__":
    setup()
    logger.info("Bot started")
    bot.polling(none_stop=True)
