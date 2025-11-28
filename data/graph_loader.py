import osmnx as ox
import geopandas as gpd
import networkx as nx
import pandas as pd
import os
import pickle


class GraphLoader:

    def create_graph_walk(self, graphfile_path, geojson_poly_path):

        graphml_path = f"{graphfile_path}.graphml"
        graphpkl_path = f"{graphfile_path}.pkl"

        # if graph pkl exists, load and return it
        if os.path.exists(graphpkl_path):
            print(f"Loading graph from {graphpkl_path}")
            with open(graphpkl_path, "rb") as f:
                G = pickle.load(f)
            return G

        # if graphml exists, load and return it
        if os.path.exists(graphml_path):
            print(f"Loading graph from {graphml_path}")
            return ox.load_graphml(graphml_path)

        # otherwise read geojson, build graph from polygon and save it
        gdf_poly = gpd.read_file(geojson_poly_path)
        if gdf_poly.empty:
            raise ValueError(f"No geometry found in {geojson_poly_path}")
        poly = gdf_poly.geometry.iloc[0]

        G = ox.graph_from_polygon(poly, network_type="walk")
        G = G.to_undirected()

        # ensure output directory exists
        os.makedirs(os.path.dirname(graphml_path), exist_ok=True)
        ox.save_graphml(G, graphml_path)
        print(f"Graph created and saved to {graphml_path}")

        with open(graphpkl_path, "wb") as f:
            pickle.dump(G, f)
        print(f"Graph also saved to {graphpkl_path}")

        return G

    def create_graph_transit(self, stops_df: pd.DataFrame) -> nx.MultiDiGraph:
        # create graph transit adjacency list in stops_df
        G = nx.MultiDiGraph()
        
        # To have the geometry (Points) in meters for distance calculations
        stops_gdf = gpd.GeoDataFrame(stops_df, geometry='geometry', crs="EPSG:4326").to_crs(epsg=3857)

        for idx, stop in stops_gdf.iterrows():
            stop_id = stop['stop_id']
            G.add_node(stop_id, pos=stop['geometry'], stop_name=stop['stop_name'], routes=stop['routes_by_stop'], shapes=stop['shapes_by_stop'])
            next_stops = stop['next_stop_id']
            for next_stop_id, edge_list in next_stops.items():
                for edge in edge_list:                
                    G.add_edge(stop_id, next_stop_id, weight=edge['weight'], shape_id=edge['shape_id'], frequency=edge['frequency'])
        return G

    

