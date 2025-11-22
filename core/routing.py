import osmnx as ox
import networkx as nx

class RouteService:
    def __init__(self, graph):
        self.graph = graph

    def nearest_node(self, lat, lon):
        return ox.nearest_nodes(self.graph, lon, lat)

    def get_route(self, start_lat, start_lon, end_lat, end_lon):
        # Convert points to graph nodes
        u = self.nearest_node(start_lat, start_lon)
        v = self.nearest_node(end_lat, end_lon)

        # Shortest path using travel time
        route_nodes = nx.shortest_path(
            self.graph, u, v, weight="travel_time"
        )

        # Convert nodes to coordinates for Leaflet
        coords = [
            [self.graph.nodes[n]["y"], self.graph.nodes[n]["x"]]
            for n in route_nodes
        ]
        return coords
