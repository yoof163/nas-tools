from enum import Enum

import log
from config import Config
from message.bark import Bark
from message.serverchan import ServerChan
from message.telegram import Telegram
from message.wechat import WeChat
from utils.functions import str_filesize
from utils.types import DownloaderType


class Message:
    __config = None
    __msg_channel = None
    __webhook_ignore = None
    wechat = None
    telegram = None
    serverchan = None
    bark = None

    def __init__(self):
        self.__config = Config()
        message = self.__config.get_config('message')
        if message:
            self.__msg_channel = message.get('msg_channel')
            self.__webhook_ignore = message.get('webhook_ignore')
            self.wechat = WeChat.get_instance()
            self.telegram = Telegram()
            self.serverchan = ServerChan()
            self.bark = Bark()

    def get_webhook_ignore(self):
        return self.__webhook_ignore or []

    def sendmsg(self, title, text="", image=""):
        log.info("【MSG】发送%s消息：title=%s, text=%s" % (self.__msg_channel, title, text))
        if self.__msg_channel == "wechat":
            return self.wechat.send_wechat_msg(title, text, image)
        elif self.__msg_channel == "serverchan":
            return self.serverchan.send_serverchan_msg(title, text)
        elif self.__msg_channel == "telegram":
            return self.telegram.send_telegram_msg(title, text, image)
        elif self.__msg_channel == "bark":
            return self.bark.send_bark_msg(title, text)
        else:
            return None

    # 发送下载的消息
    def send_download_message(self, in_from, can_item):
        va = can_item.vote_average
        bp = can_item.get_backdrop_path()
        tp = can_item.type
        se_str = can_item.get_season_episode_string()
        if isinstance(in_from, Enum):
            in_from = in_from.value
        if isinstance(tp, Enum):
            tp = tp.value

        msg_title = can_item.get_title_string()
        msg_text = f"来自{in_from}的{tp} {msg_title}{se_str} 已开始下载"
        if va:
            msg_title = f"{msg_title} 评分：{va}"

        self.sendmsg(msg_title, msg_text, bp)

    # 发送转移电影的消息
    def send_transfer_movie_message(self, in_from, media_info, media_filesize, exist_filenum):
        title_str = media_info.get_title_string()
        vote_average = media_info.vote_average
        media_pix = media_info.get_resource_type_string()
        backdrop_path = media_info.get_backdrop_path()
        if isinstance(in_from, Enum):
            in_from = in_from.value
        msg_title = f"{title_str} 转移完成"
        msg_str = "类型：电影"
        if vote_average:
            msg_str = f"{msg_str}，评分：{vote_average}"
        if media_pix:
            msg_str = f"{msg_str}，质量：{media_pix}"
        msg_str = f"{msg_str}，大小：{str_filesize(media_filesize)}，来自：{in_from}"
        if exist_filenum != 0:
            msg_str = f"{msg_str}，{exist_filenum}个文件已存在"
        self.sendmsg(msg_title, msg_str, backdrop_path)

    # 发送转移电视剧的消息
    def send_transfer_tv_message(self, message_medias, in_from):
        # 统计完成情况，发送通知
        for title_str, item_info in message_medias.items():
            # PT的不管是否有修改文件均发通知，其他渠道没变化不发通知
            send_message_flag = False
            if in_from in DownloaderType:
                send_message_flag = True
            else:
                if item_info.get('existfiles') < len(item_info.get('episodes')):
                    send_message_flag = True

            if send_message_flag:
                if isinstance(in_from, Enum):
                    in_from = in_from.value
                if len(item_info.get('episodes')) == 1:
                    msg_title = f"{title_str} 第{item_info.get('seasons')[0]}季第{item_info.get('episodes')[0]}集 转移完成"
                else:
                    if item_info.get('seasons'):
                        se_string = " ".join("S%s" % str(season).rjust(2, '0') for season in item_info.get('seasons'))
                        msg_title = f"{title_str} {se_string} 转移完成"
                    else:
                        msg_title = f"{title_str} 转移完成"

                msg_str = "类型：电视剧"
                vote_average = item_info.get('media').vote_average
                if vote_average:
                    msg_str = f"{msg_str}，评分：{vote_average}"

                if len(item_info.get('episodes')) != 1:
                    msg_str = f"{msg_str}，共{len(item_info.get('seasons'))}季{len(item_info.get('episodes'))}集，总大小：{str_filesize(item_info.get('totalsize'))}，来自：{in_from}"
                else:
                    msg_str = f"{msg_str}，大小：{str_filesize(item_info.get('totalsize'))}，来自：{in_from}"

                if item_info.get('existfiles') != 0:
                    msg_str = f"{msg_str}，{item_info.get('existfiles')}个文件已存在"

                backdrop_path = item_info.get('media').backdrop_path
                poster_path = item_info.get('media').poster_path
                msg_image = backdrop_path if backdrop_path else poster_path

                self.sendmsg(msg_title, msg_str, msg_image)
