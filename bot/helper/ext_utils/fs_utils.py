from os import remove as osremove, path as ospath, mkdir, walk, listdir, rmdir, makedirs
from sys import exit as sysexit
from shutil import rmtree, disk_usage
from PIL import Image
from magic import Magic
from subprocess import run as srun, check_output, Popen
from time import time
from math import ceil
from re import split as re_split, I
from .exceptions import NotSupportedExtractionArchive
from bot import aria2, app, LOGGER, DOWNLOAD_DIR, get_client, premium_session, config_dict, STORAGE_THRESHOLD, user_data


ARCH_EXT = [".tar.bz2", ".tar.gz", ".bz2", ".gz", ".tar.xz", ".tar", ".tbz2", ".tgz", ".lzma2",
            ".zip", ".7z", ".z", ".rar", ".iso", ".wim", ".cab", ".apm", ".arj", ".chm",
            ".cpio", ".cramfs", ".deb", ".dmg", ".fat", ".hfs", ".lzh", ".lzma", ".mbr",
            ".msi", ".mslz", ".nsis", ".ntfs", ".rpm", ".squashfs", ".udf", ".vhd", ".xar"]

def clean_target(path: str):
    if ospath.exists(path):
        LOGGER.info(f"Cleaning Target: {path}")
        if ospath.isdir(path):
            try:
                rmtree(path)
            except:
                pass
        elif ospath.isfile(path):
            try:
                osremove(path)
            except:
                pass

def clean_download(path: str):
    if ospath.exists(path):
        LOGGER.info(f"Cleaning Download: {path}")
        try:
            rmtree(path)
        except:
            pass

def start_cleanup():
    get_client().torrents_delete(torrent_hashes="all")
    try:
        rmtree(DOWNLOAD_DIR)
    except:
        pass
    makedirs(DOWNLOAD_DIR)

def clean_all():
    aria2.remove_all(True)
    get_client().torrents_delete(torrent_hashes="all")
    app.stop()
    if premium_session: premium_session.stop()
    try:
        rmtree(DOWNLOAD_DIR)
    except:
        pass

def exit_clean_up(signal, frame):
    try:
        LOGGER.info("Please wait, while we clean up the downloads and stop running downloads")
        clean_all()
        sysexit(0)
    except KeyboardInterrupt:
        LOGGER.warning("Force Exiting before the cleanup finishes!")
        sysexit(1)

def clean_unwanted(path: str):
    LOGGER.info(f"Cleaning unwanted files/folders: {path}")
    for dirpath, subdir, files in walk(path, topdown=False):
        for filee in files:
            if filee.endswith(".!qB") or filee.endswith('.parts') and filee.startswith('.'):
                osremove(ospath.join(dirpath, filee))
        if dirpath.endswith((".unwanted", "splited_files_wz")):
            rmtree(dirpath)
    for dirpath, subdir, files in walk(path, topdown=False):
        if not listdir(dirpath):
            rmdir(dirpath)

def get_path_size(path: str):
    if ospath.isfile(path):
        return ospath.getsize(path)
    total_size = 0
    for root, dirs, files in walk(path):
        for f in files:
            abs_path = ospath.join(root, f)
            total_size += ospath.getsize(abs_path)
    return total_size

def check_storage_threshold(size: int, arch=False, alloc=False):
    if not alloc:
        if not arch:
            if disk_usage(DOWNLOAD_DIR).free - size < STORAGE_THRESHOLD * 1024**3:
                return False
        elif disk_usage(DOWNLOAD_DIR).free - (size * 2) < STORAGE_THRESHOLD * 1024**3:
            return False
    elif not arch:
        if disk_usage(DOWNLOAD_DIR).free < STORAGE_THRESHOLD * 1024**3:
            return False
    elif disk_usage(DOWNLOAD_DIR).free - size < STORAGE_THRESHOLD * 1024**3:
        return False
    return True

def get_base_name(orig_path: str):
    ext = [ext for ext in ARCH_EXT if orig_path.lower().endswith(ext)]
    if ext:
        ext = ext[0]
        return re_split(f'{ext}$', orig_path, maxsplit=1, flags=I)[0]
    else:
        raise NotSupportedExtractionArchive('File format not supported for extraction')

def get_mime_type(file_path):
    mime = Magic(mime=True)
    mime_type = mime.from_file(file_path)
    mime_type = mime_type or "text/plain"
    return mime_type

def take_ss(video_file, duration):
    des_dir = 'Thumbnails'
    if not ospath.exists(des_dir):
        mkdir(des_dir)
    des_dir = ospath.join(des_dir, f"{time()}.jpg")
    if duration is None:
        duration = get_media_info(video_file)[0]
    if duration == 0:
        duration = 3
    duration = duration // 2

    status = srun(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(duration),
                   "-i", video_file, "-frames:v", "1", des_dir])

    if status.returncode != 0 or not ospath.lexists(des_dir):
        return None
    
    with Image.open(des_dir) as img:
        img.convert("RGB").save(des_dir, "JPEG")

    return des_dir

