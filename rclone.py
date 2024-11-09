# Rclone的调用
import logging
import os
import re
import sqlite3
import subprocess
import sys
from typing import Dict

import requests

from exception import RcloneError


class Rclone:
    def __init__(self,rclone):
        # Rclone二进制文件
        self.rclone = rclone
        # 启动参数
        self.link = "127.0.0.1:5572"
        self.args = ["rcd","--rc-no-auth",f"--rc-addr={self.link}"]

    def __requests(self,params,json):
        result = requests.post(self.link + params,
                               json=json)

        if result.status_code != 200:
            logging.error(f"Rclone异常，返回值为{result.text}")
            raise RcloneError(f"Rclone异常，返回值为{result.text}")
        return result.json()

    def start_rclone(self):
        try:
            cmd = [self.rclone]
            for arg in self.args:
                cmd += [arg]
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
            raise RcloneError(f"启动应用程序失败: {e}")

    def copy(self,source,dst):
        json = {
            "srcFs": source,
            "dstFs": dst,
            "createEmptySrcDirs": True
        }
        return self.__requests("/sync/copy",json)

    def copyfile(self,srcfs,srcremote,dstfs,dstremote):
        json = {
            "srcFs": srcfs,
            "srcRemote": srcremote,
            "dstFs": dstfs,
            "dstRemote": dstremote,
        }
        return self.__requests("/operations/copyfile",json)

    def movefile(self, srcfs, srcremote, dstfs, dstremote):
        json = {
            "srcFs": srcfs,
            "srcRemote": srcremote,
            "dstFs": dstfs,
            "dstRemote": dstremote,
        }
        return self.__requests("/operations/movefile", json)

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

    def move(self,source,dst):
        json = {
            "srcFs": source,
            "dstFs": dst,
            "createEmptySrcDirs": True,
            "deleteEmptySrcDirs": True
        }
        return self.__requests("/sync/move",json)

class OwnRclone(Rclone):
    """
    {"Path":"Baidu/test/圣剑传说/DIPXXZ","Name":"DIPXXZ","Size":-1,"MimeType":"inode/directory","ModTime":"2024-03-21T15:56:49Z","IsDir":true},
    {"Path":"Game/未分类/严阵以待/rune-ready.or.not.zip.012","Name":"rune-ready.or.not.zip.012","Size":4290772992,"MimeType":"application/octet-stream","ModTime":"2023-12-14T15:09:58Z","IsDir":false},
    """
    def __init__(self, db_file:str, rclone):
        super().__init__(rclone)
        self.sqlite3 = sqlite3.connect(db_file) # sqlite3文件路径
        self.cursor = self.sqlite3.cursor()
        self._open_database()

    def _open_database(self):
        """打开数据库和表格"""
        # 创建 base_files 表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS base_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                basename TEXT UNIQUE,
                total_size INTEGER,
                status INTEGER DEFAULT 0,  -- 新增状态列，默认值为0（未完成）
                log TEXT                    -- 新增日志列
            )
        ''')

        # 创建 paths 表
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_file_id INTEGER,
                path TEXT,
                FOREIGN KEY (base_file_id) REFERENCES base_files(id)
            )
        ''')

        self.sqlite3.commit()

    def _insert_data(self, basename, info):
        """插入文件的数据"""
        # 插入或忽略基础文件信息，并初始化状态和日志
        self.cursor.execute('''
            INSERT OR IGNORE INTO base_files (basename, total_size, status, log)
            VALUES (?, ?, ?, ?)
        ''', (basename, info['total_size'], 0, ''))  # status 默认为0，log为空字符串

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
                INSERT INTO paths (base_file_id, path)
                VALUES (?, ?)
            ''', (base_file_id, path))

        self.sqlite3.commit()

    def insert_data(self,filter_data:Dict[str, Dict]):
        for basename, info in filter_data.items():
            self._insert_data(basename, info)
        self.sqlite3.commit()

    def update_status(self, basename:str, status:int, log=''):
        """
        更新文件的状态和日志

        参数:
            basename (str): 文件的基准名
            status (int): 状态码（0: 未完成, 1: 完成, 2: 密码错误, 3: 错误 4：意外错误）
            log (str): 相关日志信息
        """
        self.cursor.execute('''
            UPDATE base_files
            SET status = ?, log = ?
            WHERE basename = ?
        ''', (status, log, basename))
        self.sqlite3.commit()

    def read_data(self):
        """
        从 SQLite3 数据库中读取数据，并重构为嵌套字典。

        返回：
            Dict[str, Dict]: 第一层键为基础文件名，值为包含 'paths' 列表和 'total_size' 的字典。
        """

        # 查询所有基础文件及其总大小
        self.cursor.execute('SELECT id, basename, total_size FROM base_files')
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

        self.sqlite3.close()
        return data

    @staticmethod
    def _extract_parts(text):
        """
        从给定的字符串中提取第一个:前后的内容。

        Args:
            text (str): 输入的字符串，例如 'srcfs = "Alist:src"'。

        Returns:
            tuple: 包含分隔符前的内容和分隔符后的内容。如果未找到匹配项，返回 (None, None)。
        """
        pattern = r'^(?:([^:]+):)?(.+)$'
        match = re.search(pattern, text)
        if match:
            before = match.group(1).strip() if match.group(1) else None
            after = match.group(2).strip()
            return before, after
        return None, None

    def lsjson(self,text:str,args:dict):
        fs,remote = self._extract_parts(text)
        result = super().lsjson(fs,remote,args)
        return result

    def movefile(self,src,dst):
        srcfs, srcremote = self._extract_parts(src)
        dstfs, dstremote = self._extract_parts(dst)
        os.makedirs(dstremote,exist_ok=True)
        super().movefile(srcfs,srcremote,dstfs,dstremote)

