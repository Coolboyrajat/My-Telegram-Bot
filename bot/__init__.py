from logging import getLogger, FileHandler, StreamHandler, INFO, basicConfig, error as log_error, info as log_info, warning as log_warning
from socket import setdefaulttimeout
from faulthandler import enable as faulthandler_enable
from telegram.ext import Updater as tgUpdater
from qbittorrentapi import Client as qbClient
from aria2p import API as ariaAPI, Client as ariaClient
from os import remove as osremove, path as ospath, environ
from requests import get as rget
from json import loads as jsnloads
from subprocess import Popen, run as srun, check_output
from time import sleep, time
from threading import Thread, Lock
from dotenv import load_dotenv
from pyrogram import Client, enums
from asyncio import get_event_loop
from megasdkrestclient import MegaSdkRestClient
from megasdkrestclient import errors as mega_err
main_loop = get_event_loop()

faulthandler_enable()

setdefaulttimeout(600)

botStartTime = time()

basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[FileHandler('log.txt'), StreamHandler()],
                    level=INFO)

LOGGER = getLogger(__name__)

load_dotenv('config.env', override=True)

def getConfig(name: str):
    return environ[name]

try:
    SERVER_PORT = getConfig('SERVER_PORT')
    if len(SERVER_PORT) == 0:
        raise KeyError
except:
    SERVER_PORT = 80

PORT = environ.get('PORT', SERVER_PORT)
Popen([f"gunicorn web.wserver:app --bind 0.0.0.0:{PORT}"], shell=True)
srun(["qbittorrent-nox", "-d", "--profile=."])
if not ospath.exists('.netrc'):
    srun(["touch", ".netrc"])
srun(["cp", ".netrc", "/root/.netrc"])
srun(["chmod", "600", ".netrc"])
srun(["chmod", "+x", "aria.sh"])
srun(["./aria.sh"], shell=True)

Interval = []
DRIVES_NAMES = []
DRIVES_IDS = []
INDEX_URLS = []

try:
    if bool(getConfig('_____REMOVE_THIS_LINE_____')):
        log_error('The README.md file there to be read! Exiting now!')
        exit()
except:
    pass

aria2 = ariaAPI(
    ariaClient(
        host="http://localhost",
        port=6800,
        secret="",
    )
)

def get_client():
    return qbClient(host="localhost", port=8090)

DOWNLOAD_DIR = None
BOT_TOKEN = None

download_dict_lock = Lock()
status_reply_dict_lock = Lock()
# Key: update.effective_chat.id
# Value: telegram.Message
status_reply_dict = {}
# Key: update.message.message_id
# Value: An object of Status
download_dict = {}
# key: rss_title
# value: [rss_feed, last_link, last_title, filter]
rss_dict = {}

# REQUIRED CONFIG:
try:
    OWNER_ID = int(getConfig('OWNER_ID'))
    BOT_TOKEN = getConfig('BOT_TOKEN')
    parent_id = getConfig('GDRIVE_FOLDER_ID')
    TELEGRAM_API = getConfig('TELEGRAM_API')
    TELEGRAM_HASH = getConfig('TELEGRAM_HASH')
    DOWNLOAD_DIR = getConfig('DOWNLOAD_DIR')
    if not DOWNLOAD_DIR.endswith("/"):
        DOWNLOAD_DIR = DOWNLOAD_DIR + '/'
    DOWNLOAD_STATUS_UPDATE_INTERVAL = int(getConfig('DOWNLOAD_STATUS_UPDATE_INTERVAL'))
    AUTO_DELETE_MESSAGE_DURATION = int(getConfig('AUTO_DELETE_MESSAGE_DURATION'))
except:
    LOGGER.error("One or more env variables missing! Exiting now")
    exit(1)
try:
    IS_TEAM_DRIVE = getConfig('IS_TEAM_DRIVE')
    IS_TEAM_DRIVE = IS_TEAM_DRIVE.lower() == 'true'
except:
    IS_TEAM_DRIVE = False
try:
    AUTO_DELETE_UPLOAD_MESSAGE_DURATION = int(getConfig('AUTO_DELETE_UPLOAD_MESSAGE_DURATION'))
