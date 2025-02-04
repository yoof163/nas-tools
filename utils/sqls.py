import os.path
import time

from utils.db_helper import update_by_sql, select_by_sql
from utils.functions import str_filesize, xstr
from utils.types import MediaType


# 将Jackett返回信息插入数据库
def insert_jackett_results(media_item):
    sql = "INSERT INTO JACKETT_TORRENTS(" \
          "TORRENT_NAME," \
          "ENCLOSURE," \
          "DESCRIPTION," \
          "TYPE," \
          "TITLE," \
          "YEAR," \
          "SEASON," \
          "EPISODE," \
          "ES_STRING," \
          "VOTE," \
          "IMAGE," \
          "RES_TYPE," \
          "RES_ORDER," \
          "SIZE," \
          "SEEDERS," \
          "PEERS," \
          "SITE," \
          "SITE_ORDER) VALUES (" \
          "'%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s','%s')" % (
              media_item.org_string,
              media_item.enclosure,
              media_item.description,
              "TV" if media_item.type == MediaType.TV else "MOV",
              media_item.title,
              xstr(media_item.year),
              media_item.get_season_string(),
              media_item.get_episode_string(),
              media_item.get_season_episode_string(),
              media_item.vote_average,
              media_item.backdrop_path,
              media_item.get_resource_type_string(),
              media_item.res_order,
              str_filesize(int(media_item.size)),
              media_item.seeders,
              media_item.peers,
              media_item.site,
              media_item.site_order
          )
    return update_by_sql(sql)


# 根据ID从数据库中查询Jackett检索结果的一条记录
def get_jackett_result_by_id(dl_id):
    sql = "SELECT ENCLOSURE,TITLE,YEAR,SEASON,EPISODE,VOTE,IMAGE,TYPE FROM JACKETT_TORRENTS WHERE ID=%s" % dl_id
    return select_by_sql(sql)


# 查询Jackett检索结果的所有记录
def get_jackett_results():
    sql = "SELECT ID,TITLE||' ('||YEAR||') '||ES_STRING,RES_TYPE,SIZE,SEEDERS,ENCLOSURE,SITE,YEAR,ES_STRING,IMAGE,TYPE,VOTE*1,TORRENT_NAME,DESCRIPTION FROM JACKETT_TORRENTS ORDER BY TITLE, SEEDERS DESC"
    return select_by_sql(sql)


# 查询电影关键字
def get_movie_keys():
    sql = "SELECT NAME FROM RSS_MOVIEKEYS"
    return select_by_sql(sql)


# 查询电视剧关键字
def get_tv_keys():
    sql = "SELECT NAME FROM RSS_TVKEYS"
    return select_by_sql(sql)


# 删除全部电影关键字
def delete_all_movie_keys():
    sql = "DELETE FROM RSS_MOVIEKEYS"
    return update_by_sql(sql)


# 删除全部电视剧关键字
def delete_all_tv_keys():
    sql = "DELETE FROM RSS_TVKEYS"
    return update_by_sql(sql)


# 插入电影关键字
def insert_movie_key(key):
    sql = "SELECT 1 FROM RSS_MOVIEKEYS WHERE NAME = '%s'" % key
    ret = select_by_sql(sql)
    if not ret or len(ret) == 0:
        sql = "INSERT INTO RSS_MOVIEKEYS(NAME) VALUES ('%s')" % key
        return update_by_sql(sql)
    else:
        return False


# 插入电视剧关键字
def insert_tv_key(key):
    sql = "SELECT 1 FROM RSS_TVKEYS WHERE NAME = '%s'" % key
    ret = select_by_sql(sql)
    if not ret or len(ret) == 0:
        sql = "INSERT INTO RSS_TVKEYS(NAME) VALUES ('%s')" % key
        return update_by_sql(sql)
    else:
        return False


# 查询RSS是否处理过，根据链接
def is_torrent_rssd_by_url(url):
    sql = "SELECT 1 FROM RSS_TORRENTS WHERE ENCLOSURE = '%s'" % url
    ret = select_by_sql(sql)
    if not ret:
        return False
    if len(ret) > 0:
        return True
    return False


