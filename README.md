# ⚡ Docker Studio Telemetry

[![Release](https://img.shields.io/badge/Release-v1.0.0-7aa2f7?style=for-the-badge&logo=github)](https://github.com/vishvaRam/devport-inspector/releases/latest)
[![Platform](<https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-bb9af7?style=for-the-badge&logo=linux&logoColor=white>)](https://github.com/vishvaRam/devport-inspector/releases)
[![Python](https://img.shields.io/badge/Python-3.9%2B-7dcfff?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/UI-PyQt6-f7768e?style=for-the-badge&logo=qt&logoColor=white)](https://riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-9ece6a?style=for-the-badge)](LICENSE)

A high-performance, real-time desktop telemetry dashboard and lifecycle manager for Docker daemons, built with **Python 3**, **PyQt6**, and the **Docker Engine API**.

Designed for developers and DevOps engineers who want a modern, low-overhead, dark-themed GUI to inspect container vitals, stream colored logs, update environment variables on the fly, and manage images.

---

## ✨ Features

- **📊 Real-Time Telemetry & Resource Vitals**

  - Live CPU percentage and memory (RAM) usage tracking per container.
  - Overall cluster health dashboard with telemetry metrics (Running Containers, Images, Aggregate CPU & Memory utilization).
  - Background asynchronous polling via dedicated Qt worker threads (`TelemetryWorker`) without freezing the UI.
- **🔄 Full Container Lifecycle Management**

  - **Start**, **Restart**, and **Stop** containers with one click or via context menus.
  - **Smart Rebuild / Reprovision**: Seamlessly stop, pull the latest image layer, and re-create containers while preserving port mappings, volume bindings, commands, entrypoints, and restart policies.
  - Context menu shortcuts (Inspect, View Logs, Restart, Stop, Remove).
- **📜 Live Streaming Rich Terminal Logs**

  - Non-blocking real-time log streaming (`FastLogWorker`).
  - Terminal syntax highlighting (`TerminalLogHighlighter`) with colored badges for log levels (`INFO`, `WARN`, `ERROR`, `FATAL`, `DEBUG`), timestamps, HTTP verbs, JSON keys, URLs, and UUIDs.
  - In-panel search filter and log buffer clearing.
- **⚙️ Dynamic Environment Variable Editor**

  - Inspect active container environment variables.
  - Modify `KEY=VALUE` pairs and apply changes directly; Docker Studio will automatically re-provision the container with the updated environment.
- **🔍 Configuration Inspector**

  - Formatted, syntax-highlighted JSON view of complete container specifications and inspect metadata (`docker inspect`).
- **📦 Docker Image Manager**

  - View all local images with Repository, Tag, Image ID, Virtual Size, and Creation Date.
  - Pull new images from Docker Hub or private registries with a simple prompt dialog.
  - One-click Re-pull and Delete/Remove image actions.
- **🌐 Interactive Port Mapping**

  - Displays host-to-container port bindings with clickable links to directly open services in your default web browser.
- **🎨 Modern Dark Slate UI**

  - Polished Tailwind-inspired dark theme (`#0b0f17` palette) with smooth splitters, custom metric badges, and custom application icons.
  - Native cross-platform integration for both Linux and Windows.

---

## 🛠️ Project Structure

```text
.
├── app.py                 # Main application entry point & PyQt6 GUI implementation
├── generate_icons.py      # Vector icon generation script using QPainter (PNG & ICO)
├── requirements.txt       # Python dependencies (PyQt6, docker, pyinstaller)
├── assets/                # Application icon assets
│   ├── docker_studio.png  # 512x512 application icon
│   └── docker_studio.ico  # Multi-resolution Windows icon
├── scripts/
│   └── build_deb.sh       # Automated Debian/Ubuntu .deb package build script
└── RUN.txt                # Quick build commands reference
```

---

## 📋 Prerequisites

1. **Python 3.10+**
2. **Docker Engine / Docker Desktop** running locally:
   - **Linux:** `/var/run/docker.sock` (ensure your user is in the `docker` group)
   - **Windows:** Named Pipe (`npipe:////./pipe/docker_engine`)
   - **macOS:** `/var/run/docker.sock`

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/vishvaRam/Monitor-Docker.git
cd Monitor-Docker
```

### 2. Install Dependencies

Using `pip`:

```bash
pip install -r requirements.txt
```

Or using [`uv`](https://github.com/astral-sh/uv):

```bash
uv pip install -r requirements.txt
```

### 3. Generate App Icons (Optional / First Run)

```bash
python generate_icons.py
```

### 4. Run the Application

```bash
python app.py
```

*(or `uv run app.py`)*

---

## 📦 Packaging & Building Executables

### 🐧 Linux (.deb Package)

To build a standalone Debian/Ubuntu package with desktop shortcut and icon integration:

```bash
chmod +x ./scripts/build_deb.sh
./scripts/build_deb.sh
```

Install the generated `.deb` package:

```bash
sudo apt install ./releases/docker-studio_1.0.0_amd64.deb
```

---

### 🪟 Windows (.exe Single File Executable)

To freeze the application into a standalone Windows binary using PyInstaller:

```bash
uv run pyinstaller --noconfirm --onefile --windowed \
    --name "DockerStudio_1.0.0" \
    --specpath "build" \
    --distpath "releases" \
    --icon "$(pwd -W)/assets/docker_studio.ico" \
    --hidden-import "docker" \
    --hidden-import "docker.errors" \
    --hidden-import "urllib3" \
    --hidden-import "requests" \
    --hidden-import "PyQt6.QtCore" \
    --hidden-import "PyQt6.QtGui" \
    --hidden-import "PyQt6.QtWidgets" \
    --add-data "$(pwd -W)/assets;assets" \
    app.py
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the issues page or submit a pull request.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
