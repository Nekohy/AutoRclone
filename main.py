# main.py
import argparse
import concurrent.futures
import logging
import os
from queue import Queue, Empty
import shutil
import threading
import time
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Any
from threading import Lock

import psutil
from dotenv import load_dotenv
from flask import Flask, jsonify

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
    download_queue: Queue = field(default_factory=Queue)
    decompress_queue:Queue = field(default_factory=Queue)
    compress_queue:Queue = field(default_factory=Queue)
    upload_queue:Queue = field(default_factory=Queue)
    # 活跃的下载
    active_download: int = field(default=0)
    active_decompress: int = field(default=0)
    active_compress: int = field(default=0)
    active_upload: int = field(default=0)
    lock: Lock = field(default_factory=Lock)
    # 通过这些计数器的新锁确保线程安全
    aggregate_lock: Lock = field(default_factory=Lock)
    total_completed: int = field(default=0)
    total_errors: int = field(default=0)
    unfinished_tasks: int = field(default=0)
    total_tasks: int = field(default=0)

    # 网络速度监控属性
    _prev_net_io: psutil._common.snetio = field(default_factory=lambda: psutil.net_io_counters())
    _prev_time: float = field(default_factory=lambda: time.time())
    _upload_speed: float = field(default=0.0)  # MB/s
    _download_speed: float = field(default=0.0)  # MB/s


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
        self.decompress_threads = concurrent.futures.ThreadPoolExecutor()
        self.compress_threads = concurrent.futures.ThreadPoolExecutor()
        self.upload_threads = concurrent.futures.ThreadPoolExecutor()


    def update_network_speed(self):
        current_net_io = psutil.net_io_counters()
        current_time = time.time()
        time_diff = current_time - self._prev_time

        # 计算上传和下载速度（Bytes/s）
        bytes_sent_diff = current_net_io.bytes_sent - self._prev_net_io.bytes_sent
        bytes_recv_diff = current_net_io.bytes_recv - self._prev_net_io.bytes_recv

        if time_diff > 0:
            # 转换为 MB/s
            self._upload_speed = bytes_sent_diff / time_diff / (1024 * 1024)
            self._download_speed = bytes_recv_diff / time_diff / (1024 * 1024)
        # 更新之前的值
        self._prev_net_io = current_net_io
        self._prev_time = current_time


    # 暂时用不上
    def waiting_release_disk(self):
        # 等待释放磁盘，从压缩到解压到下载逐步释放
        for event in [self.download_continue_event, self.decompress_continue_event, self.compress_continue_event]:
            event.clear()
        while True:
            # 逐步释放Thread
            if not self.upload_threads:
                self.compress_continue_event.set()

            if not self.compress_threads:
                self.decompress_continue_event.set()

            if not self.decompress_threads:
                self.download_continue_event.set()
                logging_capture.info(f"所有线程已完成，释放线程池")

            if self.download_continue_event.is_set() and self.decompress_continue_event.is_set() and self.compress_continue_event.is_set() and self.upload_continue_event.is_set():
                # 退出循环
                break

            # 轮询休眠 heart 秒
            time.sleep(self.heart)

    # 在 throttling 属性中添加 active 任务
    @property
    def throttling(self):
        with self.lock, self.aggregate_lock:
            # 更新网络速度
            self.update_network_speed()

            # 获取CPU使用率
            cpu_usage = psutil.cpu_percent(interval=None)

            # 获取CPU核心数量
            cpu_cores = psutil.cpu_count(logical=True)

            # 获取内存信息
            memory = psutil.virtual_memory()
            memory_usage = memory.percent
            total_memory = memory.total  # 总内存（Bytes）
            available_memory = memory.available  # 可用内存（Bytes）

            return {
                "totaldisk": self._totaldisk,
                "pausedisk": self._pausedisk,
                "active": {
                    "active_download": self.active_download,
                    "active_decompress": self.active_decompress,
                    "active_compress": self.active_compress,
                    "active_upload": self.active_upload,
                },
                "total_completed": self.total_completed,
                "total_errors": self.total_errors,
                "unfinished_tasks": self.unfinished_tasks,
                "total_tasks": self.total_tasks,
                "system": {
                    "cpu_usage_percent": cpu_usage /100,
                    "cpu_cores": cpu_cores,
                    "memory": {
                        "total_memory_bytes": total_memory,
                        "available_memory_bytes": available_memory,
                        "memory_usage_percent": memory_usage
                    },
                    "network": {
                        "upload_speed_mbps": self._upload_speed,
                        "download_speed_mbps": self._download_speed,
                    }
                }
            }

    @throttling.setter
    def throttling(self, usedisk):
        """
        :param usedisk: 使用的磁盘
        :return:
        若 usedisk < 0,则为释放
        若 usedisk > _totaldisk * 0.9，则直接报错
        若 usedisk + _pausedisk > _totaldisk * 0.9,则挂起下载，解压，压缩线程池并等待上传完毕后从后到前释放
        """
        self._pausedisk += usedisk
        if usedisk <= 0:
            logging_capture.info(f"已释放空间{usedisk},目前暂停{self._pausedisk},总空间{self._totaldisk * 0.9}")
            if self._pausedisk <= self._totaldisk * 0.9 and not self.download_continue_event.is_set():
                logging_capture.info(f"已有足够空间，释放线程池")
                # 退出循环
                self.download_continue_event.set()
        elif usedisk > 0:
            if usedisk > self._totaldisk * 0.9:
                self._pausedisk -= usedisk
                raise FileTooLarge(f"文件过大，文件大小为{usedisk}字节")
            if self._pausedisk >= self._totaldisk * 0.9:
                logging_capture.warning(f"目前已预留空间{self._pausedisk},总空间{self._totaldisk * 0.9},等待目前有释放空间后释放线程")
                self.download_continue_event.clear()

    # 添加方法以更新计数器

    def increment_completed(self):
        with self.aggregate_lock:
            self.total_completed += 1
            self.unfinished_tasks -= 1

    def increment_errors(self):
        with self.aggregate_lock:
            self.total_errors += 1
            self.unfinished_tasks -= 1

    def add_tasks(self, count: int):
        with self.aggregate_lock:
            self.total_tasks += count
            self.unfinished_tasks += count

