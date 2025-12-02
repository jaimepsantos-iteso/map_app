import osmnx as ox
import networkx as nx
import pandas as pd
import heapq
import geopandas as gpd
from shapely.geometry import Point, LineString
import random as rd
from geopy.geocoders import Nominatim
from pyproj import Transformer


def point_from_text(address: str) -> Point:
    geolocator = Nominatim(user_agent="geo")
    location = geolocator.geocode(address)
    #convert to metric projection (EPSG:3857)
    transformer = Transformer.from_crs(4326, 3857, always_xy=True)

    if location:
        #apply transformation if location is found
        x, y = transformer.transform(location.longitude, location.latitude)
        return Point(x, y)
    else:
        return None
    

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

# Function to trim a LineString shape between two stops
from shapely.geometry import LineString, Point
from shapely.ops import substring

def trim_shape_between_stops(shape_geometry, stops_on_route, stops_df):
    """
    Trim a shape LineString to only include the portion between first and last stop used.
    
    Args:
        shape_geometry: The full LineString of the shape
        stops_on_route: List of stop_ids that are used in this segment
        stops_df: DataFrame with stop information including geometry
    
    Returns:
        Trimmed LineString
    """
    if len(stops_on_route) < 2:
        return shape_geometry
    
    # Get the stop geometries
    first_stop = stops_df[stops_df['stop_id'] == stops_on_route[0]].iloc[0]['geometry']
    last_stop = stops_df[stops_df['stop_id'] == stops_on_route[-1]].iloc[0]['geometry']
    
    # Project stops onto the line to get their position along the line
    first_distance = shape_geometry.project(first_stop)
    last_distance = shape_geometry.project(last_stop)
    
    # Ensure first comes before last (in case route goes backwards)
    start_dist = min(first_distance, last_distance)
    end_dist = max(first_distance, last_distance)
    
    # Extract the substring between the two points
    trimmed = substring(shape_geometry, start_dist, end_dist)
    
    return trimmed


# Example: Trim shapes based on actual stops used
# Assuming you have a route result with stops grouped by shape_id

# Let's say you have a path like: [(stop1, shape1), (stop2, shape1), (stop3, shape2), ...]
# Group stops by shape_id
from collections import defaultdict

def trim_route_shapes(dijkstra_path, transit_df, stops_df):
    """
    Trim shapes to only show the portions actually traveled.
    
    Args:
        dijkstra_path: List of (stop_id, shape_id) tuples from route
        transit_df: DataFrame with shape geometries
        stops_df: DataFrame with stop information
    
    Returns:
        List of trimmed LineStrings with metadata
    """
    # Group stops by shape_id
    shape_stops = defaultdict(list)
    for stop_id, shape_id in dijkstra_path:
        if shape_id != 'walking':  # Skip walking segments
            shape_stops[shape_id].append(stop_id)
    
    trimmed_shapes = []
    
    for shape_id, stops_on_shape in shape_stops.items():
        if len(stops_on_shape) < 2:
            continue
            
        # Get the full shape geometry
        shape_row = transit_df[transit_df['shape_id'] == shape_id].iloc[0]
        full_geometry = shape_row['shape_geometry']
        
        # Trim to actual stops used
        trimmed_geom = trim_shape_between_stops(full_geometry, stops_on_shape, stops_df)
        
        trimmed_shapes.append({
            'geometry': trimmed_geom,
            'shape_id': shape_id,
            'route_long_name': shape_row['route_long_name'],
            'route_short_name': shape_row['route_short_name'],
            'route_type': shape_row['route_type'],
            'trip_headsign': shape_row['trip_headsign'],
            'route_color': shape_row.get('route_color', '#7b1fa2'),
            'stops_used': stops_on_shape
        })
    
    return trimmed_shapes


# Usage example (uncomment when you have a dijkstra_path):
# trimmed = trim_route_shapes(dijkstra_path, transit_df, stops_df)
# trimmed_gdf = gpd.GeoDataFrame(trimmed, crs='EPSG:4326')
# m = trimmed_gdf.explore(column='route_name', cmap='tab20')
# openMap(m)

