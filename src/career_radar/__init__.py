"""Career Radar：企业官网招聘信息监控工具。

包级文件只暴露版本号，避免导入包时就创建网络连接、数据库或日志文件。
这样测试、命令行帮助和第三方复用都会保持轻量、可预测。
"""

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("career-radar")
except PackageNotFoundError:  # 直接以源码方式运行时回退到显式常量
    __version__ = "1.2.0"
