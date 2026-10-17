from smartguard.core.config import Camera, Settings


def test_settings_saved_before_fps_limit_get_the_default():
    old = {"cameras": [{"name": "Portón", "source": "rtsp://cam", "id": "abc"}]}
    assert Settings.from_dict(old).cameras[0].max_fps == Camera().max_fps == 5


def test_fps_limit_survives_a_round_trip():
    settings = Settings(cameras=[Camera(name="Garita", max_fps=12)])
    assert settings.copy().cameras[0].max_fps == 12
