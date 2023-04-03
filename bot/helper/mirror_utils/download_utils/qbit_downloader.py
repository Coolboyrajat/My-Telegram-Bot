from hashlib import sha1
from base64 import b16encode, b32decode
from bencoding import bencode, bdecode
from time import sleep, time
from re import search as re_search
from os import remove
from time import sleep, time
from re import search as re_search
from threading import Lock, Thread

from bot import download_dict, download_dict_lock, get_client, config_dict, QbInterval, user_data, LOGGER, OWNER_ID
from bot.helper.mirror_utils.status_utils.qbit_download_status import QbDownloadStatus
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.telegram_helper.message_utils import sendMessage, deleteMessage, sendStatusMessage, update_all_messages, sendFile
from bot.helper.ext_utils.bot_utils import get_readable_file_size, get_readable_time, setInterval, bt_selection_buttons, getDownloadByGid, new_thread, is_sudo, is_paid, getdailytasks, userlistype
from bot.helper.ext_utils.fs_utils import clean_unwanted, get_base_name, check_storage_threshold

qb_download_lock = Lock()
STALLED_TIME = {}
STOP_DUP_CHECK = set()
LIMITS_CHECK = set()
RECHECKED = set()
UPLOADED = set()
SEEDING = set()

def __get_hash_magnet(mgt: str):
    hash_ = re_search(r'(?<=xt=urn:btih:)[a-zA-Z0-9]+', mgt).group(0)
    if len(hash_) == 32:
        hash_ = b16encode(b32decode(hash_.upper())).decode()
    return str(hash_)

def __get_hash_file(path):
    with open(path, "rb") as f:
        decodedDict = bdecode(f.read())
        hash_ = sha1(bencode(decodedDict[b'info'])).hexdigest()
    return str(hash_)

def add_qb_torrent(link, path, listener, ratio, seed_time):
    client = get_client()
    ADD_TIME = time()
    try:
        if link.startswith('magnet:'):
            ext_hash = __get_hash_magnet(link)
        else:
            ext_hash = __get_hash_file(link)
        if ext_hash is None or len(ext_hash) < 30:
            sendMessage("Not a torrent! Qbittorrent only for torrents!", listener.bot, listener.message)
            return
        tor_info = client.torrents_info(torrent_hashes=ext_hash)
        if len(tor_info) > 0:
            sendMessage("This Torrent already added!", listener.bot, listener.message)
            return
        if link.startswith('magnet:'):
            op = client.torrents_add(link, save_path=path, ratio_limit=ratio, seeding_time_limit=seed_time)
        else:
            op = client.torrents_add(torrent_files=[link], save_path=path, ratio_limit=ratio, seeding_time_limit=seed_time)
        sleep(0.3)
        if op.lower() == "ok.":
            tor_info = client.torrents_info(torrent_hashes=ext_hash)
            if len(tor_info) == 0:
                while True:
                    tor_info = client.torrents_info(torrent_hashes=ext_hash)
                    if len(tor_info) > 0:
                        break
                    elif time() - ADD_TIME >= 60:
                        msg = "Not added, maybe it will took time and u should remove it manually using eval!"
                        sendMessage(msg, listener.bot, listener.message)
                        __remove_torrent(client, ext_hash)
                        return
        else:
            sendMessage("This is an unsupported/invalid link.", listener.bot, listener.message)
            __remove_torrent(client, ext_hash)
            return
        tor_info = tor_info[0]
        ext_hash = tor_info.hash
        with download_dict_lock:
            download_dict[listener.uid] = QbDownloadStatus(listener, ext_hash)
            LOGGER.info(download_dict)
        with qb_download_lock:
            STALLED_TIME[ext_hash] = time()
            if not QbInterval:
                periodic = setInterval(5, __qb_listener)
                QbInterval.append(periodic)
        listener.onDownloadStart()
        LOGGER.info(f"QbitDownload started: {tor_info.name} - Hash: {ext_hash}")
        if config_dict['BASE_URL'] and listener.select:
            if link.startswith('magnet:'):
                metamsg = "Downloading Metadata, wait then you can select files. Use torrent file to avoid this wait."
                meta = sendMessage(metamsg, listener.bot, listener.message)
                while True:
                    tor_info = client.torrents_info(torrent_hashes=ext_hash)
                    if len(tor_info) == 0:
                        deleteMessage(listener.bot, meta)
                        return
                    try:
                        tor_info = tor_info[0]
                        if tor_info.state not in ["metaDL", "checkingResumeData", "pausedDL"]:
                            deleteMessage(listener.bot, meta)
                            break
                    except:
                        return deleteMessage(listener.bot, meta)
            client.torrents_pause(torrent_hashes=ext_hash)
            SBUTTONS = bt_selection_buttons(ext_hash)
            msg = "Your download paused. Choose files then press Done Selecting button to start downloading."
            sendMessage(msg, listener.bot, listener.message, SBUTTONS)
        else:
            sendStatusMessage(listener.message, listener.bot)
    except Exception as e:
        sendMessage(str(e), listener.bot, listener.message)
    finally:
        if not link.startswith('magnet:'):
            remove(link)
        client.auth_log_out()