except KeyError as e:
    AUTO_DELETE_UPLOAD_MESSAGE_DURATION = -1
    LOGGER.warning("AUTO_DELETE_UPLOAD_MESSAGE_DURATION var missing!")
    pass

LOGGER.info("Generating BOT_SESSION_STRING")
app = Client(name='pyrogram', api_id=int(TELEGRAM_API), api_hash=TELEGRAM_HASH, bot_token=BOT_TOKEN, parse_mode=enums.ParseMode.HTML, no_updates=True)

# OPTIONAL CONFIG:

try:
    DB_URI = getConfig('DATABASE_URL')
    if len(DB_URI) == 0:
        raise KeyError
except:
    DB_URI = None

AUTHORIZED_CHATS = set()
SUDO_USERS = set()
AS_DOC_USERS = set()
AS_MEDIA_USERS = set()
EXTENTION_FILTER = set(['.torrent'])
MIRROR_LOGS = set()
try:
    aid = getConfig('AUTHORIZED_CHATS')
    aid = aid.split(' ')
    for _id in aid:
        AUTHORIZED_CHATS.add(int(_id))
except:
    pass
try:
    aid = getConfig('SUDO_USERS')
    aid = aid.split(' ')
    for _id in aid:
        SUDO_USERS.add(int(_id))
except:
    pass

try:
    USE_SERVICE_ACCOUNTS = getConfig('USE_SERVICE_ACCOUNTS')
    USE_SERVICE_ACCOUNTS = USE_SERVICE_ACCOUNTS.lower() == 'true'
except:
    USE_SERVICE_ACCOUNTS = False
try:
    INDEX_URL = getConfig('INDEX_URL').rstrip("/")
    if len(INDEX_URL) == 0:
        raise KeyError
    INDEX_URLS.append(INDEX_URL)
except:
    INDEX_URL = None
    INDEX_URLS.append(None)
try:
    STATUS_LIMIT = getConfig('STATUS_LIMIT')
    if len(STATUS_LIMIT) == 0:
        raise KeyError
    STATUS_LIMIT = int(STATUS_LIMIT)
except:
    STATUS_LIMIT = None
try:
    STOP_DUPLICATE = getConfig('STOP_DUPLICATE')
    STOP_DUPLICATE = STOP_DUPLICATE.lower() == 'true'
except:
    STOP_DUPLICATE = False
try:
    CMD_INDEX = getConfig('CMD_INDEX')
    if len(CMD_INDEX) == 0:
        raise KeyError
except:
    CMD_INDEX = ''
try:
    UPTOBOX_PREMIUM = getConfig('UPTOBOX_PREMIUM')
    UPTOBOX_PREMIUM = UPTOBOX_PREMIUM.lower() == 'true'
    if UPTOBOX_PREMIUM == 'true':
        try:
            UPTOBOX_TOKEN = getConfig('UPTOBOX_TOKEN')
            if len(UPTOBOX_TOKEN) == 0:
                raise KeyError
        except:
            UPTOBOX_TOKEN = None
    else:
        log_error(f"Failed to Acquire Uptobox Premium Token")        
except:
    UPTOBOX_PREMIUM = False
try:
    UPTOBOX_TOKEN = getConfig('UPTOBOX_TOKEN')
    if len(UPTOBOX_TOKEN) == 0:
        raise KeyError
except:
    UPTOBOX_TOKEN = None
try:
    TORRENT_TIMEOUT = getConfig('TORRENT_TIMEOUT')
    if len(TORRENT_TIMEOUT) == 0:
        raise KeyError
    TORRENT_TIMEOUT = int(TORRENT_TIMEOUT)
except:
    TORRENT_TIMEOUT = None
try:
    fx = getConfig('EXTENTION_FILTER')
    if len(fx) > 0:
        fx = fx.split(' ')
        for x in fx:
            EXTENTION_FILTER.add(x.lower())
except:
    pass
try:
    INCOMPLETE_TASK_NOTIFIER = getConfig('INCOMPLETE_TASK_NOTIFIER')
    INCOMPLETE_TASK_NOTIFIER = INCOMPLETE_TASK_NOTIFIER.lower() == 'true'
except:
    INCOMPLETE_TASK_NOTIFIER = False
