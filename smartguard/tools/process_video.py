"""Procesa un video sin interfaz e imprime placas confirmadas y conteos.

    uv run python -m smartguard.tools.process_video samples/demo.mp4 [--line x1,y1,x2,y2] [--out carpeta]

Sirve para medir la precisión y la velocidad con grabaciones reales de las cámaras.
"""

import argparse
import tempfile
import time
from pathlib import Path

from smartguard.core.config import Camera, Settings
from smartguard.core.db import DECISION_LABELS, Database
from smartguard.core.recorder import EventRecorder
from smartguard.core.video_source import VideoSource
from smartguard.vision.counting import CounterConfig
from smartguard.vision.pipeline import Pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video")
    parser.add_argument("--line", help="línea de conteo x1,y1,x2,y2 (por defecto se cuenta todo lo que aparece)")
    parser.add_argument("--out", type=Path, help="carpeta para capturas y base de datos (por defecto, temporal)")
    parser.add_argument("--max-frames", type=int, default=0)
    args = parser.parse_args()

    counter = None
    if args.line:
        x1, y1, x2, y2 = (float(v) for v in args.line.split(","))
        counter = CounterConfig("line", ((x1, y1), (x2, y2))).to_dict()
    settings = Settings.load()
    camera = Camera(name="cli", source=args.video, counter=counter, loop_video=False)
    out = args.out or Path(tempfile.mkdtemp(prefix="smartguard-"))
    out.mkdir(parents=True, exist_ok=True)
    db = Database(out / "smartguard.db")
    recorder = EventRecorder(db, out / "captures", camera.name)

    started = time.monotonic()
    pipeline = Pipeline(settings, camera)
    print(f"Modelos cargados en {time.monotonic() - started:.1f}s (dispositivo: {pipeline.device})")

    video = VideoSource(args.video, loop=False)
    if not video.open():
        raise SystemExit(f"No se pudo abrir {args.video}")
    frames, started = 0, time.monotonic()
    while (frame := video.read()) is not None:
        frames += 1
        result = pipeline.process(frame)
        for confirmed in result.confirmed:
            access = recorder.record_plate(confirmed)
            print(f"  frame {frames:5}: placa {confirmed.plate.formatted} ({confirmed.plate.province}) "
                  f"conf={confirmed.confidence:.2f} -> {DECISION_LABELS[access.event.decision]}")
        for alert in result.weapon_alerts:
            weapon = recorder.record_weapon(alert)
            print(f"  frame {frames:5}: ALERTA {weapon.kind} conf={weapon.confidence:.2f} -> {weapon.snapshot_path}")
        for event in result.count_events:
            recorder.record_count(event)
        for shot in result.shots:
            recorder.record_shot(shot)
        if args.max_frames and frames >= args.max_frames:
            break
    for shot in pipeline.finish():
        recorder.record_shot(shot)
    video.release()
    elapsed = time.monotonic() - started
    print(f"{frames} frames en {elapsed:.1f}s ({frames / elapsed:.1f} fps)")
    if pipeline.totals:
        print(f"Conteo: {dict(pipeline.totals.by_label)}  dirección: {dict(pipeline.totals.by_direction)}")
    photos = sum(1 for r in db.count_events("2000-01-01", "2100-01-01") if r["image_path"])
    print(f"Fotos de vehículos guardadas: {photos}. Alertas de armas: {len(db.weapon_events())}. Resultados en {out}")


if __name__ == "__main__":
    main()
