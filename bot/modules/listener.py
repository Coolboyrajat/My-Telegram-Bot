from random import choice
from re import search as re_search
from time import sleep, time
from os import path as ospath, remove as osremove, listdir, walk
from subprocess import Popen
from html import escape
from threading import Thread
from requests.utils import quote as rquote
from telegram import ParseMode

from bot.helper.ext_utils.bot_utils import change_filename, get_bot_pm, is_url, is_magnet, get_readable_time, get_readable_file_size, getGDriveUploadUtils
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.ext_utils.exceptions import NotSupportedExtractionArchive
from bot.helper.ext_utils.fs_utils import get_base_name, get_path_size, split_file, clean_download, clean_target
from bot.helper.ext_utils.queued_starter import start_from_queued
from bot.helper.ext_utils.shortenurl import short_url
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.mirror_utils.status_utils.zip_status import ZipStatus
from bot.helper.mirror_utils.status_utils.split_status import SplitStatus
from bot.helper.mirror_utils.status_utils.upload_status import UploadStatus
from bot.helper.mirror_utils.status_utils.tg_upload_status import TgUploadStatus
from bot.helper.mirror_utils.status_utils.queue_status import QueueStatus
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.mirror_utils.upload_utils.pyrogramEngine import TgUploader
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import sendMessage, delete_all_messages, update_all_messages, auto_delete_upload_message, sendPhoto
from bot import aria2, bot, DOWNLOAD_DIR, LOGGER, Interval, config_dict, user_data, DATABASE_URL, download_dict_lock, download_dict, \
                queue_dict_lock, non_queued_dl, non_queued_up, queued_up, queued_dl, tgBotMaxFileSize, status_reply_dict_lock

