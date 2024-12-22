# Rclone的调用
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from typing import Dict

import requests

from Exception import RcloneError


class Rclone:
    def __init__(self,rclone):
        # Rclone二进制文件
        self.rclone = rclone
        # 启动参数
        self.link = "127.0.0.1:4572"
        self.args = ["rcd","--rc-no-auth",f"--rc-addr={self.link}"]
        # 是否检验文件完整性
        self.checknum = True

    def __requests(self,params,json):
        result = requests.post(f"http://{self.link}{params}",
                               json=json)
        if result.status_code != 200:
            raise RcloneError(f"Rclone异常，返回值为{result.text}")
        return result.json()

    def start_rclone(self):
        try:
            cmd = [self.rclone] + self.args
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,  # 捕获标准输出
                stderr=subprocess.PIPE,  # 捕获标准错误
                shell=False,
                bufsize=1,  # 行缓冲
                universal_newlines=True,  # 文本模式
            )
            print(f"已启动进程 PID: {process.pid}")
            return process

        except Exception as e:
            raise RcloneError(f"启动应用程序失败: {e}")

    def copy(self,source,dst):
        json = {
            "srcFs": source,
            "dstFs": dst,
            "createEmptySrcDirs": True,
            "CheckSum": self.checknum
        }
        return self.__requests("/sync/copy",json)

    def copyfile(self,srcfs,srcremote,dstfs,dstremote):
        json = {
            "srcFs": srcfs,
            "srcRemote": srcremote,
            "dstFs": dstfs,
            "dstRemote": dstremote,
            "CheckSum": self.checknum
        }
        return self.__requests("/operations/copyfile",json)

    def move(self,source,dst):
        json = {
            "srcFs": source,
            "dstFs": dst,
            "createEmptySrcDirs": True,
            "deleteEmptySrcDirs": True,
            "CheckSum": self.checknum
        }
        return self.__requests("/sync/move",json)

    def movefile(self, srcfs, srcremote, dstfs, dstremote):
        json = {
            "srcFs": srcfs,
            "srcRemote": srcremote,
            "dstFs": dstfs,
            "dstRemote": dstremote,
            "CheckSum": self.checknum
        }
        return self.__requests("/operations/movefile", json)

    def purge(self,fs,remote):
        json = {
            "fs": fs,
            "remote": remote
        }
        return self.__requests("/operations/purge",json)

    def joblist(self):
        return self.__requests("/job/list",{})

    def jobstatus(self,jobid):
        return self.__requests("/job/status",json=jobid)

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

    def du(self, local_dir="/"):
        """
        获取本地磁盘空间信息
        :param local_dir: 传递本地路径
        :return:
        {
            "dir": local_dir,
            "info": {
                "Available": 0,
                "Free": 0,
                "Total": 0
            }
        }
        """
        json = {
            "dir": local_dir,
        }
        return self.__requests("core/du", json)

