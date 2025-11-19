# GUI.py
# 从 xrobot.yaml 读取 ArmorDetector_0 / ArmorTracker_0 的 cfg，
# 自动生成调参 UI，通过 TCP 调用 C++ CommandFun。

import os
import sys
from typing import Any, Dict, List, Union

import yaml
from PyQt5 import QtWidgets, QtCore, QtGui

from Clients import ArmorDetectorClientTCP, ArmorTrackerClientTCP


# ==============================
# YAML & 工具函数
# ==============================

def load_yaml(path: str) -> Dict[str, Any]:
    """读取 YAML 文件，失败返回空 dict。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[WARN] 加载 YAML 失败: {path}, {e}")
        return {}


def find_module_cfg(data: Dict[str, Any],
                    module_id: str,
                    module_name: str = "") -> Dict[str, Any]:
    """
    在 xrobot.yaml 里按 id 或 name 找到对应模块的 constructor_args.cfg。
    """
    modules = data.get("modules", [])
    for m in modules:
        if m.get("id") == module_id:
            return (((m.get("constructor_args") or {}).get("cfg")) or {})
    if module_name:
        for m in modules:
            if m.get("name") == module_name:
                return (((m.get("constructor_args") or {}).get("cfg")) or {})
    return {}


def resolve_command_name(path: List[str]) -> str:
    """
    根据 YAML 的层级路径解析出对应的 C++ 命令字符串。
    由于 C++ 端命名不完全统一（有时是叶子节点名，有时是组合名），
    这里保留一些硬编码的映射规则，默认情况使用叶子节点名。
    """

    return path[-1]


# ==============================
# Tab 类
# ==============================

class AutoParamTab(QtWidgets.QWidget):
    """
    递归遍历 cfg 字典，自动生成 UI。
    - 字典 -> QGroupBox
    - 数值 -> Label + QLineEdit + Apply Button
    """

    def __init__(self,
                 module_name: str,
                 client,
                 cfg: Dict[str, Any],
                 parent=None):
        super().__init__(parent)
        self.module_name = module_name
        self.client = client
        self.cfg = cfg or {}

        # 主布局
        self.main_layout = QtWidgets.QVBoxLayout()

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(content_widget)

        self._recursive_build_ui(self.cfg, self.content_layout, path=[])

        self.content_layout.addStretch(1)
        scroll.setWidget(content_widget)
        self.main_layout.addWidget(scroll)
        self.setLayout(self.main_layout)

    def _recursive_build_ui(self,
                            data: Any,
                            parent_layout: QtWidgets.QLayout,
                            path: List[str]):
        """
        递归构建 UI 树
        :param data: 当前层级的数据 (dict 或 value)
        :param parent_layout: 父级 Layout，用于添加控件
        :param path: 当前层级的 key 路径，用于生成 command
        """
        if isinstance(data, dict):
            for key, val in data.items():
                new_path = path + [key]

                if isinstance(val, dict):
                    group = QtWidgets.QGroupBox(key)
                    group.setStyleSheet("QGroupBox { font-weight: bold; }")
                    group_layout = QtWidgets.QVBoxLayout()
                    group.setLayout(group_layout)

                    self._recursive_build_ui(val, group_layout, new_path)
                    parent_layout.addWidget(group)
                else:
                    self._recursive_build_ui(val, parent_layout, new_path)

        elif isinstance(data, (int, float)):
            # 如果是数值，生成一行参数设置
            self._add_param_row(parent_layout, path, data)

        elif isinstance(data, list):
            # 列表类型暂不支持通过单值输入框修改
            label = QtWidgets.QLabel(f"{path[-1]}: [List data ignored]")
            label.setStyleSheet("color: gray; font-style: italic;")
            parent_layout.addWidget(label)

    def _add_param_row(self, layout: QtWidgets.QLayout, path: List[str], default_value: Any):
        """添加单行参数控件：Label | LineEdit | Button"""
        cmd_name = resolve_command_name(path)
        label_text = ".".join(path)

        # 创建水平布局
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)

        # 1. 标签
        lbl = QtWidgets.QLabel(f"{path[-1]}:")
        lbl.setToolTip(f"Full path: {label_text}\nCommand: {cmd_name}")
        lbl.setFixedWidth(180)

        line_edit = QtWidgets.QLineEdit()
        line_edit.setText(str(default_value))

        # 设置校验器，防止输入非法字符
        if isinstance(default_value, int):
            validator = QtGui.QIntValidator()
            line_edit.setValidator(validator)
        else:
            validator = QtGui.QDoubleValidator()
            validator.setDecimals(6)
            validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            line_edit.setValidator(validator)

        # 3. 按钮
        btn = QtWidgets.QPushButton("Apply")
        # 绑定点击事件
        btn.clicked.connect(lambda: self._handle_apply(
            cmd_name, line_edit, type(default_value)))
        # 回车触发
        line_edit.returnPressed.connect(btn.click)

        row_layout.addWidget(lbl)
        row_layout.addWidget(line_edit)
        row_layout.addWidget(btn)

        layout.addWidget(row_widget)

    def _handle_apply(self, command: str, widget: QtWidgets.QLineEdit, value_type):
        """处理发送逻辑"""
        text = widget.text()
        try:
            val = value_type(text)
        except ValueError:
            QtWidgets.QMessageBox.warning(
                self, "格式错误", f"请输入有效的 {value_type.__name__} 数值")
            return

        if self.client is None:
            QtWidgets.QMessageBox.warning(
                self, "连接错误", f"客户端未连接，无法发送: {command}")
            return

        try:
            self.client.send_cmd(self.client.MODULE, command, val)
            print(f"[INFO] Sent: {self.client.MODULE} {command} {val}")

            widget.setStyleSheet("background-color: #ccffcc;")
            QtCore.QTimer.singleShot(300, lambda: widget.setStyleSheet(""))

        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "发送失败", str(e))


# ==============================
# 主窗口
# ==============================

class MainWindow(QtWidgets.QWidget):
    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 5555,
                 yaml_path: str = "User/xrobot.yaml"):
        super().__init__()
        self.setWindowTitle("Param Manager")

        # 1) 读取 YAML
        if not os.path.exists(yaml_path):
            yaml_path = os.path.join(os.path.dirname(__file__), yaml_path)

        yaml_abs = os.path.abspath(yaml_path)
        self.yaml_data = load_yaml(yaml_abs)

        detector_cfg = find_module_cfg(self.yaml_data,
                                       module_id="ArmorDetector_0",
                                       module_name="ArmorDetector")
        tracker_cfg = find_module_cfg(self.yaml_data,
                                      module_id="ArmorTracker_0",
                                      module_name="ArmorTracker")

        self.det_client = None
        self.trk_client = None
        det_ok = trk_ok = False

        try:
            self.det_client = ArmorDetectorClientTCP(host, port)
            det_ok = True
        except Exception as e:
            print(f"[ERROR] ArmorDetectorClientTCP: {e}")

        try:
            self.trk_client = ArmorTrackerClientTCP(host, port)
            trk_ok = True
        except Exception as e:
            print(f"[ERROR] ArmorTrackerClientTCP: {e}")

        # 3) UI 搭建
        layout = QtWidgets.QVBoxLayout()

        # 顶部信息栏
        info_group = QtWidgets.QGroupBox("Connection Info")
        info_layout = QtWidgets.QVBoxLayout()
        info_lines = [
            f"TCP Server: {host}:{port}",
            f"YAML File: {yaml_abs}",
            f"Detector Client: {'Connected' if det_ok else 'Disconnected'}",
            f"Tracker Client:  {'Connected' if trk_ok else 'Disconnected'}",
        ]
        info_label = QtWidgets.QLabel("\n".join(info_lines))
        info_layout.addWidget(info_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Tab 页
        tabs = QtWidgets.QTabWidget()

        tabs.addTab(AutoParamTab("ArmorDetector", self.det_client,
                    detector_cfg), "ArmorDetector")
        tabs.addTab(AutoParamTab("ArmorTracker", self.trk_client,
                    tracker_cfg), "ArmorTracker")

        layout.addWidget(tabs)
        self.setLayout(layout)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        for c in (self.det_client, self.trk_client):
            try:
                if c is not None:
                    c.close()
            except Exception as e:
                print(f"[WARN] Close error: {e}")
        event.accept()


# ==============================
# main
# ==============================

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    # YAML 路径
    target_yaml = "../../User/xrobot.yaml"

    w = MainWindow(host="127.0.0.1", port=5555, yaml_path=target_yaml)
    w.resize(600, 900)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
