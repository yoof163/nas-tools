from enum import Enum


class MediaType(Enum):
    TV = '电视剧'
    MOVIE = '电影'


class DownloaderType(Enum):
    QB = 'Qbittorrent'
    TR = 'Transmission'


class SyncType(Enum):
    MAN = "手动整理"
    MON = "目录监控"


class MediaCatagory(Enum):
    DM = "动漫"
    JLP = "纪录片"
    RT = "儿童"
    ZY = "综艺"
    GCJ = "国产剧"
    OMJ = "欧美剧"
    RHJ = "日韩剧"
    QTJ = "其它剧"
    HYDY = "华语电影"
    WYDY = "外语电影"
    JXDY = "精选"


class SearchType(Enum):
    WX = "微信搜索"
    WEB = "WEB搜索"
    DB = "豆瓣收藏"
    RSS = "RSS订阅"
    OT = "其它"


class RmtMode(Enum):
    LINK = "硬链接"
    SOFTLINK = "软链接"
    COPY = "复制"