@dataclass
class DataBase:
    db_file: str = field(init=True)

    def __post_init__(self):
        self.database = sqlite3.connect(self.db_file)
        self.cursor = self.database.cursor()
        self._init_database()

    def _init_database(self):
        """初始化数据库和表格"""
        # 创建 base_files 表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS base_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                basename TEXT UNIQUE,
                total_size INTEGER,
                status INTEGER DEFAULT 0,  -- 新增状态列，默认值为0（未完成）
                step INTEGER DEFAULT 0,    -- 新增步骤列，默认值为0（未开始）
                log TEXT                    -- 日志列
            )
        ''')

        # 创建 paths 表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_file_id INTEGER,
                path TEXT UNIQUE,
                FOREIGN KEY (base_file_id) REFERENCES base_files(id)
            )
        ''')

        self.database.commit()

    def _insert_data(self, basename, info):
        """插入文件的数据"""
        # 插入或忽略基础文件信息，并初始化状态和日志
        self.cursor.execute('''
            INSERT OR IGNORE INTO base_files (basename, total_size, status, step, log)
            VALUES (?, ?, ?, ?, ?)
        ''', (basename, info['total_size'], 0, 0, ''))  # status 默认为0，step 默认为0log为空字符串

        # 获取基础文件的 ID
        self.cursor.execute('SELECT id FROM base_files WHERE basename = ?', (basename,))
        result = self.cursor.fetchone()
        if result:
            base_file_id = result[0]
        else:
            raise ValueError(f"Failed to retrieve ID for basename: {basename}")

        # 插入路径信息
        for path in info['paths']:
            self.cursor.execute('''
                INSERT OR IGNORE INTO paths (base_file_id, path)
                VALUES (?, ?)
            ''', (base_file_id, path))

        self.database.commit()

    def insert_data(self, filter_data: Dict[str, Dict]):
        for basename, info in filter_data.items():
            self._insert_data(basename, info)
        self.database.commit()

    def update_status(self, basename: str, step: int, status: int = 0, log:str=''):
        """
        更新文件的状态和日志

        参数:
            basename (str): 文件的基准名
            step(int): 执行完成的步骤 0未开始 1下载 2解压 3压缩 4上传
            status (int): 状态码（0: 未完成, 1: 完成, 2: 密码错误, 3: 错误 4：意外错误）
            log (str): 相关日志信息
        """
        # 单独开一个database给多线程用
        with sqlite3.connect(self.db_file) as database:
            cursor = database.cursor()
            cursor.execute('''
                UPDATE base_files
                SET status = ?, log = ?,step = ?
                WHERE basename = ?
            ''', (status, log, step, basename))
            database.commit()

    def read_data(self, status: int):
        """
        从 SQLite3 数据库中读取数据，并重构为嵌套字典。

        返回：
            Dict[str, Dict]: 第一层键为基础文件名，值为包含 'paths' 列表和 'total_size' 的字典。
        """

        # 查询所有基础文件及其总大小
        self.cursor.execute(
            'SELECT id, basename, total_size FROM base_files WHERE status = ?',
            (status,)
        )
        base_files = self.cursor.fetchall()

        data = {}

        for base_file in base_files:
            base_id, basename, total_size = base_file
            # 查询与该基础文件相关的所有路径
            self.cursor.execute('SELECT path FROM paths WHERE base_file_id = ?', (base_id,))
            paths = [row[0] for row in self.cursor.fetchall()]

            data[basename] = {
                'paths': paths,
                'total_size': total_size
            }

        self.database.close()
        return data

@dataclass
class OwnRclone(Rclone):
    # 一些自用的数据库创建和优化一下官方HTTP那令人窒息的参数
    rclone:str = field(init=True)

    def __post_init__(self):
        # 继承Rclone
        super().__init__(self.rclone)

    @staticmethod
    def extract_parts(s):
        # 捕获分隔符
        pattern = re.compile(r'^(.*?)([:/])(.*)')
        match = pattern.match(s)
        if match:
            prefix_part = match.group(1) if match.group(1) else '/'
            separator = match.group(2)
            suffix_part = match.group(3)

            # 如果分隔符是 ':', 将其包含在 prefix 中
            if separator == ':':
                prefix = prefix_part + separator
                suffix = suffix_part
            else:
                prefix = prefix_part
                suffix = "/" + suffix_part

            return prefix, suffix
        else:
            return None

    def purge(self,s):
        # 传递完整路径即可
        fs, remote = self.extract_parts(s)
        result = super().purge(fs,remote)
        return result

    def lsjson(self,text:str,args:dict):
        fs,remote = self.extract_parts(text)
        result = super().lsjson(fs,remote,args)
        return result

    def movefile(self,src,dst,replace_name:str=None):
        srcfs, srcremote = self.extract_parts(src)
        dstfs, dstremote = self.extract_parts(dst)
        os.makedirs(dstremote,exist_ok=True)
        dstremote = os.path.join(dstremote,replace_name if replace_name else os.path.basename(srcremote)).replace("\\","/")
        return super().movefile(srcfs,srcremote,dstfs,dstremote)

    def copyfile(self,src,dst,replace_name:str=None):
        srcfs, srcremote = self.extract_parts(src)
        dstfs, dstremote = self.extract_parts(dst)
        os.makedirs(dstremote,exist_ok=True)
        dstremote = os.path.join(dstremote,replace_name if replace_name else os.path.basename(srcremote)).replace("\\","/")
        return super().copyfile(srcfs,srcremote,dstfs,dstremote)

