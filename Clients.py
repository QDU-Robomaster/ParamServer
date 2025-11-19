# Clients.py
# 仅负责 TCP 连接管理和基础协议封装。

import socket
import threading
from typing import Any


class ParamClientTCP:
    """
    通用 TCP 客户端基类：
    - 负责 TCP 连接管理 (Socket)
    - 负责线程安全 (Lock)
    - 负责基础行协议组装 (send_cmd)
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5555):
        self.host = host
        self.port = port
        self.lock = threading.Lock()
        self.sock = None
        self._connect()

    def _connect(self):
        """建立连接"""
        try:
            self.sock = socket.create_connection(
                (self.host, self.port), timeout=5)
        except OSError as e:
            raise ConnectionError(f"无法连接到 {self.host}:{self.port} - {e}")

    def send_line(self, line: str) -> None:
        """直接发送一整行"""
        if self.sock is None:
            return

        if not line.endswith("\n"):
            line += "\n"

        data = line.encode("utf-8")

        with self.lock:
            try:
                self.sock.sendall(data)
            except OSError:
                print("[WARN] Socket 发送失败，连接可能已断开")
                self.sock = None

    def send_cmd(self, module: str, *tokens: Any) -> None:
        """
        通用命令发送接口。
        参数:
          module: 模块名 (如 "armor_detector")
          tokens: 命令和参数 (如 "binary_thres", 100)
        """
        # 将所有参数转为字符串并用空格连接
        str_tokens = [str(t) for t in tokens]
        line = " ".join([module] + str_tokens)
        self.send_line(line)

    def close(self) -> None:
        """关闭连接"""
        with self.lock:
            if self.sock:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None

# ==========================================================
# 模块客户端
# ==========================================================


class ArmorDetectorClientTCP(ParamClientTCP):
    """
    ArmorDetector 的客户端标识
    """
    MODULE = "armor_detector"

    def show(self) -> None:
        """请求 C++ 端打印当前参数"""
        self.send_cmd(self.MODULE, "show")


class ArmorTrackerClientTCP(ParamClientTCP):
    """
    ArmorTracker 的客户端标识
    """
    MODULE = "armor_tracker"

    def show(self) -> None:
        """请求 C++ 端打印当前参数"""
        self.send_cmd(self.MODULE, "show")
