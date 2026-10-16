"""Estadísticas: conteos y accesos por día, por hora, fotos de vehículos y exportación CSV."""

import csv
import dataclasses
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QStackedBarSeries, QValueAxis
from PySide6.QtCore import QDate, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from smartguard.core.db import AUTHORIZED, BLOCKED, DECISION_LABELS, UNKNOWN, Database
from smartguard.core.frame_utils import load_pixmap
from smartguard.ui.theme import DECISION_COLORS
from smartguard.vision.tracking import VEHICLE_LABELS

ANIMALS = frozenset({"gato", "perro", "caballo", "oveja", "vaca"})
# Paleta categórica validada (dataviz), en orden fijo por entidad: el color sigue al tipo, no al ranking.
SERIES = (
    ("auto", "Autos", "#2a78d6", "#3987e5"),
    ("persona", "Personas", "#eb6834", "#d95926"),
    ("moto", "Motos", "#1baf7a", "#199e70"),
    ("camión", "Camiones", "#eda100", "#c98500"),
    ("bus", "Buses", "#e87ba4", "#d55181"),
    ("bicicleta", "Bicicletas", "#008300", "#008300"),
    ("animal", "Animales", "#6250d6", "#9085e9"),
)


def _group(label: str) -> str:
    return "animal" if label in ANIMALS else label


def _is_dark() -> bool:
    return QApplication.palette().window().color().lightness() < 128


def _surface() -> QColor:
    return QApplication.palette().base().color()


def _style(bar_set: QBarSet, color: str) -> None:
    bar_set.setColor(QColor(color))
    bar_set.setPen(QPen(_surface(), 2))  # separación de 2 px entre segmentos apilados


def _chart(title: str) -> tuple[QChart, QChartView]:
    chart = QChart()
    chart.setTitle(title)
    chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)
    chart.setTheme(QChart.ChartTheme.ChartThemeDark if _is_dark() else QChart.ChartTheme.ChartThemeLight)
    chart.setBackgroundBrush(_surface())
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
    view = QChartView(chart)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setMinimumHeight(260)
    return chart, view


