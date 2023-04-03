from re import match
from time import sleep, time
from os import remove, path as ospath
from bot import aria2, download_dict_lock, download_dict, LOGGER, config_dict, user_data, aria2_options, aria2c_global, OWNER_ID
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.ext_utils.bot_utils import is_magnet, getDownloadByGid, new_thread, bt_selection_buttons, get_readable_file_size, is_sudo, is_paid, getdailytasks, userlistype
from bot.helper.mirror_utils.status_utils.aria_download_status import AriaDownloadStatus
from bot.helper.telegram_helper.message_utils import sendStatusMessage, sendMessage, deleteMessage, update_all_messages, sendFile
from bot.helper.ext_utils.fs_utils import get_base_name, check_storage_threshold, clean_unwanted
from bot.modules.scraper import indexScrape

@new_thread
def __onDownloadStarted(api, gid):
    download = api.get_download(gid)
    if download.is_metadata:
        LOGGER.info(f'onDownloadStarted: {gid} METADATA')
        sleep(1)
        if dl := getDownloadByGid(gid):
            listener = dl.listener()
            if listener.select:
                metamsg = "Downloading Metadata, wait then you can select files. Use torrent file to avoid this wait."
                meta = sendMessage(metamsg, listener.bot, listener.message)
                while True:
                    if download.is_removed or download.followed_by_ids:
                        deleteMessage(listener.bot, meta)
                        break
                    download = download.live
    else:
        LOGGER.info(f'onDownloadStarted: {download.name} - Gid: {gid}')
    try:
        STOP_DUPLICATE = config_dict['STOP_DUPLICATE']
        TORRENT_DIRECT_LIMIT = config_dict['TORRENT_DIRECT_LIMIT']
        ZIP_UNZIP_LIMIT = config_dict['ZIP_UNZIP_LIMIT']
        LEECH_LIMIT = config_dict['LEECH_LIMIT']
        STORAGE_THRESHOLD = config_dict['STORAGE_THRESHOLD']
        DAILY_MIRROR_LIMIT = config_dict['DAILY_MIRROR_LIMIT'] * 1024**3 if config_dict['DAILY_MIRROR_LIMIT'] else config_dict['DAILY_MIRROR_LIMIT']
        DAILY_LEECH_LIMIT = config_dict['DAILY_LEECH_LIMIT'] * 1024**3 if config_dict['DAILY_LEECH_LIMIT'] else config_dict['DAILY_LEECH_LIMIT']
        if any([STOP_DUPLICATE, TORRENT_DIRECT_LIMIT, ZIP_UNZIP_LIMIT, LEECH_LIMIT, STORAGE_THRESHOLD, DAILY_MIRROR_LIMIT, DAILY_LEECH_LIMIT]):
            sleep(1)
            if dl := getDownloadByGid(gid):
                listener = dl.listener()
                if listener.select:
                    return
                download = api.get_download(gid)
                if not download.is_torrent:
                    sleep(3)
                    download = download.live
            user_id = listener.message.from_user.id
            user_dict = user_data.get(user_id, False)
            IS_USRTD = user_data[user_id].get('is_usertd') if user_dict and user_dict.get('is_usertd') else False
            if STOP_DUPLICATE and not dl.listener().isLeech and IS_USRTD == False:
                LOGGER.info('Checking File/Folder if already in Drive...')
                sname = download.name
                if listener.isZip:
                    sname = f"{sname}.zip"
                elif listener.extract:
                    try:
                        sname = get_base_name(sname)
                    except:
                        sname = None
                if sname is not None:
                    smsg, button = GoogleDriveHelper(user_id=user_id).drive_list(sname, True)
                    if smsg:
                        listener.onDownloadError("File/Folder is already available in Drive.")
                        api.remove([download], force=True, files=True)
                        tegr, html, tgdi = userlistype(user_id)
                        if html:
                            return sendFile(listener.bot, listener.message, button, f"Here are the search results:\n\n{smsg}")
                        elif tegr:
                            return sendMessage("Here are the search results:", listener.bot, listener.message, button)
                        else: return sendMessage(smsg, listener.bot, listener.message, button)
            size = download.total_length          
            if any([ZIP_UNZIP_LIMIT, LEECH_LIMIT, TORRENT_DIRECT_LIMIT, STORAGE_THRESHOLD]) and user_id != OWNER_ID and not is_sudo(user_id) and not is_paid(user_id):
                sleep(1)
                limit = None
                arch = any([listener.isZip, listener.isLeech, listener.extract])
                if STORAGE_THRESHOLD:
                    acpt = check_storage_threshold(size, arch, True)
                    if not acpt:
                        msg = f'You must leave {STORAGE_THRESHOLD}GB free storage.'
                        msg += f'\nYour File/Folder size is {get_readable_file_size(size)}'
                        if config_dict['PAID_SERVICE'] is True:
                            msg += f'\n#Buy Paid Service'
                        listener.onDownloadError(msg)
                        return api.remove([download], force=True, files=True)
                elif ZIP_UNZIP_LIMIT and arch:
                    mssg = f'Zip/Unzip limit is {ZIP_UNZIP_LIMIT}GB'
                    limit = ZIP_UNZIP_LIMIT
                elif LEECH_LIMIT and arch:
                    mssg = f'Leech limit is {LEECH_LIMIT}GB'
                    limit = LEECH_LIMIT
                elif TORRENT_DIRECT_LIMIT:
                    mssg = f'Torrent/Direct limit is {TORRENT_DIRECT_LIMIT}GB'
                    limit = TORRENT_DIRECT_LIMIT
                if config_dict['PAID_SERVICE'] is True:
                    mssg += f'\n#Buy Paid Service'
                if limit:
                    LOGGER.info('Checking File/Folder Size...')
                    if size > limit * 1024**3:
                        listener.onDownloadError(f'{mssg}.\nYour File/Folder size is {get_readable_file_size(size)}')
                        return api.remove([download], force=True, files=True)
            if DAILY_MIRROR_LIMIT and not listener.isLeech and user_id != OWNER_ID and not is_sudo(user_id) and not is_paid(user_id) and (size >= (DAILY_MIRROR_LIMIT - getdailytasks(user_id, check_mirror=True)) or DAILY_MIRROR_LIMIT <= getdailytasks(user_id, check_mirror=True)):
                mssg = f"Daily Mirror Limit is {get_readable_file_size(DAILY_MIRROR_LIMIT)}\nYou have exhausted Today's Mirror Limit or Size of your Mirror is greater than free Limits.\n#TRY_AGAIN_TOMORROW #Daily_Mirror_Limit"
                if config_dict['PAID_SERVICE'] is True:
                    mssg += f'\n#Buy Paid Service'
                listener.onDownloadError(mssg)
                return api.remove([download], force=True, files=True)
            elif not listener.isLeech: msize = getdailytasks(user_id, upmirror=size, check_mirror=True); LOGGER.info(f"User : {user_id} | Daily Mirror Size : {get_readable_file_size(msize)}")
            if DAILY_LEECH_LIMIT and listener.isLeech and user_id != OWNER_ID and not is_sudo(user_id) and not is_paid(user_id) and (size >= (DAILY_LEECH_LIMIT - getdailytasks(user_id, check_leech=True)) or DAILY_LEECH_LIMIT <= getdailytasks(user_id, check_leech=True)):
                mssg = f"Daily Leech Limit is {get_readable_file_size(DAILY_LEECH_LIMIT)}\nYou have exhausted Today's Leech Limit or Size of your Leech is greater than free Limits.\n#TRY_AGAIN_TOMORROW #Daily_Leech_Limit"
                if config_dict['PAID_SERVICE'] is True:
                    mssg += f'\n#Buy Paid Service'
                listener.onDownloadError(mssg)
                return api.remove([download], force=True, files=True)
            elif listener.isLeech: lsize = getdailytasks(user_id, upleech=size, check_leech=True); LOGGER.info(f"User : {user_id} | Daily Leech Size : {get_readable_file_size(lsize)}")

    except Exception as e:
        LOGGER.error(f"{e} onDownloadStart: {gid} stop duplicate and size check didn't pass")