try:
    MULTI_GDRIVE = getConfig('MULTI_GDRIVE')
    MULTI_GDRIVE = MULTI_GDRIVE.lower() == 'true'
    if MULTI_GDRIVE == 'true':
        try:
            MULTI_GDRIVE_ID = getConfig('MULTI_GDRIVE_ID')
            if len(MULTI_GDRIVE_ID) == 0:
                raise KeyError
        except:
            MULTI_GDRIVE_ID = None
    else:
        log_error(f"Failed to get Drive ID's")
except:
    MULTI_GDRIVE = False
try:
    BOT_PM = getConfig('BOT_PM')
    BOT_PM = BOT_PM.lower() == 'true'
except KeyError:
    BOT_PM = False
try:
    aid = getConfig('MIRROR_LOGS')
    aid = aid.split(' ')
    for _id in aid:
        MIRROR_LOGS.add(int(_id))
except:
    pass

def aria2c_init():
    try:
        log_info("Initializing Aria2c")
        link = "https://releases.ubuntu.com/21.10/ubuntu-21.10-desktop-amd64.iso.torrent"
        dire = DOWNLOAD_DIR.rstrip("/")
        aria2.add_uris([link], {'dir': dire})
        sleep(3)
        downloads = aria2.get_downloads()
        sleep(20)
        for download in downloads:
            aria2.remove([download], force=True, files=True)
    except Exception as e:
        log_error(f"Aria2c initializing error: {e}")
Thread(target=aria2c_init).start()
sleep(1.5)

# MEGA CONFIG:

try:
    MEGAREST = getConfig('MEGAREST')
    MEGAREST = MEGAREST.lower() == 'true'
except KeyError:
    MEGAREST = False
try:
    MEGA_API_KEY = getConfig("MEGA_API_KEY")
except KeyError:
    MEGA_API_KEY = None
    LOGGER.info("MEGA API KEY NOT AVAILABLE")
if MEGAREST is True:
    # Start megasdkrest binary
    Popen(["megasdkrest", "--apikey", MEGA_API_KEY])
    sleep(3)  # Wait for the mega server to start listening
    mega_client = MegaSdkRestClient("http://localhost:6090")
    try:
        MEGA_EMAIL_ID = getConfig("MEGA_EMAIL_ID")
        MEGA_PASSWORD = getConfig("MEGA_PASSWORD")
        if len(MEGA_EMAIL_ID) > 0 and len(MEGA_PASSWORD) > 0:
            try:
                mega_client.login(MEGA_EMAIL_ID, MEGA_PASSWORD)
            except mega_err.MegaSdkRestClientException as e:
                logging.error(e.message["message"])
                exit(0)
        else:
            LOGGER.info(
                "Mega API KEY provided but credentials not provided. Starting mega in anonymous mode!"
            )
            MEGA_EMAIL_ID = None
            MEGA_PASSWORD = None
    except KeyError:
        LOGGER.info(
            "Mega API KEY provided but credentials not provided. Starting mega in anonymous mode!"
        )
        MEGA_EMAIL_ID = None
        MEGA_PASSWORD = None
else:
    MEGA_EMAIL_ID = None
    MEGA_PASSWORD = None

# LEECH CONFIG:

LEECH_LOG = set()
try:
    aid = getConfig('LEECH_LOG')
    aid = aid.split(' ')
    for _id in aid:
        LEECH_LOG.add(int(_id))
except:
    pass
if USER_SESSION_STRING:
    try:
        with app_session:
            user = app_session.get_me()
            try:
                if user.is_premium:
                    MAX_LEECH_SIZE = 4194304000
                    LOGGER.info("User is Premium Max Leech Size is upgraded to 4 GB")
                else:
                    MAX_LEECH_SIZE = 2097152000
                    LOGGER.info("User is not Premium Max Leech Size is 2 GB")
            except Exception as e:
             MAX_LEECH_SIZE = 2097152000
             LOGGER.info(f"{e} Max Leech Size is 2 GB")
    except Exception as e:
        MAX_LEECH_SIZE = 2097152000
        LOGGER.info(f"{e} Max Leech Size is 2 GB")
else:
    MAX_LEECH_SIZE = 2097152000
    LOGGER.info(f"User Session String Was not provided Skipping Premium acc verification.")

# TORRENT SEARCH:

