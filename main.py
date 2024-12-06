# main.py
import argparse
import logging
import os
import queue
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from dotenv import load_dotenv

from exception import NoRightPasswd, UnpackError, PackError, RcloneError, NoExistDecompressDir, FileTooLarge
from fileprocess import FileProcess
from rclone import OwnRclone
from set_logger import setup_logger


@dataclass
class ThreadStatus:
    """
    线程管理类，通过剩余空间的90%和最大线程数调控
    """
    # 每个线程控制的最大数量
    max_thread:int = field(init=True)
    # 轮询监听时间
    heart:int = field(init=True)
    # 脚本可用的剩余空间
    _totaldisk:int = field(init=False)
    # # 剩余空间
    # _freedisk:int = field(init=False)
    # 已被挂起的空间
    _pausedisk:int = field(default=int(0))
    # 全局线程状态，set则可以继续添加
    download_continue_event: threading.Event =  field(default_factory=threading.Event)
    decompress_continue_event: threading.Event = field(default_factory=threading.Event)
    compress_continue_event: threading.Event = field(default_factory=threading.Event)
    upload_continue_event: threading.Event = field(default_factory=threading.Event)
    # 线程
    download_threads:list = field(default_factory=list)
    decompress_threads:list = field(default_factory=list)
    compress_threads:list = field(default_factory=list)
    upload_threads:list = field(default_factory=list)

    def __post_init__(self):
        self._totaldisk = self._freedisk = fileprocess.get_free_size(tmp)
        self.download_continue_event.set()
        self.decompress_continue_event.set()
        self.compress_continue_event.set()
        self.upload_continue_event.set()


    def waiting_release_disk(self):
        # 等待释放磁盘，从压缩到解压到下载逐步释放
        for event in [self.download_continue_event, self.decompress_continue_event, self.compress_continue_event]:
            event.clear()
        while True:
            # 逐步释放Thread
            if (not self.upload_threads) and (
            not self.upload_continue_event.is_set()) and self.compress_continue_event.is_set():
                self.compress_continue_event.set()

            if (not self.compress_threads) and (
            not self.compress_continue_event.is_set()) and self.decompress_continue_event.is_set():
                self.decompress_continue_event.set()

            if (not self.decompress_threads) and (
            not self.decompress_continue_event.is_set()) and self.download_continue_event.is_set():
                self.download_continue_event.set()
                break
            # 轮询休眠 heart 秒
            time.sleep(self.heart)

    @property
    def throttling(self):
        # 返回当前流控数据
        return {"totaldisk":self._totaldisk,
                "pausedisk":self._pausedisk,
                "num":{
                    "download_num":len(self.download_threads),
                    "decompress_num":len(self.decompress_threads),
                    "compress_num":len(self.compress_threads),
                    "upload_num":len(self.upload_threads)
                }}

    @throttling.setter
    def throttling(self, usedisk):
        """
        :param usedisk: 使用的磁盘
        :return: 若usedisk * 2 > _totaldisk * 0.9，则直接报错
        若 usedisk + _pausedisk > _totaldisk * 0.9,则挂起下载，解压，压缩线程池并等待上传完毕后从后到前释放
        """
        if not isinstance(usedisk, int):
            raise ValueError('usedisk must be int')
        if usedisk > self._totaldisk * 0.9:
            raise FileTooLarge(f"文件过大，文件大小为{usedisk}字节")
        self._pausedisk += usedisk
        if self._pausedisk > self._totaldisk * 0.9:
            t = threading.Thread(target=self.waiting_release_disk, daemon=True)
            t.start()

        # 锁定和解锁线程
        self.download_continue_event.clear() if len(
            self.download_threads) >= self.max_thread else self.download_continue_event.set()
        self.decompress_continue_event.clear() if len(
            self.decompress_threads) >= self.max_thread else self.decompress_continue_event.set()
        self.compress_continue_event.clear() if len(
            self.compress_threads) >= self.max_thread else self.compress_continue_event.set()
        self.upload_continue_event.clear() if len(
            self.upload_threads) >= self.max_thread else self.upload_continue_event.set()

