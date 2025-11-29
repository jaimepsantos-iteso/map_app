import sys

from PyQt5.QtWidgets import QApplication

from data.graph_loader import GraphLoader
from core.routing import RouteService
from data.gtfs_loader import GTFSLoader
from gui.main_window import MainWindow

def main():

    app = QApplication(sys.argv)

    graph_loader = GraphLoader()

    graph_walk = graph_loader.create_graph_walk("data/graphs/ZMG_walk", "data/osm/ZMG_enclosure_2km.geojson")

    gtfs_loader = GTFSLoader()

    transit_df = gtfs_loader.load_transit_dataframe("data/gtfs")

    stops_df = gtfs_loader.load_stops_dataframe("data/gtfs", transit_df)

    graph_transit = graph_loader.create_graph_transit(stops_df)

    route_service = RouteService(graph_walk, graph_transit)

    route_service.test_transit_routing(transit_df, stops_df)

    win = MainWindow(route_service)
    win.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