def __remove_torrent(client, hash_):
    client.torrents_delete(torrent_hashes=hash_, delete_files=True)
    with qb_download_lock:
        if hash_ in STALLED_TIME:
            del STALLED_TIME[hash_]
        if hash_ in STOP_DUP_CHECK:
            STOP_DUP_CHECK.remove(hash_)
        if hash_ in RECHECKED:
            RECHECKED.remove(hash_)
        if hash_ in UPLOADED:
            UPLOADED.remove(hash_)
        if hash_ in SEEDING:
            SEEDING.remove(hash_)

def __onDownloadError(err, client, tor):
    LOGGER.info(f"Cancelling Download: {tor.name}")
    client.torrents_pause(torrent_hashes=tor.hash)
    sleep(0.3)
    download = getDownloadByGid(tor.hash[:12])
    try:
        listener = download.listener()
        listener.onDownloadError(err)
    except:
        pass
    __remove_torrent(client, tor.hash)

@new_thread
def __onSeedFinish(client, tor):
    LOGGER.info(f"Cancelling Seed: {tor.name}")
    download = getDownloadByGid(tor.hash[:12])
    try:
        listener = download.listener()
        listener.onUploadError(f"Seeding stopped with Ratio: {round(tor.ratio, 3)} and Time: {get_readable_time(tor.seeding_time)}")
    except:
        pass
    __remove_torrent(client, tor.hash)

@new_thread
def __stop_duplicate(client, tor):
    download = getDownloadByGid(tor.hash[:12])
    try:
        listener = download.listener()
        user_id = listener.message.from_user.id
        user_dict = user_data.get(user_id, False)
        IS_USRTD = user_dict.get('is_usertd') if user_dict and user_dict.get('is_usertd') else False
        if not listener.select and not listener.isLeech and IS_USRTD == False:
            LOGGER.info('Checking File/Folder if already in Drive')
            qbname = tor.content_path.rsplit('/', 1)[-1].rsplit('.!qB', 1)[0]
            if listener.isZip:
                qbname = f"{qbname}.zip"
            elif listener.extract:
                try:
                    qbname = get_base_name(qbname)
                except:
                    qbname = None
            if qbname is not None:
                qbmsg, button = GoogleDriveHelper(user_id=user_id).drive_list(qbname, True)
                if qbmsg:
                    __onDownloadError("File/Folder is already available in Drive.", client, tor)
                    tegr, html, tgdi = userlistype(user_id)
                    if tegr:
                        sendMessage("Here are the search results:", listener.bot, listener.message, button)
                    elif html:
                        sendFile(listener.bot, listener.message, button, f"Here are the search results:\n\n{qbmsg}")
                    else:
                        sendMessage(qbmsg, listener.bot, listener.message, button)
                    return
    except:
        pass

