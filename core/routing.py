import osmnx as ox
import networkx as nx
import pandas as pd
import heapq
import geopandas as gpd
from shapely.geometry import Point, LineString
import random as rd
from geopy.geocoders import Nominatim
from pyproj import Transformer
import folium



def point_from_text(address: str) -> Point:
    if address is None:
        return None
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

   
    def route_walking(self, start_point:Point, end_point: Point) -> tuple[LineString, int]:

        start_walking_node = ox.distance.nearest_nodes(self.graph_walk, start_point.x, start_point.y)
        end_walking_node = ox.distance.nearest_nodes(self.graph_walk, end_point.x, end_point.y)

        start_walking_point = Point(self.graph_walk.nodes[start_walking_node]['x'], self.graph_walk.nodes[start_walking_node]['y'])
        end_walking_point = Point(self.graph_walk.nodes[end_walking_node]['x'], self.graph_walk.nodes[end_walking_node]['y'])

        #add first segment from start point to nearest walking node
        coords = [(start_point.x, start_point.y), (start_walking_point.x, start_walking_point.y)]
        time_walking = round(start_point.distance(start_walking_point) / (3 / 3.6))  # average walking speed 3 km/h in m/s due to unknown path
        if start_walking_node == end_walking_node:
            pass
        elif nx.has_path(self.graph_walk, start_walking_node, end_walking_node) == False:

            time_walking += round(start_walking_point.distance(end_walking_point) / (3 / 3.6)) # average walking speed 3 km/h in m/s due to unknown path
        else:
            route_nodes = nx.shortest_path(self.graph_walk, start_walking_node, end_walking_node)
            # get time walking
            distance = nx.shortest_path_length(self.graph_walk, start_walking_node, end_walking_node, weight='length')
            time_walking += round(distance / (5 / 3.6))  # average walking speed 5 km/h in m/s
            # Convert nodes to list of coordinates
            coords += [(self.graph_walk.nodes[n]["x"], self.graph_walk.nodes[n]["y"]) for n in route_nodes]
        
        #add last segment from end walking point to end point
        coords += [(end_walking_point.x, end_walking_point.y), (end_point.x, end_point.y)]
        time_walking += round(end_walking_point.distance(end_point) / (3 / 3.6))  # average walking speed 3 km/h in m/s due to unknown path
        
        #create line geometry        
        line = LineString(coords)
       
        return line, time_walking
    
    def route_transit(self, start_transit_node: str, end_transit_node: str, start_walking_edges: list[tuple[str, int]] = []) -> tuple[list[LineString], float, pd.DataFrame]:
        
        path, total_cost = self.dijkstra_transit(start_transit_node, end_transit_node, start_walking_edges=start_walking_edges, heuristic=euclidean_heuristic)

        dijkstra_path_stops = []
        dijkstra_path_shapes = []

        for stop, shape in path:
            dijkstra_path_stops.append(stop)
            if shape != 'walking' and shape not in dijkstra_path_shapes:
                dijkstra_path_shapes.append(shape)

       
        subset = self.transit_gdf[self.transit_gdf['shape_id'].isin(dijkstra_path_shapes)]


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


        return path, total_cost, m

    def get_transit_segments_df(self, path : tuple[str,str], start_point:Point, end_point:Point) -> pd.DataFrame:
        """Build a detailed segment DataFrame for a transit-only route.

        Each row represents a contiguous segment by mode. For transit, the
        segment is a sequence of stops on the same `shape_id`. If any 'walking'
        steps appear in the path, they are included as separate rows.

        Columns:
        - mode: 'transit' or 'walking'
        - shape_id: shape identifier for transit segments, else None
        - route_long_name, route_short_name, trip_headsign, route_type, route_color
        - stops: list of stop_ids in segment order
        - stop_names: list of stop names corresponding to `stops`
        - stop_positions: list of dicts with lat/lon (EPSG:4326)
        - stop_time_deltas: per-hop time deltas for this segment (seconds)
        - frequency: median headway (seconds) across edges in the segment (if available)
        - segment_time_seconds: sum of weights for the segment (seconds)
        - segment_geometry: trimmed LineString geometry in EPSG:3857 for transit segments; for walking, a LineString via node positions if available
        """
        
        if not path:
            return pd.DataFrame(columns=[
                'mode','shape_id','route_long_name','route_short_name','trip_headsign','route_type','route_color',
                'stops','stop_names','stop_positions','stop_time_deltas','frequency','segment_time_seconds','segment_geometry'
            ])

        segments = []

        # Helper to finalize a transit segment row
        def finalize_transit_segment(shape_id: str, seg_stops: list[str]):
            if not seg_stops:
                return
            shape_row = self.transit_gdf[self.transit_gdf['shape_id'] == shape_id]
            if shape_row.empty:
                return
            shape_row = shape_row.iloc[0]
            # Stop names and positions
            stops_sub = self.stops_gdf[self.stops_gdf['stop_id'].isin(seg_stops)].copy()
            # Preserve order of seg_stops
            stops_sub['__order'] = stops_sub['stop_id'].apply(lambda s: seg_stops.index(s) if s in seg_stops else -1)
            stops_sub.sort_values('__order', inplace=True)
            stop_names = stops_sub['stop_name'].tolist() if 'stop_name' in stops_sub.columns else seg_stops
            # Positions as lat/lon
            to4326 = Transformer.from_crs(3857, 4326, always_xy=True)
            stop_positions = []
            for geom in stops_sub.geometry.tolist():
                lon, lat = to4326.transform(geom.x, geom.y)
                stop_positions.append({'lat': lat, 'lon': lon})

            # Stop time deltas for just this segment
            full_stop_ids = shape_row.get('stop_ids', [])
            full_deltas = shape_row.get('stop_time_deltas', [])
            # Build per-hop deltas within the segment by looking up indices in full list
            seg_deltas = []
            for i in range(len(seg_stops)-1):
                try:
                    idx = full_stop_ids.index(seg_stops[i])
                    # Verify the next stop also matches to ensure we're on the right hop
                    idx_next = full_stop_ids.index(seg_stops[i+1])
                    # If they're consecutive in the full list, use the delta
                    if idx_next == idx + 1 and idx < len(full_deltas):
                        seg_deltas.append(full_deltas[idx])
                    else:
                        seg_deltas.append(None)
                except (ValueError, IndexError):
                    seg_deltas.append(None)

            # Frequency and time from graph edges
            freqs = []
            weights = []
            for i in range(len(seg_stops)-1):
                u, v = seg_stops[i], seg_stops[i+1]
                data = self.graph_transit.get_edge_data(u, v)
                if not data:
                    continue
                # pick edge that matches shape_id if parallel edges exist
                chosen = None
                for _, attrs in data.items():
                    if attrs.get('shape_id') == shape_id:
                        chosen = attrs
                        break
                if chosen is None:
                    # fallback to any
                    _, chosen = next(iter(data.items()))
                if chosen is not None:
                    if 'frequency' in chosen:
                        freqs.append(chosen['frequency'])
                    if 'weight' in chosen:
                        weights.append(chosen['weight'])
            frequency = float(pd.Series(freqs).median()) if freqs else None
            segment_time_seconds = float(pd.Series(weights).sum()) if weights else None

            # Trim geometry to the portion actually used
            full_geom = shape_row['shape_geometry']
            try:
                seg_geom = trim_shape_between_stops(full_geom, seg_stops, self.stops_gdf)
            except Exception:
                seg_geom = full_geom

            segments.append({
                'mode': 'transit',
                'shape_id': shape_id,
                'route_long_name': shape_row.get('route_long_name'),
                'route_short_name': shape_row.get('route_short_name'),
                'trip_headsign': shape_row.get('trip_headsign'),
                'route_type': shape_row.get('route_type'),
                'route_color': shape_row.get('route_color', '#7b1fa2'),
                'stops': seg_stops,
                'stop_names': stop_names,
                'stop_positions': stop_positions,
                'stop_time_deltas': seg_deltas,
                'frequency': frequency,
                'segment_time_seconds': segment_time_seconds,
                'segment_geometry': seg_geom,
            })

        # Helper to finalize a walking segment row (if present in path)
        def finalize_walking_segment(walk_stops: list[str]):
            if len(walk_stops) < 2:
                return
            # just take the start and end stops for walking
            walk_stops = [walk_stops[0], walk_stops[-1]]
            
            if walk_stops[0] == "Real_Start":
                start_walk_stop_pos = start_point
                start_walk_stop_name = "Origen"
            else:
                start_walk_stop_pos = self.graph_transit.nodes[walk_stops[0]].get('pos')
                start_walk_stop_name = self.stops_gdf[self.stops_gdf['stop_id']==walk_stops[0]]['stop_name'].iloc[0]

            if walk_stops[1] == "Real_End":
                end_walk_stop_pos = end_point
                end_walk_stop_name = "Destino"
            else:
                end_walk_stop_pos = self.graph_transit.nodes[walk_stops[1]].get('pos')
                end_walk_stop_name = self.stops_gdf[self.stops_gdf['stop_id']==walk_stops[1]]['stop_name'].iloc[0]

            geom, time_walking = self.route_walking(start_walk_stop_pos, end_walk_stop_pos)

            stop_names = [start_walk_stop_name, end_walk_stop_name]
            to4326 = Transformer.from_crs(3857, 4326, always_xy=True)
            stop_positions = []
            for g in [start_walk_stop_pos, end_walk_stop_pos]:
                lon, lat = to4326.transform(g.x, g.y)
                stop_positions.append({'lat': lat, 'lon': lon})

            segments.append({
                'mode': 'walking',
                'shape_id': None,
                'route_long_name': None,
                'route_short_name': None,
                'trip_headsign': None,
                'route_type': 'walking',
                'route_color': '#333333',
                'stops': walk_stops,
                'stop_names': stop_names,
                'stop_positions': stop_positions,
                'stop_time_deltas': None,
                'frequency': None,
                'segment_time_seconds': time_walking,
                'segment_geometry': geom,
            })

        # Group contiguous path entries by shape_id
        
        current_shape = path[0][1]  # initial shape_id, looks into the second element of the tuple
        current_stops = [path[0][0]] # initial stop_id

        #look for all stops and shapes in path except the first one
        for stop_id, shape_id in path[1:]:
            if shape_id == current_shape:
                current_stops.append(stop_id)
            else:
                # Shape change (transfer). Always include the transfer stop
                # as the last stop of the outgoing segment
                
                if current_shape == 'walking':
                    finalize_walking_segment(current_stops)
                else:
                    finalize_transit_segment(current_shape, current_stops)
                # Start new segment. Include transfer stop as first stop
                current_shape = shape_id
                current_stops = [current_stops[-1], stop_id]

        # finalize last segment
        if current_stops:
            if current_shape == 'walking':
                finalize_walking_segment(current_stops)
            else:
                finalize_transit_segment(current_shape, current_stops)

        return pd.DataFrame(segments)


    def route_combined(self, start: Point, end: Point) -> tuple[list[LineString], float]:

        def find_nearest_transit_and_walking_nodes(walking_point: Point) -> tuple[str, int, int]:
            # Find nearest transit stops to start and end points
            walking_node = ox.distance.nearest_nodes(self.graph_walk, walking_point.x, walking_point.y)
            walking_node_point = Point(self.graph_walk.nodes[walking_node]['x'], self.graph_walk.nodes[walking_node]['y'])
            nearest_stop_idx = self.stops_gdf.geometry.distance(walking_node_point).idxmin()
            nearest_transit_node = self.stops_gdf.loc[nearest_stop_idx]['stop_id']
            nearest_transit_node_pos = self.graph_transit.nodes[nearest_transit_node]['pos']

            return nearest_transit_node, nearest_transit_node_pos
        
        start_transit_node, start_transit_node_pos = find_nearest_transit_and_walking_nodes(start)
        end_transit_node, end_transit_node_pos = find_nearest_transit_and_walking_nodes(end)
        # Route walking from start to nearest transit stop
        walk_to_transit_line, time_walking_start = self.route_walking(start, start_transit_node_pos)
        # Route transit from start transit stop to end transit stop
        path_transit, time_transit, m = self.route_transit(start_transit_node, end_transit_node)
        # Route walking from nearest transit stop to end
        walk_from_transit_line, time_walking_end = self.route_walking(end_transit_node_pos, end)


        # Combine all geometries
        # Create a GeoSeries to hold all parts of the route
        route_parts_walking = [walk_to_transit_line, walk_from_transit_line]

        path_transit.append(('Real_End', 'walking'))  # dummy entry to indicate walking at the end

        route_df = self.get_transit_segments_df(path_transit, start, end)

        total_time = [time_walking_start, time_transit, time_walking_end]

        route_gdf = gpd.GeoDataFrame(geometry=route_parts_walking, crs="EPSG:3857")
        m = route_gdf.explore(m=m, color='blue', style_kwds={'weight': 3, 'opacity': 0.8}, name='Walking Route')

        #add start point and end point - they are already in EPSG:3857
        start_gdf = gpd.GeoDataFrame(geometry=[start], crs="EPSG:3857")   
        end_gdf = gpd.GeoDataFrame(geometry=[end], crs="EPSG:3857")   

        # Add markers with better visibility
        m = start_gdf.explore(m=m, color='green', marker_kwds={'radius': 10}, name='Start Point')
        m = end_gdf.explore(m=m, color='red', marker_kwds={'radius': 10}, name='End Point')

        return route_df, total_time , m, path_transit


    def create_map(self, segments_df):
        # Add route segments to the map one by one with styling and stop markers

        #create empty map 
        m = folium.Map(location=[20.6597, -103.3496], zoom_start=12)  # Example location (Guadalajara)

        # Ensure transformer to 4326 for folium
        _to4326 = Transformer.from_crs(3857, 4326, always_xy=True)

        # Helper to compute weight from route_type
        # Walking -> thinnest; then types 3,2,1; type 0 is thickest
        # If route_type is None for walking, set minimal
        def weight_for_route_type(route_type):
            if route_type == 'walking' or route_type is None:
                return 3
            # Numeric mapping: bigger width for smaller type value
            mapping = {0: 12, 1: 9, 2: 7, 3: 5}
            return mapping.get(route_type, 6)

        # Iterate rows in df and add to map
        for _, row in segments_df.iterrows():
            mode = row.get('mode')
            color = row.get('route_color', '#3366cc')
            seg_geom = row.get('segment_geometry')
            route_type = row.get('route_type')
            long_name = row.get('route_long_name')
            short_name = row.get('route_short_name')
            headsign = row.get('trip_headsign')
            seconds = row.get('segment_time_seconds')

            # Build tooltip text
            tooltip_txt = []
            tooltip_txt.append(f"Modo: {mode}")
            if long_name or short_name:
                tooltip_txt.append(f"Ruta: {long_name or ''} {('('+short_name+')') if short_name else ''}")
            if seconds is not None and not pd.isna(seconds):
                tooltip_txt.append(f"Tiempo segmento: {int(seconds)} s")
            if headsign:
                tooltip_txt.append(f"Dirección: {headsign}")
            tooltip_html = "<br>".join(tooltip_txt)

            # Draw line if geometry exists
            if isinstance(seg_geom, LineString):
                coords3857 = list(seg_geom.coords)
                coords4326 = []
                for (x, y) in coords3857:
                    lon, lat = _to4326.transform(x, y)
                    coords4326.append([lat, lon])
                folium.PolyLine(
                    locations=coords4326,
                    color=color,
                    weight=weight_for_route_type(route_type),
                    opacity=0.9,
                    tooltip=tooltip_html
                ).add_to(m)

            # Add stop circles
            stops = row.get('stops', [])
            stop_names = row.get('stop_names', [])
            stop_positions = row.get('stop_positions', [])
            # Expect stop_positions as list of dicts with lat/lon in 4326
            for i, pos in enumerate(stop_positions):
                lat = pos.get('lat')
                lon = pos.get('lon')
                if lat is None or lon is None:
                    continue
                # Style: transit mode first/last are white fill with black border; others use route color
                if (i == 0 or i == len(stop_positions)-1):
                    fill_color = 'white'
                    line_color = 'black'
                    radius = 8
                else:
                    fill_color = color
                    line_color = color
                    radius = 6
                # Tooltip prefix: Estación for route_type 0 (Tren Ligero) or 1 (Macrobus), otherwise Parada
                if i < len(stop_names) and (stop_names[i] == 'Origen' or stop_names[i] == 'Destino'):
                    prefix = ''
                    radius = 10
                    if stop_names[i] == 'Origen':
                        fill_color = '#72AF26'
                        line_color = 'darkgreen'
                    else:
                        fill_color = '#D53E2A'
                        line_color = 'darkred'
                elif route_type in [0, 1]:
                    prefix = 'Estación: '
                else:
                    prefix = 'Parada: '
                
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    color=line_color,
                    fill=True,
                    fill_color=fill_color,
                    fill_opacity=1.0,
                    weight=2,
                    tooltip=f"{prefix}{stop_names[i] if i < len(stop_names) else ''}"
                ).add_to(m)

              
        return m








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



    def dijkstra_transit(self, src:str, dst:str, start_walking_edges: list[tuple[str, int]] = [], heuristic=euclidean_heuristic) -> tuple[list[tuple[str, str]], float]:

        #accumulated cost for each node from the start, keys are (node, shape_id)
        cost = dict()
        #stores the node and shape that it was coming from, keys are (node, shape_id)
        previous = dict()

        #"minimum heap" of the candidates (priorty_cost, node, shape_id)
        queue = []
        #to return the path from src to dst, list of tuples (node, shape_id)
        path = []

        graph = self.graph_transit

        # fill the queue with all the possible starting walking edges from the real origin
        if start_walking_edges:
            src = "Real_Start"
            shape_id = "walking"
            for first_transit_stop, walking_time in start_walking_edges:
                tentative_cost = walking_time
                cost[(first_transit_stop, shape_id)] = tentative_cost
                previous[(first_transit_stop, shape_id)] = (src, None)
                heuristic_cost = heuristic(graph.nodes[first_transit_stop]['pos'], graph.nodes[first_transit_stop]['pos'])
                priority_cost = walking_time + heuristic_cost
                heapq.heappush(queue, (priority_cost, first_transit_stop, shape_id))
        else:
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


        # Recreate the path by following predecessors back from (dst, end_shape)
        current = (dst, end_shape)
        while current in previous:
            path.append(current)
            current = previous.get(current)
        # add the src to the path, the shape is None since it's the starting point, the shape represents how we arrived to the node
        path.append((src, None))
        path.reverse()

        return path, cost[(dst, end_shape)]    