try:
    SEARCH_API_LINK = getConfig('SEARCH_API_LINK').rstrip("/")
    if len(SEARCH_API_LINK) == 0:
        raise KeyError
except:
    SEARCH_API_LINK = None
try:
    SEARCH_LIMIT = getConfig('SEARCH_LIMIT')
    if len(SEARCH_LIMIT) == 0:
        raise KeyError
    SEARCH_LIMIT = int(SEARCH_LIMIT)
except:
    SEARCH_LIMIT = 0


# SIZE LIMITS:

try:
    TORRENT_DIRECT_LIMIT = getConfig('TORRENT_DIRECT_LIMIT')
    if len(TORRENT_DIRECT_LIMIT) == 0:
        raise KeyError
    TORRENT_DIRECT_LIMIT = float(TORRENT_DIRECT_LIMIT)
except:
    TORRENT_DIRECT_LIMIT = None
try:
    ZIP_UNZIP_LIMIT = getConfig('ZIP_UNZIP_LIMIT')
    if len(ZIP_UNZIP_LIMIT) == 0:
        raise KeyError
    ZIP_UNZIP_LIMIT = float(ZIP_UNZIP_LIMIT)
except:
    ZIP_UNZIP_LIMIT = None
try:
    CLONE_LIMIT = getConfig('CLONE_LIMIT')
    if len(CLONE_LIMIT) == 0:
        raise KeyError
    CLONE_LIMIT = float(CLONE_LIMIT)
except:
    CLONE_LIMIT = None
try:
    MEGA_LIMIT = getConfig('MEGA_LIMIT')
    if len(MEGA_LIMIT) == 0:
        raise KeyError
    MEGA_LIMIT = float(MEGA_LIMIT)
except:
    MEGA_LIMIT = None
try:
    STORAGE_THRESHOLD = getConfig('STORAGE_THRESHOLD')
    if len(STORAGE_THRESHOLD) == 0:
        raise KeyError
    STORAGE_THRESHOLD = float(STORAGE_THRESHOLD)
except:
    STORAGE_THRESHOLD = None

# RSS:

try:
    RSS_DELAY = getConfig('RSS_DELAY')
    if len(RSS_DELAY) == 0:
        raise KeyError
    RSS_DELAY = int(RSS_DELAY)
except:
    RSS_DELAY = 900
try:
    RSS_COMMAND = getConfig('RSS_COMMAND')
    if len(RSS_COMMAND) == 0:
        raise KeyError
except:
    RSS_COMMAND = None
try:
    RSS_CHAT_ID = getConfig('RSS_CHAT_ID')
    if len(RSS_CHAT_ID) == 0:
        raise KeyError
    RSS_CHAT_ID = int(RSS_CHAT_ID)
except:
    RSS_CHAT_ID = None
try:
    RSS_USER_SESSION_STRING = getConfig('RSS_USER_SESSION_STRING')
    if len(RSS_USER_SESSION_STRING) == 0:
        raise KeyError
    rss_session = Client(name='rss_session', api_id=int(TELEGRAM_API), api_hash=TELEGRAM_HASH, session_string=RSS_USER_SESSION_STRING, parse_mode=enums.ParseMode.HTML, no_updates=True)
except:
    RSS_USER_SESSION_STRING = None
    rss_session = None
    
try:
    USER_SESSION_STRING = getConfig('USER_SESSION_STRING')
    if len(USER_SESSION_STRING) == 0:
        raise KeyError

    app_session = Client(name='app_session', api_id=int(TELEGRAM_API), api_hash=TELEGRAM_HASH, session_string=USER_SESSION_STRING, parse_mode=enums.ParseMode.HTML, no_updates=True)
except:
    USER_SESSION_STRING = None
    app_session = None
    
# BUTTONS:

try:
    VIEW_LINK = getConfig('VIEW_LINK')
    VIEW_LINK = VIEW_LINK.lower() == 'true'
except:
    VIEW_LINK = False
try:
    SOURCE_LINK = getConfig('SOURCE_LINK')
    SOURCE_LINK = SOURCE_LINK.lower() == 'true'
except KeyError:
    SOURCE_LINK = False
try:
    DELETE_FILE = getConfig('DELETE_FILE')
    DELETE_FILE = DELETE_FILE.lower() == 'true'
