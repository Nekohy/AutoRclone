# Rclone的调用
import subprocess
import sys
import requests
import sqlite3

class Rclone:
    def __init__(self,rclone,source,tmp,dst):
        # Rclone二进制文件
        self.rclone = rclone
        # 启动参数
        self.link = "127.0.0.1:5572"
        self.args = ["rcd","--rc-no-auth",f"--rc-addr={self.link}"]

    def __requests(self,params,json):
        result = requests.post(self.link + params,
                               json=json)
        return result.json()

    def start_rclone(self):
        try:
            cmd = self.rclone + self.args
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,    # 捕获标准输出
                stderr=subprocess.PIPE,    # 捕获标准错误
                shell=False,
                bufsize=1,                 # 行缓冲
                universal_newlines=True    # 文本模式
            )
            print(f"已启动进程 PID: {process.pid}")
            return process

        except Exception as e:
            print(f"启动应用程序失败: {e}", file=sys.stderr)
            return None

    def copy(self,source,dst):
        json = {
            "srcFs": source,
            "dstFs": dst,
            "createEmptySrcDirs": True
        }
        return self.__requests("/sync/copy",json)

    def purge(self,fs,remote):
        json = {
            "fs": fs,
            "remote": remote
        }
        return self.__requests("/operations/purge",json)

    def lsjson(self,fs,remote,args:dict):
        # args 很建议为 {recurse: True,filesOnly: True,noMimeType: True,noModTime: True}
        """
        opt - a dictionary of options to control the listing (optional)
            recurse - If set recurse directories
            noModTime - If set return modification time
            showEncrypted - If set show decrypted names
            showOrigIDs - If set show the IDs for each item if known
            showHash - If set return a dictionary of hashes
            noMimeType - If set don't show mime types
            dirsOnly - If set only show directories
            filesOnly - If set only show files
            metadata - If set return metadata of objects also
            hashTypes - array of strings of hash types to show if showHash set
        """
        json = {
            "fs": fs,
            "remote": remote,
            "opt": args if args else None
        }
        return self.__requests("/operations/list",json)

class OwnRclone(Rclone):
    """
    {"Path":"Baidu/test/圣剑传说/DIPXXZ","Name":"DIPXXZ","Size":-1,"MimeType":"inode/directory","ModTime":"2024-03-21T15:56:49Z","IsDir":true},
    {"Path":"Game/未分类/严阵以待/rune-ready.or.not.zip.012","Name":"rune-ready.or.not.zip.012","Size":4290772992,"MimeType":"application/octet-stream","ModTime":"2023-12-14T15:09:58Z","IsDir":false},
    """
    def __init__(self, sqlite3, rclone, source, tmp, dst):
        super().__init__(rclone, source, tmp, dst)
        self.sqlite3 = sqlite3

    def sqlite3tree(self,fs,remote,args:dict):
        origin_json = self.lsjson(fs,remote,args)
        name = origin_json["Name"]
