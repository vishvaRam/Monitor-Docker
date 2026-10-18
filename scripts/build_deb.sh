#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# If the script is inside a subfolder (e.g., scripts/), point to parent; otherwise use current directory
if [ -f "${SCRIPT_DIR}/app.py" ]; then
    PROJECT_ROOT="${SCRIPT_DIR}"
elif [ -f "${SCRIPT_DIR}/main.py" ]; then
    PROJECT_ROOT="${SCRIPT_DIR}"
else
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
fi
cd "$PROJECT_ROOT"

# Determine main entry file
ENTRY_FILE="app.py"

APP_NAME="docker-studio"
VERSION="1.0.0"
ARCH="amd64"
DEB_NAME="${APP_NAME}_${VERSION}_${ARCH}.deb"

RELEASE_DIR="${PROJECT_ROOT}/releases"
BUILD_DIR="${PROJECT_ROOT}/build"
STAGE_ROOT=$(mktemp -d /tmp/deb-build-XXXXXX)
PKG_DIR="${STAGE_ROOT}/${APP_NAME}_${VERSION}_${ARCH}"

echo "==> Project root: ${PROJECT_ROOT}"
echo "==> Entry file: ${ENTRY_FILE}"
echo "==> Cleaning old build artifacts..."
rm -rf build dist "${RELEASE_DIR}/${DEB_NAME}"
mkdir -p "${RELEASE_DIR}" "${BUILD_DIR}"

# 0. Ensure assets exist
if [ ! -f "${PROJECT_ROOT}/assets/docker_studio.png" ]; then
    echo "==> Assets missing. Generating application icons..."
    uv run generate_icons.py
fi

# 1. Build PyInstaller bundle
echo "==> Freezing application with PyInstaller..."
uv run pyinstaller --noconfirm --onedir --windowed \
    --name "${APP_NAME}" \
    --specpath "${BUILD_DIR}" \
    --hidden-import "docker" \
    --hidden-import "docker.errors" \
    --hidden-import "urllib3" \
    --hidden-import "requests" \
    --hidden-import "PyQt6.QtCore" \
    --hidden-import "PyQt6.QtGui" \
    --hidden-import "PyQt6.QtWidgets" \
    --add-data "${PROJECT_ROOT}/assets:assets" \
    "${ENTRY_FILE}"

# 2. Setup standard Linux packaging filesystem
echo "==> Assembling deb package structure..."
mkdir -p "${PKG_DIR}/opt/${APP_NAME}"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/share/applications"
mkdir -p "${PKG_DIR}/usr/share/icons/hicolor/256x256/apps"
mkdir -p "${PKG_DIR}/DEBIAN"

# Copy binary & runtime assets
cp -a "dist/${APP_NAME}/." "${PKG_DIR}/opt/${APP_NAME}/"
ln -s "/opt/${APP_NAME}/${APP_NAME}" "${PKG_DIR}/usr/bin/${APP_NAME}"

# Install desktop icon (using the generated 256/512 PNG)
if [ -f "${PROJECT_ROOT}/assets/docker_studio.png" ]; then
    cp "${PROJECT_ROOT}/assets/docker_studio.png" "${PKG_DIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
fi

# 3. Generate Desktop Entry
cat << EOF > "${PKG_DIR}/usr/share/applications/${APP_NAME}.desktop"
[Desktop Entry]
Name=Docker Studio
GenericName=Container Telemetry & Lifecycle Manager
Comment=Real-time kernel sockets, container telemetry and image manager
Exec=/usr/bin/${APP_NAME}
Icon=${APP_NAME}
Terminal=false
Type=Application
Categories=Development;System;Utility;Monitor;
StartupWMClass=${APP_NAME}
Keywords=docker;container;telemetry;monitor;logs;images;
EOF

# 4. Generate Control File
cat << EOF > "${PKG_DIR}/DEBIAN/control"
Package: ${APP_NAME}
Version: ${VERSION}
Section: devel
Priority: optional
Architecture: ${ARCH}
Depends: libxcb-cursor0, libgl1, libxcb1, libxkbcommon-x11-0, libdbus-1-3
Suggests: docker-ce | docker.io
Maintainer: Vishva Ramamurthy
Description: Docker Studio Telemetry & Container Dashboard
 A high-performance real-time desktop telemetry dashboard for Docker daemons.
 Features container runtime vitals, async live streaming colored logs,
 dynamic environment variable re-provisioning, and image management.
EOF

# 5. Generate Post-Install Hook (Update desktop/icon databases)
cat << 'EOF' > "${PKG_DIR}/DEBIAN/postinst"
#!/bin/sh
set -e

if [ -x /usr/bin/update-desktop-database ]; then
    /usr/bin/update-desktop-database -q || true
fi

if [ -x /usr/bin/gtk-update-icon-cache ]; then
    /usr/bin/gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
EOF
chmod 755 "${PKG_DIR}/DEBIAN/postinst"

# 6. Fix permissions & Build Package
chmod -R 755 "${PKG_DIR}"
chmod 644 "${PKG_DIR}/DEBIAN/control"
chmod 644 "${PKG_DIR}/usr/share/applications/${APP_NAME}.desktop"
if [ -f "${PKG_DIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png" ]; then
    chmod 644 "${PKG_DIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
fi

echo "==> Building .deb package..."
dpkg-deb --build --root-owner-group "${PKG_DIR}" "${RELEASE_DIR}/${DEB_NAME}"
rm -rf "${STAGE_ROOT}"

echo "✅ Linux package successfully generated at: ${RELEASE_DIR}/${DEB_NAME}"