except:
    DELETE_FILE = False
try:
    BUTTON_FIVE_NAME = getConfig('BUTTON_FIVE_NAME')
    BUTTON_FIVE_URL = getConfig('BUTTON_FIVE_URL')
    if len(BUTTON_FIVE_NAME) == 0 or len(BUTTON_FIVE_URL) == 0:
        raise KeyError
except:
    BUTTON_FIVE_NAME = None
    BUTTON_FIVE_URL = None
try:
    BUTTON_SIX_NAME = getConfig('BUTTON_SIX_NAME')
    BUTTON_SIX_URL = getConfig('BUTTON_SIX_URL')
    if len(BUTTON_SIX_NAME) == 0 or len(BUTTON_SIX_URL) == 0:
        raise KeyError
except:
    BUTTON_SIX_NAME = None
    BUTTON_SIX_URL = None


# qBITORRENT:

try:
    BASE_URL = getConfig('BASE_URL_OF_BOT').rstrip("/")
    if len(BASE_URL) == 0:
        raise KeyError
except:
    log_warning('BASE_URL_OF_BOT not provided!')
    BASE_URL = None
try:
    WEB_PINCODE = getConfig('WEB_PINCODE')
    WEB_PINCODE = WEB_PINCODE.lower() == 'true'
except:
    WEB_PINCODE = False
try:
    QB_SEED = getConfig('QB_SEED')
    QB_SEED = QB_SEED.lower() == 'true'
except:
    QB_SEED = False

# SHORTNER:
try:
    SHORTENER = getConfig('SHORTENER')
    SHORTENER_API = getConfig('SHORTENER_API')
    if len(SHORTENER) == 0 or len(SHORTENER_API) == 0:
        raise KeyError
except:
    SHORTENER = None
    SHORTENER_API = None

try:
    AS_DOCUMENT = getConfig('AS_DOCUMENT')
    AS_DOCUMENT = AS_DOCUMENT.lower() == 'true'
except:
    AS_DOCUMENT = False
try:
    EQUAL_SPLITS = getConfig('EQUAL_SPLITS')
    EQUAL_SPLITS = EQUAL_SPLITS.lower() == 'true'
except:
    EQUAL_SPLITS = False
try:
    CUSTOM_FILENAME = getConfig('CUSTOM_FILENAME')
    if len(CUSTOM_FILENAME) == 0:
        raise KeyError
except:
    CUSTOM_FILENAME = None
try:
    CRYPT = getConfig('CRYPT')
    if len(CRYPT) == 0:
        raise KeyError
except:
    CRYPT = None

# TELEGRAPH UI:

try:
    TITLE_NAME = getConfig('TITLE_NAME')
    if len(TITLE_NAME) == 0:
        TITLE_NAME = 'Radioactive-Mirror-Search'
except KeyError:
    TITLE_NAME = 'Radioactive-Mirror-Search'
try:
    AUTHOR_NAME = getConfig('AUTHOR_NAME')
    if len(AUTHOR_NAME) == 0:
        AUTHOR_NAME = 'Arsh Sisodiya'
except KeyError:
    AUTHOR_NAME = 'Arsh Sisodiya'

try:
    AUTHOR_URL = getConfig('AUTHOR_URL')
    if len(AUTHOR_URL) == 0:
        AUTHOR_URL = 'https://t.me/The_Positive_Viewer'
except KeyError:
    AUTHOR_URL = 'https://t.me/The_Positive_Viewer'

try:
    GD_INFO = getConfig('GD_INFO')
    if len(GD_INFO) == 0:
        GD_INFO = 'Uploaded by Radioactive Bot'
except KeyError:
    GD_INFO = 'Uploaded by Radioactive Bot'

# APP DRIVE:
try:
    APPDRIVE_EMAIL = getConfig('APPDRIVE_EMAIL')
    APPDRIVE_PASS = getConfig('APPDRIVE_PASS')
    if len(APPDRIVE_EMAIL) == 0 or len(APPDRIVE_PASS) == 0:
        raise KeyError
except KeyError:
    APPDRIVE_EMAIL = None
    APPDRIVE_PASS = None
     
