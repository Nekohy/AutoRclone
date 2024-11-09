# main.py
import logging
import queue
import threading
import time
from contextlib import contextmanager

from exception import NoRightPasswd, UnpackError, PackError, RcloneError, NoExistDecompressDir
from fileprocess import FileProcess
from rclone import OwnRclone


@contextmanager
def manage_queue(queue, task):
    """
    上下文管理器，用于管理队列的加减操作。
    """
    try:
        queue.put(task)  # 将任务添加到队列，如果队列已满，会阻塞直到有空位
        yield
    finally:
        queue.get()      # 从队列中移除任务
        queue.task_done()


def worker():
    while True:
        download_task = download_queue.get()
        if download_task is None:
            download_queue.task_done()
            break
        name,task = download_task[0], download_task[1]
        for retry in range(3):
            try:
                with manage_queue(download_queue, download_task):
                    ownrclone.movefile(srcfs,f"{tmp}/download/{name}")
                    decompress_queue.put(f"{tmp}/download/{name}")


                with manage_queue(decompress_queue, decompress_queue.get()):
                    fileprocess.decompress(f"{tmp}/download/{name}",f"{tmp}/decompress/{name}",passwords=passwords)
                    compress_queue.put(f"{tmp}/decompress/{name}")

                with manage_queue(compress_queue, compress_queue.get()):
                    fileprocess.compress(f"{tmp}/decompress/{name}",f"{tmp}/compress/{name}",password=password,mx=mx,volumes=volumes)
                    upload_queue.put(f"{tmp}/compress/{name}")

                with manage_queue(upload_queue, upload_queue.get()):
                    ownrclone.move(source=f"{tmp}/compress/{name}",dst=f"{dstfs}/{name}")
                status = 1
                error_msg = None
                break
            except NoRightPasswd as e:
                logging.error(str(e))
                status = 2
                error_msg = str(e)
                break
            except UnpackError or PackError or RcloneError or NoExistDecompressDir as e:
                logging.error(f"当前任务{download_task[0]}出错{e}")
                status = 3
                error_msg = str(e)
            except Exception as e:
                status = 4
                logging.error(f"当前任务{download_task[0]}未知出错{e}")
                error_msg = str(e)
            time.sleep(1)
            print(f"重试第{retry}次")

        # 写入数据库
        # noinspection PyUnboundLocalVariable
        # 虽然我也不知道Pycharm为什么会报错这个（
        ownrclone.update_status(basename=name, status=status,log=error_msg if error_msg else "")


def transfer(tasks):
    # 创建任务
    threads = []
    for _ in range(THREAD):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)
    # 添加任务到下载队列
    for task in tasks:
        download_queue.put(task)
    # 等待所有队列完成任务
    download_queue.join()
    decompress_queue.join()
    compress_queue.join()
    upload_queue.join()

    for t in threads:
        t.join()


def main():
    # 获取lsjson的值
    lsjson = ownrclone.lsjson(srcfs,args={"recurse": True,"filesOnly": True,"noMimeType": True,"noModTime": True})
    # 过滤文件列表
    filter_list = fileprocess.filter_files(lsjson)
    # 写入到sqlite3(不必担心覆盖问题)
    ownrclone.insert_data(filter_list)
    # 读取sqlite3数据
    tasks = ownrclone.read_data()
    transfer(tasks)




if __name__ == "__main__":
    # 每个阶段的最大任务数量
    MAX_TASKS = 2
    # 线程数,建议是MAX_TASKS的4倍数
    THREAD = 4
    # db_file 数据库文件
    db_file = "./test.db"
    # rclone文件
    rclone = "./rclone.exe"
    # 7zip文件
    p7zip_file = "./7z.exe"
    # 临时目录
    tmp = "./tmp"
    # 起源目录
    srcfs = "Alist:src"
    # 终点目录
    dstfs = "Alist:dst"
    # 解压密码
    passwords = [None,]
    # 压缩密码,默认None
    password = None
    # 压缩等级,默认为0即仅储存
    mx = 0
    # 分卷大小
    volumes = "4G"

    # 阶段使用的队列
    download_queue, decompress_queue, compress_queue, upload_queue = [
        queue.Queue(maxsize=MAX_TASKS) for _ in range(4)
    ]
    ownrclone = OwnRclone(db_file,rclone)
    ownrclone.start_rclone()
    fileprocess = FileProcess()
    main()