# ProcessThread 类
@dataclass
class ProcessThread:
    download_magnification = 1
    # 正常流控, 按10 % 压缩率算吧
    decompress_magnification = compress_magnification = 1.1

    # todo 传入Rclone的参数来启动

    @classmethod
    def _parse_files_info(cls, files_info):
        """
        解析文件信息
        :param files_info: 文件信息
        :return: 返回文件名、路径列表和总大小
        """
        name: str = files_info[0]
        # 所有对应的文件路径和总大小
        paths: list = files_info[1]['paths']
        sizes: int = files_info[1]['total_size']
        return name, paths, sizes

    @staticmethod
    def _get_name(name):
        """
        构建各阶段的路径，防止Windows路径问题
        :param name: 文件名
        :return: 返回包含各阶段路径的字典
        """
        download = os.path.join(tmp, "download", name).replace("\\", "/")
        decompress = os.path.join(tmp, "decompress", name).replace("\\", "/")
        compress = os.path.join(tmp, "compress", name).replace("\\", "/")
        # todo 修改此处upload为目录树
        upload = os.path.join(dst, name).replace("\\", "/")
        return {"download": download, "decompress": decompress, "compress": compress, "upload": upload}

    """
    接下来的四个都是独立的线程，传递Queues中的files_info
    """

    @classmethod
    def download_thread(cls, files_info):
        """
        下载线程
        :param files_info: 文件信息
        """
        name, paths, sizes = cls._parse_files_info(files_info)
        pause_sizes = sizes * (cls.download_magnification + cls.decompress_magnification + cls.compress_magnification)
        release_sizes = 0
        try:
            # 等待下载事件被设置
            threadstatus.download_continue_event.wait()
            with threadstatus.lock:
                threadstatus.active_download += 1
                threadstatus.throttling = pause_sizes
            logging_capture.info(f"开始下载: {name}，大小{sizes}字节")
            for file in paths:
                rclone.copyfile(file, cls._get_name(name)["download"], replace_name=None)
            logging_capture.info(f"下载步骤完成: {name}")
            database.update_status(basename=name, step=1)
            # 添加到解压Queue当前files_info
            threadstatus.decompress_queue.put(files_info)
            # 更新总完成任务数
            threadstatus.increment_completed()
        except (RcloneError, FileTooLarge) as e:
            logging_capture.error(f"当前任务{name}下载过程出错: {e}")
            database.update_status(basename=name, step=1, status=3, log=str(e))
            # 更新总错误任务数
            threadstatus.increment_errors()
            threadstatus.throttling = -pause_sizes
            shutil.rmtree(str(cls._get_name(name)["download"]), ignore_errors=True)
        except Exception as e:
            logging_capture.error(f"当前任务{name}下载过程未知出错: {e}")
            database.update_status(basename=name, step=1, status=4, log=str(e))
            # 更新总错误任务数
            threadstatus.increment_errors()
            threadstatus.throttling = -pause_sizes
            shutil.rmtree(str(cls._get_name(name)["download"]), ignore_errors=True)
        finally:
            threadstatus.throttling = -release_sizes
            with threadstatus.lock:
                threadstatus.active_download -= 1

    @classmethod
    def decompress_thread(cls, files_info):
        """
        解压线程
        :param files_info: 文件信息
        """
        name, paths, sizes = cls._parse_files_info(files_info)
        pause_sizes = sizes * (cls.decompress_magnification + cls.compress_magnification)
        release_sizes = sizes * cls.download_magnification
        try:
            # 等待解压事件被设置
            threadstatus.decompress_continue_event.wait()
            with threadstatus.lock:
                threadstatus.active_decompress += 1
            # todo 增加错误重试,这里有坑，不能多次解压已成功的，没有抓响应码
            logging_capture.info(f"开始解压: {name}")
            fileprocess.decompress(cls._get_name(name)["download"], cls._get_name(name)["decompress"], passwords=passwords)
            logging_capture.info(f"解压步骤完成: {name}")
            database.update_status(basename=name, step=2)
            # 添加到压缩Queue当前files_info
            threadstatus.compress_queue.put(files_info)
            # 更新总完成任务数
            threadstatus.increment_completed()
        except NoRightPasswd:
            log = f"当前任务{name}无正确的解压密码"
            logging_capture.warning(log)
            database.update_status(basename=name, step=2, status=2, log=log)
            # 更新总错误任务数
            threadstatus.throttling = -pause_sizes
            threadstatus.increment_errors()
            shutil.rmtree(str(cls._get_name(name)["decompress"]), ignore_errors=True)
        except NoExistDecompressDir:
            log = f"当前任务{name}不存在解压目录"
            logging_capture.warning(log)
            database.update_status(basename=name, step=2, status=3, log=log)
            # 更新总错误任务数
            threadstatus.throttling = -pause_sizes
            threadstatus.increment_errors()
            shutil.rmtree(str(cls._get_name(name)["decompress"]), ignore_errors=True)
        except UnpackError as e:
            log = f"当前任务{name}解压过程出错: {e}"
            logging_capture.error(log)
            database.update_status(basename=name, step=2, status=3, log=log)
            # 更新总错误任务数
            threadstatus.throttling = -pause_sizes
            threadstatus.increment_errors()
            shutil.rmtree(str(cls._get_name(name)["decompress"]), ignore_errors=True)
        except Exception as e:
            log = f"当前任务{name}解压过程未知出错: {e}"
            logging_capture.error(log)
            database.update_status(basename=name, step=2, status=4, log=log)
            # 更新总错误任务数
            threadstatus.throttling = -pause_sizes
            threadstatus.increment_errors()
            shutil.rmtree(str(cls._get_name(name)["decompress"]), ignore_errors=True)
        finally:
            # 释放下载阶段占用的磁盘空间
            shutil.rmtree(str(cls._get_name(name)["download"]), ignore_errors=True)
            threadstatus.throttling = -release_sizes
            with threadstatus.lock:
                threadstatus.active_decompress -= 1

    @classmethod
    def compress_thread(cls, files_info):
        """
        压缩线程
        :param files_info: 文件信息
        """
        name, paths, sizes = cls._parse_files_info(files_info)
        pause_sizes = sizes * cls.compress_magnification
        release_sizes = sizes * cls.decompress_magnification
        try:
            # 等待压缩事件被设置
            threadstatus.compress_continue_event.wait()
            with threadstatus.lock:
                threadstatus.active_compress += 1
            logging_capture.info(f"开始压缩: {name}")
            # noinspection PyTypeChecker
            fileprocess.compress(
                cls._get_name(name)["decompress"],
                cls._get_name(name)["compress"],
                password=password,
                mx=mx,
                volumes=volumes
            )
            logging_capture.info(f"压缩步骤完成: {name}")
            database.update_status(basename=name, step=3)
            # 添加到上传Queue当前files_info
            threadstatus.upload_queue.put(files_info)
            # 更新总完成任务数
            threadstatus.increment_completed()
        except PackError as e:
            log = f"当前任务{name}压缩过程出错: {e}"
            logging_capture.error(log)
            database.update_status(basename=name, step=3, status=3, log=log)
            # 更新总错误任务数
            threadstatus.increment_errors()
            threadstatus.throttling = -pause_sizes
            shutil.rmtree(str(cls._get_name(name)["compress"]), ignore_errors=True)
        except Exception as e:
            log = f"当前任务{name}压缩过程未知出错: {e}"
            logging_capture.error(log)
            database.update_status(basename=name, step=3, status=4, log=log)
            # 更新总错误任务数
            threadstatus.increment_errors()
            threadstatus.throttling = -pause_sizes
            shutil.rmtree(str(cls._get_name(name)["compress"]), ignore_errors=True)
        finally:
            # 释放解压阶段占用的磁盘空间
            shutil.rmtree(str(cls._get_name(name)["decompress"]), ignore_errors=True)
            threadstatus.throttling = -release_sizes
            with threadstatus.lock:
                threadstatus.active_compress -= 1

    @classmethod
    def upload_thread(cls, files_info):
        """
        上传线程
        :param files_info: 文件信息
        """
        name, paths, sizes = cls._parse_files_info(files_info)
        pause_sizes = 0
        release_sizes = sizes * cls.compress_magnification
        try:
            # 等待上传事件被设置
            threadstatus.upload_continue_event.wait()
            with threadstatus.lock:
                threadstatus.active_upload += 1
            logging_capture.info(f"开始上传: {name}")
            rclone.move(cls._get_name(name)["compress"], cls._get_name(name)["upload"])
            logging_capture.info(f"上传步骤完成: {name}")
            database.update_status(basename=name, step=4, status=1)
            # 更新总完成任务数
            threadstatus.increment_completed()
        except RcloneError as e:
            log = f"当前任务{name}上传过程出错: {e}"
            logging_capture.error(log)
            database.update_status(basename=name, step=4, status=3, log=log)
            # 更新总错误任务数
            threadstatus.throttling = -pause_sizes
            threadstatus.increment_errors()
        except Exception as e:
            log = f"当前任务{name}上传过程未知出错: {e}"
            logging_capture.error(log)
            database.update_status(basename=name, step=4, status=4, log=log)
            # 更新总错误任务数
            threadstatus.throttling = -pause_sizes
            threadstatus.increment_errors()
        finally:
            # 释放压缩阶段占用的磁盘空间
            shutil.rmtree(str(cls._get_name(name)["compress"]), ignore_errors=True)
            threadstatus.throttling = -release_sizes
            with threadstatus.lock:
                threadstatus.active_upload -= 1

    @staticmethod
    def parse_return_result(future):
        """
        处理线程完成后的结果（当前暂未实现）
        :param future: 线程Future对象
        """
        pass

    @classmethod
    def _start_threads(cls, function: Callable, queue: Queue, threads: ThreadPoolExecutor) -> list[Future[Any]]:
        """
        启动线程池中的任务
        :param function: 要执行的函数
        :param queue: 任务队列
        :param threads: 线程池执行器
        :return: 返回Future对象列表
        """
        futures = []
        while not queue.empty():
            try:
                # 获取任务
                data = queue.get_nowait()
            except Empty:
                break
            # 提交任务但不等待
            future = threads.submit(function, data)
            # 为每个future添加回调，但不等待完成
            future.add_done_callback(lambda f: cls.parse_return_result(f))
            futures.append(future)
        return futures

    @classmethod
    def start_threads(cls, heart):
        """
        启动所有阶段的线程，并持续监控任务状态
        :param heart: 轮询间隔时间（秒）
        """
        total_futures = set()
        # 循环启动各阶段的线程
        while True:
            # 启动下载线程
            download_futures = cls._start_threads(
                function=cls.download_thread,
                queue=threadstatus.download_queue,
                threads=threadstatus.download_threads
            )
            # 启动解压线程
            decompress_futures = cls._start_threads(
                function=cls.decompress_thread,
                queue=threadstatus.decompress_queue,
                threads=threadstatus.decompress_threads
            )
            # 启动压缩线程
            compress_futures = cls._start_threads(
                function=cls.compress_thread,
                queue=threadstatus.compress_queue,
                threads=threadstatus.compress_threads
            )
            # 启动上传线程
            upload_futures = cls._start_threads(
                function=cls.upload_thread,
                queue=threadstatus.upload_queue,
                threads=threadstatus.upload_threads
            )
            # 将所有新的Future加入总集合
            for futures in [download_futures, decompress_futures, compress_futures, upload_futures]:
                total_futures.update(futures)
            # 检查所有任务是否完成
            if all(future.done() for future in total_futures) and \
               threadstatus.download_queue.empty() and \
               threadstatus.decompress_queue.empty() and \
               threadstatus.compress_queue.empty() and \
               threadstatus.upload_queue.empty():
                logging_capture.info("所有任务已完成")
                rclone.stop_rclone()
                break
            # 轮询休眠heart秒
            time.sleep(heart)


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
    parser.add_argument('--depth', type=int, default=int(os.getenv('DEPTH', 0)), help='使用路径中的目录作为最终文件夹名的探测深度,为0则使用文件名，例如 Alist:c/a/b.zip 0使用b为文件名，1使用a')
    parser.add_argument('--loglevel',type=log_level_type,default=os.getenv('LOGLEVEL', "INFO"), help='Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
    parser.add_argument('--console_log',type=bool,default=os.getenv('CONSOLE_LOG', True),help='是否输出到控制台')
    parser.add_argument('--max_spaces',type=int,default=os.getenv("MAX_SPACES",0),help='脚本允许使用的最大缓存空间,单位字节，为0为不限制（均预留10%容灾空间）')
    args = parser.parse_args()
    return args

def main():
    lsjson = rclone.lsjson(src, args={"recurse": True, "filesOnly": True, "noMimeType": True, "noModTime": True})["list"]
    # todo 临时补丁,分离驱动器和名称，前者是驱动器的,例如 Alist:
    srcfs,_ = rclone.extract_parts(src)
    # 过滤文件列表
    filter_list = fileprocess.filter_files(lsjson,srcfs,depth)
    # 写入到sqlite3(不必担心覆盖问题)
    database.insert_data(filter_list)
    # 读取sqlite3数据,只读取未完成的数据
    tasks = database.read_data(status=0)
    task_count = len(tasks)
    threadstatus.add_tasks(task_count)  # 更新总计数器
    # 写入到Queue
    for task in tasks.items():
        threadstatus.download_queue.put(task)
    logging_capture.info(f"已读取到{len(tasks)}条任务")
    # 启动线程
    ProcessThread.start_threads(heart)

# 覆盖系统内变量
load_dotenv(override=True)

app = Flask(__name__)
@app.route('/throttling', methods=['GET'])
def get_throttling():
    return jsonify(threadstatus.throttling)

def run_flask():
    app.run(host='0.0.0.0', port=30000)

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
    threadstatus = ThreadStatus(max_thread=max_threads, heart=heart, max_spaces=fileprocess.get_free_size(tmp) if max_spaces == 0 else max_spaces)

    # 启动 Flask 应用在一个单独的线程
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    # 启动rclone
    process = rclone.start_rclone()

    # 启动函数
    main()