try:
    HEROKU_API_KEY = getConfig('HEROKU_API_KEY')
    HEROKU_APP_NAME = getConfig('HEROKU_APP_NAME')
    if len(HEROKU_API_KEY) == 0 or len(HEROKU_APP_NAME) == 0:
        raise KeyError
except KeyError:
    LOGGER.warning("Heroku details not entered.")
    HEROKU_API_KEY = None
    HEROKU_APP_NAME = None

# PRIVATE FILES:
   
try:
    ACCOUNTS_ZIP_URL = getConfig('ACCOUNTS_ZIP_URL')
    if len(ACCOUNTS_ZIP_URL) == 0:
        raise KeyError
    try:
        res = rget(ACCOUNTS_ZIP_URL)
        if res.status_code == 200:
            with open('accounts.zip', 'wb+') as f:
                f.write(res.content)
        else:
            log_error(f"Failed to download accounts.zip, link got HTTP response: {res.status_code}")
    except Exception as e:
        log_error(f"ACCOUNTS_ZIP_URL: {e}")
        raise KeyError
    srun(["unzip", "-q", "-o", "accounts.zip"])
    srun(["chmod", "-R", "777", "accounts"])
    osremove("accounts.zip")
except:
    pass
try:
    TOKEN_PICKLE_URL = getConfig('TOKEN_PICKLE_URL')
    if len(TOKEN_PICKLE_URL) == 0:
        raise KeyError
    try:
        res = rget(TOKEN_PICKLE_URL)
        if res.status_code == 200:
            with open('token.pickle', 'wb+') as f:
                f.write(res.content)
        else:
            log_error(f"Failed to download token.pickle, link got HTTP response: {res.status_code}")
    except Exception as e:
        log_error(f"TOKEN_PICKLE_URL: {e}")
except:
    pass
try:
    MULTI_SEARCH_URL = getConfig('MULTI_SEARCH_URL')
    if len(MULTI_SEARCH_URL) == 0:
        raise KeyError
    try:
        res = rget(MULTI_SEARCH_URL)
        if res.status_code == 200:
            with open('drive_folder', 'wb+') as f:
                f.write(res.content)
        else:
            log_error(f"Failed to download drive_folder, link got HTTP response: {res.status_code}")
    except Exception as e:
        log_error(f"MULTI_SEARCH_URL: {e}")
except:
    pass
try:
    YT_COOKIES_URL = getConfig('YT_COOKIES_URL')
    if len(YT_COOKIES_URL) == 0:
        raise KeyError
    try:
        res = rget(YT_COOKIES_URL)
        if res.status_code == 200:
            with open('cookies.txt', 'wb+') as f:
                f.write(res.content)
        else:
            log_error(f"Failed to download cookies.txt, link got HTTP response: {res.status_code}")
    except Exception as e:
        log_error(f"YT_COOKIES_URL: {e}")
except:
    pass
try:
    NETRC_URL = getConfig('NETRC_URL')
    if len(NETRC_URL) == 0:
        raise KeyError
    try:
        res = rget(NETRC_URL)
        if res.status_code == 200:
            with open('.netrc', 'wb+') as f:
                f.write(res.content)
        else:
            log_error(f"Failed to download .netrc {res.status_code}")
    except Exception as e:
        log_error(f"NETRC_URL: {e}")
except:
    pass

DRIVES_NAMES.append("Main")
DRIVES_IDS.append(parent_id)
if ospath.exists('drive_folder'):
    with open('drive_folder', 'r+') as f:
        lines = f.readlines()
        for line in lines:
            try:
                temp = line.strip().split()
                DRIVES_IDS.append(temp[1])
                DRIVES_NAMES.append(temp[0].replace("_", " "))
            except:
                pass
            try:
                INDEX_URLS.append(temp[2])
            except:
                INDEX_URLS.append(None)
try:
    SEARCH_PLUGINS = getConfig('SEARCH_PLUGINS')
    if len(SEARCH_PLUGINS) == 0:
        raise KeyError
    SEARCH_PLUGINS = jsnloads(SEARCH_PLUGINS)
except:
    SEARCH_PLUGINS = None

updater = tgUpdater(token=BOT_TOKEN, request_kwargs={'read_timeout': 20, 'connect_timeout': 15})
bot = updater.bot
dispatcher = updater.dispatcher
job_queue = updater.job_queue
botname = bot.username
