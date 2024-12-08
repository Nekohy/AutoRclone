class UnpackError(Exception):
    # 解压错误
    pass

class NoRightPasswd(ValueError):
    # 没有正确的密码错误
    pass

class PackError(ValueError):
    # 压缩错误
    pass

class RcloneError(ValueError):
    pass

class NoExistDecompressDir(ValueError):
    pass

class FileTooLarge(ValueError):
    # 文件过大
    pass

#todo 可以添加一个容量不足报错