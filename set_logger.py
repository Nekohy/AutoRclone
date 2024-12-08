import logging
import sys


def setup_logger(logger_name, log_file,console_log:bool=False,level=logging.INFO):
    """
    创建并配置一个日志记录器。

    :param logger_name: 日志记录器的名称
    :param log_file: 日志文件的路径
    :param console_log: 是否输出到控制台
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
        logger.addHandler(file_handler)
        logger.addHandler(file_handler)
        if console_log:
            # 创建控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)  # 设置控制台处理器的日志级别
            console_handler.setFormatter(formatter)
            # 将处理器添加到日志记录器
            logger.addHandler(console_handler)

    return logger