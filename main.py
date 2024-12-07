# main.py
import argparse
import logging
import os
import queue
import threading
import concurrent.futures
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from queue import Queue

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
    # Queue用来储存当前*所有*任务的信息
    download_queue: queue.Queue = field(default_factory=queue.Queue)
    decompress_queue:queue.Queue = field(default_factory=queue.Queue)
    compress_queue:queue.Queue = field(default_factory=queue.Queue)
    upload_queue:queue.Queue = field(default_factory=queue.Queue)
    # Threads用于储存所有的Thread
    download_threads: concurrent.futures.ThreadPoolExecutor = field(init=False)
    decompress_threads: concurrent.futures.ThreadPoolExecutor = field(init=False)
    compress_threads: concurrent.futures.ThreadPoolExecutor = field(init=False)
    upload_threads: concurrent.futures.ThreadPoolExecutor = field(init=False)


    def __post_init__(self):
        self._totaldisk = self._freedisk = fileprocess.get_free_size(tmp)
        self.download_continue_event.set()
        self.decompress_continue_event.set()
        self.compress_continue_event.set()
        self.upload_continue_event.set()
        self.download_threads = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_thread)
        self.decompress_threads = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_thread)
        self.compress_threads = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_thread)
        self.upload_threads = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_thread)


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
        # 返回当前任务流控数据
        return {"totaldisk":self._totaldisk,
                "pausedisk":self._pausedisk,
                "num":{
                    "download_num":self.download_queue.qsize(),
                    "decompress_num":self.decompress_queue.qsize(),
                    "compress_num":self.compress_queue.qsize(),
                    "upload_num":self.upload_queue.qsize()
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

@dataclass
class ProcessThread:
    #todo 传入Rclone的参数来启动
    # 文件信息
    files_info:list = field(default_factory=list)
    # 任务线程状态，set则可以继续运行
    download_continue_event: threading.Event =  field(default_factory=threading.Event)
    decompress_continue_event: threading.Event = field(default_factory=threading.Event)
    compress_continue_event: threading.Event = field(default_factory=threading.Event)
    upload_continue_event: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self):
        self.ownrclone = OwnRclone(db_file, rclone, logging=logging_capture)

    def _parse_files_info(self):
        # 解析文件信息
        name:str = self.files_info[0]
        # 所有对应的文件路径和总大小
        paths:list = self.files_info[1][0]
        sizes:int = self.files_info[1][1]
        return name, paths, sizes

    @staticmethod
    # noinspection PyUnresolvedReferences
    def _get_name(name):
        # 构建路径,防止Windows作妖
        download = os.path.join(tmp, "download", name).replace("\\", "/")
        decompress = os.path.join(tmp, "decompress", name).replace("\\", "/")
        compress = os.path.join(tmp, "compress", name).replace("\\", "/")
        upload = os.path.join(dst, name).replace("\\", "/")
        return {"download": download, "decompress": decompress, "compress": compress, "upload": upload}

    """
    接下来的四个都是独立的线程，传递Queues中的files_info
    """

    @classmethod
    def download_thread(cls,files_info):
        # 传递文件大小进行流控
        name,paths,sizes = cls._parse_files_info(files_info)
        # 创建ownrclone实例
        ownrclone = OwnRclone(db_file, rclone, logging=logging_capture)
        # 正常流控
        ThreadStatus.throttling = sizes
        ProcessThread.download_continue_event.wait()
        ThreadStatus.download_continue_event.wait()
        try:
            #todo 增加错误重试
            ownrclone.copyfile(paths, cls._get_name("download"), replace_name=None)
            logging_capture.info(f"下载步骤完成: {name}")
        except RcloneError as e:
            logging_capture.error(f"当前任务{name}下载过程出错{e}")
        except Exception as e:
            logging_capture.error(f"当前任务{name}下载过程未知出错{e}")
        # 释放空间
        ThreadStatus.throttling = -sizes
        # 添加到解压Queue当前files_info
        ThreadStatus.decompress_queue.put(files_info)

    @classmethod
    def decompress_thread(cls,files_info):
        # 传递文件大小进行流控
        name,paths,sizes = cls._parse_files_info(files_info)
        ProcessThread.decompress_continue_event.wait()
        ThreadStatus.decompress_continue_event.wait()
        try:
            #todo 增加错误重试,这里有坑，不能多次解压已成功的，没有抓响应码
            fileprocess.decompress(cls._get_name("download"), cls._get_name("decompress"), passwords=passwords)
            logging_capture.info(f"解压步骤完成: {name}")
        except UnpackError or NoExistDecompressDir as e:
            logging_capture.error(f"当前任务{name}解压过程出错{e}")
        except Exception as e:
            logging_capture.error(f"当前任务{name}解压过程未知出错{e}")
        # 释放空间
        ThreadStatus.throttling = -sizes
        ThreadStatus.compress_queue.put(files_info)

    @classmethod
    def compress_thread(cls,files_info):
        # 传递文件大小进行流控
        name,paths,sizes = cls._parse_files_info(files_info)
        ProcessThread.compress_continue_event.wait()
        ThreadStatus.compress_continue_event.wait()
        try:
            # noinspection PyTypeChecker
            fileprocess.compress(cls._get_name("decompress"), cls._get_name("compress"), password=password,
                                 mx=mx, volumes=volumes)
            logging_capture.info(f"压缩步骤完成: {name}")
        except PackError as e:
            logging_capture.error(f"当前任务{name}压缩过程出错{e}")
        except Exception as e:
            logging_capture.error(f"当前任务{name}压缩过程未知出错{e}")
        # 释放空间
        ThreadStatus.throttling = -sizes
        ThreadStatus.upload_queue.put(files_info)

    @classmethod
    def upload_thread(cls,files_info):
        # 传递文件大小进行流控
        name,paths,sizes = cls._parse_files_info(files_info)
        # 创建ownrclone实例
        ownrclone = OwnRclone(db_file, rclone, logging=logging_capture)
        ProcessThread.upload_continue_event.wait()
        ThreadStatus.upload_continue_event.wait()
        try:
            ownrclone.copyfile(cls._get_name("compress"), cls._get_name("upload"), replace_name=None)
            logging_capture.info(f"上传步骤完成: {name}")
        except RcloneError as e:
            logging_capture.error(f"当前任务{name}上传过程出错{e}")
        except Exception as e:
            logging_capture.error(f"当前任务{name}上传过程未知出错{e}")
        # 释放空间
        ThreadStatus.throttling = -sizes

    @staticmethod
    def _start_threads(queue: Queue, threads: concurrent.futures.ThreadPoolExecutor) -> None:
        # 把每个ThreadStatusQueue的内容用来启动线程
        while not queue.empty():
            # 启动线程并添加到线程池
            t = queue.get()
            t.start()
            threads.submit(t)
            threads.add_done_callback()

    @classmethod
    def start_threads(cls):
        # 循环把每个ThreadStatus Queue的内容用来启动线程
        while True:
            cls._start_threads(ThreadStatus.download_queue,ThreadStatus.download_threads)
            cls._start_threads(ThreadStatus.decompress_queue,ThreadStatus.decompress_threads)
            cls._start_threads(ThreadStatus.compress_queue,ThreadStatus.compress_threads)
            cls._start_threads(ThreadStatus.upload_queue,ThreadStatus.upload_threads)


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

    # 初始化Rclone log和class实例
    logging_capture = setup_logger('AutoRclone', logfile, level=loglevel)
    ownrclone = OwnRclone(db_file, rclone, logging_capture)
    process = ownrclone.start_rclone()
    fileprocess = FileProcess(mmt=mmt, p7zip_file=p7zip_file, autodelete=True, logging=logging_capture)

    # 启动函数
    main()

    # Terminate process
    process.kill()
