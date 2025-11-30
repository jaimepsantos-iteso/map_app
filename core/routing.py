import osmnx as ox
import networkx as nx
import pandas as pd
import heapq
import geopandas as gpd
from shapely.geometry import Point
import random as rd


#src and dst are Point in meters, crs EPSG:3857
def euclidean_heuristic(src:Point, dst:Point) -> float:
    # Time to reache the dst
    transit_average_speed_kph = 55.0  # average transit max speed in km/h
    transit_average_speed_mps = transit_average_speed_kph / 3.6  # convert to m/s
    distance_meters = src.distance(dst)
    time_to_reach = distance_meters / transit_average_speed_mps  #time in s
    return round(time_to_reach)

def no_heuristic(src, dst):
    return 0

def openMap(m):
    html = "map.html"
    m.save(html)

    import webbrowser
    webbrowser.open(html)

class RouteService:
    def __init__(self, graph_walk, graph_transit):
        self.graph_walk = graph_walk
        self.graph_transit = graph_transit

    def nearest_node(self, lat, lon):
        return ox.nearest_nodes(self.graph_walk, lon, lat)

    def route_walking(self, start_lat, start_lon, end_lat, end_lon):
        # Convert points to graph nodes
        u = self.nearest_node(start_lat, start_lon)
        v = self.nearest_node(end_lat, end_lon)

        # Shortest path using travel time
        route_nodes = nx.shortest_path(
            self.graph_walk, u, v, weight="travel_time"
        )

        # Convert nodes to coordinates for Leaflet
        coords = [
            [self.graph_walk.nodes[n]["y"], self.graph_walk.nodes[n]["x"]]
            for n in route_nodes
        ]
        return coords
    
    def route_transit(self, start_lat, start_lon, end_lat, end_lon):
        pass


    def check_no_transfers(graph:nx.MultiDiGraph, src, dst, transit_df, stops_df):


        #verify if src and dst share a shape, only one bus is taken
        src_shapes = set(stops_df[stops_df['stop_id'] == src]['shapes_by_stop'].iloc[0])
        dst_shapes = set(stops_df[stops_df['stop_id'] == dst]['shapes_by_stop'].iloc[0])

        shared_shapes = src_shapes & dst_shapes

        if shared_shapes:
            print("Shared shapes found:", shared_shapes)
            shape = shared_shapes.pop()
            shape_info = transit_df[transit_df['shape_id'] == shape].iloc[0]
            
            shape_stops = shape_info['stop_ids']
            src_index = shape_stops.index(src)
            dst_index = shape_stops.index(dst)
            if src_index < dst_index:
                path = shape_stops[src_index:dst_index + 1]
                stop_time_deltas = shape_info['stop_time_deltas']          
                total_cost = sum(stop_time_deltas[src_index:dst_index])
                
                #add to the path the shape info
                path = [(stop, shape) for stop in path]
                return path, total_cost
            
        return [], None
    


    def check_one_transfer(graph:nx.MultiDiGraph, src:str, dst:str, transit_df: pd.DataFrame, stops_df: pd.DataFrame):
    
        #verif if src and dst shapes share a stop, only one transfer is needed
        src_shapes = set(stops_df[stops_df['stop_id'] == src]['shapes_by_stop'].iloc[0])
        dst_shapes = set(stops_df[stops_df['stop_id'] == dst]['shapes_by_stop'].iloc[0])

        for src_shape in src_shapes:
            src_shape_stops = transit_df[transit_df['shape_id'] == src_shape]['stop_ids'].iloc[0]
            for dst_shape in dst_shapes:
                dst_shape_stops = transit_df[transit_df['shape_id'] == dst_shape]['stop_ids'].iloc[0]
                #find common stops
                common_stops = set(src_shape_stops) & set(dst_shape_stops)
                if common_stops:
                    transfer_stop = common_stops.pop()
                    #build path from src to transfer_stop
                    src_index = src_shape_stops.index(src)
                    transfer_index_src = src_shape_stops.index(transfer_stop)
                    path_src = src_shape_stops[src_index:transfer_index_src + 1]
                    #build path from transfer_stop to dst
                    transfer_index_dst = dst_shape_stops.index(transfer_stop)
                    dst_index = dst_shape_stops.index(dst)
                    path_dst = dst_shape_stops[transfer_index_dst:dst_index + 1]
                    #combine paths
                    full_path = path_src + path_dst[1:]  #avoid duplicating transfer_stop
                    total_cost = 0
                    for i in range(len(full_path) - 1):
                        edge_data = graph.get_edge_data(full_path[i], full_path[i + 1])
                        weight = edge_data.get('weight', 1)
                        total_cost += weight
                    return full_path, total_cost    
        
        return [], None



    def dijkstra_transit(self, src:str, dst:str, heuristic=euclidean_heuristic) -> tuple[list[tuple[str, str]], float]:

        #accumulated cost for each node from the start, keys are (node, shape_id)
        cost = dict()
        #stores the node and shape that it was coming from, keys are (node, shape_id)
        previous = dict()

        #"minimum heap" of the candidates (priorty_cost, node, shape_id)
        queue = []
        #to return the path from src to dst, list of tuples (node, shape_id)
        path = []

        graph = self.graph_transit

        # fill the queue with all the possible starting edges from src
        for neighbor in graph.neighbors(src):
            edges = graph.get_edge_data(src, neighbor)
            if not edges:
                continue
            for k, attrs in edges.items():
                shape_id = attrs.get('shape_id')
                weight = attrs.get('weight', 1)
                frequency = attrs.get('frequency', 600)
                tentative_cost = weight + frequency #initial transfer penalty
                cost[(neighbor, shape_id)] = tentative_cost
                previous[(neighbor, shape_id)] = (src, None)
                heuristic_cost = heuristic(graph.nodes[neighbor]['pos'], graph.nodes[dst]['pos'])
                priority_cost = tentative_cost + heuristic_cost
                heapq.heappush(queue, (priority_cost, neighbor, shape_id))
        

        end_shape = None

        while queue:

            _, current, current_shape = heapq.heappop(queue)

            if current == dst:
                end_shape = current_shape
                break


            # explore all neighbors (MultiDiGraph may have parallel edges)
            for neighbor in graph.neighbors(current):

                edges = graph.get_edge_data(current, neighbor)
                if not edges:
                    continue
                
                for k, attrs in edges.items():
                    next_shape = attrs.get('shape_id')
                    weight = attrs.get('weight', 1)
                    frequency = attrs.get('frequency', 600)
                    
                    if (current_shape is not None and next_shape is not None and next_shape != current_shape):
                        penalty = frequency
                    else:
                        penalty = 0
                    
                    tentative_cost = cost[(current, current_shape)] + weight + penalty

                    # if cost for neighbor with next_shape is not set or tentative_cost is lower, update
                    if (neighbor, next_shape) not in cost or tentative_cost < cost[(neighbor, next_shape)]:
                        cost[(neighbor, next_shape)] = tentative_cost                
                        previous[(neighbor, next_shape)] = (current, current_shape)
                        heuristic_cost = heuristic(graph.nodes[neighbor]['pos'], graph.nodes[dst]['pos']) + 2*penalty
                        priority_cost = tentative_cost + heuristic_cost
                        heapq.heappush(queue, (priority_cost, neighbor, next_shape))
            
        if end_shape is None:
            return [], None


        #recreate the path based on the previous going backwards but store it in forward 
        current = (dst, end_shape)

        while current in previous:
            path.append(current)
            current = previous.get(current)
        path.reverse()
        
        return path, cost[(dst, end_shape)]
    
    def test_transit_routing(self, transit_df, stops_df):

        path = []

        while path == []:
            start = rd.choice(list(self.graph_transit.nodes))
            destination = rd.choice(list(self.graph_transit.nodes))

            try:
                path = nx.shortest_path(self.graph_transit, source=start, target=destination, weight='weight')
            except nx.NetworkXNoPath:
                path = []

        dijkstra_path, dijkstra_cost = self.dijkstra_transit(start, destination, heuristic=euclidean_heuristic)
        print("Shortest path from", start, "to", destination, ":", dijkstra_path)

        print("Cost of the path:", dijkstra_cost/60)

        transit_gdf = gpd.GeoDataFrame(transit_df, geometry='shape_geometry', crs='EPSG:4326')

        dijkstra_path_stops = []
        dijkstra_path_shapes = []
        prev_shape = None
        for stop, shape in dijkstra_path:
            dijkstra_path_stops.append(stop)
            dijkstra_path_shapes.append(shape)
            if prev_shape is None:
                print("Walk to stop:", stop)
            if shape == 'walking':
                print("Walk to stop:", stop)
            elif shape != prev_shape:
                print("Take Bus:", shape, "from stop:", stop, " direction to:", transit_df[transit_df['shape_id'] == shape]['trip_headsign'].iloc[0])
            prev_shape = shape


        #show all the shapes in the path
        #assign colors based on shape_id or randomly
        shapes_in_path = sorted(set(dijkstra_path_shapes))
        subset = transit_gdf[transit_gdf['shape_id'].isin(shapes_in_path)]
        m = subset.explore(
            column='route_long_name',
            cmap='tab20',
            legend=True,
            tooltip=['route_long_name', 'route_short_name', 'trip_headsign'],
            style_kwds={'weight': 6, 'opacity': 0.9}
        )
        print(set(shapes_in_path))

        stops_gdf = gpd.GeoDataFrame(stops_df, geometry='geometry', crs="EPSG:4326").to_crs(epsg=3857)

        path_gdf = stops_gdf[stops_gdf['stop_id'].isin(dijkstra_path_stops)]
        m = path_gdf.explore(color='red', m=m)

        openMap(m)
