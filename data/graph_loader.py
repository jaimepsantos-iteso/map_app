import osmnx as ox
import geopandas as gpd
import networkx as nx
import pandas as pd
import os
import pickle


class GraphLoader:

    def create_graph_walk(self, graphfile_path, geojson_poly_path) -> nx.MultiGraph:

        # if graph pkl exists, load and return it
        if os.path.exists(graphfile_path):
            print(f"Loading walking graph from {graphfile_path}")
            with open(graphfile_path, "rb") as f:
                G = pickle.load(f)
            return G

        # otherwise read geojson, build graph from polygon and save it
        gdf_poly = gpd.read_file(geojson_poly_path)
        if gdf_poly.empty:
            raise ValueError(f"No geometry found in {geojson_poly_path}")
        poly = gdf_poly.geometry.iloc[0]

        print("Creating walking graph from OSM data")

        # retrieve walkable graph within polygon from open street maps
        G = ox.graph_from_polygon(poly, network_type="walk")
        
        # change graph locations to be metric
        G = ox.project_graph(G, to_crs="EPSG:3857")
        
        # assumption one can walk both ways on all paths, this simplifies the graph
        G = G.to_undirected()

        with open(graphfile_path, "wb") as f:
            pickle.dump(G, f)
        print(f"Walking graph saved to {graphfile_path}")
        return G

    def create_graph_transit(self, graphfile_path, stops_df: pd.DataFrame, max_walking_time: int = 300) -> nx.MultiDiGraph:
        
        graphfile_path = graphfile_path.rstrip(".pkl")
        graphfile_path = f"{graphfile_path}_{max_walking_time}.pkl"

        # if graph pkl exists, load and return it
        if os.path.exists(graphfile_path):
            print(f"Loading transit graph from {graphfile_path}")
            with open(graphfile_path, "rb") as f:
                G = pickle.load(f)
            return G
        
        
        print("Creating transit graph")
        
        # create graph transit adjacency list in stops_df
        graph_transit = nx.MultiDiGraph()
        
        # To have the geometry (Points) in meters for distance calculations
        stops_gdf = gpd.GeoDataFrame(stops_df, geometry='geometry', crs="EPSG:4326").to_crs(epsg=3857)

        add_adjacent_stops(graph_transit, stops_gdf)
        add_walking_edges(graph_transit, stops_gdf, max_walking_time)

        with open(graphfile_path, "wb") as f:
            pickle.dump(graph_transit, f)
        print(f"Transit graph saved to {graphfile_path}")

        return graph_transit


def add_adjacent_stops(graph_transit: nx.MultiDiGraph, stops_gdf:gpd.GeoDataFrame):

    print("Adding transit edges between adjacent stops")    

    for idx, stop in stops_gdf.iterrows():
        stop_id = stop['stop_id']
        graph_transit.add_node(stop_id, pos=stop['geometry'], stop_name=stop['stop_name'], routes=stop['routes_by_stop'], shapes=stop['shapes_by_stop'])
        next_stops = stop['next_stop_id']
        for next_stop_id, edge_list in next_stops.items():
            for edge in edge_list:                
                graph_transit.add_edge(stop_id, next_stop_id, weight=edge['weight'], shape_id=edge['shape_id'], frequency=edge['frequency'])

def add_walking_edges(graph_transit: nx.MultiDiGraph, stops_gdf: gpd.GeoDataFrame, max_walking_time: int = 300):

    print("Adding walking edges between nearby stops at a max walking time of", max_walking_time, "seconds")

    walking_speed_mps = 5 / 3.6 # average walking speed 5 km/h in m/s
    walking_distance = max_walking_time * walking_speed_mps  

    # Use spatial index to efficiently find nearby stops
    sindex = stops_gdf.sindex

    for stop_idx, stop in stops_gdf.iterrows():
        stop_id = stop['stop_id']
        stop_point_geo = stop['geometry']
        stop_circle_walking = stop_point_geo.buffer(walking_distance)

        # candidate indices whose geometries intersect the walking reach
        nearby_stops_idx = sindex.query(stop_circle_walking, predicate="intersects")

        for nearby_stop_idx in nearby_stops_idx:
            # we dont want to add walking edge to itself
            if nearby_stop_idx == stop_idx:
                continue
            nearby_stop = stops_gdf.iloc[nearby_stop_idx]
            #calculate real distance in meters between the two stops
            distance = stop_point_geo.distance(nearby_stop['geometry'])            
            # walking time in seconds
            walking_time = round(distance / walking_speed_mps) 
            # add walking edge, shape_id='walking' due to the mode of transport, frequency=0 as its not a scheduled transport you have to wait
            graph_transit.add_edge(stop_id, nearby_stop['stop_id'], weight=walking_time, shape_id='walking', frequency=0)