def _attach_axes(chart: QChart, series, categories: list[str], maximum: int) -> None:
    x = QBarCategoryAxis()
    x.append(categories)
    y = QValueAxis()
    y.setLabelFormat("%d")
    top = max(maximum, 1)
    if top <= 10:  # pocas unidades: una marca por entero, sin repetir "1, 1"
        y.setRange(0, top)
        y.setTickCount(top + 1)
    else:
        y.setRange(0, top)
        y.applyNiceNumbers()
    y.setGridLineColor(QColor(128, 128, 128, 50))
    chart.addAxis(x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(x)
    series.attachAxis(y)


def _hover(bar_set: QBarSet, categories: list[str]) -> None:
    def show(status: bool, index: int) -> None:
        if status:
            QToolTip.showText(QCursor.pos(), f"{categories[index]}\n{bar_set.label()}: {int(bar_set.at(index))}")
        else:
            QToolTip.hideText()

    bar_set.hovered.connect(show)


class Kpi(QWidget):
    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.value = QLabel("0")
        self.value.setProperty("role", "kpi")
        label = QLabel(caption)
        label.setProperty("role", "kpi-caption")
        layout = QVBoxLayout(self)
        layout.addWidget(self.value)
        layout.addWidget(label)


class StatisticsPage(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.start = QDateEdit(QDate.currentDate().addDays(-6))
        self.end = QDateEdit(QDate.currentDate())
        for edit in (self.start, self.end):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd/MM/yyyy")
            edit.dateChanged.connect(self.refresh)
        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh)
        export_access = QPushButton("Exportar accesos CSV")
        export_access.clicked.connect(self._export_access)
        export_counts = QPushButton("Exportar conteos CSV")
        export_counts.clicked.connect(self._export_counts)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Desde"))
        filters.addWidget(self.start)
        filters.addWidget(QLabel("Hasta"))
        filters.addWidget(self.end)
        filters.addWidget(refresh)
        filters.addStretch(1)
        filters.addWidget(export_access)
        filters.addWidget(export_counts)

        self.kpis = {key: Kpi(caption) for key, caption in (
            ("vehicles", "Vehículos contados"), ("people", "Personas"), ("animals", "Animales"),
            ("access", "Placas leídas"), ("unknown", "No registradas"), ("blocked", "Bloqueadas"),
            ("weapons", "Alertas de armas"),
        )}
        kpi_row = QHBoxLayout()
        for kpi in self.kpis.values():
            kpi_row.addWidget(kpi)

        self.counts_chart, counts_view = _chart("Conteo por día")
        self.access_chart, access_view = _chart("Accesos por placa por día")
        self.hours_chart, hours_view = _chart("Conteo por hora del día (todo el período)")
        charts = QWidget()
        grid = QGridLayout(charts)
        grid.addWidget(counts_view, 0, 0)
        grid.addWidget(access_view, 0, 1)
        grid.addWidget(hours_view, 1, 0, 1, 2)

        self.photo_filter = QComboBox()
        self.photo_filter.addItem("Todos los vehículos", "")
        for label in sorted(VEHICLE_LABELS):
            self.photo_filter.addItem(label.capitalize(), label)
        self.photo_filter.currentIndexChanged.connect(self._load_photos)
        self.photos = QListWidget()
        self.photos.setViewMode(QListWidget.ViewMode.IconMode)
        self.photos.setIconSize(QSize(200, 140))
        self.photos.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.photos.setSpacing(8)
        self.photos.itemDoubleClicked.connect(
            lambda item: QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole)))
        )
        photos_tab = QWidget()
        photos_layout = QVBoxLayout(photos_tab)
        photos_layout.addWidget(self.photo_filter)
        photos_layout.addWidget(self.photos, 1)
        photos_layout.addWidget(QLabel("Doble clic para abrir la foto en tamaño completo."))

        tabs = QTabWidget()
        tabs.addTab(charts, "Gráficos")
        tabs.addTab(photos_tab, "Fotos de vehículos")
        tabs.currentChanged.connect(lambda i: i == 1 and self._load_photos())
        self.tabs = tabs

        title = QLabel("Estadísticas")
        title.setProperty("role", "title")
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(filters)
        layout.addLayout(kpi_row)
        layout.addWidget(tabs, 1)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def _range(self) -> tuple[str, str, list[str]]:
        start = self.start.date().toPython()
        end = max(self.end.date().toPython(), start)
        days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
        return start.isoformat(), (end + timedelta(days=1)).isoformat(), days

    def refresh(self) -> None:
        start, end, days = self._range()
        per_day = self.db.counts_per_day(start, end)
        decisions = self.db.decisions_per_day(start, end)
        labels = self.db.counts_per_label(start, end)
        vehicles = sum(n for k, n in labels.items() if k in VEHICLE_LABELS)
        self.kpis["vehicles"].value.setText(str(vehicles))
        self.kpis["people"].value.setText(str(labels.get("persona", 0)))
        self.kpis["animals"].value.setText(str(sum(n for k, n in labels.items() if k in ANIMALS)))
        self.kpis["access"].value.setText(str(sum(sum(d.values()) for d in decisions.values())))
        self.kpis["unknown"].value.setText(str(sum(d.get(UNKNOWN, 0) for d in decisions.values())))
        self.kpis["blocked"].value.setText(str(sum(d.get(BLOCKED, 0) for d in decisions.values())))
        self.kpis["weapons"].value.setText(str(len(self.db.weapon_events(start, end, limit=None))))
        categories = [date.fromisoformat(d).strftime("%d/%m") for d in days]
        self._draw_counts(per_day, days, categories)
        self._draw_access(decisions, days, categories)
        self._draw_hours(self.db.counts_per_hour(start, end))
        if self.tabs.currentIndex() == 1:
            self._load_photos()

    def _draw_counts(self, per_day: dict, days: list[str], categories: list[str]) -> None:
        chart = self.counts_chart
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)
        grouped = {d: {} for d in days}
        for day, counts in per_day.items():
            for label, n in counts.items():
                grouped[day][_group(label)] = grouped[day].get(_group(label), 0) + n
        series = QStackedBarSeries()
        dark = _is_dark()
        for key, name, light_color, dark_color in SERIES:
            values = [grouped[d].get(key, 0) for d in days]
            if not any(values):
                continue
            bar_set = QBarSet(name)
            bar_set.append(values)
            _style(bar_set, dark_color if dark else light_color)
            _hover(bar_set, categories)
            series.append(bar_set)
        chart.addSeries(series)
        _attach_axes(chart, series, categories, max((sum(g.values()) for g in grouped.values()), default=0))

    def _draw_access(self, decisions: dict, days: list[str], categories: list[str]) -> None:
        chart = self.access_chart
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)
        series = QStackedBarSeries()
        for decision in (AUTHORIZED, UNKNOWN, BLOCKED):
            bar_set = QBarSet(DECISION_LABELS[decision])
            bar_set.append([decisions.get(d, {}).get(decision, 0) for d in days])
            _style(bar_set, DECISION_COLORS[decision])
            _hover(bar_set, categories)
            series.append(bar_set)
        chart.addSeries(series)
        _attach_axes(chart, series, categories, max((sum(d.values()) for d in decisions.values()), default=0))

    def _draw_hours(self, per_hour: dict[int, int]) -> None:
        chart = self.hours_chart
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)
        categories = [f"{h:02d}" for h in range(24)]
        bar_set = QBarSet("Conteos")
        bar_set.append([per_hour.get(h, 0) for h in range(24)])
        _style(bar_set, SERIES[0][3] if _is_dark() else SERIES[0][2])
        _hover(bar_set, [f"{c}:00" for c in categories])
        series = QBarSeries()
        series.append(bar_set)
        chart.addSeries(series)
        chart.legend().hide()
        _attach_axes(chart, series, categories, max(per_hour.values(), default=0))

    def _load_photos(self) -> None:
        start, end, _ = self._range()
        self.photos.clear()
        rows = [r for r in self.db.count_events(start, end, self.photo_filter.currentData()) if r["image_path"]]
        for row in rows[:500]:
            if not Path(row["image_path"]).exists():
                continue
            item = QListWidgetItem(QIcon(load_pixmap(row["image_path"], 200, 140)),
                                   f"{row['label']} · {row['camera']}\n{row['ts']}")
            item.setData(Qt.ItemDataRole.UserRole, row["image_path"])
            self.photos.addItem(item)

    def _export_access(self) -> None:
        start, end, _ = self._range()
        path, _ = QFileDialog.getSaveFileName(self, "Exportar accesos", f"accesos_{start}.csv", "CSV (*.csv)")
        if not path:
            return
        events = self.db.plate_events(start=start, end=end, limit=None)
        fields = [f.name for f in dataclasses.fields(events[0])] if events else ["ts", "plate", "decision"]
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            for event in events:
                writer.writerow(dataclasses.asdict(event))

    def _export_counts(self) -> None:
        start, end, _ = self._range()
        path, _ = QFileDialog.getSaveFileName(self, "Exportar conteos", f"conteos_{start}.csv", "CSV (*.csv)")
        if not path:
            return
        rows = self.db.count_events(start, end)
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["id", "ts", "camera", "label", "track_id", "direction", "image_path"])
            writer.writerows(tuple(row) for row in rows)