@new_thread
def __onDownloadComplete(api, gid):
    try:
        download = api.get_download(gid)
    except:
        return
    if download.followed_by_ids:
        new_gid = download.followed_by_ids[0]
        LOGGER.info(f'Gid changed from {gid} to {new_gid}')
        if dl := getDownloadByGid(new_gid):
            listener = dl.listener()
            if config_dict['BASE_URL'] and listener.select:
                api.client.force_pause(new_gid)
                SBUTTONS = bt_selection_buttons(new_gid)
                msg = "Your download paused. Choose files then press Done Selecting button to start downloading."
                sendMessage(msg, listener.bot, listener.message, SBUTTONS)
    elif download.is_torrent:
        if dl := getDownloadByGid(gid):
            if hasattr(dl, 'listener') and dl.seeding:
                LOGGER.info(f"Cancelling Seed: {download.name} onDownloadComplete")
                dl.listener().onUploadError(f"Seeding stopped with Ratio: {dl.ratio()} and Time: {dl.seeding_time()}")
                api.remove([download], force=True, files=True)
    else:
        LOGGER.info(f"onDownloadComplete: {download.name} - Gid: {gid}")
        if dl := getDownloadByGid(gid):
            dl.listener().onDownloadComplete()
            api.remove([download], force=True, files=True)