class MirrorLeechListener:
    def __init__(self, bot, message, isZip=False, extract=False, isQbit=False, isLeech=False, pswd=None, tag=None, select=False, seed=False, c_index=0, u_index=None):
        self.bot = bot
        self.message = message
        self.uid = message.message_id
        self.extract = extract
        self.isZip = isZip
        self.isQbit = isQbit
        self.isLeech = isLeech
        self.pswd = pswd
        self.tag = tag
        self.seed = seed
        self.newDir = ""
        self.dir = f"{DOWNLOAD_DIR}{self.uid}"
        self.select = select
        self.isPrivate = message.chat.type in ['private', 'group']
        self.__user_settings()
        self.suproc = None
        self.user_id = self.message.from_user.id
        self.reply_to = self.message.reply_to_message
        self.c_index = c_index
        self.u_index = u_index
        self.queuedUp = False

    def clean(self):
        try:
            with status_reply_dict_lock:
                Interval[0].cancel()
                Interval.clear()
            aria2.purge()
            delete_all_messages()
        except:
            pass

    def onDownloadStart(self):
        if not self.isPrivate and config_dict['INCOMPLETE_TASK_NOTIFIER'] and DATABASE_URL:
            DbManger().add_incomplete_task(self.message.chat.id, self.message.link, self.tag)

    def onDownloadComplete(self):
        user_dict = user_data.get(self.message.from_user.id, False)
        with download_dict_lock:
            download = download_dict[self.uid]
            name = str(download.name()).replace('/', '')
            gid = download.gid()
        LOGGER.info(f"Download completed: {name}")
        if name == "None" or self.isQbit or not ospath.exists(f"{self.dir}/{name}"):
            name = listdir(self.dir)[-1]
        m_path = f'{self.dir}/{name}'
        size = get_path_size(m_path)
        with queue_dict_lock:
            if self.uid in non_queued_dl:
                non_queued_dl.remove(self.uid)
        start_from_queued()
        user_dict = user_data.get(self.message.from_user.id, False)
        if self.isZip:
            if self.seed and self.isLeech:
                self.newDir = f"{self.dir}10000"
                path = f"{self.newDir}/{name}.zip"
            else:
                path = f"{m_path}.zip"
            with download_dict_lock:
                download_dict[self.uid] = ZipStatus(name, size, gid, self)
            TG_SPLIT_SIZE = int((user_dict and user_dict.get('split_size')) or config_dict['TG_SPLIT_SIZE'])
            if self.pswd is not None:
                if self.isLeech and int(size) > TG_SPLIT_SIZE:
                    LOGGER.info(f'Zip: orig_path: {m_path}, zip_path: {path}.0*')
                    self.suproc = Popen(["7z", f"-v{TG_SPLIT_SIZE}b", "a", "-mx=0", f"-p{self.pswd}", path, m_path])
                else:
                    LOGGER.info(f'Zip: orig_path: {m_path}, zip_path: {path}')
                    self.suproc = Popen(["7z", "a", "-mx=0", f"-p{self.pswd}", path, m_path])
            elif self.isLeech and int(size) > TG_SPLIT_SIZE:
                LOGGER.info(f'Zip: orig_path: {m_path}, zip_path: {path}.0*')
                self.suproc = Popen(["7z", f"-v{TG_SPLIT_SIZE}b", "a", "-mx=0", path, m_path])
            else:
                LOGGER.info(f'Zip: orig_path: {m_path}, zip_path: {path}')
                self.suproc = Popen(["7z", "a", "-mx=0", path, m_path])
            self.suproc.wait()
            if self.suproc.returncode == -9:
                return
            elif not self.seed:
                clean_target(m_path)
        elif self.extract:
            try:
                if ospath.isfile(m_path):
                    path = get_base_name(m_path)
                LOGGER.info(f"Extracting: {name}")
                with download_dict_lock:
                    download_dict[self.uid] = ExtractStatus(name, size, gid, self)
                if ospath.isdir(m_path):
                    if self.seed:
                        self.newDir = f"{self.dir}10000"
                        path = f"{self.newDir}/{name}"
                    else:
                        path = m_path
                    for dirpath, subdir, files in walk(m_path, topdown=False):
                        for file_ in files:
                            if re_search(r'\.part0*1\.rar$|\.7z\.0*1$|\.zip\.0*1$|\.zip$|\.7z$|^.(?!.*\.part\d+\.rar)(?=.*\.rar$)', file_):
                                f_path = ospath.join(dirpath, file_)
                                t_path = dirpath.replace(self.dir, self.newDir) if self.seed else dirpath
                                if self.pswd is not None:
                                    self.suproc = Popen(["7z", "x", f"-p{self.pswd}", f_path, f"-o{t_path}", "-aot"])
                                else:
                                    self.suproc = Popen(["7z", "x", f_path, f"-o{t_path}", "-aot"])
                                self.suproc.wait()
                                if self.suproc.returncode == -9:
                                    return
                                elif self.suproc.returncode != 0:
                                    LOGGER.error('Unable to extract archive splits!')
                        if not self.seed and self.suproc is not None and self.suproc.returncode == 0:
                            for file_ in files:
                                if re_search(r'\.r\d+$|\.7z\.\d+$|\.z\d+$|\.zip\.\d+$|\.zip$|\.rar$|\.7z$', file_):
                                    del_path = ospath.join(dirpath, file_)
                                    try:
                                        osremove(del_path)
                                    except:
                                        return
                else:
                    if self.seed and self.isLeech:
                        self.newDir = f"{self.dir}10000"
                        path = path.replace(self.dir, self.newDir)
                    if self.pswd is not None:
                        self.suproc = Popen(["7z", "x", f"-p{self.pswd}", m_path, f"-o{path}", "-aot"])
                    else:
                        self.suproc = Popen(["7z", "x", m_path, f"-o{path}", "-aot"])
                    self.suproc.wait()
                    if self.suproc.returncode == -9:
                        return
                    elif self.suproc.returncode == 0:
                        LOGGER.info(f"Extracted Path: {path}")
                        if not self.seed:
                            try:
                                osremove(m_path)
                            except:
                                return
                    else:
                        LOGGER.error('Unable to extract archive! Uploading anyway')
                        self.newDir = ""
                        path = m_path
            except NotSupportedExtractionArchive:
                LOGGER.info("Not any valid archive, uploading file as it is.")
                self.newDir = ""
                path = m_path
        else:
            path = m_path
        up_dir, up_name = path.rsplit('/', 1)
        size = get_path_size(up_dir)
        if self.isLeech:
            m_size = []
            o_files = []
            if not self.isZip:
                checked = False
                TG_SPLIT_SIZE = int((user_dict and user_dict.get('split_size')) or config_dict['TG_SPLIT_SIZE'])
                for dirpath, subdir, files in walk(up_dir, topdown=False):
                    for file_ in files:
                        f_path = ospath.join(dirpath, file_)
                        f_size = ospath.getsize(f_path)
                        if f_size > TG_SPLIT_SIZE:
                            if not checked:
                                checked = True
                                with download_dict_lock:
                                    download_dict[self.uid] = SplitStatus(up_name, size, gid, self)
                                LOGGER.info(f"Splitting: {up_name}")
                            res = split_file(f_path, f_size, file_, dirpath, TG_SPLIT_SIZE, self)
                            if not res:
                                return
                            if res == "errored":
                                if f_size <= tgBotMaxFileSize:
                                    continue
                                try:
                                    osremove(f_path)
                                except:
                                    return
                            elif not self.seed or self.newDir:
                                try:
                                    osremove(f_path)
                                except:
                                    return
                            else:
                                m_size.append(f_size)
                                o_files.append(file_)
        up_limit = config_dict['QUEUE_UPLOAD']
        all_limit = config_dict['QUEUE_ALL']
        added_to_queue = False
        with queue_dict_lock:
            dl = len(non_queued_dl)
            up = len(non_queued_up)
            if (all_limit and dl + up >= all_limit and (not up_limit or up >= up_limit)) or (up_limit and up >= up_limit):
                added_to_queue = True
                LOGGER.info(f"Added to Queue/Upload: {name}")
                queued_up[self.uid] = [self]
        if added_to_queue:
            with download_dict_lock:
                download_dict[self.uid] = QueueStatus(name, size, gid, self, 'Up')
                self.queuedUp = True
            while self.queuedUp:
                sleep(1)
                continue
            with download_dict_lock:
                if self.uid not in download_dict.keys():
                    return
            LOGGER.info(f'Start from Queued/Upload: {name}')
        with queue_dict_lock:
            non_queued_up.add(self.uid)

        if self.isLeech:
            size = get_path_size(up_dir)
            for s in m_size:
                size = size - s
            LOGGER.info(f"Leech Name: {up_name}")
            tg = TgUploader(up_name, up_dir, size, self)
            tg_upload_status = TgUploadStatus(tg, size, gid, self)
            with download_dict_lock:
                download_dict[self.uid] = tg_upload_status
            update_all_messages()
            tg.upload(o_files)
        else:
            up_path = f'{up_dir}/{up_name}'
            size = get_path_size(up_path)
            LOGGER.info(f"Upload Name: {up_name}")
            drive = GoogleDriveHelper(up_name, up_dir, size, self, self.user_id)
            upload_status = UploadStatus(drive, size, gid, self)
            with download_dict_lock:
                download_dict[self.uid] = upload_status
            update_all_messages()
            drive.upload(up_name, self.u_index, self.c_index)


    def onUploadComplete(self, link: str, size, files, folders, typ, name):
        buttons = ButtonMaker()
        mesg = self.message.text.split('\n')
        message_args = mesg[0].split(maxsplit=1)
        reply_to = self.message.reply_to_message
        user_id_ = self.message.from_user.id
        up_path, name, _ = change_filename(name, user_id_, all_edit=False, mirror_type=(False if self.isLeech else True))
        
        BOT_PM_X = get_bot_pm(user_id_)     
        
        NAME_FONT = config_dict['NAME_FONT']
        if config_dict['EMOJI_THEME']:
            slmsg = f"🗂️ Name: <{NAME_FONT}>{escape(name)}</{NAME_FONT}>\n\n"
            slmsg += f"📐 Size: {size}\n"
            slmsg += f"👥 Added by: {self.tag} | <code>{self.user_id}</code>\n\n"
        else:
            slmsg = f"Name: <{NAME_FONT}>{escape(name)}</{NAME_FONT}>\n\n"
            slmsg += f"Size: {size}\n"
            slmsg += f"Added by: {self.tag} | <code>{self.user_id}</code>\n\n"
        if 'link_logs' in user_data:
            try:
                upper = f"‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒\n"
                source_link = f"<code>{message_args[1]}</code>\n"
                lower = f"‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒\n"
                for link_log in user_data['link_logs']:
                    bot.sendMessage(link_log, text=slmsg + upper + source_link + lower, parse_mode=ParseMode.HTML )
            except IndexError:
                pass
            if reply_to is not None:
                try:
                    reply_text = reply_to.text
                    if is_url(reply_text):
                        upper = f"‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒\n"
                        source_link = f"<code>{reply_text.strip()}</code>\n"
                        lower = f"‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒‒\n"
                        for link_log in user_data['link_logs']:
                            bot.sendMessage(chat_id=link_log, text=slmsg + upper + source_link + lower, parse_mode=ParseMode.HTML )
                except TypeError:
                    pass
        AUTO_DELETE_UPLOAD_MESSAGE_DURATION = config_dict['AUTO_DELETE_UPLOAD_MESSAGE_DURATION']
        if AUTO_DELETE_UPLOAD_MESSAGE_DURATION != -1:
            reply_to = self.message.reply_to_message
            if reply_to is not None:
                reply_to.delete()
            auto_delete_message = int(AUTO_DELETE_UPLOAD_MESSAGE_DURATION / 60)
            if self.message.chat.type == 'private':
                warnmsg = ''
            else:
                if config_dict['EMOJI_THEME']:
                    warnmsg = f'<b>❗ This message will be deleted in <i>{auto_delete_message} minutes</i> from this group.</b>\n'
                else:
                    warnmsg = f'<b>This message will be deleted in <i>{auto_delete_message} minutes</i> from this group.</b>\n'
        else:
            warnmsg = ''
        if BOT_PM_X and self.message.chat.type != 'private':
            if config_dict['EMOJI_THEME']:
                pmwarn = f"<b>😉 I have sent files in PM.</b>\n"
            else:
                pmwarn = f"<b>I have sent files in PM.</b>\n"
        elif self.message.chat.type == 'private':
            pmwarn = ''
        else:
            pmwarn = ''
        if 'mirror_logs' in user_data and self.message.chat.type != 'private':
            if config_dict['EMOJI_THEME']:
                logwarn = f"<b>⚠️ I have sent files in Mirror Log Channel. Join <a href=\"{config_dict['MIRROR_LOG_URL']}\">Mirror Log channel</a> </b>\n"
            else:
                logwarn = f"<b>I have sent files in Mirror Log Channel. Join <a href=\"{config_dict['MIRROR_LOG_URL']}\">Mirror Log channel</a> </b>\n"
        elif self.message.chat.type == 'private':
            logwarn = ''
        else:
            logwarn = ''
        if 'is_leech_log' in user_data and self.message.chat.type != 'private':
            if config_dict['EMOJI_THEME']:
                logleechwarn = f"<b>⚠️ I have sent files in Leech Log Channel. Join <a href=\"{config_dict['LEECH_LOG_URL']}\">Leech Log channel</a> </b>\n"
            else:
                logleechwarn = f"<b>I have sent files in Leech Log Channel. Join <a href=\"{config_dict['LEECH_LOG_URL']}\">Leech Log channel</a> </b>\n"
        elif self.message.chat.type == 'private':
            logleechwarn = ''
        else:
            logleechwarn = ''
        if not self.isPrivate and config_dict['INCOMPLETE_TASK_NOTIFIER'] and DATABASE_URL is not None:
            DbManger().rm_complete_task(self.message.link)




        if config_dict['EMOJI_THEME']:
            msg = f"<b>╭🗂️ Name: </b><{config_dict['NAME_FONT']}>{escape(name)}</{config_dict['NAME_FONT']}>\n<b>├📐 Size: </b>{size}"
        else:
            msg = f"<b>╭ Name: </b><{config_dict['NAME_FONT']}>{escape(name)}</{config_dict['NAME_FONT']}>\n<b>├ Size: </b>{size}"

        if self.isLeech:
            if config_dict['SOURCE_LINK']:
                try:
                    mesg = message_args[1]
                    if is_magnet(mesg):
                        link = telegraph.create_page(
                            title=f"{config_dict['TITLE_NAME']} Source Link",
                            content=mesg,
                        )["path"]
                        buttons.buildbutton(f"🔗 Source Link", f"https://telegra.ph/{link}")
                    elif is_url(mesg):
                        source_link = mesg
                        if source_link.startswith(("|", "pswd: ", "c:")):
                            pass
                        else:
                            buttons.buildbutton(f"🔗 Source Link", source_link)
                    else:
                        pass
                except Exception:
                    pass
                if reply_to is not None:
                    try:
                        reply_text = reply_to.text
                        if is_url(reply_text):
                            source_link = reply_text.strip()
                            if is_magnet(source_link):
                                link = telegraph.create_page(
                                    title=f"{config_dict['TITLE_NAME']} Source Link",
                                    content=source_link,
                                )["path"]
                                buttons.buildbutton(f"🔗 Source Link", f"https://telegra.ph/{link}")
                            else:
                                buttons.buildbutton(f"🔗 Source Link", source_link)
                    except Exception:
                        pass
            else:
                pass
            # if BOT_PM_X and self.message.chat.type != 'private':
            #     bot_d = bot.get_me()
            #     b_uname = bot_d.username
            #     botstart = f"http://t.me/{b_uname}"
            #     buttons.buildbutton("View file in PM", f"{botstart}")
            # elif self.message.chat.type == 'private':
            #     botstart = ''
            # else:
            #     botstart = ''

            if config_dict['EMOJI_THEME']:
                msg += f'\n<b>├📚 Total Files: </b>{folders}'
            else:
                msg += f'\n<b>├ Total Files: </b>{folders}'
            if typ != 0:
                if config_dict['EMOJI_THEME']:
                    msg += f'\n<b>├💀 Corrupted Files: </b>{typ}'
                else:
                    msg += f'\n<b>├ Corrupted Files: </b>{typ}'
            if config_dict['EMOJI_THEME']:
                msg += f'\n<b>├⌛ It Tooks:</b> {get_readable_time(time() - self.message.date.timestamp())}'
                msg += f'\n<b>╰👤 #Leech_by: </b>{self.tag}\n\n'
            else: 
                msg += f'\n<b>├ It Tooks:</b> {get_readable_time(time() - self.message.date.timestamp())}'
                msg += f'\n<b>╰ #Leech_by: </b>{self.tag}\n\n'

            if not self.isPrivate and config_dict['SAVE_MSG']:
                buttons.sbutton('Save This Message', 'save', 'footer')

            if not files:
                if config_dict['PICS']:
                    uploadmsg = sendPhoto(msg, self.bot, self.message, choice(config_dict['PICS']), buttons.build_menu(2))
                else:
                    uploadmsg = sendMessage(msg, self.bot, self.message, buttons.build_menu(2))
            else:
                fmsg = ''
                for index, (link, name) in enumerate(files.items(), start=1):
                    fmsg += f"{index}. <a href='{link}'>{name}</a>\n"
                    if len(fmsg.encode() + msg.encode()) > 2000:
                        sleep(1.5)
                        if not BOT_PM_X:
                            if config_dict['PICS']:
                                uploadmsg = sendPhoto(msg + fmsg + pmwarn + logleechwarn + warnmsg, self.bot, self.message, choice(config_dict['PICS']), buttons.build_menu(2))
                            else:
                                uploadmsg = sendMessage(msg + fmsg + pmwarn + logleechwarn + warnmsg, self.bot, self.message, buttons.build_menu(2))
                            Thread(target=auto_delete_upload_message, args=(bot, self.message, uploadmsg)).start()
                        fmsg = ''
                if fmsg != '':
                    sleep(1.5)
                    if not BOT_PM_X:
                        if config_dict['PICS']:
                            uploadmsg = sendPhoto(msg + fmsg + pmwarn + logleechwarn + warnmsg, self.bot, self.message, choice(config_dict['PICS']), buttons.build_menu(2))
                        else:
                            uploadmsg = sendMessage(msg + fmsg + pmwarn + logleechwarn + warnmsg, self.bot, self.message, buttons.build_menu(2))
                        Thread(target=auto_delete_upload_message, args=(bot, self.message, uploadmsg)).start()
                if config_dict['LEECH_LOG_INDEXING'] and config_dict['LEECH_LOG']:
                    for i in user_data['is_leech_log']:
                        indexmsg = ''
                        for index, (link, name) in enumerate(files.items(), start=1):
                            indexmsg += f"{index}. <a href='{link}'>{name}</a>\n"
                            if len(indexmsg.encode() + msg.encode()) > 4000:
                                bot.sendMessage(chat_id=i, text=msg + indexmsg,
                                                reply_markup=buttons.build_menu(2),
                                                parse_mode=ParseMode.HTML)
                                indexmsg = ''
                        if indexmsg != '':
                                bot.sendMessage(chat_id=i, text=msg + indexmsg,
                                                reply_markup=buttons.build_menu(2),
                                                parse_mode=ParseMode.HTML)
                else:
                    pass
            if self.seed:
                if self.newDir:
                    clean_target(self.newDir)
                with queue_dict_lock:
                    if self.uid in non_queued_up:
                        non_queued_up.remove(self.uid)
                return     

        else:
            if config_dict['EMOJI_THEME']:
                msg += f'\n<b>├📦 Type: </b>{typ}'
            else:
                msg += f'\n<b>├ Type: </b>{typ}'
            if typ == "Folder":
                if config_dict['EMOJI_THEME']:
                    msg += f'\n<b>├🗃️ SubFolders: </b>{folders}'
                    msg += f'\n<b>├🗂️ Files: </b>{files}'
                else:
                    msg += f'\n<b>├ SubFolders: </b>{folders}'
                    msg += f'\n<b>├ Files: </b>{files}'
            if config_dict['EMOJI_THEME']:
                msg += f'\n<b>├⌛ It Tooks:</b> {get_readable_time(time() - self.message.date.timestamp())}'
                msg += f'\n<b>╰👤 #Mirror_By: </b>{self.tag}\n\n'
            else:
                msg += f'\n<b>├ It Tooks:</b> {get_readable_time(time() - self.message.date.timestamp())}'
                msg += f'\n<b>╰ #Mirror_By: </b>{self.tag}\n\n' 
            buttons = ButtonMaker()
            link = short_url(link, user_id_)
            if config_dict['DISABLE_DRIVE_LINK'] and self.message.chat.type != 'private':
                pass
            else:
                buttons.buildbutton("☁️ Drive Link", link)
            LOGGER.info(f'Done Uploading {name}')
            _, INDEXURL = getGDriveUploadUtils(user_id_, self.u_index, self.c_index)
            if INDEX_URL:= INDEXURL:
                url_path = rquote(f'{name}', safe='')
                share_url = f'{INDEX_URL}/{url_path}'
                if typ == "Folder":
                    share_url += '/'
                    share_url = short_url(share_url, user_id_)
                    buttons.buildbutton("⚡ Index Link", share_url)
                else:
                    share_url = short_url(share_url, user_id_)
                    buttons.buildbutton("⚡ Index Link", share_url)
                    if config_dict['VIEW_LINK']:
                        share_urls = f'{INDEX_URL}/{url_path}?a=view'
                        share_urls = short_url(share_urls, user_id_)
                        buttons.buildbutton("🌐 View Link", share_urls)
                    if config_dict['SOURCE_LINK']:
                        try:
                            mesg = message_args[1]
                            if is_magnet(mesg):
                                link = telegraph.create_page(
                                    title=f"{config_dict['TITLE_NAME']} Source Link",
                                    content=mesg,
                                )["path"]
                                buttons.buildbutton(f"🔗 Source Link", f"https://telegra.ph/{link}")
                            elif is_url(mesg):
                                source_link = mesg
                                if source_link.startswith(("|", "pswd: ", "c:")):
                                    pass
                                else:
                                    buttons.buildbutton(f"🔗 Source Link", source_link)
                            else:
                                pass
                        except Exception:
                            pass
                        if reply_to is not None:
                            try:
                                reply_text = reply_to.text
                                if is_url(reply_text):
                                    source_link = reply_text.strip()
                                    if is_magnet(source_link):
                                        link = telegraph.create_page(
                                            title=f"{config_dict['TITLE_NAME']} Source Link",
                                            content=source_link,
                                        )["path"]
                                        buttons.buildbutton(f"🔗 Source Link", f"https://telegra.ph/{link}")
                                    else:
                                        buttons.buildbutton(f"🔗 Source Link", source_link)
                            except Exception:
                                pass
                    else:
                        pass
                    

                    # if BOT_PM_X and self.message.chat.type != 'private':
                    #     bot_d = bot.get_me()
                    #     b_uname = bot_d.username
                    #     botstart = f"http://t.me/{b_uname}"
                    #     buttons.buildbutton("View file in PM", f"{botstart}")
                    # elif self.message.chat.type == 'private':
                    #     botstart = ''
                    # else:
                    #     botstart = ''

            if config_dict['BUTTON_FOUR_NAME'] != '' and config_dict['BUTTON_FOUR_URL'] != '':
                buttons.buildbutton(f"{config_dict['BUTTON_FOUR_NAME']}", f"{config_dict['BUTTON_FOUR_URL']}")
            if config_dict['BUTTON_FIVE_NAME'] != '' and config_dict['BUTTON_FIVE_URL'] != '':
                buttons.buildbutton(f"{config_dict['BUTTON_FIVE_NAME']}", f"{config_dict['BUTTON_FIVE_URL']}")
            if config_dict['BUTTON_SIX_NAME'] != '' and config_dict['BUTTON_SIX_URL'] != '':
                buttons.buildbutton(f"{config_dict['BUTTON_SIX_NAME']}", f"{config_dict['BUTTON_SIX_URL']}")

            if BOT_PM_X and self.message.chat.type != 'private':
                try:
                    bot.sendMessage(chat_id=self.user_id, text=msg,
                                    reply_markup=buttons.build_menu(2),
                                    parse_mode=ParseMode.HTML)
                except Exception as e:
                    LOGGER.warning(e)

            if not self.isPrivate and config_dict['SAVE_MSG']:
                buttons.sbutton('Save This Message', 'save', 'footer')

            if not BOT_PM_X or self.message.chat.type == 'private':
                if config_dict['PICS']:
                    uploadmsg = sendPhoto(msg + pmwarn + logwarn + warnmsg, self.bot, self.message, choice(config_dict['PICS']), buttons.build_menu(2))
                else:
                    uploadmsg = sendMessage(msg + pmwarn + logwarn + warnmsg, self.bot, self.message, buttons.build_menu(2))
                Thread(target=auto_delete_upload_message, args=(bot, self.message, uploadmsg)).start()
        
            if 'mirror_logs' in user_data:
                try:
                    for chatid in user_data['mirror_logs']:
                        bot.sendMessage(chat_id=chatid, text=msg,
                                        reply_markup=buttons.build_menu(2),
                                        parse_mode=ParseMode.HTML)
                except Exception as e:
                    LOGGER.warning(e)

            if self.seed:
                if self.isZip:
                    clean_target(f"{self.dir}/{name}")
                elif self.newDir:
                    clean_target(self.newDir)
                with queue_dict_lock:
                    if self.uid in non_queued_up:
                        non_queued_up.remove(self.uid)
                return

        if BOT_PM_X and self.message.chat.type != 'private':
            if config_dict['EMOJI_THEME']:
                bmsg = f"<b>🗂️ Name: </b><{config_dict['NAME_FONT']}>{escape(name)}</{config_dict['NAME_FONT']}>\n"
            else:
                bmsg = f"<b>Name: </b><{config_dict['NAME_FONT']}>{escape(name)}</{config_dict['NAME_FONT']}>\n"
            botpm = f"<b>\nHey {self.tag}!, I have sent your stuff in PM.</b>\n"
            buttons = ButtonMaker()
            b_uname = bot.get_me().username
            botstart = f"http://t.me/{b_uname}"
            buttons.buildbutton("View links in PM", f"{botstart}")

            if config_dict['PICS']:
                sendPhoto(bmsg + botpm, self.bot, self.message, choice(config_dict['PICS']), buttons.build_menu(2))
            else:
                sendMessage(bmsg + botpm, self.bot, self.message, buttons.build_menu(2))
            try:
                self.message.delete()
            except Exception as e:
                    LOGGER.warning(e)
            pass
            reply_to = self.message.reply_to_message
            if reply_to is not None and config_dict['AUTO_DELETE_UPLOAD_MESSAGE_DURATION'] == -1:
                reply_to.delete()

        clean_download(self.dir)
        with download_dict_lock:
            if self.uid in download_dict.keys():
                del download_dict[self.uid]
            count = len(download_dict)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

        with queue_dict_lock:
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)

        start_from_queued()


    def onDownloadError(self, error):
        try:
            if config_dict['AUTO_DELETE_UPLOAD_MESSAGE_DURATION'] != -1 and self.reply_to is not None:
                self.reply_to.delete()
            else:
                pass
        except Exception as e:
            LOGGER.warning(e)
            pass
        clean_download(self.dir)
        if self.newDir:
            clean_download(self.newDir)
        with download_dict_lock:
            if self.uid in download_dict.keys():
                del download_dict[self.uid]
            count = len(download_dict)
        msg = f"{self.tag} your download has been stopped due to: {escape(error)}"
        sendMessage(msg, self.bot, self.message)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

        if not self.isPrivate and config_dict['INCOMPLETE_TASK_NOTIFIER'] and DATABASE_URL:
            DbManger().rm_complete_task(self.message.link)

        with queue_dict_lock:
            if self.uid in queued_dl:
                del queued_dl[self.uid]
            if self.uid in non_queued_dl:
                non_queued_dl.remove(self.uid)
            if self.uid in queued_up:
                del queued_up[self.uid]
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)

        self.queuedUp = False
        start_from_queued()

    def onUploadError(self, error):
        clean_download(self.dir)
        if self.newDir:
            clean_download(self.newDir)
        with download_dict_lock:
            if self.uid in download_dict.keys():
                del download_dict[self.uid]
            count = len(download_dict)
        sendMessage(f"{self.tag} {escape(error)}", self.bot, self.message)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

        if not self.isPrivate and config_dict['INCOMPLETE_TASK_NOTIFIER'] and DATABASE_URL:
            DbManger().rm_complete_task(self.message.link)
        with queue_dict_lock:
            if self.uid in queued_up:
                del queued_up[self.uid]
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)

        self.queuedUp = False
        start_from_queued()

    def __user_settings(self):
        user_id = self.message.from_user.id
        user_dict = user_data.get(user_id, False)            
