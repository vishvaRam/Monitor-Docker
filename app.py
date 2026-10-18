import os
import json
import re
import sys
import time
import webbrowser

import docker
from docker.errors import DockerException
from PyQt6.QtCore import (
    QPoint,
    QRegularExpression,
    Qt,
    QThread,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QIcon,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


# -------------------------------------------------------------
# Cross-Platform Asset & Process Initialization
# -------------------------------------------------------------
# On Windows, tell the shell this is an independent app so the taskbar displays our icon
if sys.platform.startswith("win"):
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "vishva.dockerstudio.telemetry.1_0_0"
        )
    except Exception:
        pass


def get_asset_path(filename):
    """
    Cross-platform path resolver:
    - PyInstaller bundled executable (_MEIPASS)
    - Installed Linux layout (/opt/docker-studio/assets)
    - Local development (assets/)
    """
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, "assets", filename)


# -------------------------------------------------------------
# Cross-Platform Docker Connection
# -------------------------------------------------------------
def get_docker_client():
    # 1. Try standard environment settings
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception:
        pass

    # 2. Windows Docker Desktop named pipes
    if sys.platform.startswith("win"):
        try:
            client = docker.DockerClient(base_url="npipe:////./pipe/docker_engine")
            client.ping()
            return client
        except Exception:
            pass

    # 3. Linux / macOS default Unix socket
    else:
        try:
            client = docker.DockerClient(base_url="unix://var/run/docker.sock")
            client.ping()
            return client
        except Exception:
            pass

    raise DockerException(
        "Could not connect to Docker Daemon. Ensure Docker Desktop is running."
    )


# -------------------------------------------------------------
# High-Performance Terminal Syntax Highlighter
# -------------------------------------------------------------
class TerminalLogHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        # Timestamps
        f_time = QTextCharFormat()
        f_time.setForeground(QColor("#64748b"))
        self.rules.append(
            (
                QRegularExpression(
                    r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?\b"
                ),
                f_time,
            )
        )

        # Errors / Fatal
        f_err = QTextCharFormat()
        f_err.setForeground(QColor("#f87171"))
        f_err.setFontWeight(QFont.Weight.Bold)
        self.rules.append(
            (
                QRegularExpression(
                    r"\b(ERROR|ERR|FATAL|CRITICAL|FAIL|FAILED)\b",
                    QRegularExpression.PatternOption.CaseInsensitiveOption,
                ),
                f_err,
            )
        )

        # Warnings
        f_warn = QTextCharFormat()
        f_warn.setForeground(QColor("#fbbf24"))
        f_warn.setFontWeight(QFont.Weight.Bold)
        self.rules.append(
            (
                QRegularExpression(
                    r"\b(WARN|WARNING)\b",
                    QRegularExpression.PatternOption.CaseInsensitiveOption,
                ),
                f_warn,
            )
        )

        # Info / Success
        f_info = QTextCharFormat()
        f_info.setForeground(QColor("#34d399"))
        f_info.setFontWeight(QFont.Weight.Bold)
        self.rules.append(
            (
                QRegularExpression(
                    r"\b(INFO|NOTICE|SUCCESS)\b",
                    QRegularExpression.PatternOption.CaseInsensitiveOption,
                ),
                f_info,
            )
        )

        # HTTP Verbs
        f_http = QTextCharFormat()
        f_http.setForeground(QColor("#38bdf8"))
        f_http.setFontWeight(QFont.Weight.Bold)
        self.rules.append(
            (
                QRegularExpression(r"\b(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\b"),
                f_http,
            )
        )

        # HTTP Status codes
        f_2xx = QTextCharFormat()
        f_2xx.setForeground(QColor("#4ade80"))
        self.rules.append((QRegularExpression(r"\b2\d{2}\b"), f_2xx))

        f_4xx = QTextCharFormat()
        f_4xx.setForeground(QColor("#fb923c"))
        self.rules.append((QRegularExpression(r"\b4\d{2}\b"), f_4xx))

        f_5xx = QTextCharFormat()
        f_5xx.setForeground(QColor("#ef4444"))
        f_5xx.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r"\b5\d{2}\b"), f_5xx))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            match_iter = pattern.globalMatch(text)
            while match_iter.hasNext():
                m = match_iter.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# -------------------------------------------------------------