@new_thread
def __onBtDownloadComplete(api, gid):
    seed_start_time = time()
    sleep(1)
    download = api.get_download(gid)
    LOGGER.info(f"onBtDownloadComplete: {download.name} - Gid: {gid}")
    if dl := getDownloadByGid(gid):
        listener = dl.listener()
        if listener.select:
            res = download.files
            for file_o in res:
                f_path = file_o.path
                if not file_o.selected and ospath.exists(f_path):
                    try:
                        remove(f_path)
                    except:
                        pass
            clean_unwanted(download.dir)
        if listener.seed:
            try:
                api.set_options({'max-upload-limit': '0'}, [download])
            except Exception as e:
                LOGGER.error(f'{e} You are not able to seed because you added global option seed-time=0 without adding specific seed_time for this torrent GID: {gid}')
        else:
            try:
                api.client.force_pause(gid)
            except Exception as e:
                LOGGER.error(f"{e} GID: {gid}" )
        listener.onDownloadComplete()
        download = download.live
        if listener.seed:
            if download.is_complete:
                if dl := getDownloadByGid(gid):
                    LOGGER.info(f"Cancelling Seed: {download.name}")
                    listener.onUploadError(f"Seeding stopped with Ratio: {dl.ratio()} and Time: {dl.seeding_time()}")
                    api.remove([download], force=True, files=True)
            else:
                with download_dict_lock:
                    if listener.uid not in download_dict:
                        api.remove([download], force=True, files=True)
                        return
                    download_dict[listener.uid] = AriaDownloadStatus(gid, listener, True)
                    download_dict[listener.uid].start_time = seed_start_time
                LOGGER.info(f"Seeding started: {download.name} - Gid: {gid}")
                update_all_messages()
        else:
            api.remove([download], force=True, files=True)

@new_thread
def __onDownloadStopped(api, gid):
    sleep(6)
    if dl := getDownloadByGid(gid):
        dl.listener().onDownloadError('Dead torrent!')

@new_thread
def __onDownloadError(api, gid):
    LOGGER.info(f"onDownloadError: {gid}")
    error = "None"
    try:
        download = api.get_download(gid)
        error = download.error_message
        LOGGER.info(f"Download Error: {error}")
    except:
        pass
    if dl := getDownloadByGid(gid):
        dl.listener().onDownloadError(error)

def start_listener():
    aria2.listen_to_notifications(threaded=True,
                                  on_download_start=__onDownloadStarted,
                                  on_download_error=__onDownloadError,
                                  on_download_stop=__onDownloadStopped,
                                  on_download_complete=__onDownloadComplete,
                                  on_bt_download_complete=__onBtDownloadComplete,
                                  timeout=60)

def add_aria2c_download(link: str, path, listener, filename, auth, ratio, seed_time):
    args = {'dir': path, 'max-upload-limit': '1K', 'netrc-path': '/usr/src/app/.netrc'}
    a2c_opt = {**aria2_options}
    [a2c_opt.pop(k) for k in aria2c_global if k in aria2_options]
    args.update(a2c_opt)
    if filename:
        args['out'] = filename
    if auth:
        args['header'] = f"authorization: {auth}"
    if ratio:
        args['seed-ratio'] = ratio
    if seed_time:
        args['seed-time'] = seed_time
    if TORRENT_TIMEOUT := config_dict['TORRENT_TIMEOUT']:
        args['bt-stop-timeout'] = str(TORRENT_TIMEOUT)
    if is_magnet(link):
        download = aria2.add_magnet(link, args)
    elif match(r'https?://.+\/\d+\:\/', link) and link[-1] == '/':
        links, error = indexScrape({"page_token": "", "page_index": 0}, link, auth, folder_mode=True)
        if error:
            LOGGER.info(f"Download Error: {links}")
            return sendMessage(links, listener.bot, listener.message)
        dls = []
        for link in links:
            dls.append(aria2.add_uris([link], args))
        LOGGER.info(dls)
        download = dls[0]
    else:
        download = aria2.add_uris([link], args)
    if download.error_message:
        error = str(download.error_message).replace('<', ' ').replace('>', ' ')
        LOGGER.info(f"Download Error: {error}")
        return sendMessage(error, listener.bot, listener.message)
    with download_dict_lock:
        download_dict[listener.uid] = AriaDownloadStatus(download.gid, listener)
        LOGGER.info(f"Aria2Download started: {download.gid}")
    listener.onDownloadStart()
    if not listener.select:
        sendStatusMessage(listener.message, listener.bot)

start_listener()
