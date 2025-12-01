import json
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QSplitter, QFrame
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from .map_widget import MapWidget
from shapely.geometry import Point, shape as shp_shape
from pyproj import Transformer

class MainWindow(QWidget):
    def __init__(self, route_service, polygon_path: str = None):
        super().__init__()
        self.route_service = route_service
        self.setWindowTitle("Mapa de Rutas")
        try:
            icon_path = Path(__file__).resolve().parent / 'assets' / 'train.svg'
            self.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass

        # Center map
        self.map = MapWidget()

        # Left panel (origen/destino)
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)

        self.txt_origin = QLineEdit()
        self.txt_origin.setPlaceholderText("Origen (texto)")
        btn_origin_search = QPushButton("Buscar Origen")
        btn_origin_search.clicked.connect(lambda: self.map.search_and_set('origin', self.txt_origin.text()))
        btn_origin_pick = QPushButton("Seleccionar Origen en Mapa")
        btn_origin_pick.clicked.connect(lambda: self.map.set_pick_mode('origin'))

        self.txt_dest = QLineEdit()
        self.txt_dest.setPlaceholderText("Destino (texto)")
        btn_dest_search = QPushButton("Buscar Destino")
        btn_dest_search.clicked.connect(lambda: self.map.search_and_set('dest', self.txt_dest.text()))
        btn_dest_pick = QPushButton("Seleccionar Destino en Mapa")
        btn_dest_pick.clicked.connect(lambda: self.map.set_pick_mode('dest'))

        btn_calc = QPushButton("Calcular Ruta")
        btn_calc.clicked.connect(self.on_calc)
        btn_clear = QPushButton("Limpiar Ruta")
        btn_clear.clicked.connect(self.map.clear_route)

        left_layout.addWidget(QLabel("Origen"))
        left_layout.addWidget(self.txt_origin)
        left_layout.addWidget(btn_origin_search)
        left_layout.addWidget(btn_origin_pick)
        left_layout.addSpacing(8)
        left_layout.addWidget(QLabel("Destino"))
        left_layout.addWidget(self.txt_dest)
        left_layout.addWidget(btn_dest_search)
        left_layout.addWidget(btn_dest_pick)
        left_layout.addSpacing(12)
        left_layout.addWidget(btn_calc)
        left_layout.addWidget(btn_clear)
        left_layout.addStretch(1)

        # Right panel (resumen)
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        self.lbl_total = QLabel("Total: -")
        self.list_summary = QListWidget()
        right_layout.addWidget(QLabel("Resumen"))
        right_layout.addWidget(self.lbl_total)
        right_layout.addWidget(self.list_summary)

        # Splitter: left | map | right
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.map)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([280, 900, 320])

        # Toggle buttons row
        top_row = QHBoxLayout()
        btn_toggle_left = QPushButton("Panel Origen/Destino")
        btn_toggle_right = QPushButton("Panel Resumen")
        btn_toggle_left.clicked.connect(lambda: self.toggle_widget(self.left_panel))
        btn_toggle_right.clicked.connect(lambda: self.toggle_widget(self.right_panel))
        top_row.addWidget(btn_toggle_left)
        top_row.addWidget(btn_toggle_right)
        top_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(splitter)

        # Load polygon and set on map
        self.boundary_shape = None
        if polygon_path is None:
            polygon_path = str(Path(__file__).resolve().parents[1] / 'data' / 'osm' / 'jalisco.geojson.txt')
        try:
            with open(polygon_path, 'r', encoding='utf-8') as f:
                gj = json.load(f)
            self.map.set_polygon(gj)
            # Keep shapely geometry for server-side validation
            feat = gj['features'][0]
            self.boundary_shape = shp_shape(feat['geometry'])
        except Exception:
            self.boundary_shape = None

        # Transformer to metric (EPSG:3857)
        self.to_3857 = Transformer.from_crs(4326, 3857, always_xy=True)

    def toggle_widget(self, w: QWidget):
        w.setVisible(not w.isVisible())

    def _validate_inside(self, lat: float, lon: float) -> bool:
        if self.boundary_shape is None:
            return True
        try:
            return self.boundary_shape.contains(Point(lon, lat)) or self.boundary_shape.touches(Point(lon, lat))
        except Exception:
            return True

    def _width_for_route_type(self, route_type) -> int:
        try:
            rt = int(route_type)
        except Exception:
            rt = 1
        mapping = {0: 8, 1: 6, 2: 4, 3: 3}
        return mapping.get(rt, 4)

    def on_calc(self):
        # Get origin/dest from the map asynchronously
        def _after_points(pts):
            origin = pts.get('origin') if pts else None
            dest = pts.get('dest') if pts else None
            if not origin or not dest:
                self.lbl_total.setText("Faltan origen y/o destino")
                return

            olat, olon = origin
            dlat, dlon = dest
            # Validate inside polygon
            if not (self._validate_inside(olat, olon) and self._validate_inside(dlat, dlon)):
                self.lbl_total.setText("Origen/Destino fuera del polígono")
                return

            # Project to meters EPSG:3857
            ox, oy = self.to_3857.transform(olon, olat)
            dx, dy = self.to_3857.transform(dlon, dlat)
            p_o = Point(ox, oy)
            p_d = Point(dx, dy)

            segments = None
            total_time = None
            # Prefer a rich route_service API if available
            if hasattr(self.route_service, 'plan_route'):
                try:
                    result = self.route_service.plan_route(p_o, p_d)
                    segments = result.get('segments', []) if result else []
                    total_time = result.get('total_time_sec', None)
                except Exception:
                    segments = None
            # Fallback to a simple polyline using metric Points
            if segments is None:
                try:
                    coords = None
                    if hasattr(self.route_service, 'route_walking'):
                        coords = self.route_service.route_walking(p_o, p_d)
                    elif hasattr(self.route_service, 'get_route'):
                        # legacy API fallback if present
                        coords = self.route_service.get_route(olat, olon, dlat, dlon)
                    self.map.draw_route(coords)
                    self.lbl_total.setText("Ruta dibujada (fallback)")
                    self.list_summary.clear()
                    return
                except Exception:
                    self.lbl_total.setText("No se pudo obtener ruta")
                    return

            # Normalize segments for map drawing
            draw_segments = []
            walking_time = 0
            self.list_summary.clear()
            for seg in segments:
                mode = seg.get('mode', 'transit')
                coords = seg.get('coords') or seg.get('geometry') or []
                route_color = seg.get('route_color') or seg.get('color')
                if route_color and not route_color.startswith('#'):
                    route_color = f"#{route_color}"
                route_type = seg.get('route_type', 1)
                width = self._width_for_route_type(route_type) if mode != 'walk' else 3
                dash = '6,6' if mode == 'walk' else None
                draw_segments.append({
                    'mode': mode,
                    'coords': coords,
                    'route_color': route_color or ("#666666" if mode == 'walk' else "#7b1fa2"),
                    'weight': width,
                    'dashArray': dash
                })

                # Summary item
                time_sec = seg.get('time_sec', None)
                title = None
                if mode == 'walk':
                    title = f"Caminar: {round((time_sec or 0)/60)} min"
                    walking_time += (time_sec or 0)
                else:
                    headsign = seg.get('headsign') or seg.get('trip_headsign') or ''
                    rname = seg.get('route_short_name') or seg.get('route_long_name') or ''
                    title = f"{rname} → {headsign}: {round((time_sec or 0)/60)} min"
                item = QListWidgetItem(title)
                if route_color:
                    item.setForeground(Qt.white) if mode != 'walk' else None
                    # Apply colored background for quick visual
                    item_widget = QLabel(title)
                    bg = route_color if mode != 'walk' else '#666666'
                    item_widget.setStyleSheet(f"padding:6px; background:{bg}; color:white;")
                    lw_item = QListWidgetItem()
                    lw_item.setSizeHint(item_widget.sizeHint())
                    self.list_summary.addItem(lw_item)
                    self.list_summary.setItemWidget(lw_item, item_widget)
                else:
                    self.list_summary.addItem(item)

            if total_time is not None:
                self.lbl_total.setText(f"Total: {round(total_time/60)} min (caminar ~{round(walking_time/60)} min)")
            else:
                self.lbl_total.setText("Ruta calculada")

            self.map.draw_route_segments(draw_segments)

        # Fetch points from JS and continue in callback
        self.map.get_points(_after_points)