# Background Worker for Heavy Docker Operations (Async)
# -------------------------------------------------------------
class OperationWorker(QThread):
    finished_op = pyqtSignal(bool, str, str)  # success, message, new_container_id

    def __init__(self, op_type, **kwargs):
        super().__init__()
        self.op_type = op_type
        self.kwargs = kwargs

    def run(self):
        try:
            client = get_docker_client()

            if self.op_type == "pull":
                tag = self.kwargs["tag"]
                client.images.pull(tag)
                self.finished_op.emit(True, f"Image '{tag}' pulled successfully.", "")

            elif self.op_type == "delete_image":
                img_id = self.kwargs["image_id"]
                tag = self.kwargs.get("tag", img_id)
                client.images.remove(img_id, force=True)
                self.finished_op.emit(True, f"Image '{tag}' removed.", "")

            elif self.op_type == "lifecycle":
                cid = self.kwargs["cid"]
                action = self.kwargs["action"]
                container = client.containers.get(cid)
                if action == "restart":
                    container.restart()
                elif action == "stop":
                    container.stop()
                elif action == "start":
                    container.start()
                self.finished_op.emit(True, f"Container {action}ed successfully.", cid)

            elif self.op_type == "rebuild":
                cid = self.kwargs["cid"]
                old_c = client.containers.get(cid)
                attrs = old_c.attrs
                img_tag = attrs["Config"]["Image"]
                name = old_c.name

                sanitized_ports = {}
                port_bindings = attrs.get("HostConfig", {}).get("PortBindings") or {}
                for container_port, host_list in port_bindings.items():
                    if host_list:
                        host_port = host_list[0].get("HostPort")
                        if host_port:
                            sanitized_ports[container_port] = int(host_port)

                env = attrs.get("Config", {}).get("Env", [])
                volumes = attrs.get("HostConfig", {}).get("Binds") or []
                cmd = attrs.get("Config", {}).get("Cmd")
                entrypoint = attrs.get("Config", {}).get("Entrypoint")
                restart_policy = (
                    attrs.get("HostConfig", {})
                    .get("RestartPolicy", {})
                    .get("Name", "no")
                )

                try:
                    client.images.pull(img_tag)
                except Exception:
                    pass

                try:
                    old_c.stop(timeout=5)
                except Exception:
                    pass
                old_c.remove(force=True)
                time.sleep(0.5)

                create_kwargs = {
                    "image": img_tag,
                    "name": name,
                    "environment": env,
                    "detach": True,
                }
                if sanitized_ports:
                    create_kwargs["ports"] = sanitized_ports
                if volumes:
                    create_kwargs["volumes"] = volumes
                if cmd:
                    create_kwargs["command"] = cmd
                if entrypoint:
                    create_kwargs["entrypoint"] = entrypoint
                if restart_policy and restart_policy != "no":
                    create_kwargs["restart_policy"] = {"Name": restart_policy}

                new_c = client.containers.run(**create_kwargs)
                self.finished_op.emit(
                    True, f"Container '{name}' rebuilt successfully!", new_c.id
                )

            elif self.op_type == "apply_env":
                cid = self.kwargs["cid"]
                new_env = self.kwargs["new_env"]
                old_c = client.containers.get(cid)
                attrs = old_c.attrs
                img_tag = attrs["Config"]["Image"]
                name = old_c.name

                sanitized_ports = {}
                port_bindings = attrs.get("HostConfig", {}).get("PortBindings") or {}
                for container_port, host_list in port_bindings.items():
                    if host_list:
                        host_port = host_list[0].get("HostPort")
                        if host_port:
                            sanitized_ports[container_port] = int(host_port)

                volumes = attrs.get("HostConfig", {}).get("Binds") or []
                cmd = attrs.get("Config", {}).get("Cmd")

                try:
                    old_c.stop(timeout=5)
                except Exception:
                    pass
                old_c.remove(force=True)
                time.sleep(0.5)

                create_kwargs = {
                    "image": img_tag,
                    "name": name,
                    "environment": new_env,
                    "detach": True,
                }
                if sanitized_ports:
                    create_kwargs["ports"] = sanitized_ports
                if volumes:
                    create_kwargs["volumes"] = volumes
                if cmd:
                    create_kwargs["command"] = cmd

                new_c = client.containers.run(**create_kwargs)
                self.finished_op.emit(
                    True,
                    f"Container '{name}' updated with new environment variables.",
                    new_c.id,
                )

        except Exception as e:
            self.finished_op.emit(False, str(e), "")


