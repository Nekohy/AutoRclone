# main.py
import argparse
import concurrent.futures
import logging
import os
import queue
import shutil
import threading
import time
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from queue import Queue
from typing import Callable

from dotenv import load_dotenv

from Exception import NoRightPasswd, UnpackError, PackError, RcloneError, NoExistDecompressDir, FileTooLarge
from fileprocess import FileProcess
from rclone import OwnRclone, DataBase
from set_logger import setup_logger


@dataclass
class ThreadStatus:
    """
    线程管理类，通过剩余空间的90%和最大线程数调控
    """
    # 每个线程控制的最大数量
    max_thread:int = field(init=True)
    max_spaces:int = field(init=True)
    # 轮询监听时间
    heart:int = field(init=True)
    # 全局线程状态，set则可以继续添加
    download_continue_event: threading.Event =  field(default_factory=threading.Event)
    decompress_continue_event: threading.Event = field(default_factory=threading.Event)
    compress_continue_event: threading.Event = field(default_factory=threading.Event)
    upload_continue_event: threading.Event = field(default_factory=threading.Event)
    # Queue用来全局储存当前*所有*任务的Files_info
    download_queue: queue.Queue = field(default_factory=queue.Queue)
    decompress_queue:queue.Queue = field(default_factory=queue.Queue)
    compress_queue:queue.Queue = field(default_factory=queue.Queue)
    upload_queue:queue.Queue = field(default_factory=queue.Queue)


    def __post_init__(self):
        self._totaldisk = self._freedisk = self.max_spaces
        self._pausedisk = int(0)
        # 设置事件可继续
        self.download_continue_event.set()
        self.decompress_continue_event.set()
        self.compress_continue_event.set()
        self.upload_continue_event.set()
        # Threads用于储存所有的Threads,最大值为max_thread
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
        :return:
        若 usedisk < 0,则为释放
        若 usedisk * 2 > _totaldisk * 0.9，则直接报错
        若 usedisk + _pausedisk > _totaldisk * 0.9,则挂起下载，解压，压缩线程池并等待上传完毕后从后到前释放
        """
        if not isinstance(usedisk, int):
            raise ValueError('usedisk must be int')
        self._pausedisk += usedisk
        if usedisk < 0:
            return
        if usedisk > self._totaldisk * 0.9:
            raise FileTooLarge(f"文件过大，文件大小为{usedisk}字节")
        if self._pausedisk > self._totaldisk * 0.9:
            t = threading.Thread(target=self.waiting_release_disk, daemon=True)
            t.start()



@dataclass
class ProcessThread:

    # todo 传入Rclone的参数来启动

    @classmethod
    def _parse_files_info(cls, files_info):
        # 解析文件信息
        name: str = files_info[0]
        # 所有对应的文件路径和总大小
        paths: list = files_info[1]['paths']
        sizes: int = files_info[1]['total_size']
        return name, paths, sizes

    @staticmethod
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
        database = DataBase(db_file)
        # 传递文件大小进行流控
        name,paths,sizes = cls._parse_files_info(files_info)
        # 正常流控
        threadstatus.throttling = sizes
        threadstatus.download_continue_event.wait()
        try:
            for file in paths:
                rclone.copyfile(file, cls._get_name(name)["download"], replace_name=None)
            logging_capture.info(f"下载步骤完成: {name}")
            database.update_status(basename=name, step=1)
        except RcloneError as e:
            logging_capture.error(f"当前任务{name}下载过程出错{e}")
            database.update_status(basename=name,step=1,status=3)
            raise
        except Exception as e:
            logging_capture.error(f"当前任务{name}下载过程未知出错{e}")
            database.update_status(basename=name, step=1, status=4)
            raise
        finally:
            # 释放空间
            threadstatus.throttling = -sizes
            # 添加到解压Queue当前files_info
            threadstatus.decompress_queue.put(files_info)

    @classmethod
    def decompress_thread(cls,files_info):
        # 传递文件大小进行流控
        name,paths,sizes = cls._parse_files_info(files_info)
        threadstatus.decompress_continue_event.wait()
        try:
            #todo 增加错误重试,这里有坑，不能多次解压已成功的，没有抓响应码
            fileprocess.decompress(cls._get_name(name)["download"], cls._get_name(name)["decompress"], passwords=passwords)
            logging_capture.info(f"解压步骤完成: {name}")
            database.update_status(basename=name, step=2)
        except NoRightPasswd:
            logging_capture.warning(f"当前任务{name}无正确的解压密码")
            database.update_status(basename=name, step=2,status=2)
            raise
        except NoExistDecompressDir:
            logging_capture.warning(f"当前任务{name}不存在")
            database.update_status(basename=name, step=2, status=3)
            raise
        except UnpackError as e:
            logging_capture.error(f"当前任务{name}解压过程出错{e}")
            database.update_status(basename=name, step=2, status=3)
            raise
        except Exception as e:
            logging_capture.error(f"当前任务{name}解压过程未知出错{e}")
            database.update_status(basename=name, step=2, status=4)
            raise
        finally:
            # 释放空间
            shutil.rmtree(str(cls._get_name(name)["download"]))
            threadstatus.throttling = -sizes
            threadstatus.compress_queue.put(files_info)

    @classmethod
    def compress_thread(cls,files_info):
        # 传递文件大小进行流控
        name,paths,sizes = cls._parse_files_info(files_info)
        threadstatus.compress_continue_event.wait()
        try:
            # noinspection PyTypeChecker
            fileprocess.compress(cls._get_name(name)["decompress"], cls._get_name(name)["compress"], password=password,
                                 mx=mx, volumes=volumes)
            logging_capture.info(f"压缩步骤完成: {name}")
            database.update_status(basename=name, step=3)
        except PackError as e:
            logging_capture.error(f"当前任务{name}压缩过程出错{e}")
            database.update_status(basename=name, step=3, status=3)
            raise
        except Exception as e:
            logging_capture.error(f"当前任务{name}压缩过程未知出错{e}")
            database.update_status(basename=name, step=3, status=4)
            raise
        finally:
            # 释放空间
            shutil.rmtree(str(cls._get_name(name)["decompress"]))
            threadstatus.throttling = -sizes
            threadstatus.upload_queue.put(files_info)

    @classmethod
    def upload_thread(cls,files_info):
        # 传递文件大小进行流控
        name,paths,sizes = cls._parse_files_info(files_info)
        threadstatus.upload_continue_event.wait()
        try:
            rclone.copyfile(cls._get_name(name)["compress"],cls._get_name(name)["upload"], replace_name=None)
            logging_capture.info(f"上传步骤完成: {name}")
            database.update_status(basename=name, step=4,status=1)
        except RcloneError as e:
            logging_capture.error(f"当前任务{name}上传过程出错{e}")
            database.update_status(basename=name, step=4, status=3)
            raise
        except Exception as e:
            logging_capture.error(f"当前任务{name}上传过程未知出错{e}")
            database.update_status(basename=name, step=4, status=4)
            raise
        finally:
            # 释放空间
            shutil.rmtree(str(cls._get_name(name)["compress"]))
            threadstatus.throttling = -sizes

    @staticmethod
    def parse_return_result(future):
        pass

    @classmethod
    def _start_threads(cls, function:Callable, queue: Queue,threads:ThreadPoolExecutor) -> None:
        # 把每个ThreadStatusQueue的内容用来启动线程
        while not queue.empty():
            # 把现有的Queue转换为可以传入的list
            data_list = [queue.get_nowait() for _ in range(queue.qsize())]
            # 提交任务但不等待
            futures = [threads.submit(function, data) for data in data_list]

            # 为每个future添加回调，但不等待完成
            for future in futures:
                future.add_done_callback(lambda f: cls.parse_return_result(f))

    @classmethod
    def start_threads(cls):
        # 循环把每个threadstatus Queue的内容用来启动线程
        while True:
            cls._start_threads(function=cls.download_thread,queue=threadstatus.download_queue,threads=threadstatus.download_threads)
            cls._start_threads(function=cls.decompress_thread,queue=threadstatus.decompress_queue,threads=threadstatus.decompress_threads)
            cls._start_threads(function=cls.compress_thread,queue=threadstatus.compress_queue,threads=threadstatus.compress_threads)
            cls._start_threads(function=cls.upload_thread,queue=threadstatus.upload_queue,threads=threadstatus.upload_threads)


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
    parser.add_argument('--console_log',type=bool,default=os.getenv('CONSOLE_LOG', True),help='是否输出到控制台')
    parser.add_argument('--max_spaces',type=int,default=os.getenv("MAX_SPACES",0),help='脚本允许使用的最大缓存空间,单位字节，为0为不限制（均预留10%容灾空间）')
    args = parser.parse_args()
    return args


def main():
    lsjson = rclone.lsjson(src, args={"recurse": True, "filesOnly": True, "noMimeType": True, "noModTime": True})["list"]
    #todo 临时补丁,分离驱动器和名称，前者是不带驱动器的
    srcfs,_ = rclone.extract_parts(src)
    # 过滤文件列表
    filter_list = fileprocess.filter_files(lsjson,srcfs,depth)
    # 写入到sqlite3(不必担心覆盖问题)
    database.insert_data(filter_list)
    # 读取sqlite3数据,只读取未完成的数据
    tasks = database.read_data(status=0)
    # 写入到Queue
    for task in tasks.items():
        threadstatus.download_queue.put(task)
    logging_capture.info(f"已读取到{len(tasks)}条任务")
    # 启动线程
    ProcessThread.start_threads()

# 覆盖系统内变量
load_dotenv(override=True)

if __name__ == "__main__":
    args = load_env()
    # Use parsed arguments
    max_threads = args.max_threads
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
    console_log = args.console_log
    max_spaces = args.max_spaces

    # 初始化实例
    logging_capture = setup_logger(logger_name='AutoRclone', log_file=logfile,console_log=console_log,level=loglevel)
    database = DataBase(db_file)
    rclone = OwnRclone(rclone)
    fileprocess = FileProcess(mmt=mmt, p7zip_file=p7zip_file, autodelete=True)
    # 传递空间，若为0则不限制，否则限制空间
    threadstatus = ThreadStatus(max_thread=max_threads, heart=heart, max_spaces=max_spaces if max_spaces == 0 else fileprocess.get_free_size(tmp))

    # 启动rclone
    rclone.start_rclone()

    # 启动函数
    main()