@new_thread
def __check_limits(client, tor):
    download = getDownloadByGid(tor.hash[:12])
    listener = download.listener()
    size = tor.size
    arch = any([listener.isZip, listener.extract])
    user_id = listener.message.from_user.id
    TORRENT_DIRECT_LIMIT = config_dict['TORRENT_DIRECT_LIMIT']
    ZIP_UNZIP_LIMIT = config_dict['ZIP_UNZIP_LIMIT']
    LEECH_LIMIT = config_dict['LEECH_LIMIT']
    STORAGE_THRESHOLD = config_dict['STORAGE_THRESHOLD']
    if any([ZIP_UNZIP_LIMIT, LEECH_LIMIT, TORRENT_DIRECT_LIMIT, STORAGE_THRESHOLD]) and user_id != OWNER_ID and not is_sudo(user_id) and not is_paid(user_id):
        if STORAGE_THRESHOLD is not None:
            acpt = check_storage_threshold(size, arch)
            if not acpt:
                msg = f'You must leave {STORAGE_THRESHOLD}GB free storage.'
                msg += f'\nYour File/Folder size is {get_readable_file_size(size)}'
                if config_dict['PAID_SERVICE'] is True:
                    msg += f'\n#Buy Paid Service'
                __onDownloadError(msg, client, tor)
                return
                limit = None
        if ZIP_UNZIP_LIMIT and arch:
            mssg = f'Zip/Unzip limit is {ZIP_UNZIP_LIMIT}GB'
            limit = ZIP_UNZIP_LIMIT
        if LEECH_LIMIT and listener.isLeech:
            mssg = f'Leech limit is {LEECH_LIMIT}GB'
            limit = LEECH_LIMIT
        elif TORRENT_DIRECT_LIMIT is not None:
            mssg = f'Torrent limit is {TORRENT_DIRECT_LIMIT}GB'
            limit = TORRENT_DIRECT_LIMIT
        if config_dict['PAID_SERVICE'] is True:
            mssg += f'\n#Buy Paid Service'
        if limit is not None:
            LOGGER.info('Checking File/Folder Size...')
            if size > limit * 1024**3:
                fmsg = f"{mssg}.\nYour File/Folder size is {get_readable_file_size(size)}"
                __onDownloadError(fmsg, client, tor)
    DAILY_MIRROR_LIMIT = config_dict['DAILY_MIRROR_LIMIT'] * 1024**3 if config_dict['DAILY_MIRROR_LIMIT'] else config_dict['DAILY_MIRROR_LIMIT']
    DAILY_LEECH_LIMIT = config_dict['DAILY_LEECH_LIMIT'] * 1024**3 if config_dict['DAILY_LEECH_LIMIT'] else config_dict['DAILY_LEECH_LIMIT']
    if DAILY_MIRROR_LIMIT and not listener.isLeech and user_id != OWNER_ID and not is_sudo(user_id) and not is_paid(user_id) and (size >= (DAILY_MIRROR_LIMIT - getdailytasks(user_id, check_mirror=True)) or DAILY_MIRROR_LIMIT <= getdailytasks(user_id, check_mirror=True)):
        mssg = f"Daily Mirror Limit is {get_readable_file_size(DAILY_MIRROR_LIMIT)}\nYou have exhausted Today's Mirror Limit or Size of your Mirror is greater than free Limits.\n#TRY_AGAIN_TOMORROW #Daily_Mirror_Limit"
        if config_dict['PAID_SERVICE'] is True:
            mssg += f'\n#Buy Paid Service'
        __onDownloadError(mssg, client, tor)
    elif not listener.isLeech: msize = getdailytasks(user_id, upmirror=size, check_mirror=True); LOGGER.info(f"User : {user_id} | Daily Mirror Size : {get_readable_file_size(msize)}")
    if DAILY_LEECH_LIMIT and listener.isLeech and user_id != OWNER_ID and not is_sudo(user_id) and not is_paid(user_id) and (size >= (DAILY_LEECH_LIMIT - getdailytasks(user_id, check_leech=True)) or DAILY_LEECH_LIMIT <= getdailytasks(user_id, check_leech=True)):
        mssg = f"Daily Leech Limit is {get_readable_file_size(DAILY_LEECH_LIMIT)}\nYou have exhausted Today's Leech Limit or Size of your Leech is greater than free Limits.\n#TRY_AGAIN_TOMORROW #Daily_Leech_Limit"
        if config_dict['PAID_SERVICE'] is True:
            mssg += f'\n#Buy Paid Service'
        __onDownloadError(mssg, client, tor)
    elif listener.isLeech: lsize = getdailytasks(user_id, upleech=size, check_leech=True); LOGGER.info(f"User : {user_id} | Daily Leech Size : {get_readable_file_size(lsize)}")

