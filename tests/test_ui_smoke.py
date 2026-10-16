"""La interfaz arranca, navega y se cierra sin cámaras ni modelos (QT_QPA_PLATFORM=offscreen)."""

import pytest

from smartguard.core.camera_manager import CameraManager
from smartguard.core.config import Camera, Settings
from smartguard.core.db import Database, Vehicle


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("SMARTGUARD_HOME", str(tmp_path))
    from smartguard.ui.main_window import MainWindow

    settings = Settings(cameras=[Camera(name="Garita", source="0"), Camera(name="Piscina", source="rtsp://x")])
    db = Database(tmp_path / "test.db")
    db.save_vehicle(Vehicle(plate="PBZ5579", owner_name="Ana", unit="Casa 1"))
    manager = CameraManager(settings, tmp_path / "test.db")  # no se llama start(): sin hilos de cámara
    win = MainWindow(settings, db, manager)
    qtbot.addWidget(win)
    win.show()
    yield win
    db.close()


def test_navigates_every_page(window):
    for i, action in enumerate(window.actions):
        action.trigger()
        assert window.pages.currentIndex() == i


def test_manual_lookup_shows_registered_vehicle(window):
    window.access.lookup.setText("pbz-5579")
    window.access._manual_lookup()
    assert window.access.card.banner.text() == "AUTORIZADO"
    assert "Ana" in window.access.card.details.text()
    window.access.lookup.setText("XYZ1234")
    window.access._manual_lookup()
    assert window.access.card.banner.text() == "NO REGISTRADO"


def test_cameras_page_has_a_tile_per_enabled_camera(window):
    assert set(window.cameras.tiles) == {c.id for c in window.settings.cameras}


def test_registry_lists_vehicles(window):
    assert window.registry.table.rowCount() == 1
    window.registry.search.setText("casa 9")
    assert window.registry.table.rowCount() == 0


def test_weapon_alert_banner_counter_and_review(window):
    from smartguard.core.db import FALSE_ALARM, WeaponEvent

    event = window.db.add_weapon_event(
        WeaponEvent(ts="2026-10-16 21:15:00", camera="Garita", kind="firearm", confidence=0.71)
    )
    window._on_weapon_alert("cam", event)
    assert window.banner.isVisible()
    assert "ARMA DE FUEGO" in window.banner.text.text()
    assert window.alerts_action.text() == "Alertas (1)"
    window.banner.dismiss()
    window._view_alert(event.id)
    assert window.pages.currentWidget() is window.alerts
    window.alerts._review(FALSE_ALARM)
    assert window.alerts_action.text() == "Alertas"
    assert window.db.weapon_events()[0].review == FALSE_ALARM
