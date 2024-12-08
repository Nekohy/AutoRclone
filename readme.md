# 简介
    一个用来搬（pa）运 (qu) 资源的Python脚本，需要Rclone和7zip

# 参数说明

| 参数 | 环境变量 | 默认值 | 说明                           |
|------|----------|--------|------------------------------|
| --rclone | RCLONE_PATH | - | rclone可执行文件路径                |
| --p7zip_file | P7ZIP_FILE | - | 7zip可执行文件路径                  |
| --src | SRC | - | 源目录路径,需要处理的文件目录              |
| --dst | DST | - | 目标目录路径,处理后文件的存放目录            |
| --passwords | PASSWORDS | [] | 解压密码列表,多个密码用空格分隔，将自动添加无密码到队列后 |
| --password | PASSWORD | - | 压缩密码                         |
| --max_threads | MAX_THREADS | 2 | 每个处理阶段的最大并发任务数               |
| --db_file | DB_FILE | ./data.db | SQLite数据库文件路径                |
| --tmp | TMP | ./tmp | 临时文件目录路径                     |
| --heart | HEART | 10 | Rclone监听轮询间隔时间(秒)            |
| --mx | MX | 0 | 压缩等级(0-9),0表示仅存储             |
| --mmt | MMT | 4 | 压缩/解压使用的线程数                  |
| --volumes | VOLUMES | 4g | 分卷大小,支持KB/MB/GB单位            |
| --logfile | LOGFILE | AutoRclone.log | 日志文件路径                       |
| --depth | DEPTH | 0 | 使用源路径中的目录作为最终文件夹名的探测深度       |
| --loglevel | LOGLEVEL | INFO | 日志级别(DEBUG/INFO/WARNING/ERROR/CRITICAL) |
| --console_log | CONSOLE_LOG | True | 是否在控制台输出日志                   |

## 说明
1. 所有参数都可以通过命令行传入,也可以通过环境变量设置
2. 命令行参数优先级高于环境变量高于系统变量
3. 部分参数有默认值,未设置时使用默认值
4. passwords参数支持多个密码,环境变量中用空格分隔
5. volumes参数支持KB(k)、MB(m)、GB(g)等单位
6. loglevel参数只接受指定的日志级别值

# 特性
1.支持7z/zip/rar等各分卷/非分卷，带密码/无密码的压缩文件
2.支持网盘目录探测，并保留原目录结构和文件名
3.使用Rclone RC HTTP通信
4.使用Sqlite3，支持断点续传
5.针对云端大文件动态调整线程，阻断下载/跳过任务

# todo

- [ ] Linux环境下无法启动系统下的Rclone
- [ ] Rclone鉴权
- [ ] 多目标上传
- [ ] 进度条设计
- [ ] 待定