@dataclass
class ProcessThread:
    # 文件信息
    files_info:list = field(default_factory=list)
    # 任务线程状态，set则可以继续运行
    download_continue_event: threading.Event =  field(default_factory=threading.Event)
    decompress_continue_event: threading.Event = field(default_factory=threading.Event)
    compress_continue_event: threading.Event = field(default_factory=threading.Event)
    upload_continue_event: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self):
        self.ownrclone = OwnRclone(db_file, rclone, logging=logging_capture)
        # 去掉后缀的文件名
        self.name:str = self.files_info[0]
        # 所有对应的文件路径和总大小
        self.paths:list = self.files_info[1][0]
        self.sizes:int = self.files_info[1][1]
        # 获取路径
        paths_dict = self.get_name(self.name)
        self.download = paths_dict['download']
        self.decompress = paths_dict['decompress']
        self.compress = paths_dict['compress']
        self.upload = paths_dict['upload']

    @staticmethod
    # noinspection PyUnresolvedReferences
    def get_name(name):
        # 构建路径,防止Windows作妖
        download = os.path.join(tmp, "download", name).replace("\\", "/")
        decompress = os.path.join(tmp, "decompress", name).replace("\\", "/")
        compress = os.path.join(tmp, "compress", name).replace("\\", "/")
        upload = os.path.join(dst, name).replace("\\", "/")
        return {"download": download, "decompress": decompress, "compress": compress, "upload": upload}


    def download_thread(self):
        # 传递文件大小进行流控
        ThreadStatus.throttling = self.sizes
        ProcessThread.download_continue_event.wait()
        ThreadStatus.download_continue_event.wait()
        ownrclone.copyfile(self.paths, self.download, replace_name=None)
        # 释放空间
        ThreadStatus.throttling = -self.sizes
        logging_capture.info(f"下载步骤完成: {self.name}")


    def decompress_thread(self):
        # 传递文件大小进行流控
        ThreadStatus.throttling = self.sizes
        ProcessThread.decompress_continue_event.wait()
        ThreadStatus.decompress_continue_event.wait()
        fileprocess.decompress(self.download, self.decompress, passwords=passwords)
        # 释放空间
        ThreadStatus.throttling = -self.sizes
        logging_capture.info(f"解压步骤完成: {self.name}")


    def compress_thread(self):
        # 传递文件大小进行流控
        ThreadStatus.throttling = self.sizes
        ProcessThread.compress_continue_event.wait()
        ThreadStatus.compress_continue_event.wait()
        # noinspection PyTypeChecker
        fileprocess.compress(self.decompress, self.compress, password=password,
                             mx=mx, volumes=volumes)
        # 释放空间
        ThreadStatus.throttling = -self.sizes
        logging_capture.info(f"压缩步骤完成: {self.name}")


    def upload_thread(self):
        ProcessThread.upload_continue_event.wait()
        ThreadStatus.upload_continue_event.wait()
        ownrclone.copyfile(self.compress, self.upload, replace_name=None)
        # 释放空间
        ThreadStatus.throttling = -self.sizes
        logging_capture.info(f"上传步骤完成: {self.name}")


    @classmethod
    def start_threads(cls):
        # 启动线程并添加进线程池
        thread_configs = [
            (cls.download_thread, ThreadStatus.download_threads),
            (cls.decompress_thread, ThreadStatus.decompress_threads),
            (cls.compress_thread, ThreadStatus.compress_threads),
            (cls.upload_thread, ThreadStatus.upload_threads)
        ]

        for target, thread_list in thread_configs:
            thread = threading.Thread(target=target, daemon=True)
            thread_list.append(thread)








@contextmanager
def manage_queue(queue):
    """
    上下文管理器，用于管理队列的加减操作。
    """
    try:
        task = queue.get()
        yield task  # 获取任务
    finally:
        queue.task_done()

def log_level_type(level_str):
    # 转换Env的Log Level
    try:
        # 将字符串转为大写，并根据 logging 的属性进行解析
        return getattr(logging, level_str.upper())
    except AttributeError:
        raise argparse.ArgumentTypeError(f"Invalid log level: {level_str}")

def create_worker(tasks):
    """
    创建任务，主线程
    :param tasks:
    :return:
    """
    # 创建管理线程
    threads = []
    for _ in range(MAX_THREADS):
        t = threading.Thread(target=control_worker, daemon=True)
        t.start()
        threads.append(t)
    # 添加任务到下载队列
    for task in tasks.items():
        download_queue.put(task)
    # 等待所有队列完成任务
    download_queue.join()
    decompress_queue.join()
    compress_queue.join()
    upload_queue.join()

