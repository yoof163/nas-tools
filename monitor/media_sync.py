import os
import threading
from time import sleep

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from config import RMT_MEDIAEXT, SYNC_DIR_CONFIG, Config
import log
from rmt.filetransfer import FileTransfer
from utils.functions import get_dir_files_by_ext, singleton
from utils.types import SyncType

lock = threading.Lock()


@singleton
class Sync(object):
    filetransfer = None
    __observer = []
    __sync_path = None
    __sync_sys = "Linux"
    __config = None
    __synced_files = []
    __need_sync_paths = {}

    def __init__(self):
        self.filetransfer = FileTransfer()
        self.__config = Config()
        app = self.__config.get_config('app')
        if app:
            self.__sync_sys = app.get('nas_sys', "Linux")
        sync = self.__config.get_config('sync')
        if sync:
            self.__sync_path = sync.get('sync_path')

    # 处理文件变化
    def file_change_handler(self, event, text, event_path):
        if not event.is_directory:
            # 文件发生变化
            try:
                # 目的目录的子文件不处理
                for tpath in SYNC_DIR_CONFIG.values():
                    if tpath:
                        if tpath in event_path:
                            return
                        if os.path.samefile(event_path, tpath):
                            return
                # 回收站及隐藏的文件不处理
                if event_path.find('/@Recycle/') != -1 or event_path.find('/#recycle/') != -1 or event_path.find(
                        '/.') != -1:
                    return False
                # 文件名
                name = os.path.basename(event_path)
                if not name:
                    return
                # 判断是不是媒体文件
                ext = os.path.splitext(name)[-1]
                if ext not in RMT_MEDIAEXT:
                    return
                # 判断是否处理过了
                need_handler_flag = False
                try:
                    lock.acquire()
                    if event_path not in self.__synced_files:
                        self.__synced_files.append(event_path)
                        need_handler_flag = True
                finally:
                    lock.release()

                if not need_handler_flag:
                    log.debug("【SYNC】文件已处理过：%s" % event_path)
                    return

                log.info("【SYNC】文件%s：%s" % (text, event_path))
                # 找到是哪个监控目录下的
                monitor_dir = event_path
                from_dir = os.path.dirname(event_path)
                is_root_path = False
                for m_path in SYNC_DIR_CONFIG.keys():
                    if m_path in event_path:
                        monitor_dir = m_path
                    if os.path.samefile(m_path, from_dir):
                        is_root_path = True

                # 查找目的目录
                target_dir = SYNC_DIR_CONFIG.get(monitor_dir)
                # 监控根目录下的文件发生变化时直接发走
                if is_root_path:
                    self.filetransfer.transfer_media(in_from=SyncType.MON,
                                                     in_path=event_path,
                                                     target_dir=target_dir)
                else:
                    try:
                        lock.acquire()
                        if self.__need_sync_paths.get(from_dir):
                            files = self.__need_sync_paths.get('files')
                            if not files:
                                files = [event_path]
                            else:
                                if event_path not in files:
                                    files.append(event_path)
                                else:
                                    return
                            self.__need_sync_paths[from_dir].update({'files': files})
                        else:
                            self.__need_sync_paths[from_dir] = {'target_dir': target_dir, 'files': [event_path]}
                    finally:
                        lock.release()

            except Exception as e:
                log.error("【SYNC】发生错误：%s" % str(e))
        else:
            # 文件变化时上级文件夹也会变化
            # 目的目录的子文件不处理
            for tpath in SYNC_DIR_CONFIG.values():
                if tpath:
                    if tpath in event_path:
                        return
                    if os.path.samefile(event_path, tpath):
                        return
            # 源目录本身或上级目录不处理
            for tpath in SYNC_DIR_CONFIG.keys():
                if event_path in tpath:
                    return
                if os.path.samefile(event_path, tpath):
                    return
            # 回收站及隐藏的文件不处理
            if event_path.find('/@Recycle') != -1 or event_path.find('/#recycle') != -1 or event_path.find('/.') != -1:
                return False
            # 开始处理变化，等10秒钟，让文件充分变化
            sleep(10)
            try:
                lock.acquire()
                sync_item = self.__need_sync_paths.get(event_path)
                if sync_item:
                    sync_len = len(sync_item.get('files'))
                    file_len = len(get_dir_files_by_ext(event_path, RMT_MEDIAEXT))
                    if sync_len >= file_len:
                        # 该目录下所有的文件都发生了改变，发走
                        self.filetransfer.transfer_media(in_from=SyncType.MON,
                                                         in_path=event_path,
                                                         target_dir=sync_item.get('target_dir'))
                        del self.__need_sync_paths[event_path]
            finally:
                lock.release()

    # 批量转移文件
    def transfer_mon_files(self, no_path=None):
        try:
            lock.acquire()
            items = self.__need_sync_paths.items()
            for path, item in items:
                if path == no_path:
                    continue
                log.info("【SYNC】开始转移监控目录文件...")
                self.filetransfer.transfer_media(in_from=SyncType.MON,
                                                 in_path=path,
                                                 target_dir=item.get('target_dir'))
                del self.__need_sync_paths[path]
        finally:
            lock.release()

    # 启动进程
    def run_service(self):
        # Sync监控转移
        if self.__sync_path:
            for sync_monpath in self.__sync_path:
                # 目录是两段式，需要把配对关系存起来
                if sync_monpath.find('|') != -1:
                    # 源目录|目的目录，这个格式的目的目录在源目录同级建立
                    monpath = sync_monpath.split("|")[0]
                    target_path = sync_monpath.split("|")[1]
                    if target_path:
                        log.info("【SYNC】读取到监控目录：%s，目的目录：%s" % (monpath, target_path))
                        if not os.path.exists(target_path):
                            log.info("【SYNC】目的目录不存在，正在创建：%s" % target_path)
                            os.makedirs(target_path)
                        # 去掉末尾的/
                        if monpath.endswith('/'):
                            monpath = monpath[0:-1]
                        SYNC_DIR_CONFIG[monpath] = target_path
                else:
                    monpath = sync_monpath
                    SYNC_DIR_CONFIG[monpath] = None
                    log.info("【SYNC】读取监控目录：%s" % monpath)

                if os.path.exists(monpath):
                    if self.__sync_sys == "Linux":
                        # linux
                        observer = Observer()
                    else:
                        # 其他
                        observer = PollingObserver()
                    self.__observer.append(observer)

                    observer.schedule(FileMonitorHandler(monpath, self), path=monpath, recursive=True)
                    observer.setDaemon(False)
                    observer.start()
                    log.info("【RUN】%s 的monitor.media_sync启动..." % monpath)
                else:
                    log.error("【SYNC】%s 目录不存在！" % sync_monpath)

    # 关闭服务
    def stop_service(self):
        if self.__observer:
            for observer in self.__observer:
                observer.stop()


# 监听文件夹
class FileMonitorHandler(FileSystemEventHandler):
    sync = None

    def __init__(self, monpath, sync, **kwargs):
        super(FileMonitorHandler, self).__init__(**kwargs)
        # 监控目录 目录下面以device_id为目录存放各自的图片
        self._watch_path = monpath
        self.sync = sync

    # 重写文件创建函数，文件创建都会触发文件夹变化
    def on_created(self, event):
        self.sync.file_change_handler(event, "创建", event.src_path)

    def on_moved(self, event):
        self.sync.file_change_handler(event, "移动", event.dest_path)

    def on_modified(self, event):
        self.sync.file_change_handler(event, "修改", event.src_path)
