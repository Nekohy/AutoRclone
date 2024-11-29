# main.py
import argparse
import logging
import os
import queue
import sys
import threading
from dotenv import load_dotenv
from contextlib import contextmanager

from exception import NoRightPasswd, UnpackError, PackError, RcloneError, NoExistDecompressDir
from fileprocess import FileProcess
from rclone import OwnRclone


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

def setup_logger(logger_name, log_file, level=logging.DEBUG):
    """
    创建并配置一个日志记录器。

    :param logger_name: 日志记录器的名称
    :param log_file: 日志文件的路径
    :param level: 日志级别
    :return: 配置好的日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    logger.propagate = False  # 防止日志重复

    # 检查是否已经添加过处理器
    if not logger.handlers:
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # 创建文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)  # 设置文件处理器的日志级别
        file_handler.setFormatter(formatter)

        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)  # 设置控制台处理器的日志级别
        console_handler.setFormatter(formatter)

        # 将处理器添加到日志记录器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

def get_name(name):
    # 构建路径
    download = os.path.join(tmp, "download", name).replace("\\", "/")
    decompress = os.path.join(tmp, "decompress", name).replace("\\", "/")
    compress = os.path.join(tmp, "compress", name).replace("\\", "/")
    upload = os.path.join(dst, name).replace("\\", "/")
    return {"download":download, "decompress":decompress, "compress":compress, "upload":upload}

def get_job_status(jobid):
    status = ownrclone.jobstatus(jobid)
    if status["success"] is False:
        raise RcloneError(f"{jobid}失败")
    else:
        return status["output"]

def worker():
    ownrclone = OwnRclone(db_file, rclone)
    while True:
        step = 0
        try:
            # Queue控制流程
            if step == 0:
                with manage_queue(download_queue) as download_task:
                    name = download_task[0]
                    for file in download_task[1]["paths"]:
                        jobid = ownrclone.copyfile(file,get_name(name)["download"], replace_name=None)
                        get_job_status(jobid)
                    decompress_queue.put(name)
                    step += 1
                    logging.info(f"下载步骤完成: {name}")

            if step == 1:
                with manage_queue(decompress_queue) as name:
                    fileprocess.decompress(get_name(name)["download"], get_name(name)["decompress"], passwords=passwords)
                    compress_queue.put(name)
                    step += 1
                    logging.info(f"解压步骤完成: {get_name(name)['decompress']}")

            if step == 2:
                with manage_queue(compress_queue) as name:
                    jobid = ownrclone.move(source=get_name(name)['compress'], dst=get_name(name)['upload'])
                    get_job_status(jobid)
                step += 1
                logging.info(f"压缩步骤完成: {get_name(name)['compress']}")

            if step == 3:
                with manage_queue(upload_queue) as name:
                    ownrclone.move(source=get_name(name)['compress'], dst=get_name(name)['upload'])
                step += 1
                logging.info(f"上传步骤完成: {get_name(name)['upload']}")
            status = 1
            error_msg = None
            # 成功了删除file
            ownrclone.purge(file)
        except NoRightPasswd as e:
            logging.error(str(e))
            status = 2
            error_msg = str(e)
        except (UnpackError, PackError, RcloneError, NoExistDecompressDir) as e:
            logging.error(f"当前任务{name}出错{e}")
            status = 3
            error_msg = str(e)
        except Exception as e:
            status = 4
            logging.error(f"当前任务{name}未知出错{e}")
            error_msg = str(e)
        # 如果不成功删除缓存 todo step检查，也就不用删了
        for del_task in ["download", "decompress", "compress", "upload"]:
            ownrclone.purge(get_name(name)[del_task])
        # 写入数据库
        # noinspection PyUnboundLocalVariable
        # 虽然我也不知道Pycharm为什么会报错这个（
        ownrclone.update_status(basename=name, status=status,step=step,log=error_msg if error_msg else "")

def transfer(tasks):
    # 创建任务
    threads = []
    for _ in range(THREAD):
        t = threading.Thread(target=worker, daemon=True)
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

def start():
    lsjson = ownrclone.lsjson(src, args={"recurse": True, "filesOnly": True, "noMimeType": True, "noModTime": True})["list"]
    #todo 临时补丁,分离驱动器和名称，前者是不带驱动器的
    srcfs,_ = ownrclone.extract_parts(src)
    # 过滤文件列表
    filter_list = fileprocess.filter_files(lsjson,srcfs,depth)
    # 写入到sqlite3(不必担心覆盖问题)
    ownrclone.insert_data(filter_list)
    # 读取sqlite3数据,只读取未完成的数据
    tasks = ownrclone.read_data(status=0)
    logging.info(f"已读取到{len(tasks)}条任务")
    transfer(tasks)


# Load environment variables from .env file
load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="自动化任务处理脚本")

    # Add command line arguments with defaults from environment variables
    parser.add_argument('--rclone', type=str, default=os.getenv('RCLONE_PATH'), help='rclone文件路径')
    parser.add_argument('--p7zip_file', type=str, default=os.getenv('P7ZIP_FILE'), help='7zip文件路径')
    parser.add_argument('--src', type=str, default=os.getenv('SRC'), help='起源目录路径')
    parser.add_argument('--dst', type=str, default=os.getenv('DST'), help='终点目录路径')
    parser.add_argument('--passwords', nargs='+', default=os.getenv('PASSWORDS', '').split(), help='解压密码列表')
    parser.add_argument('--password', type=str, default=os.getenv('PASSWORD'), help='压缩密码')
    parser.add_argument('--max_tasks', type=int, default=int(os.getenv('MAX_TASKS', 2)), help='每个阶段的最大任务数量，默认2')
    parser.add_argument('--thread', type=int, default=int(os.getenv('THREAD', 8)), help='线程数，建议是MAX_TASKS的4倍，默认8')
    parser.add_argument('--db_file', type=str, default=os.getenv('DB_FILE', './data.db'), help='数据库文件路径')
    parser.add_argument('--tmp', type=str, default=os.getenv('TMP', './tmp'), help='临时目录路径')
    parser.add_argument('--mx', type=int, default=int(os.getenv('MX', 0)), help='压缩等级，默认为0即仅储存')
    parser.add_argument('--mmt', type=int, default=int(os.getenv('MMT', 4)), help='解压缩线程数')
    parser.add_argument('--volumes', type=str, default=os.getenv('VOLUMES', '4g'), help='分卷大小')
    parser.add_argument('--logfile', type=str, default=os.getenv('LOGFILE', 'AutoRclone.log'), help='日志文件路径')
    parser.add_argument('--depth', type=int, default=int(os.getenv('DEPTH', 0)), help='使用路径中的目录作为最终文件夹名的探测深度')

    args = parser.parse_args()
    return args

if __name__ == "__main__":
    args = main()
    # Use parsed arguments
    MAX_TASKS = args.max_tasks
    THREAD = args.thread
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

    # Queues for each stage
    download_queue, decompress_queue, compress_queue, upload_queue = [
        queue.Queue(maxsize=MAX_TASKS) for _ in range(4)
    ]

    # Initialize
    ownrclone = OwnRclone(db_file, rclone)
    process = ownrclone.start_rclone()
    fileprocess = FileProcess(mmt=mmt, p7zip_file=p7zip_file, autodelete=True)

    # Start
    start()

    # Terminate process
    process.kill()