# 查询RSS是否处理过，根据名称
def is_torrent_rssd_by_name(media_title, media_year, media_seaion, media_episode):
    if not media_title:
        return True
    sql = "SELECT 1 FROM RSS_TORRENTS WHERE TITLE = '%s'" % media_title
    if media_year:
        sql = "%s AND YEAR='%s'" % (sql, media_year)
    if media_seaion:
        sql = "%s AND SEASON='%s'" % (sql, media_seaion)
    if media_episode:
        sql = "%s AND EPISODE='%s'" % (sql, media_episode)
    ret = select_by_sql(sql)
    if not ret:
        return False
    if len(ret) > 0:
        return True
    return False


# 删除所有JACKETT的记录
def delete_all_jackett_torrents():
    return update_by_sql("DELETE FROM JACKETT_TORRENTS")


# 将RSS的记录插入数据库
def insert_rss_torrents(media_info):
    sql = "INSERT INTO RSS_TORRENTS(TORRENT_NAME, ENCLOSURE, TYPE, TITLE, YEAR, SEASON, EPISODE) VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s')" % (
        media_info.title, media_info.enclosure, media_info.type, media_info.title, media_info.year,
        media_info.get_season_string(), media_info.get_episode_string())
    return update_by_sql(sql)


# 将豆瓣的数据插入数据库
def insert_douban_media_state(media, state):
    if not media.year:
        sql = "DELETE FROM DOUBAN_MEDIAS WHERE NAME = '%s'" % media.get_name()
    else:
        sql = "DELETE FROM DOUBAN_MEDIAS WHERE NAME = '%s' AND YEAR = '%s'" % (media.get_name(), media.year)
    # 先删除
    update_by_sql(sql)
    sql = "INSERT INTO DOUBAN_MEDIAS(NAME, YEAR, TYPE, RATING, IMAGE, STATE) VALUES ('%s', '%s', '%s', '%s', '%s', '%s')" % (
        media.get_name(), media.year, media.type.value, media.vote_average, media.poster_path, state)
    # 再插入
    return update_by_sql(sql)


# 标记豆瓣数据的状态
def update_douban_media_state(media, state):
    sql = "UPDATE DOUBAN_MEDIAS SET STATE = '%s' WHERE NAME = '%s' AND YEAR = '%s'" % (state, media.title, media.year)
    return update_by_sql(sql)


# 查询未检索的豆瓣数据
def get_douban_search_state(title, year):
    sql = "SELECT STATE FROM DOUBAN_MEDIAS WHERE NAME = '%s' AND YEAR = '%s'" % (title, year)
    return select_by_sql(sql)


# 插入识别转移记录
def insert_transfer_history(in_from, rmt_mode, in_path, dest, media_info):
    if not media_info or not media_info.tmdb_info:
        return
    file_path = os.path.dirname(in_path)
    file_name = os.path.basename(in_path)
    timestr = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    sql = "INSERT INTO TRANSFER_HISTORY(SOURCE, MODE, TYPE, FILE_PATH, FILE_NAME, TITLE, CATEGORY, YEAR, SE, DEST, DATE) VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')" % (
        in_from.value, rmt_mode.value, media_info.type.value, file_path, file_name, media_info.title, media_info.category.value, media_info.year, media_info.get_season_episode_string(), dest, timestr)
    return update_by_sql(sql)


# 查询识别转移记录
def get_transfer_history(search, page, rownum):
    if page == 1:
        begin_pos = 0
    else:
        begin_pos = (page-1) * rownum

    if search:
        count_sql = f"SELECT COUNT(1) FROM TRANSFER_HISTORY WHERE FILE_NAME LIKE '%{search}%' OR TITLE LIKE '%{search}%'"
        sql = f"SELECT SOURCE, MODE, TYPE, FILE_NAME, TITLE, CATEGORY, YEAR, SE, DEST, DATE FROM TRANSFER_HISTORY WHERE FILE_NAME LIKE '%{search}%' OR TITLE LIKE '%{search}%' LIMIT {rownum} OFFSET {begin_pos}"
    else:
        count_sql = f"SELECT COUNT(1) FROM TRANSFER_HISTORY"
        sql = f"SELECT SOURCE, MODE, TYPE, FILE_NAME, TITLE, CATEGORY, YEAR, SE, DEST, DATE FROM TRANSFER_HISTORY LIMIT {rownum} OFFSET {begin_pos}"
    return select_by_sql(count_sql), select_by_sql(sql)