def split_file(path, size, file_, dirpath, split_size, listener, start_time=0, i=1, inLoop=False, noMap=False):
    if listener.seed and not listener.newDir:
        dirpath = f"{dirpath}/splited_files_wz"
        if not ospath.exists(dirpath):
            mkdir(dirpath)
    user_id = listener.message.from_user.id
    user_dict = user_data.get(user_id, False)
    leech_split_size = int((user_dict and user_dict.get('split_size')) or config_dict['TG_SPLIT_SIZE'])
    parts = ceil(size/leech_split_size)
    if ((user_dict and user_dict.get('equal_splits')) or config_dict['EQUAL_SPLITS']) and not inLoop:
        split_size = ceil(size/parts) + 1000
    if get_media_streams(path)[0]:
        duration = get_media_info(path)[0]
        base_name, extension = ospath.splitext(file_)
        split_size = split_size - 5000000
        while i <= parts:
            parted_name = f"{str(base_name)}.part{str(i).zfill(3)}{str(extension)}"
            out_path = ospath.join(dirpath, parted_name)
            if not noMap:
                listener.suproc = Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start_time),
                                         "-i", path, "-fs", str(split_size), "-map", "0", "-map_chapters", "-1",
                                         "-c", "copy", out_path])
            else:
                listener.suproc = Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start_time),
                                          "-i", path, "-fs", str(split_size), "-map_chapters", "-1", "-c", "copy",
                                          out_path])
            listener.suproc.wait()
            if listener.suproc.returncode == -9:
                return False
            elif listener.suproc.returncode != 0 and not noMap:
                LOGGER.warning(f"Retrying without map, -map 0 not working in all situations. Path: {path}")
                try:
                    osremove(out_path)
                except:
                    pass
                return split_file(path, size, file_, dirpath, split_size, listener, start_time, i, True, True)
            elif listener.suproc.returncode != 0:
                LOGGER.warning(f"Unable to split this video, if it's size less than {config_dict['TG_SPLIT_SIZE']} will be uploaded as it is. Path: {path}")
                try:
                    osremove(out_path)
                except:
                    pass
                return "errored"
            out_size = get_path_size(out_path)
            if out_size > (config_dict['TG_SPLIT_SIZE'] + 1000):
                dif = out_size - (config_dict['TG_SPLIT_SIZE'] + 1000)
                split_size = split_size - dif + 5000000
                osremove(out_path)
                return split_file(path, size, file_, dirpath, split_size, listener, start_time, i, True, noMap)
            lpd = get_media_info(out_path)[0]
            if lpd == 0:
                LOGGER.error(f'Something went wrong while splitting mostly file is corrupted. Path: {path}')
                break
            elif duration == lpd:
                if not noMap:
                    LOGGER.warning(f"Retrying without map, -map 0 not working in all situations. Path: {path}")
                    try:
                        osremove(out_path)
                    except:
                        pass
                    return split_file(path, size, file_, dirpath, split_size, listener, start_time, i, True, True)
                else:
                    LOGGER.warning(f"This file has been splitted with default stream and audio, so you will only see one part with less size from orginal one because it doesn't have all streams and audios. This happens mostly with MKV videos. noMap={noMap}. Path: {path}")
                    break
            elif lpd <= 4:
                osremove(out_path)
                break
            start_time += lpd - 3
            i = i + 1
    else:
        out_path = ospath.join(dirpath, f"{file_}.")
        listener.suproc = Popen(["split", "--numeric-suffixes=1", "--suffix-length=3",
                                f"--bytes={split_size}", path, out_path])
        listener.suproc.wait()
        if listener.suproc.returncode == -9:
            return False
    return True

def get_media_info(path):

    try:
        result = check_output(["ffprobe", "-hide_banner", "-loglevel", "error", "-print_format",
                               "json", "-show_format", "-show_streams", path]).decode('utf-8')
    except Exception as e:
        LOGGER.error(f'{e} Mostly file not Found!')
        return 0, None, None

    fields = eval(result).get('format')
    if fields is None:
        LOGGER.error(f"get_media_info: {result}")
        return 0, None, None

    duration = round(float(fields.get('duration', 0)))

    fields = fields.get('tags')
    if fields:
        artist = fields.get('artist')
        if artist is None:
            artist = fields.get('ARTIST')
        title = fields.get('title')
        if title is None:
            title = fields.get('TITLE')
    else:
        title = None
        artist = None

    return duration, artist, title



def get_media_streams(path):

    is_video = False
    is_audio = False

    mime_type = get_mime_type(path)
    if mime_type.startswith('audio'):
        is_audio = True
        return is_video, is_audio

    if not mime_type.startswith('video'):
        return is_video, is_audio

    try:
        result = check_output(["ffprobe", "-hide_banner", "-loglevel", "error", "-print_format",
                               "json", "-show_streams", path]).decode('utf-8')
    except Exception as e:
        LOGGER.error(f'{e}. Mostly file not found!')
        return is_video, is_audio

    fields = eval(result).get('streams')
    if fields is None:
        LOGGER.error(f"get_media_streams: {result}")
        return is_video, is_audio


    for stream in fields:
        if stream.get('codec_type') == 'video':
            is_video = True
        elif stream.get('codec_type') == 'audio':
            is_audio = True
    return is_video, is_audio