@new_thread
def __onDownloadComplete(client, tor):
    download = getDownloadByGid(tor.hash[:12])
    try:
        listener = download.listener()
    except:
        return
    if not listener.seed:
        client.torrents_pause(torrent_hashes=tor.hash)
    if listener.select:
        clean_unwanted(listener.dir)
    listener.onDownloadComplete()
    if listener.seed:
        with download_dict_lock:
            if listener.uid in download_dict:
                removed = False
                download_dict[listener.uid] = QbDownloadStatus(listener, tor.hash, True)
            else:
                removed = True
        if removed:
            __remove_torrent(client, tor.hash)
            return
        with qb_download_lock:
            SEEDING.add(tor.hash)
        update_all_messages()
        LOGGER.info(f"Seeding started: {tor.name} - Hash: {tor.hash}")
    else:
        __remove_torrent(client, tor.hash)

def __qb_listener():
    client = get_client()
    with qb_download_lock:
        if len(client.torrents_info()) == 0:
            QbInterval[0].cancel()
            QbInterval.clear()
            return
        try:
            for tor_info in client.torrents_info():
                if tor_info.state == "metaDL":
                    TORRENT_TIMEOUT = config_dict['TORRENT_TIMEOUT']
                    STALLED_TIME[tor_info.hash] = time()
                    if TORRENT_TIMEOUT and time() - tor_info.added_on >= TORRENT_TIMEOUT:
                        Thread(target=__onDownloadError, args=("Dead Torrent!", client, tor_info)).start()
                    else:
                        client.torrents_reannounce(torrent_hashes=tor_info.hash)
                elif tor_info.state == "downloading":
                    STALLED_TIME[tor_info.hash] = time()
                    if config_dict['STOP_DUPLICATE'] and tor_info.hash not in STOP_DUP_CHECK:
                        STOP_DUP_CHECK.add(tor_info.hash)
                        __stop_duplicate(client, tor_info)
                    if (config_dict['TORRENT_DIRECT_LIMIT'] or config_dict['ZIP_UNZIP_LIMIT'] or config_dict['LEECH_LIMIT'] or config_dict['STORAGE_THRESHOLD'] or config_dict['DAILY_MIRROR_LIMIT'] or config_dict['DAILY_LEECH_LIMIT']) and tor_info.hash not in LIMITS_CHECK:
                        LIMITS_CHECK.add(tor_info.hash)
                        __check_limits(client, tor_info)
                elif tor_info.state == "stalledDL":
                    TORRENT_TIMEOUT = config_dict['TORRENT_TIMEOUT']
                    if tor_info.hash not in RECHECKED and 0.99989999999999999 < tor_info.progress < 1:
                        msg = f"Force recheck - Name: {tor_info.name} Hash: "
                        msg += f"{tor_info.hash} Downloaded Bytes: {tor_info.downloaded} "
                        msg += f"Size: {tor_info.size} Total Size: {tor_info.total_size}"
                        LOGGER.error(msg)
                        client.torrents_recheck(torrent_hashes=tor_info.hash)
                        RECHECKED.add(tor_info.hash)
                    elif TORRENT_TIMEOUT and time() - STALLED_TIME.get(tor_info.hash, 0) >= TORRENT_TIMEOUT:
                        Thread(target=__onDownloadError, args=("Dead Torrent!", client, tor_info)).start()
                    else:
                        client.torrents_reannounce(torrent_hashes=tor_info.hash)
                elif tor_info.state == "missingFiles":
                    client.torrents_recheck(torrent_hashes=tor_info.hash)
                elif tor_info.state == "error":
                    Thread(target=__onDownloadError, args=("No enough space for this torrent on device", client, tor_info)).start()
                elif tor_info.completion_on != 0 and tor_info.hash not in UPLOADED and \
                      tor_info.state not in ['checkingUP', 'checkingDL', 'checkingResumeData']:
                    UPLOADED.add(tor_info.hash)
                    __onDownloadComplete(client, tor_info)
                elif tor_info.state in ['pausedUP', 'pausedDL'] and tor_info.hash in SEEDING:
                    SEEDING.remove(tor_info.hash)
                    __onSeedFinish(client, tor_info)
        except Exception as e:
            LOGGER.error(str(e))
