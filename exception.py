class UnpackError(Exception):
    # 解压错误
    pass

class NoRightPasswd(ValueError):
    # 没有正确的密码错误
    pass

class PackError(Exception):
    # 压缩错误
    pass

class RcloneError(Exception):
    pass

class NoExistDecompressDir(Exception):
    pass