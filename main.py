# main.py
import threading
import queue
from contextlib import contextmanager
from rclone import download, upload
from compress import decompress, compress

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

        with manage_queue(download_queue, download_task):
            downloaded_file = download()


        with manage_queue(decompress_queue, decompress_task):
            decompressed_file = decompress()

        with manage_queue(compress_queue, compress_task):
            compressed_file = compress()

        with manage_queue(upload_queue, upload_task):
            uploaded_file = upload()

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

def

if __name__ == "__main__":
    # 全局变量：每个阶段的最大任务数量
    MAX_TASKS = 2
    # 线程数,建议是MAX_TASKS的4倍数
    THREAD = 4
    # 阶段使用的队列
    download_queue, decompress_queue, compress_queue, upload_queue = [
        queue.Queue(maxsize=MAX_TASKS) for _ in range(4)
    ]
    transfer(tasks)
