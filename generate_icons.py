import os
import sys
from PyQt6 import QtCore, QtGui, QtWidgets


def generate_docker_studio_icon():
    app = (
        QtWidgets.QApplication.instance()
        or QtWidgets.QApplication(sys.argv)
    )

    os.makedirs("assets", exist_ok=True)
    size = 512
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    center_x, center_y = size / 2.0, size / 2.0

    # ------------------------------------------------------------------
    # 1. Base Squircle Frame
    # ------------------------------------------------------------------
    badge_path = QtGui.QPainterPath()
    badge_path.addRoundedRect(28.0, 28.0, float(size - 56), float(size - 56), 116.0, 116.0)

    bg_grad = QtGui.QLinearGradient(0, 0, size, size)
    bg_grad.setColorAt(0.0, QtGui.QColor("#111827"))
    bg_grad.setColorAt(0.5, QtGui.QColor("#0b0f17"))
    bg_grad.setColorAt(1.0, QtGui.QColor("#030712"))
    painter.fillPath(badge_path, bg_grad)

    badge_pen = QtGui.QPen(QtGui.QColor("#1e293b"), 5.0)
    painter.setPen(badge_pen)
    painter.drawPath(badge_path)

    # ------------------------------------------------------------------
    # 2. Telemetry Gauge Track & Activity Arc
    # ------------------------------------------------------------------
    gauge_rect = QtCore.QRectF(64.0, 64.0, size - 128.0, size - 128.0)

    # Inactive track
    track_pen = QtGui.QPen(QtGui.QColor("#1e293b"), 8.0, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(track_pen)
    painter.drawArc(gauge_rect, 35 * 16, 290 * 16)

    # Active telemetry sweep (QConicalGradient for Qt sweep/angular gradients)
    active_grad = QtGui.QConicalGradient(QtCore.QPointF(center_x, center_y), 0.0)
    active_grad.setColorAt(0.0, QtGui.QColor("#0284c7"))
    active_grad.setColorAt(0.65, QtGui.QColor("#38bdf8"))
    active_grad.setColorAt(1.0, QtGui.QColor("#4ade80"))

    active_pen = QtGui.QPen(QtGui.QBrush(active_grad), 8.0, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(active_pen)
    painter.drawArc(gauge_rect, 60 * 16, 210 * 16)

    # Orbiting telemetry pulse indicator
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor(56, 189, 248, 55))
    painter.drawEllipse(QtCore.QPointF(center_x + 155, center_y - 100), 16.0, 16.0)
    painter.setBrush(QtGui.QColor("#38bdf8"))
    painter.drawEllipse(QtCore.QPointF(center_x + 155, center_y - 100), 7.0, 7.0)

    # Telemetry radial tick marks
    tick_pen = QtGui.QPen(QtGui.QColor("#334155"), 3.0, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(tick_pen)
    for angle in [-40, -15, 10, 170, 195, 220]:
        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(angle)
        painter.drawLine(160, 0, 174, 0)
        painter.restore()

    # ------------------------------------------------------------------
    # 3. Stacked Isometric Containers (Docker Units)
    # ------------------------------------------------------------------
    def draw_container_cube(origin_x, origin_y, w=64, h=34, depth=26, primary_color="#0284c7", top_color="#38bdf8"):
        # Top Face
        top = QtGui.QPainterPath()
        top.moveTo(origin_x, origin_y - depth)
        top.lineTo(origin_x + w, origin_y - depth)
        top.lineTo(origin_x + w - 16, origin_y)
        top.lineTo(origin_x - 16, origin_y)
        top.closeSubpath()
        painter.fillPath(top, QtGui.QColor(top_color))

        # Front Face
        front = QtGui.QPainterPath()
        front.moveTo(origin_x - 16, origin_y)
        front.lineTo(origin_x + w - 16, origin_y)
        front.lineTo(origin_x + w - 16, origin_y + h)
        front.lineTo(origin_x - 16, origin_y + h)
        front.closeSubpath()
        painter.fillPath(front, QtGui.QColor(primary_color))

        # Container Rib Grooves
        groove_pen = QtGui.QPen(QtGui.QColor("#0369a1"), 2.0)
        painter.setPen(groove_pen)
        for gx in [origin_x + 4, origin_x + 22, origin_x + 40]:
            painter.drawLine(int(gx - 16), int(origin_y + 4), int(gx - 16), int(origin_y + h - 4))

        # Outlines
        outline_pen = QtGui.QPen(QtGui.QColor("#082f49"), 2.0)
        painter.setPen(outline_pen)
        painter.drawPath(top)
        painter.drawPath(front)

    # Base container tier
    draw_container_cube(164, 305, w=76, h=38, primary_color="#0369a1", top_color="#0284c7")
    draw_container_cube(252, 305, w=76, h=38, primary_color="#0369a1", top_color="#0284c7")
    draw_container_cube(340, 305, w=60, h=38, primary_color="#075985", top_color="#0369a1")

    # Mid container tier
    draw_container_cube(208, 252, w=76, h=38, primary_color="#0284c7", top_color="#38bdf8")
    draw_container_cube(296, 252, w=76, h=38, primary_color="#0284c7", top_color="#38bdf8")

    # Top container
    draw_container_cube(252, 199, w=76, h=38, primary_color="#38bdf8", top_color="#7dd3fc")

    # ------------------------------------------------------------------
    # 4. Telemetry Energy Bolt (Live Activity Overlay)
    # ------------------------------------------------------------------
    bolt = QtGui.QPainterPath()
    bolt_points = [
        QtCore.QPointF(276, 126),  # Top tip
        QtCore.QPointF(204, 238),  # Left elbow
        QtCore.QPointF(254, 238),  # Mid shelf
        QtCore.QPointF(230, 350),  # Bottom strike tip
        QtCore.QPointF(324, 218),  # Right elbow
        QtCore.QPointF(272, 218),  # Return notch
    ]
    bolt.moveTo(bolt_points[0])
    for pt in bolt_points[1:]:
        bolt.lineTo(pt)
    bolt.closeSubpath()

    bolt_grad = QtGui.QLinearGradient(204, 126, 324, 350)
    bolt_grad.setColorAt(0.0, QtGui.QColor("#fef08a"))
    bolt_grad.setColorAt(0.5, QtGui.QColor("#facc15"))
    bolt_grad.setColorAt(1.0, QtGui.QColor("#f97316"))

    painter.fillPath(bolt, bolt_grad)

    bolt_border = QtGui.QPen(QtGui.QColor("#ffffff"), 3.5, QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(bolt_border)
    painter.drawPath(bolt)

    painter.end()

    # ------------------------------------------------------------------
    # 5. Export Assets
    # ------------------------------------------------------------------
    png_path = os.path.join("assets", "docker_studio.png")
    ico_path = os.path.join("assets", "docker_studio.ico")

    pixmap.save(png_path, "PNG")
    print(f"Generated PNG: {png_path}")

    # Scale icon down to standard Windows icon sizes
    icon = QtGui.QIcon()
    for s in [16, 24, 32, 48, 64, 128, 256]:
        scaled = pixmap.scaled(
            s,
            s,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        icon.addPixmap(scaled)

    # Save highest resolution layer as ICO
    pixmap_256 = pixmap.scaled(
        256,
        256,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    pixmap_256.save(ico_path, "ICO")
    print(f"Generated Windows ICO: {ico_path}")


if __name__ == "__main__":
    generate_docker_studio_icon()