def load_env():
    # 读取环境变量
    parser = argparse.ArgumentParser(description="自动化任务处理脚本")

    # Add command line arguments with defaults from environment variables
    parser.add_argument('--rclone', type=str, default=os.getenv('RCLONE_PATH'), help='rclone文件路径')
    parser.add_argument('--p7zip_file', type=str, default=os.getenv('P7ZIP_FILE'), help='7zip文件路径')
    parser.add_argument('--src', type=str, default=os.getenv('SRC'), help='起源目录路径')
    parser.add_argument('--dst', type=str, default=os.getenv('DST'), help='终点目录路径')
    parser.add_argument('--passwords', nargs='+', default=os.getenv('PASSWORDS', '').split(), help='解压密码列表')
    parser.add_argument('--password', type=str, default=os.getenv('PASSWORD'), help='压缩密码')
    parser.add_argument('--max_threads', type=int, default=int(os.getenv('MAX_THREADS', 2)), help='每个阶段的最大任务数量，默认2')
    parser.add_argument('--db_file', type=str, default=os.getenv('DB_FILE', './data.db'), help='数据库文件路径')
    parser.add_argument('--tmp', type=str, default=os.getenv('TMP', './tmp'), help='临时目录路径')
    parser.add_argument('--heart', type=int, default=os.getenv('HEART', 10), help='监听轮询时间，默认10')
    parser.add_argument('--mx', type=int, default=int(os.getenv('MX', 0)), help='压缩等级，默认为0即仅储存')
    parser.add_argument('--mmt', type=int, default=int(os.getenv('MMT', 4)), help='解压缩线程数')
    parser.add_argument('--volumes', type=str, default=os.getenv('VOLUMES', '4g'), help='分卷大小')
    parser.add_argument('--logfile', type=str, default=os.getenv('LOGFILE', 'AutoRclone.log'), help='日志文件路径')
    parser.add_argument('--depth', type=int, default=int(os.getenv('DEPTH', 0)), help='使用路径中的目录作为最终文件夹名的探测深度')
    parser.add_argument('--loglevel',type=log_level_type,default=os.getenv('LOGLEVEL', "INFO"), help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')

    args = parser.parse_args()
    return args

def main():
    lsjson = ownrclone.lsjson(src, args={"recurse": True, "filesOnly": True, "noMimeType": True, "noModTime": True})["list"]
    #todo 临时补丁,分离驱动器和名称，前者是不带驱动器的
    srcfs,_ = ownrclone.extract_parts(src)
    # 过滤文件列表
    filter_list = fileprocess.filter_files(lsjson,srcfs,depth)
    # 写入到sqlite3(不必担心覆盖问题)
    ownrclone.insert_data(filter_list)
    # 读取sqlite3数据,只读取未完成的数据
    tasks = ownrclone.read_data(status=0)
    logging_capture.info(f"已读取到{len(tasks)}条任务")
    create_worker(tasks)

# 覆盖系统内变量
load_dotenv(override=True)

if __name__ == "__main__":
    args = load_env()
    # Use parsed arguments
    MAX_THREADS = args.MAX_THREADS
    db_file = args.db_file
    rclone = args.rclone
    p7zip_file = args.p7zip_file
    tmp = args.tmp
    src = args.src
    dst = args.dst
    passwords = args.passwords
    password = args.password
    mx = args.mx
    mmt = args.mmt
    volumes = args.volumes
    logfile = args.logfile
    depth = args.depth
    loglevel = args.loglevel
    heart = args.heart

    # Queues for each stage
    download_queue, decompress_queue, compress_queue, upload_queue = [
        queue.Queue(maxsize=MAX_THREADS) for _ in range(4)
    ]

    # 初始化Rclone log和class实例
    logging_capture = setup_logger('AutoRclone', logfile, level=loglevel)
    ownrclone = OwnRclone(db_file, rclone, logging_capture)
    process = ownrclone.start_rclone()
    fileprocess = FileProcess(mmt=mmt, p7zip_file=p7zip_file, autodelete=True, logging=logging_capture)

    # 启动函数
    main()

    # Terminate process
    process.kill()
