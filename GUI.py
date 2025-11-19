# GUI.py
# 从 xrobot.yaml 读取 cfg，
# 自动生成调参 UI，通过 TCP 调用 C++ CommandFun。

import os
import sys
from typing import Any, Dict, List, Tuple
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


def save_yaml(path: str, data: Dict[str, Any]) -> bool:
    """将 dict 写回 YAML 文件"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True,
                           sort_keys=False, default_flow_style=False)
        return True
    except Exception as e:
        print(f"[ERROR] 保存 YAML 失败: {path}, {e}")
        return False


def find_module_cfg(data: Dict[str, Any],
                    module_id: str,
                    module_name: str = "") -> Dict[str, Any]:
    """
    在 xrobot.yaml 里按 id 或 name 找到对应模块的 constructor_args.cfg。
    注意：这里返回的是 data 中对应节点的引用（reference），
    所以直接修改返回的 dict 会影响 data。
    """
    modules = data.get("modules", [])
    for m in modules:
        if m.get("id") == module_id:
            args = m.get("constructor_args") or {}
            if "cfg" not in args:
                args["cfg"] = {}
            return args["cfg"]

    if module_name:
        for m in modules:
            if m.get("name") == module_name:
                args = m.get("constructor_args") or {}
                if "cfg" not in args:
                    args["cfg"] = {}
                return args["cfg"]
    return {}


def resolve_command_name(path: List[str]) -> str:
    """根据 YAML 的层级路径解析出对应的 C++ 命令字符串。"""
    return path[-1]


def set_by_path(root: Dict[str, Any], path: List[str], value: Any):
    """
    辅助函数：根据 path 列表更新嵌套字典 root 中的值。
    例如 path=['light', 'max_ratio'], value=0.5 -> root['light']['max_ratio'] = 0.5
    """
    cur = root
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


# ==============================
# Tab 类
# ==============================

class AutoParamTab(QtWidgets.QWidget):
    """
    递归遍历 cfg 字典，自动生成 UI。
    维护一个 widget_registry，用于在保存时从 UI 拉取最新值。
    """

    def __init__(self,
                 module_name: str,
                 client,
                 cfg: Dict[str, Any],
                 parent=None):
        super().__init__(parent)
        self.module_name = module_name
        self.client = client
        self.cfg = cfg or {}  # 这是一个引用，指向 yaml_data 的一部分

        # 注册表：保存 (path, QLineEdit, type) 以便回写数据
        # List item structure: (path_list, widget_obj, data_type)
        self.widget_registry: List[Tuple[List[str],
                                         QtWidgets.QLineEdit, type]] = []

        # 主布局
        self.main_layout = QtWidgets.QVBoxLayout()

        # 滚动区域
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(content_widget)

        # 开始递归构建
        self._recursive_build_ui(self.cfg, self.content_layout, path=[])

        self.content_layout.addStretch(1)
        scroll.setWidget(content_widget)
        self.main_layout.addWidget(scroll)
        self.setLayout(self.main_layout)

    def update_cfg_from_ui(self):
        """
        【新功能】
        遍历所有已生成的输入框，读取当前文本，转为对应类型，
        并更新 self.cfg (即更新内存中的 YAML 结构)。
        """
        for path, widget, value_type in self.widget_registry:
            text = widget.text()
            try:
                new_val = value_type(text)
                # 更新内存字典
                set_by_path(self.cfg, path, new_val)
            except ValueError:
                print(f"[WARN] 无法将 {path} 的值 '{text}' 转换为 {value_type}")

    def _recursive_build_ui(self,
                            data: Any,
                            parent_layout: QtWidgets.QLayout,
                            path: List[str]):
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
            self._add_param_row(parent_layout, path, data)

        elif isinstance(data, list):
            label = QtWidgets.QLabel(f"{path[-1]}: [List data ignored]")
            label.setStyleSheet("color: gray; font-style: italic;")
            parent_layout.addWidget(label)

    def _add_param_row(self, layout: QtWidgets.QLayout, path: List[str], default_value: Any):
        """添加单行参数控件，并将控件注册到 registry 中"""
        cmd_name = resolve_command_name(path)

        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)

        lbl = QtWidgets.QLabel(f"{path[-1]}:")
        lbl.setToolTip(f"Full path: {'.'.join(path)}")
        lbl.setFixedWidth(180)

        line_edit = QtWidgets.QLineEdit()
        line_edit.setText(str(default_value))

        val_type = type(default_value)
        if isinstance(default_value, int):
            line_edit.setValidator(QtGui.QIntValidator())
        else:
            validator = QtGui.QDoubleValidator()
            validator.setDecimals(6)
            validator.setNotation(QtGui.QDoubleValidator.StandardNotation)
            line_edit.setValidator(validator)

        # === 注册控件以便后续保存 ===
        self.widget_registry.append((path, line_edit, val_type))

        btn = QtWidgets.QPushButton("Apply")
        btn.clicked.connect(lambda: self._handle_apply(
            cmd_name, line_edit, val_type))
        line_edit.returnPressed.connect(btn.click)

        row_layout.addWidget(lbl)
        row_layout.addWidget(line_edit)
        row_layout.addWidget(btn)

        layout.addWidget(row_widget)

    def _handle_apply(self, command: str, widget: QtWidgets.QLineEdit, value_type):
        text = widget.text()
        try:
            val = value_type(text)
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "格式错误", "数值无效")
            return

        if self.client is None:
            QtWidgets.QMessageBox.warning(self, "连接错误", "客户端未连接")
            return

        try:
            self.client.send_cmd(self.client.MODULE, command, val)
            print(f"[INFO] Sent: {self.client.MODULE} {command} {val}")
            # 视觉反馈
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
        self.setWindowTitle("XRobot 动态调参 GUI (YAML Driven)")

        # 路径处理
        if not os.path.exists(yaml_path):
            yaml_path = os.path.join(os.path.dirname(__file__), yaml_path)
        self.yaml_path = os.path.abspath(yaml_path)

        # 1) 读取 YAML (self.yaml_data 保存了完整结构)
        self.yaml_data = load_yaml(self.yaml_path)

        # 获取子模块的配置引用 (Reference)
        # 修改这些引用会直接修改 self.yaml_data
        detector_cfg = find_module_cfg(self.yaml_data,
                                       module_id="ArmorDetector_0",
                                       module_name="ArmorDetector")
        tracker_cfg = find_module_cfg(self.yaml_data,
                                      module_id="ArmorTracker_0",
                                      module_name="ArmorTracker")

        # 2) 初始化客户端
        self.det_client = None
        self.trk_client = None
        det_ok = trk_ok = False
        try:
            self.det_client = ArmorDetectorClientTCP(host, port)
            det_ok = True
        except Exception:
            pass  # 忽略连接错误，仅打印日志或不处理

        try:
            self.trk_client = ArmorTrackerClientTCP(host, port)
            trk_ok = True
        except Exception:
            pass

        # 3) UI 搭建
        layout = QtWidgets.QVBoxLayout()

        # -- 顶部信息 --
        info_group = QtWidgets.QGroupBox("Control Panel")
        info_layout = QtWidgets.QHBoxLayout()

        info_label = QtWidgets.QLabel(f"YAML: {os.path.basename(self.yaml_path)}\n"
                                      f"Clients: {'OK' if (det_ok and trk_ok) else 'Partial/None'}")
        info_layout.addWidget(info_label)
        info_layout.addStretch(1)

        # === Save Button ===
        self.btn_save = QtWidgets.QPushButton("Save Parameters to YAML")
        self.btn_save.setMinimumHeight(40)
        self.btn_save.setStyleSheet(
            "font-weight: bold; font-size: 12px; background-color: #e1f5fe;")
        self.btn_save.clicked.connect(self.on_save_clicked)
        info_layout.addWidget(self.btn_save)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # -- Tab 页 --
        self.tabs = QtWidgets.QTabWidget()

        # 保存 Tab 对象的引用，以便 save 时调用
        self.tab_detector = AutoParamTab(
            "ArmorDetector", self.det_client, detector_cfg)
        self.tab_tracker = AutoParamTab(
            "ArmorTracker", self.trk_client, tracker_cfg)

        self.tabs.addTab(self.tab_detector, "ArmorDetector")
        self.tabs.addTab(self.tab_tracker, "ArmorTracker")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def on_save_clicked(self):
        """保存按钮回调"""
        # 1. 让所有 Tab 将 UI 上的当前值写回内存中的 self.yaml_data 引用
        self.tab_detector.update_cfg_from_ui()
        self.tab_tracker.update_cfg_from_ui()

        # 2. 将内存数据写入磁盘
        success = save_yaml(self.yaml_path, self.yaml_data)

        if success:
            QtWidgets.QMessageBox.information(self, "保存成功",
                                              f"参数已成功写入文件：\n{self.yaml_path}")
        else:
            QtWidgets.QMessageBox.critical(self, "保存失败",
                                           "写入 YAML 文件时发生错误，请检查控制台输出。")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        for c in (self.det_client, self.trk_client):
            if c:
                c.close()
        event.accept()


# ==============================
# main
# ==============================

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    target_yaml = "../../User/xrobot.yaml"  # 默认相对路径
    port = 5555
    # 简单的参数查找逻辑
    if len(sys.argv) > 1:
        target_yaml = sys.argv[1]
    if len(sys.argv) > 2:
        port = eval(sys.argv[2])

    w = MainWindow(host="127.0.0.1", port=port, yaml_path=target_yaml)
    w.resize(600, 750)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
