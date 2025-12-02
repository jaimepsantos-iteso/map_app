import sys
import argparse
import random as rd
from shapely.geometry import Point
import folium

from PyQt5.QtWidgets import QApplication

from data.graph_loader import GraphLoader
from core.routing import RouteService
from data.gtfs_loader import GTFSLoader
from gui.main_window import MainWindow

from core.routing import point_from_text, openMap

def main(args):

    #app = QApplication(sys.argv)

    graph_loader = GraphLoader()

    # Create walking graph limited to the polygon
    graph_walk = graph_loader.create_graph_walk("data/graphs/ZMG_walk.pkl", "data/osm/ZMG_enclosure_2km.geojson")

    gtfs_loader = GTFSLoader()

    # Load transit data from GTFS files
    transit_df = gtfs_loader.load_transit_dataframe("data/gtfs")

    stops_df = gtfs_loader.load_stops_dataframe("data/gtfs", transit_df)
    # Create transit graph from GTFS data and stops with a max walking distance of 300 seconds
    graph_transit = graph_loader.create_graph_transit("data/graphs/ZMG_transit.pkl", stops_df, 300)

    route_service = RouteService(graph_walk, graph_transit, stops_df, transit_df)

        # Si se pasaron src y dst, los usamos para calcular la ruta automáticamente
    if args.src and args.dst:

        src = point_from_text(args.src)
        dst = point_from_text(args.dst)

        if src is None or dst is None:
            print("No posible to geocode the provided addresses")
            #choose random points if geocoding fails
            start = rd.choice(list(graph_walk.nodes))
            destination = rd.choice(list(graph_walk.nodes))

            src = Point(graph_walk.nodes[start]['x'], graph_walk.nodes[start]['y'])
            dst = Point(graph_walk.nodes[destination]['x'], graph_walk.nodes[destination]['y'])

        try:
            route_service.route_combined(src, dst)
            total_time, m = route_service.route_combined(src, dst)

            folium.LayerControl().add_to(m)

            print("Total time (minutes):", round(sum(total_time)/60))

            openMap(m)
            
        except Exception as e:
            print(f"Error to calculate route: {e}")


    # Le pasamos el polygon_path a la ventana principal
    #win = MainWindow(route_service, polygon_path=args.polygon_path)
    #win.show()
    #sys.exit(app.exec_())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aplicación de Mapa de Rutas")
    
    parser.add_argument(
        "--src",
        type=str,
        default=None,
        help="Texto de la dirección de origen para buscar automáticamente."
    )

    parser.add_argument(
        "--dst",
        type=str,
        default=None,
        help="Texto de la dirección de destino para buscar automáticamente."
    )

    args = parser.parse_args()
    main(args)