class RouteService:
    def __init__(self, graph_walk, graph_transit, stops_df, transit_df):
        self.graph_walk = graph_walk
        self.graph_transit = graph_transit
        self.stops_gdf = gpd.GeoDataFrame(stops_df, geometry='geometry', crs="EPSG:4326").to_crs(epsg=3857)
        self.transit_gdf = gpd.GeoDataFrame(transit_df, geometry='shape_geometry', crs='EPSG:4326').to_crs(epsg=3857)

   
    def route_walking(self, start_walking_node:int, end_walking_node: int) -> tuple[LineString, int]:

        if nx.has_path(self.graph_walk, start_walking_node, end_walking_node) == False or start_walking_node == end_walking_node:
            print("No walking path found between the two points.")
            start = Point(self.graph_walk.nodes[start_walking_node]['x'], self.graph_walk.nodes[start_walking_node]['y'])
            end = Point(self.graph_walk.nodes[end_walking_node]['x'], self.graph_walk.nodes[end_walking_node]['y'])
            return LineString([start, end]), round(start.distance(end) / (5 / 3.6))
        
        # Shortest path, to use my own Dijkstra implementation, replace this line
        route_nodes = nx.shortest_path(self.graph_walk, start_walking_node, end_walking_node)
        # get time walking
        distance = nx.shortest_path_length(self.graph_walk, start_walking_node, end_walking_node, weight='length')
        time_walking = round(distance / (5 / 3.6))  # average walking speed 5 km/h in m/s
        # Convert nodes to list of coordinates
        coords = [(self.graph_walk.nodes[n]["x"], self.graph_walk.nodes[n]["y"]) for n in route_nodes]
        #create line geometry
        line = LineString(coords)
       
        return line, time_walking
    
    def route_transit(self, start_transit_node: str, end_transit_node: str) -> tuple[list[LineString], float]:
        
        path, total_cost = self.dijkstra_transit(start_transit_node, end_transit_node, heuristic=euclidean_heuristic)

        dijkstra_path_stops = []
        dijkstra_path_shapes = []

        for stop, shape in path:
            dijkstra_path_stops.append(stop)
            if shape != 'walking' and shape not in dijkstra_path_shapes:
                dijkstra_path_shapes.append(shape)

       
        subset = self.transit_gdf[self.transit_gdf['shape_id'].isin(dijkstra_path_shapes)]

        trimmed_shapes = trim_route_shapes(path, self.transit_gdf, self.stops_gdf)

        trimmed_gdf = gpd.GeoDataFrame(trimmed_shapes, crs='EPSG:4326')

        print(subset)



        m = subset.explore(
            name = "Transit Route",
            column='route_long_name',
            cmap='tab20',
            legend=True,
            tooltip=['route_long_name', 'route_short_name', 'trip_headsign'],
            style_kwds={'weight': 6, 'opacity': 0.9}
        )

        path_gdf = self.stops_gdf[self.stops_gdf['stop_id'].isin(dijkstra_path_stops)]
        m = path_gdf.explore(color='orange', m=m, name="Transit Stops")


        return subset, total_cost, m


    def route_combined(self, start: Point, end: Point) -> tuple[list[LineString], float]:

        def find_nearest_transit_and_walking_nodes(walking_point: Point) -> tuple[str, int, int]:
            # Find nearest transit stops to start and end points
            walking_node = ox.distance.nearest_nodes(self.graph_walk, walking_point.x, walking_point.y)
            walking_node_point = Point(self.graph_walk.nodes[walking_node]['x'], self.graph_walk.nodes[walking_node]['y'])
            nearest_stop_idx = self.stops_gdf.geometry.distance(walking_node_point).idxmin()
            nearest_transit_node = self.stops_gdf.loc[nearest_stop_idx]['stop_id']
            transit_point = self.graph_transit.nodes[nearest_transit_node]['pos']
            nearest_transit_walking_node = ox.distance.nearest_nodes(self.graph_walk, transit_point.x, transit_point.y)

            return nearest_transit_node, walking_node, nearest_transit_walking_node
        
        start_transit_node, start_walking_node, start_nearest_walking_node = find_nearest_transit_and_walking_nodes(start)
        end_transit_node, end_walking_node, end_nearest_walking_node = find_nearest_transit_and_walking_nodes(end)
        # Route walking from start to nearest transit stop
        walk_to_transit_line, time_walking_start = self.route_walking(start_walking_node, start_nearest_walking_node)
        # Route transit from start transit stop to end transit stop
        transit_line, time_transit, m = self.route_transit(start_transit_node, end_transit_node)
        # Route walking from nearest transit stop to end
        walk_from_transit_line, time_walking_end = self.route_walking(end_nearest_walking_node, end_walking_node)
        # Combine all geometries
        # Create a GeoSeries to hold all parts of the route
        route_parts_walking = [walk_to_transit_line, walk_from_transit_line]

        total_time = [time_walking_start, time_transit, time_walking_end]

        route_gdf = gpd.GeoDataFrame(geometry=route_parts_walking, crs="EPSG:3857")
        m = route_gdf.explore(m=m, color='blue', style_kwds={'weight': 3, 'opacity': 0.8}, name='Walking Route')

        #add start point and end point - they are already in EPSG:3857
        start_gdf = gpd.GeoDataFrame(geometry=[start], crs="EPSG:3857")   
        end_gdf = gpd.GeoDataFrame(geometry=[end], crs="EPSG:3857")   

        # Add markers with better visibility
        m = start_gdf.explore(m=m, color='green', marker_kwds={'radius': 10}, name='Start Point')
        m = end_gdf.explore(m=m, color='red', marker_kwds={'radius': 10}, name='End Point')

        return total_time , m











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
