"""Start the RetroBake desktop app: ``python -m retrobake.ui``."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import theme
from .screens import default_steps
from .wizard import WizardWindow


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance()
    if app is None:
        # Honor fractional display scaling (e.g. 125% on Windows laptops).
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("RetroBake")
    app.setApplicationDisplayName("RetroBake")
    app.setOrganizationName("RetroBake")
    theme.apply_theme(app)
    return app


def create_window(app: QApplication) -> WizardWindow:
    return WizardWindow(default_steps(), app)


def main() -> int:
    app = create_app()
    win = create_window(app)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
