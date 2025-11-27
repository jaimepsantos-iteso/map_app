import sys

from PyQt5.QtWidgets import QApplication

from data.graph_loader import GraphLoader
from core.routing import RouteService
from gui.main_window import MainWindow

LOAD_TYPE="local"

def main():

    for v in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        os.environ.pop(v, None)

    app = QApplication(sys.argv)

    graph_loader = GraphLoader()

    graph_walk = graph_loader.create_graph_walk("data/graphs/ZMG_walk.graphml", "data/osm/ZMG_enclosure_2km.geojson")

    transit_df = load_transit_dataframe("data/gtfs")

    graph_transit = graph_loader.create_graph_transit(transit_df)

    route_service = RouteService(graph)

    win = MainWindow(route_service)
    win.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
