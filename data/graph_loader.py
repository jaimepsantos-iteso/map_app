import osmnx as ox

class GraphLoader:
    def load(self, place_name):
        print(f"Loading OSM graph for: {place_name}")
        # Drive or walk network depending on your application
        graph = ox.graph_from_place(place_name, network_type="drive")
        graph = ox.add_edge_speeds(graph)
        graph = ox.add_edge_travel_times(graph)
        return graph
    
    def load_local(self, filepath, network_type="drive", bbox=None):
        """
        Load a graph from a local OSM file.

        Args:
            filepath (str): Path to .osm, .osm.xml or .osm.pbf file.
            network_type (str): Type of network ("drive", "walk", etc.)
            bbox (tuple): Optional (north, south, east, west) to clip.

        Returns:
            networkx.MultiDiGraph: The loaded (and clipped) graph.
        """
        print(f"Loading OSM data from: {filepath}")

        G = ox.graph_from_xml(filepath) #, network_type=network_type arg not supported TBD to fix the filter

        if bbox:
            north, south, east, west = bbox
            print("Clipping graph to bounding box...")
            G = ox.truncate.truncate_graph_bbox(
                G, north=north, south=south, east=east, west=west
            )
        
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)

        return G
