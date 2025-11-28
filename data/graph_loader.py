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

    def create_graph_transit(self, transit_df, stops_df):
        pass
    

