import argparse
import os
import shutil
from enum import Enum
from threading import Lock
from subprocess import call

import log
from config import RMT_SUBEXT, RMT_MEDIAEXT, RMT_DISKFREESIZE, RMT_FAVTYPE, Config
from utils.functions import get_dir_files_by_ext, get_free_space_gb
from message.send import Message
from rmt.media import Media
from utils.sqls import insert_transfer_history
from utils.types import MediaType, DownloaderType, SyncType, MediaCatagory, RmtMode

lock = Lock()


class FileTransfer:
    __config = None
    __pt_rmt_mode = None
    __sync_rmt_mode = None
    __movie_path = None
    __tv_path = None
    __movie_subtypedir = None
    __tv_subtypedir = None
    __sync_path = None
    __unknown_path = None
    media = None
    message = None

    def __init__(self):
        self.__config = Config()
        media = self.__config.get_config('media')
        if media:
            self.__movie_path = media.get('movie_path')
            self.__tv_path = media.get('tv_path')
            self.__unknown_path = media.get('unknown_path')
            self.__movie_subtypedir = media.get('movie_subtypedir', True)
            self.__tv_subtypedir = media.get('tv_subtypedir', True)
        sync = self.__config.get_config('sync')
        if sync:
            rmt_mode = sync.get('sync_mod', 'COPY').upper()
            if rmt_mode == "LINK":
                self.__sync_rmt_mode = RmtMode.LINK
            elif rmt_mode == "SOFTLINK":
                self.__sync_rmt_mode = RmtMode.SOFTLINK
            else:
                self.__sync_rmt_mode = RmtMode.COPY
            self.__sync_path = sync.get('sync_path')
        pt = self.__config.get_config('pt')
        if pt:
            rmt_mode = pt.get('rmt_mode', 'COPY').upper()
            if rmt_mode == "LINK":
                self.__pt_rmt_mode = RmtMode.LINK
            elif rmt_mode == "SOFTLINK":
                self.__pt_rmt_mode = RmtMode.SOFTLINK
            else:
                self.__pt_rmt_mode = RmtMode.COPY
        self.media = Media()
        self.message = Message()

    def get_media_subtype_flag(self):
        return self.__movie_subtypedir

    # 返回一个子路径
    def get_media_dest_path(self, media_info):
        if media_info.type == MediaType.MOVIE:
            if self.__movie_subtypedir:
                return os.path.join(self.__movie_path, media_info.category.value)
            else:
                return self.__movie_path
        elif media_info.type == MediaType.TV:
            if self.__tv_subtypedir:
                return os.path.join(self.__tv_path, media_info.category.value)
            else:
                return self.__tv_path
        else:
            return None

    # 根据文件名转移对应字幕文件
    @staticmethod
    def transfer_subtitles(org_name, new_name, rmt_mode=RmtMode.COPY):
        dir_name = os.path.dirname(org_name)
        file_name = os.path.basename(org_name)
        file_list = get_dir_files_by_ext(dir_name, RMT_SUBEXT)
        Media_FileNum = len(file_list)
        if Media_FileNum == 0:
            log.debug("【RMT】%s 目录下没有找到字幕文件..." % dir_name)
        else:
            log.debug("【RMT】字幕文件清单：" + str(file_list))
            find_flag = False
            for file_item in file_list:
                org_subname = os.path.splitext(org_name)[0]
                if org_subname in file_item:
                    find_flag = True
                    file_ext = os.path.splitext(file_item)[-1]
                    if file_item.find(".zh-cn" + file_ext) != -1:
                        new_file = os.path.splitext(new_name)[0] + ".zh-cn" + file_ext
                    else:
                        new_file = os.path.splitext(new_name)[0] + file_ext
                    if not os.path.exists(new_file):
                        log.debug("【RMT】正在处理字幕：%s" % file_name)
                        if rmt_mode == RmtMode.LINK:
                            retcode = call(["ln", file_item, new_file])
                        elif rmt_mode == RmtMode.SOFTLINK:
                            retcode = call(["ln", "-s", file_item, new_file])
                        else:
                            retcode = call(["cp", file_item, new_file])
                        if retcode == 0:
                            log.info("【RMT】字幕 %s %s完成" % (file_name, rmt_mode.value))
                        else:
                            log.error("【RMT】字幕 %s %s失败，错误码：%s" % (file_name, rmt_mode.value, str(retcode)))
                    else:
                        log.info("【RMT】字幕 %s 已存在！" % new_file)
            if not find_flag:
                log.debug("【RMT】没有相同文件名的字幕文件，不处理！")
        return True

    # 转移蓝光文件夹
    '''
    mv_flag：是否为移动，否则为复制
    over_falg：是否覆盖
    '''

    def transfer_bluray_dir(self, file_path, new_path, mv_flag=False, over_flag=False):
        if not over_flag and os.path.exists(new_path):
            log.warn("【RMT】目录已存在：%s" % new_path)
            return False

        try:
            lock.acquire()
            if over_flag and os.path.exists(new_path):
                log.warn("【RMT】正在删除已存在的目录：%s" % new_path)
                shutil.rmtree(new_path)
            log.info("【RMT】正在复制目录：%s 到 %s" % (file_path, new_path))
            retcode = call(['cp', '-r', file_path, new_path])
        finally:
            lock.release()

        if retcode == 0:
            log.info("【RMT】文件 %s 复制完成" % new_path)
        else:
            log.error("【RMT】文件复制失败，错误码：%s" % str(retcode))
            return False

        if mv_flag:
            if file_path != self.__movie_path and file_path != self.__tv_path:
                shutil.rmtree(file_path)
            log.info("【RMT】%s 已删除！" % file_path)
        return True

    # 按原文件名link文件到目的目录
    @staticmethod
    def link_origin_file(file_item, target_dir, rmt_mode):
        if os.path.isdir(file_item):
            log.warn("【RMT】目录不支持硬链接处理！")
            return False

        if not target_dir:
            return False
        # 文件名
        file_name = os.path.basename(file_item)
        parent_name = os.path.basename(os.path.dirname(file_item))
        target_dir = os.path.join(target_dir, parent_name)
        if not os.path.exists(target_dir):
            log.debug("【RMT】正在创建目录：%s" % target_dir)
            os.makedirs(target_dir)
        target_file = os.path.join(target_dir, file_name)
        if rmt_mode == RmtMode.LINK:
            retcode = call(['ln', file_item, target_file])
        elif rmt_mode == RmtMode.SOFTLINK:
            retcode = call(['ln', '-s', file_item, target_file])
        else:
            retcode = call(['cp', file_item, target_file])

        if retcode == 0:
            log.info("【RMT】文件 %s 硬链接完成" % file_name)
        else:
            log.error("【RMT】文件 %s 硬链接失败，错误码：%s" % (file_name, retcode))
            return False
        return True

    # 复制或者硬链接一个文件
    def transfer_file(self, file_item, new_file, over_flag=False, rmt_mode=RmtMode.COPY):
        file_name = os.path.basename(file_item)
        new_file_name = os.path.basename(new_file)
        if not over_flag and os.path.exists(new_file):
            log.warn("【RMT】文件已存在：%s" % new_file_name)
            return False

        try:
            if rmt_mode == RmtMode.COPY:
                lock.acquire()
            if over_flag and os.path.isfile(new_file):
                log.info("【RMT】正在删除已存在的文件：%s" % new_file_name)
                os.remove(new_file)
            log.info("【RMT】正在转移文件：%s 到 %s" % (file_name, new_file_name))
            if rmt_mode == RmtMode.LINK:
                retcode = call(['ln', file_item, new_file])
            elif rmt_mode == RmtMode.SOFTLINK:
                retcode = call(['ln', '-s', file_item, new_file])
            else:
                retcode = call(['cp', file_item, new_file])
        finally:
            if rmt_mode == RmtMode.COPY:
                lock.release()

        if retcode == 0:
            log.info("【RMT】文件 %s %s完成" % (file_name, rmt_mode.value))
        else:
            log.error("【RMT】文件 %s %s失败，错误码：%s" % (file_name, rmt_mode.value, str(retcode)))
            return False
        # 处理字幕
        return self.transfer_subtitles(file_item, new_file, rmt_mode)

    # 转移识别媒体文件 in_from：来源  in_path：路径，可有是个目录也可能是一个文件  target_dir：指定目的目录，否则按电影、电视剧目录
    def transfer_media(self,
                       in_from,
                       in_path,
                       target_dir=None):
        if not in_path:
            log.error("【RMT】输入路径错误!")
            return False

        # 进到这里来的，可能是一个大目录，目录中有电影也有电视剧；也有可能是一个电视剧目录或者一个电影目录；也有可能是一个文件

        if in_from in DownloaderType:
            rmt_mode = self.__pt_rmt_mode
        else:
            rmt_mode = self.__sync_rmt_mode

        in_path = in_path.replace('\\\\', '/').replace('\\', '/')
        # 回收站及隐藏的文件不处理
        if in_path.find('/@Recycle/') != -1 or in_path.find('/#recycle/') != -1 or in_path.find('/.') != -1:
            return False
        # 不是媒体后缀的文件不处理
        if os.path.isfile(in_path):
            in_ext = os.path.splitext(in_path)[-1]
            if in_ext not in RMT_MEDIAEXT:
                return False
        log.info("【RMT】开始处理：%s" % in_path)

        bluray_disk_flag = False
        if os.path.isdir(in_path):
            # 如果传入的是个目录
            if not os.path.exists(in_path):
                log.error("【RMT】目录不存在：%s" % in_path)
                return False

            # 判断是不是原盘文件夹
            if os.path.exists(os.path.join(in_path, "BDMV/index.bdmv")):
                bluray_disk_flag = True

            # 处理蓝光原盘
            if bluray_disk_flag:
                if rmt_mode == RmtMode.LINK:
                    log.warn("【RMT】硬链接下不支持蓝光原盘目录，不处理...")
                    return False
            # 开始处理里面的文件
            if bluray_disk_flag:
                file_list = [in_path]
                log.info("【RMT】当前为蓝光原盘文件夹：%s" % str(in_path))
            else:
                file_list = get_dir_files_by_ext(in_path, RMT_MEDIAEXT)
                Media_FileNum = len(file_list)
                log.debug("【RMT】文件清单：" + str(file_list))
                if Media_FileNum == 0:
                    log.warn("【RMT】目录下未找到媒体文件：%s" % in_path)
                    return False
        else:
            # 如果传入的是个文件
            if not os.path.exists(in_path):
                log.error("【RMT】文件不存在：%s" % in_path)
                return False
            ext = os.path.splitext(in_path)[-1]
            if ext not in RMT_MEDIAEXT:
                log.warn("【RMT】不支持的媒体文件格式，不处理：%s" % in_path)
                return False
            file_list = [in_path]

        # API检索出媒体信息，传入一个文件列表，得出每一个文件的名称，这里是当前目录下所有的文件了
        Medias = self.media.get_media_info_on_files(file_list)
        if not Medias:
            log.error("【RMT】检索媒体信息出错！")
            return False

        # 统计总的文件数、失败文件数
        failed_count = 0
        total_count = 0
        # 如果是电影，因为只会有一个文件，直接在循环里就发了消息
        # 但是电视剧可能有多集，如果在循环里发消息就太多了，要在外面发消息
        # 如果这个目录很复杂，有多集或者多部电影电视剧，则电视剧也要在外面统一发消息
        # title: {year, media_filesize, season_ary[], episode_ary}
        message_medias = {}

        for file_item, media in Medias.items():
            total_count = total_count + 1
            # 文件名
            file_name = os.path.basename(file_item)
            if not media or not media.tmdb_info:
                log.warn("【RMT】%s 无法识别媒体信息！" % file_name)
                failed_count = failed_count + 1
                # 原样转移过去
                log.warn("【RMT】按原文件名硬链接到unknown目录...")
                if target_dir:
                    target_dir = os.path.join(target_dir, 'unknown')
                    self.link_origin_file(file_item, target_dir, rmt_mode)
                    insert_transfer_history(in_from, rmt_mode, file_item, target_dir, media)
                elif self.__unknown_path:
                    self.link_origin_file(file_item, self.__unknown_path, rmt_mode)
                    insert_transfer_history(in_from, rmt_mode, file_item, self.__unknown_path, media)
                else:
                    log.error("【RMT】%s 处理失败！" % file_name)
                continue
            # 记录目录下是不是有多种类型，来决定怎么发通知
            Search_Type = media.type
            Title_Str = media.get_title_string()

            # 电影
            if Search_Type == MediaType.MOVIE:
                if target_dir:
                    # 有输入target_dir时，往这个目录放
                    movie_dist = target_dir
                else:
                    movie_dist = self.__movie_path
                # 是否新电影标志
                new_movie_flag = False
                exist_filenum = 0
                # 检查剩余空间
                disk_free_size = get_free_space_gb(movie_dist)
                if float(disk_free_size) < RMT_DISKFREESIZE:
                    log.error("【RMT】目录 %s 剩余磁盘空间不足 %s GB，不处理！" % (movie_dist, RMT_DISKFREESIZE))
                    self.message.sendmsg("【RMT】磁盘空间不足", "目录 %s 剩余磁盘空间不足 %s GB！" % (movie_dist, RMT_DISKFREESIZE))
                    return False
                # 判断文件是否已存在，返回：目录存在标志、目录名、文件存在标志、文件名
                dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path = self.is_media_exists(movie_dist, media)
                media_filesize = os.path.getsize(file_item)
                if dir_exist_flag:
                    # 新路径存在
                    if bluray_disk_flag:
                        log.warn("【RMT】蓝光原盘目录已存在：%s" % Title_Str)
                        continue
                    if file_exist_flag:
                        exist_filenum = exist_filenum + 1
                        if rmt_mode == RmtMode.COPY:
                            existfile_size = os.path.getsize(ret_file_path)
                            if media_filesize > existfile_size:
                                log.info("【RMT】文件 %s 已存在，但新文件质量更好，覆盖..." % ret_file_path)
                                ret = self.transfer_file(file_item, ret_file_path, True, rmt_mode)
                                if not ret:
                                    continue
                                new_movie_flag = True
                            else:
                                log.warn("【RMT】文件 %s 已存在！" % ret_file_path)
                        else:
                            log.warn("【RMT】文件 %s 已存在！" % ret_file_path)
                else:
                    if bluray_disk_flag:
                        # 转移蓝光原盘
                        ret = self.transfer_bluray_dir(file_item, ret_dir_path)
                        if ret:
                            insert_transfer_history(in_from, rmt_mode, file_item, movie_dist, media)
                            log.info("【RMT】蓝光原盘 %s 转移成功！" % file_name)
                        else:
                            log.error("【RMT】蓝光原盘 %s 转移失败！" % file_name)
                        continue
                    else:
                        # 创建电影目录
                        log.debug("【RMT】正在创建目录：%s" % ret_dir_path)
                        os.makedirs(ret_dir_path)
                    file_ext = os.path.splitext(file_item)[-1]
                    if not ret_file_path:
                        log.error("【RMT】拼装路径错误！")
                        continue
                    new_file = "%s%s" % (ret_file_path, file_ext)
                    ret = self.transfer_file(file_item, new_file, False, rmt_mode)
                    if not ret:
                        continue
                    else:
                        insert_transfer_history(in_from, rmt_mode, file_item, movie_dist, media)
                    new_movie_flag = True

                # 电影的话，处理一部马上开始发送消息
                if in_from not in DownloaderType:
                    #  不是PT转移的，只有有变化才通知
                    if not new_movie_flag:
                        continue
                self.message.send_transfer_movie_message(in_from, media, media_filesize, exist_filenum)
                log.info("【RMT】%s 转移完成" % file_name)

            # 电视剧
            elif Search_Type == MediaType.TV:
                # 记录下来
                if not message_medias.get(Title_Str):
                    message_medias[Title_Str] = {"media": media,
                                                 "seasons": [],
                                                 "episodes": [],
                                                 "totalsize": 0,
                                                 "existfiles": 0}

                if bluray_disk_flag:
                    log.error("【RMT】识别有误：蓝光原盘目录被识别为电视剧！")
                    continue

                # 自定义目的目录
                if target_dir:
                    # 有输入target_dir时，往这个目录放
                    tv_dist = target_dir
                else:
                    tv_dist = self.__tv_path

                # 文件大小
                media_filesize = os.path.getsize(file_item)
                message_medias[Title_Str]['totalsize'] = message_medias[Title_Str]['totalsize'] + media_filesize

                # 检查磁盘空间
                disk_free_size = get_free_space_gb(tv_dist)
                if float(disk_free_size) < RMT_DISKFREESIZE:
                    log.error("【RMT】目录 %s 剩余磁盘空间不足 %s GB，不处理！" % (tv_dist, RMT_DISKFREESIZE))
                    self.message.sendmsg("【RMT】磁盘空间不足", "目录 %s 剩余磁盘空间不足 %s GB，不处理！" % (tv_dist, RMT_DISKFREESIZE))
                    return False

                # 季集合
                message_medias[Title_Str]['seasons'] = list(set(message_medias[Title_Str].get('seasons')).union(set(media.get_season_list())))
                # 集集合
                message_medias[Title_Str]['episodes'] = list(set(message_medias[Title_Str].get('episodes')).union(set(media.get_episode_list())))

                # 判断是否存在目录及文件，返因目录及文件路径
                dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path = self.is_media_exists(tv_dist, media)
                if file_exist_flag:
                    # 文件已存在
                    existfile_size = os.path.getsize(ret_file_path)
                    message_medias[Title_Str]['existfiles'] = message_medias[Title_Str]['existfiles'] + 1
                    if rmt_mode == RmtMode.COPY:
                        if media_filesize > existfile_size:
                            log.info("【RMT】文件 %s 已存在，但新文件质量更好，覆盖..." % ret_file_path)
                            ret = self.transfer_file(file_item, ret_file_path, True, rmt_mode)
                            if not ret:
                                continue
                        else:
                            log.warn("【RMT】文件 %s 已存在！" % ret_file_path)
                            continue
                    else:
                        log.warn("【RMT】文件 %s 已存在！" % ret_file_path)
                        continue
                else:
                    # 文件不存在
                    if not dir_exist_flag:
                        # 目录不存在
                        log.debug("【RMT】正在创建目录：%s" % ret_dir_path)
                        os.makedirs(ret_dir_path)
                    file_ext = os.path.splitext(file_item)[-1]
                    if not ret_file_path:
                        log.error("【RMT】拼装路径错误！")
                        continue
                    new_file = "%s%s" % (ret_file_path, file_ext)
                    ret = self.transfer_file(file_item, new_file, False, rmt_mode)
                    if not ret:
                        continue
                    else:
                        insert_transfer_history(in_from, rmt_mode, file_item, tv_dist, media)
            else:
                log.error("【RMT】%s 无法识别是什么类型的媒体文件！" % file_name)
                failed_count = failed_count + 1
                continue

        # 统计完成情况，发送通知
        self.message.send_transfer_tv_message(message_medias, in_from)

        # 总结
        log.info("【RMT】%s 处理完成，总数：%s，失败：%s！" % (in_path, total_count, failed_count))
        return True

    # 全量转移，用于使用命令调用
    def transfer_manually(self, s_path, t_path):
        if not s_path:
            return
        if not os.path.exists(s_path):
            print("【RMT】源目录不存在：%s" % s_path)
            return
        if t_path:
            if not os.path.exists(t_path):
                print("【RMT】目的目录不存在：%s" % t_path)
                return
        print("【RMT】正在转移以下目录中的全量文件：%s" % s_path)
        print("【RMT】转移模式为：%s" % self.__sync_rmt_mode.value)
        ret = self.transfer_media(in_from=SyncType.MAN, in_path=s_path, target_dir=t_path)
        if not ret:
            print("【RMT】%s 处理失败！" % s_path)
        else:
            print("【RMT】%s 处理完成" % s_path)

    # 全量转移Sync目录下的文件
    def transfer_all_sync(self):
        monpaths = self.__sync_path
        if monpaths:
            log.info("【SYNC】开始全量转移...")
            if not isinstance(monpaths, list):
                monpaths = [monpaths]
            for monpath in monpaths:
                # 目录是两段式，需要把配对关系存起来
                if monpath.find('|') != -1:
                    # 源目录|目的目录，这个格式的目的目录在源目录同级建立
                    s_path = monpath.split("|")[0]
                    t_path = monpath.split("|")[1]
                else:
                    s_path = monpath
                    t_path = None
                ret = self.transfer_media(in_from=SyncType.MON, in_path=s_path, target_dir=t_path)
                if not ret:
                    log.error("【SYNC】%s 处理失败！" % s_path)
                else:
                    log.info("【SYNC】%s 处理成功！" % s_path)

    # 判断媒体文件是否忆存在，返回：目录存在标志、目录名、文件存在标志、文件名
    def is_media_exists(self,
                        media_dest,
                        media):
        dir_exist_flag = False
        file_exist_flag = False
        ret_dir_path = None
        ret_file_path = None
        if media.year:
            dir_name = "%s (%s)" % (media.title, media.year)
        else:
            dir_name = media.title
        if media.type == MediaType.MOVIE:
            file_path = os.path.join(media_dest, dir_name)
            if self.__movie_subtypedir:
                file_path = os.path.join(media_dest, media.category.value, dir_name)
                for m_type in MediaCatagory:
                    type_path = os.path.join(media_dest, m_type.value, dir_name)
                    # 目录是否存在
                    if os.path.exists(type_path):
                        file_path = type_path
                        break
            ret_dir_path = file_path
            if os.path.exists(file_path):
                dir_exist_flag = True
            if media.resource_pix:
                file_dest = os.path.join(file_path, "%s - %s" % (dir_name, media.resource_pix))
            else:
                file_dest = os.path.join(file_path, dir_name)
            ret_file_path = file_dest
            for ext in RMT_MEDIAEXT:
                ext_dest = "%s%s" % (file_dest, ext)
                if os.path.exists(ext_dest):
                    file_exist_flag = True
                    ret_file_path = ext_dest
                    break
        else:
            # 剧集目录
            if self.__tv_subtypedir:
                media_path = os.path.join(media_dest, media.category.value, dir_name)
            else:
                media_path = os.path.join(media_dest, dir_name)
            # 季
            seasons = media.get_season_list()
            if seasons:
                # 季 Season
                season_str = "Season %s" % seasons[0]
                season_dir = os.path.join(media_path, season_str)
                ret_dir_path = season_dir
                if os.path.exists(season_dir):
                    dir_exist_flag = True
                episodes = media.get_episode_list()
                if episodes:
                    # 集 xx
                    if len(episodes) == 1:
                        file_seq_num = episodes[0]
                    else:
                        file_seq_num = "%s-%s" % (episodes[0], episodes[-1])
                    # 文件路径
                    file_path = os.path.join(season_dir,
                                             "%s - %s%s - 第 %s 集" % (media.title, media.get_season_item(), media.get_episode_items(), file_seq_num))
                    ret_file_path = file_path
                    for ext in RMT_MEDIAEXT:
                        log.debug("【RSS】路径：%s%s" % (file_path, ext))
                        ext_dest = "%s%s" % (file_path, ext)
                        if os.path.exists(ext_dest):
                            file_exist_flag = True
                            ret_file_path = ext_dest
                            break
        return dir_exist_flag, ret_dir_path, file_exist_flag, ret_file_path

    # 检查媒体库是否存在，返回TRUE或FLASE
    def is_media_file_exists(self, item):
        mtype = item.type
        title = item.title
        year = item.year
        season = item.get_season_list()
        episode = item.get_episode_list()
        category = item.category

        if isinstance(category, Enum):
            category = category.value

        # 如果是电影
        if mtype == MediaType.MOVIE:
            if self.__movie_subtypedir:
                dest_path = os.path.join(self.__movie_path, RMT_FAVTYPE.value, "%s (%s)" % (title, year))
                if os.path.exists(dest_path):
                    return True
                dest_path = os.path.join(self.__movie_path, category, "%s (%s)" % (title, year))
            else:
                dest_path = os.path.join(self.__movie_path, "%s (%s)" % (title, year))
            return os.path.exists(dest_path)
        else:
            if not season:
                # 没有季信息的情况下，只判断目录
                if self.__tv_subtypedir:
                    dest_path = os.path.join(self.__tv_path, category, "%s (%s)" % (title, year))
                else:
                    dest_path = os.path.join(self.__tv_path, "%s (%s)" % (title, year))
                return os.path.exists(dest_path)
            else:
                if not episode:
                    # 有季没有集的情况下，只要有一季缺失就下
                    for sea in season:
                        if not sea:
                            continue
                        if self.__tv_subtypedir:
                            dest_path = os.path.join(self.__tv_path, category, "%s (%s)" % (title, year),
                                                     "Season %s" % sea)
                        else:
                            dest_path = os.path.join(self.__tv_path, "%s (%s)" % (title, year), "Season %s" % sea)
                        if not os.path.exists(dest_path):
                            return False
                    return True
                else:
                    # 有季又有集的情况下，检查对应的文件有没有，只要有一集缺失就下
                    for sea in season:
                        if not sea:
                            continue
                        sea_str = "S" + str(sea).rjust(2, "0")
                        for epi in episode:
                            if not epi:
                                continue
                            epi_str = "E%s" % str(epi).rjust(2, "0")
                            ext_exist = False
                            for ext in RMT_MEDIAEXT:
                                if self.__tv_subtypedir:
                                    dest_path = os.path.join(self.__tv_path, category, "%s (%s)" % (title, year),
                                                             "Season %s" % sea, "%s - %s%s - 第 %s 集%s" % (
                                                             title, sea_str, epi_str, epi, ext))
                                else:
                                    dest_path = os.path.join(self.__tv_path, "%s (%s)" % (title, year),
                                                             "Season %s" % sea, "%s - %s%s - 第 %s 集%s" % (
                                                             title, sea_str, epi_str, epi, ext))
                                if os.path.exists(dest_path):
                                    ext_exist = True
                            if not ext_exist:
                                return False
                    return True

    # Emby点红星后转移文件
    def transfer_embyfav(self, item_path):
        if not self.__movie_subtypedir or not self.__movie_path:
            return False, None
        if os.path.isdir(item_path):
            movie_dir = item_path
        else:
            movie_dir = os.path.dirname(item_path)
        if movie_dir.count(self.__movie_path) == 0:
            return False, None
        name = movie_dir.split('/')[-1]
        org_type = movie_dir.split('/')[-2]
        if org_type not in [MediaCatagory.HYDY.value, MediaCatagory.WYDY.value]:
            return False, None
        if org_type == RMT_FAVTYPE.value:
            return False, None
        new_path = os.path.join(self.__movie_path, RMT_FAVTYPE.value, name)
        log.info("【EMBY】开始转移文件 %s 到 %s ..." % (movie_dir, new_path))
        if os.path.exists(new_path):
            log.info("【EMBY】目录 %s 已存在！" % new_path)
            return False, None
        ret = call(['mv', movie_dir, new_path])
        if ret == 0:
            return True, org_type
        else:
            return False, None


if __name__ == "__main__":
    # 参数
    parser = argparse.ArgumentParser(description='Rename Media Tool')
    parser.add_argument('-s', '--source', dest='s_path', required=True, help='硬链接源目录路径')
    parser.add_argument('-d', '--target', dest='t_path', required=False, help='硬链接目的目录路径')
    args = parser.parse_args()
    if os.environ.get('NASTOOL_CONFIG'):
        print("【RMT】配置文件地址：%s" % os.environ.get('NASTOOL_CONFIG'))
        print("【RMT】源目录路径：%s" % args.s_path)
        if args.t_path:
            print("【RMT】目的目录路径：%s" % args.t_path)
        else:
            print("【RMT】目的目录为配置文件中的电影、电视剧媒体库目录")
        FileTransfer().transfer_manually(args.s_path, args.t_path)
    else:
        print("【RMT】未设置环境变量，请先设置 NASTOOL_CONFIG 环境变量为配置文件地址")