# -------------------------------------------------------------
# Background Telemetry & Images Poller (Fully Async)
# -------------------------------------------------------------
class TelemetryWorker(QThread):
    containers_updated = pyqtSignal(list)
    images_updated = pyqtSignal(list)
    stats_updated = pyqtSignal(dict)
    daemon_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._is_running = True
        self._force_poll = False

    def request_immediate_poll(self):
        self._force_poll = True

    def run(self):
        while self._is_running:
            self.poll_docker()
            for _ in range(20):
                if not self._is_running:
                    return
                if self._force_poll:
                    self._force_poll = False
                    break
                self.msleep(100)

    def poll_docker(self):
        try:
            client = get_docker_client()

            # Containers list
            containers = client.containers.list(all=True)
            container_data = []

            for c in containers:
                ports = []
                seen_ports = set()
                raw_ports = c.attrs.get("NetworkSettings", {}).get("Ports") or {}
                for internal_port, host_bindings in raw_ports.items():
                    if host_bindings:
                        for b in host_bindings:
                            hp = b.get("HostPort")
                            key = f"{hp}->{internal_port}"
                            if hp and key not in seen_ports:
                                seen_ports.add(key)
                                ports.append({"host": hp, "container": internal_port})

                container_data.append(
                    {
                        "id": c.id,
                        "short_id": c.short_id,
                        "name": c.name.lstrip("/"),
                        "status": c.status.lower(),
                        "image": c.image.tags[0]
                        if c.image.tags
                        else (c.attrs.get("Config", {}).get("Image") or c.short_id),
                        "created": c.attrs.get("Created", "")[:19].replace("T", " "),
                        "ports": ports,
                        "attrs": c.attrs,
                        "env": c.attrs.get("Config", {}).get("Env", []),
                    }
                )

            self.containers_updated.emit(container_data)

            # Images list
            images = client.images.list()
            img_data = []
            for img in images:
                tags = img.tags if img.tags else ["<none>:<none>"]
                for t in tags:
                    repo, tag = t.split(":") if ":" in t else (t, "<none>")
                    size_mb = round(img.attrs.get("Size", 0) / (1024 * 1024), 1)
                    img_data.append(
                        {
                            "id": img.short_id.replace("sha256:", ""),
                            "full_id": img.id,
                            "repo": repo,
                            "tag": tag,
                            "full_tag": t,
                            "size": f"{size_mb} MB"
                            if size_mb < 1000
                            else f"{round(size_mb / 1024, 2)} GB",
                            "created": img.attrs.get("Created", "")[:10],
                        }
                    )
            self.images_updated.emit(img_data)

            # Container stats (running containers only)
            for c in containers:
                if not self._is_running:
                    break
                if c.status == "running":
                    try:
                        raw = c.stats(stream=False)
                        cpu = self._calculate_cpu(raw)
                        mem_usage_gb = raw.get("memory_stats", {}).get("usage", 0) / (
                            1024**3
                        )
                        mem_limit_gb = raw.get("memory_stats", {}).get("limit", 1) / (
                            1024**3
                        )

                        self.stats_updated.emit(
                            {
                                "id": c.id,
                                "cpu": cpu,
                                "mem_usage_gb": round(mem_usage_gb, 2),
                                "mem_limit_gb": round(mem_limit_gb, 2),
                            }
                        )
                    except Exception:
                        continue

        except Exception as e:
            self.daemon_error.emit(str(e))

    def _calculate_cpu(self, d):
        try:
            cpu_count = len(d["cpu_stats"]["cpu_usage"]["percpu_usage"])
        except (KeyError, TypeError):
            cpu_count = 1

        cpu_delta = float(d["cpu_stats"]["cpu_usage"]["total_usage"]) - float(
            d["precpu_stats"]["cpu_usage"]["total_usage"]
        )
        system_delta = float(d["cpu_stats"].get("system_cpu_usage", 0)) - float(
            d["precpu_stats"].get("system_cpu_usage", 0)
        )

        if system_delta > 0.0 and cpu_delta > 0.0:
            return round((cpu_delta / system_delta) * cpu_count * 100.0, 1)
        return 0.0

    def stop(self):
        self._is_running = False
        self.wait(1000)


class FastLogWorker(QThread):
    new_chunk = pyqtSignal(str)

    def __init__(self, container_id):
        super().__init__()
        self.container_id = container_id
        self._is_active = True

    def run(self):
        try:
            client = get_docker_client()
            container = client.containers.get(self.container_id)
            # Fetch existing tail first to avoid pipe blocking
            initial_logs = container.logs(stream=False, tail=120).decode(
                "utf-8", errors="replace"
            )
            cleaned_initial = re.sub(
                r"(?:\x1b|\u001b)\[[0-9;]*[a-zA-Z]", "", initial_logs
            )
            if cleaned_initial:
                self.new_chunk.emit(cleaned_initial)

            # Stream updates
            stream = container.logs(stream=True, follow=True, tail=0)
            for chunk in stream:
                if not self._is_active:
                    break
                text = chunk.decode("utf-8", errors="replace")
                cleaned_text = re.sub(r"(?:\x1b|\u001b)\[[0-9;]*[a-zA-Z]", "", text)
                self.new_chunk.emit(cleaned_text)
        except Exception:
            pass

    def stop(self):
        self._is_active = False
        self.terminate()  # Forces release of the blocking Windows named pipe handle
        self.wait(300)


# -------------------------------------------------------------
# Metric Pill Widget
# -------------------------------------------------------------
class MetricPill(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(4)

        self.title_lbl = QLabel(title.upper())
        self.title_lbl.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;"
        )

        self.val_lbl = QLabel("—")
        self.val_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #f1f5f9;")

        self.bar = QProgressBar()
        self.bar.setFixedHeight(4)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet("""
            QProgressBar { background-color: #1e293b; border-radius: 2px; }
            QProgressBar::chunk { background-color: #38bdf8; border-radius: 2px; }
        """)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.val_lbl)
        layout.addWidget(self.bar)

        self.setStyleSheet("""
            MetricPill {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
        """)

    def set_data(self, val_text, percentage=0, color="#38bdf8"):
        self.val_lbl.setText(val_text)
        self.bar.setValue(min(max(int(percentage), 0), 100))
        self.bar.setStyleSheet(f"""
            QProgressBar {{ background-color: #1e293b; border-radius: 2px; }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 2px; }}
        """)


