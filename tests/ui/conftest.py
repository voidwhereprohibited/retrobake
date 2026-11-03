import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["RETROBAKE_OFFLINE"] = "1"  # tests never touch the network
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def app():
    from retrobake.ui.app import create_app

    return create_app([])


@pytest.fixture
def window(app):
    from retrobake.ui import theme
    from retrobake.ui.app import create_window

    theme.set_font_scale(app, 1.0)
    win = create_window(app)
    win.show()
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()
