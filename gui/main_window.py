from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QPushButton
)
from .map_widget import MapWidget

class MainWindow(QWidget):
    def __init__(self, route_service):
        super().__init__()
        self.route_service = route_service

        self.map = MapWidget()

        self.start_lat = QLineEdit()
        self.start_lon = QLineEdit()
        self.end_lat = QLineEdit()
        self.end_lon = QLineEdit()

        btn = QPushButton("Calculate Route")
        btn.clicked.connect(self.on_calc)

        form = QHBoxLayout()
        form.addWidget(QLabel("Start lat:"))
        form.addWidget(self.start_lat)
        form.addWidget(QLabel("lon:"))
        form.addWidget(self.start_lon)
        form.addWidget(QLabel("End lat:"))
        form.addWidget(self.end_lat)
        form.addWidget(QLabel("lon:"))
        form.addWidget(self.end_lon)
        form.addWidget(btn)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.map)
        self.setLayout(layout)

    def on_calc(self):
        lat1 = float(self.start_lat.text())
        lon1 = float(self.start_lon.text())
        lat2 = float(self.end_lat.text())
        lon2 = float(self.end_lon.text())

        coords = self.route_service.get_route(lat1, lon1, lat2, lon2)
        self.map.draw_route(coords)