# -------------------------------------------------------------
# Main Application Dashboard
# -------------------------------------------------------------
class DockerStudioApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Docker Studio Telemetry")

        # Set titlebar and window icon (works on both Windows & Linux)
        icon_path = get_asset_path("docker_studio.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.resize(1440, 920)

        self.containers = {}
        self.images_cache = []
        self.container_metrics = {}
        self.selected_cid = None
        self.log_worker = None
        self.op_worker = None
        self.raw_log_buffer = []

        # Cross-platform fonts (Windows: Segoe UI, Ubuntu: Ubuntu/Noto/DejaVu)
        self.font_status = QFont()
        self.font_status.setFamilies(
            ["Segoe UI", "Ubuntu", "Noto Sans", "DejaVu Sans", "sans-serif"]
        )
        self.font_status.setPointSize(9)
        self.font_status.setWeight(QFont.Weight.Bold)

        self.font_name = QFont()
        self.font_name.setFamilies(
            ["Segoe UI", "Ubuntu", "Noto Sans", "DejaVu Sans", "sans-serif"]
        )
        self.font_name.setPointSize(10)
        self.font_name.setWeight(QFont.Weight.Bold)

        self.init_theme()
        self.init_ui()
        self.init_worker()

    def init_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b0f17;
            }
            QWidget {
                color: #e2e8f0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            QTableWidget {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: #1e293b;
                selection-color: #ffffff;
                outline: none;
            }
            QTableWidget::item {
                padding: 4px 12px;
                border-bottom: 1px solid #1e293b;
            }
            QHeaderView::section {
                background-color: #0b0f17;
                color: #64748b;
                font-size: 11px;
                font-weight: 700;
                padding: 10px 12px;
                border: none;
                border-bottom: 2px solid #1e293b;
                text-transform: uppercase;
            }
            QTabWidget::pane {
                border: 1px solid #1e293b;
                background: #0f172a;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #0b0f17;
                color: #94a3b8;
                padding: 8px 18px;
                font-size: 12px;
                font-weight: 600;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #1e293b;
                color: #38bdf8;
                border-bottom: 2px solid #38bdf8;
            }
            QSplitter::handle {
                background-color: #1e293b;
                height: 2px;
            }
            QScrollBar:vertical {
                background: #0b0f17;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                min-height: 20px;
                border-radius: 3px;
            }
        """)

    def init_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # 1. Top Header Toolbar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        logo = QLabel("⚡")
        logo.setStyleSheet("font-size: 20px;")
        top_bar.addWidget(logo)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(1)
        brand = QLabel("Docker Studio Telemetry")
        brand.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc;")
        sub = QLabel("Real-time kernel sockets, containers & image manager")
        sub.setStyleSheet("font-size: 11px; color: #64748b;")
        brand_col.addWidget(brand)
        brand_col.addWidget(sub)
        top_bar.addLayout(brand_col)

        top_bar.addStretch()

        # Dedicated Refresh Button (Rounded)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_refresh.setFixedHeight(30)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #f1f5f9; font-weight: 600; font-size: 12px;
                padding: 0 16px; border-radius: 6px; border: 1px solid #334155;
            }
            QPushButton:hover { background: #334155; }
        """)
        btn_refresh.clicked.connect(self.trigger_manual_refresh)
        top_bar.addWidget(btn_refresh)

        # Pull Image Button (Rounded)
        btn_pull_top = QPushButton("Pull Image...")
        btn_pull_top.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_pull_top.setFixedHeight(30)
        btn_pull_top.setStyleSheet("""
            QPushButton {
                background: #0284c7; color: white; font-weight: 700; font-size: 12px;
                padding: 0 18px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background: #0369a1; }
        """)
        btn_pull_top.clicked.connect(self.prompt_pull_image)
        top_bar.addWidget(btn_pull_top)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Filter current view...")
        self.search_bar.setFixedWidth(240)
        self.search_bar.setFixedHeight(30)
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #111827;
                border: 1px solid #1f2937;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                color: #ffffff;
            }
            QLineEdit:focus { border: 1px solid #38bdf8; }
        """)
        self.search_bar.textChanged.connect(self.filter_active_table)
        top_bar.addWidget(self.search_bar)

        self.status_pill = QLabel("Connecting...")
        self.status_pill.setFixedHeight(30)
        self.status_pill.setStyleSheet("""
            background-color: #111827; color: #94a3b8; font-size: 12px;
            font-weight: 600; padding: 0 14px; border-radius: 6px; border: 1px solid #1f2937;
        """)
        top_bar.addWidget(self.status_pill)

        layout.addLayout(top_bar)

        # 2. Main Splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        # TOP VIEW: Master Navigation Tabs
        self.master_tabs = QTabWidget()

        # Tab 1: Containers Table (Evenly Spaced Rows)
        self.table_containers = QTableWidget()
        self.table_containers.setColumnCount(6)
        self.table_containers.setHorizontalHeaderLabels(
            ["Status", "Name", "Image", "CPU %", "RAM Usage (GB)", "Mapped Ports"]
        )
        self.table_containers.verticalHeader().setVisible(False)
        self.table_containers.verticalHeader().setDefaultSectionSize(48)
        self.table_containers.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_containers.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table_containers.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table_containers.itemSelectionChanged.connect(self.on_container_selected)
        self.table_containers.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table_containers.customContextMenuRequested.connect(
            self.show_container_context_menu
        )

        ch = self.table_containers.horizontalHeader()
        ch.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        ch.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        ch.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        ch.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        ch.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        ch.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table_containers.setColumnWidth(0, 140)
        self.table_containers.setColumnWidth(3, 100)
        self.table_containers.setColumnWidth(4, 180)

        self.master_tabs.addTab(self.table_containers, "Containers")

        # Tab 2: Images Table (Evenly Spaced Rows)
        self.table_images = QTableWidget()
        self.table_images.setColumnCount(6)
        self.table_images.setHorizontalHeaderLabels(
            ["Repository", "Tag", "Image ID", "Virtual Size", "Created Date", "Actions"]
        )
        self.table_images.verticalHeader().setVisible(False)
        self.table_images.verticalHeader().setDefaultSectionSize(48)
        self.table_images.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table_images.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table_images.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        ih = self.table_images.horizontalHeader()
        ih.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ih.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        ih.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        ih.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        ih.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        ih.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table_images.setColumnWidth(1, 130)
        self.table_images.setColumnWidth(2, 140)
        self.table_images.setColumnWidth(3, 130)
        self.table_images.setColumnWidth(4, 140)
        self.table_images.setColumnWidth(5, 230)

        self.master_tabs.addTab(self.table_images, "Images")
        splitter.addWidget(self.master_tabs)

        # BOTTOM VIEW: Telemetry Drawer
        drawer = QWidget()
        drawer_layout = QVBoxLayout(drawer)
        drawer_layout.setContentsMargins(0, 6, 0, 0)
        drawer_layout.setSpacing(8)

        # Action Strip
        action_strip = QHBoxLayout()
        action_strip.setSpacing(10)

        self.cpu_pill = MetricPill("CPU Core Load")
        self.mem_pill = MetricPill("Resident Memory (GB)")
        action_strip.addWidget(self.cpu_pill)
        action_strip.addWidget(self.mem_pill)

        action_strip.addStretch()

        # Rounded Action Buttons
        self.btn_start = self._make_action_btn(
            "Start", "primary", lambda: self.exec_container_action("start")
        )
        self.btn_restart = self._make_action_btn(
            "Restart", "neutral", lambda: self.exec_container_action("restart")
        )
        self.btn_stop = self._make_action_btn(
            "Stop", "danger", lambda: self.exec_container_action("stop")
        )
        self.btn_rebuild = self._make_action_btn(
            "Rebuild", "neutral", self.rebuild_current_container
        )

        action_strip.addWidget(self.btn_start)
        action_strip.addWidget(self.btn_restart)
        action_strip.addWidget(self.btn_stop)
        action_strip.addWidget(self.btn_rebuild)

        drawer_layout.addLayout(action_strip)

        # Bottom Inspector Tabs
        self.detail_tabs = QTabWidget()

        # Tab 1: Live Rich Logs
        log_panel = QWidget()
        v_log = QVBoxLayout(log_panel)
        v_log.setContentsMargins(10, 8, 10, 8)
        v_log.setSpacing(8)

        log_ctrls = QHBoxLayout()
        self.log_filter = QLineEdit()
        self.log_filter.setPlaceholderText("Filter logs...")
        self.log_filter.setFixedWidth(200)
        self.log_filter.setFixedHeight(28)
        self.log_filter.setStyleSheet("""
            QLineEdit { background-color: #0b0f17; border: 1px solid #1f2937; border-radius: 6px; padding: 4px 8px; color: #ffffff; font-size: 11px; }
        """)
        self.log_filter.textChanged.connect(self.render_filtered_logs)
        log_ctrls.addWidget(self.log_filter)

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedHeight(28)
        btn_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_clear.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #cbd5e1; border: 1px solid #334155;
                padding: 0 14px; border-radius: 6px; font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background: #334155; }
        """)
        btn_clear.clicked.connect(self.clear_logs)
        log_ctrls.addWidget(btn_clear)
        log_ctrls.addStretch()

        v_log.addLayout(log_ctrls)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #05080e;
                color: #e2e8f0;
                font-family: 'Consolas', 'Menlo', 'Monaco', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        self.highlighter = TerminalLogHighlighter(self.console.document())

        v_log.addWidget(self.console)
        self.detail_tabs.addTab(log_panel, "Live Rich Logs")

        # Tab 2: Environment Variables Editor
        env_panel = QWidget()
        v_env = QVBoxLayout(env_panel)
        v_env.setContentsMargins(10, 8, 10, 8)
        v_env.setSpacing(8)

        env_help = QLabel(
            "Environment variables used by this container. Edit or append new KEY=VALUE lines below."
        )
        env_help.setStyleSheet("color: #94a3b8; font-size: 11px;")
        v_env.addWidget(env_help)

        self.env_editor = QPlainTextEdit()
        self.env_editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #070a0f;
                color: #f1f5f9;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        v_env.addWidget(self.env_editor)

        btn_apply_env = QPushButton("Apply & Recreate Container")
        btn_apply_env.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_apply_env.setFixedHeight(34)
        btn_apply_env.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold; font-size: 12px;
                padding: 0 20px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        btn_apply_env.clicked.connect(self.apply_env_changes)
        v_env.addWidget(btn_apply_env)

        self.detail_tabs.addTab(env_panel, "Environment Variables (Edit)")

        # Tab 3: Inspect Configuration
        self.spec_view = QPlainTextEdit()
        self.spec_view.setReadOnly(True)
        self.spec_view.setStyleSheet("""
            QPlainTextEdit {
                background-color: #070a0f; color: #38bdf8; font-family: 'Consolas', monospace;
                font-size: 12px; border: none; padding: 10px;
            }
        """)
        self.detail_tabs.addTab(self.spec_view, "Inspect Configuration")

        drawer_layout.addWidget(self.detail_tabs)
        splitter.addWidget(drawer)

        splitter.setSizes([450, 420])
        layout.addWidget(splitter)

        self.showMaximized()

    def _make_action_btn(self, text, style_type, slot):
        btn = QPushButton(text)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setFixedHeight(30)

        if style_type == "primary":  # Blue like 'Pull Image...'
            style = """
                QPushButton { background-color: #0284c7; color: #ffffff; font-weight: 700; font-size: 12px; padding: 0 16px; border-radius: 6px; border: none; }
                QPushButton:hover { background-color: #0369a1; }
                QPushButton:disabled { background-color: #1e293b; color: #475569; }
            """
        elif style_type == "danger":  # Dark muted red for Stop
            style = """
                QPushButton { background-color: #1e293b; color: #f87171; border: 1px solid #7f1d1d; font-weight: 600; font-size: 12px; padding: 0 16px; border-radius: 6px; }
                QPushButton:hover { background-color: #991b1b; color: #ffffff; border: 1px solid #ef4444; }
                QPushButton:disabled { background-color: #0f172a; color: #475569; border: 1px solid #1e293b; }
            """
        else:  # Neutral slate for Start / Restart
            style = """
                QPushButton { background-color: #1e293b; color: #f1f5f9; border: 1px solid #334155; font-weight: 600; font-size: 12px; padding: 0 16px; border-radius: 6px; }
                QPushButton:hover { background-color: #334155; color: #ffffff; border: 1px solid #64748b; }
                QPushButton:disabled { background-color: #0f172a; color: #475569; border: 1px solid #1e293b; }
            """

        btn.setStyleSheet(style)
        btn.clicked.connect(slot)
        return btn

    def init_worker(self):
        self.worker = TelemetryWorker()
        self.worker.containers_updated.connect(self.on_containers_updated)
        self.worker.images_updated.connect(self.on_images_updated)
        self.worker.stats_updated.connect(self.on_stats_updated)
        self.worker.daemon_error.connect(self.on_error)
        self.worker.start()

    def trigger_manual_refresh(self):
        self.status_pill.setText("Refreshing...")
        # Delegate directly to the background thread without freezing GUI
        self.worker.request_immediate_poll()

    def on_containers_updated(self, containers):
        active = sum(1 for c in containers if c["status"] == "running")
        self.status_pill.setText(f"{active} Running  /  {len(containers)} Total")
        self.status_pill.setStyleSheet("""
            background-color: #10b9811a; color: #10b981; font-size: 12px;
            font-weight: 600; padding: 6px 14px; border-radius: 6px; border: 1px solid #10b98144;
        """)

        currently_selected_id = self.selected_cid
        self.containers = {c["id"]: c for c in containers}

        self.table_containers.setRowCount(len(containers))
        for row, c in enumerate(containers):
            cid = c["id"]
            status = c["status"]

            status_item = QTableWidgetItem(f"●  {status.upper()}")
            color = "#10b981" if status == "running" else "#ef4444"
            status_item.setForeground(QColor(color))
            status_item.setFont(self.font_status)
            status_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.table_containers.setItem(row, 0, status_item)

            name_item = QTableWidgetItem(c["name"])
            name_item.setFont(self.font_name)
            name_item.setData(Qt.ItemDataRole.UserRole, cid)
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.table_containers.setItem(row, 1, name_item)

            img_item = QTableWidgetItem(c["image"])
            img_item.setForeground(QColor("#94a3b8"))
            img_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.table_containers.setItem(row, 2, img_item)

            stats = self.container_metrics.get(cid, {})
            cpu_val = f"{stats.get('cpu', 0.0)}%"
            cpu_item = QTableWidgetItem(cpu_val)
            cpu_item.setForeground(QColor("#38bdf8"))
            cpu_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.table_containers.setItem(row, 3, cpu_item)

            mem_u = stats.get("mem_usage_gb", 0.0)
            mem_l = stats.get("mem_limit_gb", 0.0)
            mem_str = f"{mem_u:.2f} GB / {mem_l:.2f} GB" if mem_u > 0 else "—"
            mem_item = QTableWidgetItem(mem_str)
            mem_item.setForeground(QColor("#cbd5e1"))
            mem_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.table_containers.setItem(row, 4, mem_item)

            port_strs = [
                f"{p['host']} -> {p['container']}" for p in c["ports"] if p.get("host")
            ]
            port_item = QTableWidgetItem(", ".join(port_strs) if port_strs else "—")
            port_item.setForeground(QColor("#38bdf8" if port_strs else "#64748b"))
            port_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.table_containers.setItem(row, 5, port_item)

            if cid == currently_selected_id:
                self.table_containers.selectRow(row)

        if not currently_selected_id and len(containers) > 0:
            self.table_containers.selectRow(0)

        self.update_action_button_states()

    def on_images_updated(self, images):
        self.images_cache = images
        self.table_images.setRowCount(len(images))

        for row, img in enumerate(images):
            repo_item = QTableWidgetItem(img["repo"])
            repo_item.setFont(self.font_name)
            repo_item.setData(Qt.ItemDataRole.UserRole, img)
            repo_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

            tag_item = QTableWidgetItem(img["tag"])
            tag_item.setForeground(QColor("#38bdf8"))
            tag_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

            id_item = QTableWidgetItem(img["id"])
            id_item.setForeground(QColor("#94a3b8"))
            id_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

            size_item = QTableWidgetItem(img["size"])
            size_item.setForeground(QColor("#cbd5e1"))
            size_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

            date_item = QTableWidgetItem(img["created"])
            date_item.setForeground(QColor("#64748b"))
            date_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )

            self.table_images.setItem(row, 0, repo_item)
            self.table_images.setItem(row, 1, tag_item)
            self.table_images.setItem(row, 2, id_item)
            self.table_images.setItem(row, 3, size_item)
            self.table_images.setItem(row, 4, date_item)

            # Capsule Rounded Action Buttons
            actions_cell = QWidget()
            h = QHBoxLayout(actions_cell)
            h.setContentsMargins(6, 4, 6, 4)
            h.setSpacing(8)

            tag_ref = img["full_tag"]
            img_id = img["full_id"]

            # Clean Slate Buttons for Table Actions
            btn_p = QPushButton("Pull latest")
            btn_p.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_p.setFixedHeight(28)
            btn_p.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #38bdf8;
                    border: 1px solid #334155;
                    font-size: 11px;
                    font-weight: 600;
                    border-radius: 6px;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: #0284c7;
                    color: #ffffff;
                    border: 1px solid #0284c7;
                }
            """)
            btn_p.clicked.connect(lambda _, t=tag_ref: self.repull_image(t))

            btn_d = QPushButton("Delete")
            btn_d.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_d.setFixedHeight(28)
            btn_d.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #f87171;
                    border: 1px solid #334155;
                    font-size: 11px;
                    font-weight: 600;
                    border-radius: 6px;
                    padding: 0 12px;
                }
                QPushButton:hover {
                    background-color: #dc2626;
                    color: #ffffff;
                    border: 1px solid #dc2626;
                }
            """)
            btn_d.clicked.connect(
                lambda _, i=img_id, t=tag_ref: self.delete_image(i, t)
            )

            h.addWidget(btn_p)
            h.addWidget(btn_d)
            self.table_images.setCellWidget(row, 5, actions_cell)

    def on_stats_updated(self, stats):
        cid = stats["id"]
        self.container_metrics[cid] = stats

        if cid == self.selected_cid:
            cpu = stats.get("cpu", 0.0)
            mem_u = stats.get("mem_usage_gb", 0.0)
            mem_l = stats.get("mem_limit_gb", 1.0)
            mem_pct = (mem_u / mem_l) * 100 if mem_l > 0 else 0

            self.cpu_pill.set_data(f"{cpu}%", cpu, "#38bdf8")
            self.mem_pill.set_data(
                f"{mem_u:.2f} GB / {mem_l:.2f} GB", mem_pct, "#a855f7"
            )

    def update_action_button_states(self):
        c_info = self.containers.get(self.selected_cid)
        if not c_info:
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_restart.setEnabled(False)
            self.btn_rebuild.setEnabled(False)
            return

        is_running = c_info["status"] == "running"
        self.btn_start.setEnabled(not is_running)
        self.btn_stop.setEnabled(is_running)
        self.btn_restart.setEnabled(True)
        self.btn_rebuild.setEnabled(True)

    def on_container_selected(self):
        row = self.table_containers.currentRow()
        if row < 0:
            return
        name_item = self.table_containers.item(row, 1)
        if not name_item:
            return

        cid = name_item.data(Qt.ItemDataRole.UserRole)
        if cid == self.selected_cid:
            return

        self.selected_cid = cid
        c_info = self.containers.get(cid)
        if not c_info:
            return

        self.update_action_button_states()
        self.spec_view.setPlainText(json.dumps(c_info["attrs"], indent=2))
        self.env_editor.setPlainText("\n".join(c_info.get("env", [])))

        self.clear_logs()
        if self.log_worker:
            self.log_worker.stop()

        self.log_worker = FastLogWorker(cid)
        self.log_worker.new_chunk.connect(self.append_log)
        self.log_worker.start()

    def append_log(self, text):
        lines = text.splitlines()
        for line in lines:
            self.raw_log_buffer.append(line)
            q = self.log_filter.text().lower()
            if not q or q in line.lower():
                self.console.appendPlainText(line)

    def render_filtered_logs(self):
        q = self.log_filter.text().lower()
        self.console.clear()
        for line in self.raw_log_buffer:
            if not q or q in line.lower():
                self.console.appendPlainText(line)

    def clear_logs(self):
        self.console.clear()
        self.raw_log_buffer = []

    def filter_active_table(self):
        query = self.search_bar.text().lower()
        for r in range(self.table_containers.rowCount()):
            name = self.table_containers.item(r, 1).text().lower()
            img = self.table_containers.item(r, 2).text().lower()
            self.table_containers.setRowHidden(r, not (query in name or query in img))

        for r in range(self.table_images.rowCount()):
            repo = self.table_images.item(r, 0).text().lower()
            tag = self.table_images.item(r, 1).text().lower()
            self.table_images.setRowHidden(r, not (query in repo or query in tag))

    # -------------------------------------------------------------
    # Context Menus
    # -------------------------------------------------------------
    def show_container_context_menu(self, pos: QPoint):
        item = self.table_containers.itemAt(pos)
        if not item:
            return
        row = item.row()
        cid = self.table_containers.item(row, 1).data(Qt.ItemDataRole.UserRole)
        c_info = self.containers.get(cid)
        if not c_info:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; padding: 6px; }
            QMenu::item:selected { background-color: #0284c7; }
        """)

        menu.addAction("Start", lambda: self.exec_container_action("start", cid))
        menu.addAction("Restart", lambda: self.exec_container_action("restart", cid))
        menu.addAction("Stop", lambda: self.exec_container_action("stop", cid))
        menu.addAction("Rebuild Container", lambda: self.rebuild_current_container(cid))
        menu.addSeparator()

        for p in c_info["ports"]:
            host = p.get("host")
            if host:
                menu.addAction(
                    f"Open http://localhost:{host}",
                    lambda h=host: webbrowser.open(f"http://localhost:{h}"),
                )

        menu.exec(self.table_containers.mapToGlobal(pos))

    # -------------------------------------------------------------
    # Async Image Operations
    # -------------------------------------------------------------
    def prompt_pull_image(self):
        text, ok = QInputDialog.getText(
            self, "Pull Image", "Enter Image Repository & Tag (e.g. redis:alpine):"
        )
        if ok and text.strip():
            self.repull_image(text.strip())

    def repull_image(self, tag):
        if "<none>" in tag:
            QMessageBox.warning(
                self, "Invalid Tag", "Cannot pull an untagged dangling image."
            )
            return

        self.status_pill.setText(f"Pulling {tag}...")
        self.status_pill.setStyleSheet(
            "background-color: #0284c722; color: #38bdf8; padding: 6px 14px; border-radius: 6px;"
        )

        self.op_worker = OperationWorker("pull", tag=tag)
        self.op_worker.finished_op.connect(self.on_operation_done)
        self.op_worker.start()

    def delete_image(self, image_id, tag_label):
        reply = QMessageBox.question(
            self,
            "Delete Image",
            f"Are you sure you want to delete image {tag_label}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_pill.setText("Deleting image...")
        self.op_worker = OperationWorker(
            "delete_image", image_id=image_id, tag=tag_label
        )
        self.op_worker.finished_op.connect(self.on_operation_done)
        self.op_worker.start()

    # -------------------------------------------------------------
    # Async Container Rebuild & Lifecycle
    # -------------------------------------------------------------
    def exec_container_action(self, action, target_cid=None):
        cid = target_cid or self.selected_cid
        if not cid:
            return

        self.status_pill.setText(f"{action.capitalize()}ing container...")
        self.op_worker = OperationWorker("lifecycle", action=action, cid=cid)
        self.op_worker.finished_op.connect(self.on_operation_done)
        self.op_worker.start()

    def rebuild_current_container(self, target_cid=None):
        cid = target_cid or self.selected_cid
        if not cid:
            return

        reply = QMessageBox.question(
            self,
            "Rebuild Container",
            "This will pull the latest version of the image in the background, remove the current container, "
            "and create a new one with identical volumes, ports, and configuration.\n\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_pill.setText("Rebuilding container in background...")
        self.status_pill.setStyleSheet(
            "background-color: #8b5cf622; color: #a78bfa; padding: 6px 14px; border-radius: 6px;"
        )

        self.op_worker = OperationWorker("rebuild", cid=cid)
        self.op_worker.finished_op.connect(self.on_operation_done)
        self.op_worker.start()

    def apply_env_changes(self):
        if not self.selected_cid:
            return

        reply = QMessageBox.question(
            self,
            "Recreate Container?",
            "Recreating container to apply updated environment variables.\nProceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        new_env = [
            line.strip()
            for line in self.env_editor.toPlainText().splitlines()
            if line.strip()
        ]
        self.status_pill.setText("Applying env changes...")
        self.op_worker = OperationWorker(
            "apply_env", cid=self.selected_cid, new_env=new_env
        )
        self.op_worker.finished_op.connect(self.on_operation_done)
        self.op_worker.start()

    def on_operation_done(self, success, message, new_cid):
        self.trigger_manual_refresh()

        if success:
            if new_cid:
                self.selected_cid = new_cid
                self.clear_logs()
                if self.log_worker:
                    self.log_worker.stop()
                self.log_worker = FastLogWorker(new_cid)
                self.log_worker.new_chunk.connect(self.append_log)
                self.log_worker.start()
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.critical(
                self, "Operation Error", f"Operation failed:\n{message}"
            )

    def on_error(self, err):
        self.status_pill.setText("Docker Daemon Offline")
        self.status_pill.setStyleSheet("""
            background-color: #ef444422; color: #ef4444; border: 1px solid #ef4444;
            padding: 6px 14px; border-radius: 6px; font-weight: 600; font-size: 12px;
        """)

    def closeEvent(self, event):
        self.worker.stop()
        if self.log_worker:
            self.log_worker.stop()
        event.accept()


# -------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Sets application-wide icon for dialogs, modals, and taskbar entries
    icon_path = get_asset_path("docker_studio.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = DockerStudioApp()
    window.show()
    sys.exit(app.exec())
