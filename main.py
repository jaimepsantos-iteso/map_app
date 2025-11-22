import sys
import os

from PyQt5.QtWidgets import QApplication

from data.graph_loader import GraphLoader
from core.routing import RouteService
from gui.main_window import MainWindow

LOAD_TYPE="local"

def main():

    for v in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        os.environ.pop(v, None)

    app = QApplication(sys.argv)

    loader = GraphLoader()
    if LOAD_TYPE=="local":
        filepath = "data/osm/mexico.osm"

        # Guadalajara bounding box
        bbox_guadalajara = (20.80, 20.50, -103.20, -103.50)

        graph = loader.load_local(
            filepath=filepath,
            network_type="drive",
            bbox=bbox_guadalajara
        )    
    else:
        graph = loader.load("Guadalajara, Mexico")

    route_service = RouteService(graph)

    win = MainWindow(route_service)
    win.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
