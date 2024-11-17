# main.py
import logging
import os
import queue
import threading
import time
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

def get_name(name):
    # 构建路径
    download = os.path.join(tmp, "download", name).replace("\\", "/")
    decompress = os.path.join(tmp, "decompress", name).replace("\\", "/")
    compress = os.path.join(tmp, "compress", name).replace("\\", "/")
    upload = os.path.join(dst, name).replace("\\", "/")
    return {"download":download, "decompress":decompress, "compress":compress, "upload":upload}

def wait_job(jobid):
    while True:
        status = ownrclone.jobstatus(jobid)
        print(status.get("progress"))
        if status["finished"]:
            if status["success"] is False:
                raise RcloneError(f"{jobid}失败")
            else:
                return status["output"]
        else:
            logging.debug(f"当前{jobid}进度{status.get('progress')}")
        time.sleep(heart)

def worker():
    while True:
        ownrclone = OwnRclone(db_file, rclone)
        steps_completed = {
            'download': False,
            'decompress': False,
            'compress': False,
            'upload': False,
        }
        for retry in range(3):
            try:
                # Queue控制流程
                if not steps_completed['download']:
                    with manage_queue(download_queue) as download_task:
                        name = download_task[0]
                        for file in download_task[1]["paths"]:
                            jobid = ownrclone.movefile(file,get_name(name)["download"], replace_name=None)
                            wait_job(jobid)
                        decompress_queue.put(name)
                        steps_completed['download'] = True
                        logging.info(f"下载步骤完成: {name}")

                if not steps_completed['decompress']:
                    with manage_queue(decompress_queue) as name:
                        fileprocess.decompress(get_name(name)["download"], get_name(name)["decompress"], passwords=passwords)
                        compress_queue.put(name)
                        steps_completed['decompress'] = True
                        logging.info(f"解压步骤完成: {get_name(name)['decompress']}")

                if not steps_completed['compress']:
                    with manage_queue(compress_queue) as name:
                        fileprocess.compress(get_name(name)['decompress'], get_name(name)['compress'], password=password, mx=mx, volumes=volumes)
                        upload_queue.put(name)
                    steps_completed['compress'] = True
                    logging.info(f"压缩步骤完成: {get_name(name)['compress']}")

                if not steps_completed['upload']:
                    with manage_queue(upload_queue) as name:
                        jobid = ownrclone.move(source=get_name(name)['compress'], dst=get_name(name)['upload'])
                        wait_job(jobid)
                    steps_completed['upload'] = True
                    logging.info(f"上传步骤完成: {get_name(name)['upload']}")
                status = 1
                error_msg = None
                break
            except NoRightPasswd as e:
                logging.error(str(e))
                status = 2
                error_msg = str(e)
                break
            except (UnpackError, PackError, RcloneError, NoExistDecompressDir) as e:
                logging.error(f"当前任务{name}出错{e}")
                status = 3
                error_msg = str(e)
            except Exception as e:
                status = 4
                logging.error(f"当前任务{name}未知出错{e}")
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
    for task in tasks.items():
        download_queue.put(task)
    # 等待所有队列完成任务
    download_queue.join()
    decompress_queue.join()
    compress_queue.join()
    upload_queue.join()

def main():
    lsjson = ownrclone.lsjson(src, args={"recurse": True, "filesOnly": True, "noMimeType": True, "noModTime": True})["list"]
    #todo 临时补丁
    srcfs,_ = ownrclone.extract_parts(src)
    # 过滤文件列表
    filter_list = fileprocess.filter_files(lsjson,srcfs)
    # 写入到sqlite3(不必担心覆盖问题)
    ownrclone.insert_data(filter_list)
    # 读取sqlite3数据,只读取未完成的数据
    tasks = ownrclone.read_data(status=0)
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
    # Rclone HTTP监听间隔，以s为单位
    heart = 1
    # 7zip文件
    p7zip_file = "./7zip/7z.exe"
    # 临时目录
    tmp = "./tmp"
    # 起源目录
    src = "./before"
    # 终点目录
    dst = "./dst"
    # 解压密码
    passwords = [123456,]
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
    process = ownrclone.start_rclone()
    fileprocess = FileProcess()
    main()
    process.kill()
