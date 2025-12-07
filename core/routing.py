import osmnx as ox
import networkx as nx
import pandas as pd
import heapq
import geopandas as gpd
from shapely.geometry import Point, LineString
from shapely.ops import substring
import random as rd
from geopy.geocoders import Nominatim
from pyproj import Transformer
import folium
import math


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
    

def euclidean_heuristic(src:Point, dst:Point) -> int:
    """
    Estimates the travel time in seconds between two points using the Euclidean distance and an average transit speed.

    Args:
        src (Point): The starting point in meters (EPSG:3857).
        dst (Point): The destination point in meters (EPSG:3857).

    Returns:
        int: The estimated time to reach the destination from the source, in seconds, rounded to the nearest integer.

    Notes:
        - Assumes an average transit speed of 55 km/h.
        - The distance is calculated using the Euclidean metric.
    """
    # Time to reache the dst
    transit_average_speed_mps = 55.0 / 3.6  # average transit max speed from km/h to m/s
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

class RouteService:
    """
    RouteService provides routing and mapping functionalities for multimodal transportation networks,
    including walking and transit (bus/train) routes. It integrates geographic data, network graphs,
    and transit schedules to compute optimal routes, segment details, and interactive maps.
    Attributes:
        graph_walk (networkx.Graph): Graph representing the walkable street network.
        graph_transit (networkx.MultiDiGraph): Graph representing the transit network (bus/train).
        stops_gdf (geopandas.GeoDataFrame): DataFrame of transit stops with geometry in EPSG:3857.
        transit_gdf (geopandas.GeoDataFrame): DataFrame of transit shapes/routes with geometry in EPSG:3857.
    Methods:
        route_walking(start_point, end_point):
            Computes the walking route and estimated time between two geographic points.
        route_transit(start_transit_node, end_transit_node, start_walking_edges, restricted_shapes):
            Finds the optimal transit route between two transit nodes, optionally including walking segments and restricted transit shapes.
        get_transit_segments_df(path, start_point, end_point):
            Builds a detailed DataFrame of route segments (walking and transit), including geometry, stop info, and timing.
        get_start_walking_edges(start):
            Identifies all transit stops reachable by walking from the origin within a time threshold.
        get_end_transit_node(end):
            Finds the nearest transit stop to the destination point.
        route_combined(start, end):
            Computes multimodal routes (walking + transit) from origin to destination, returning alternatives sorted by total time.
        create_map(segments_df):
            Generates an interactive Folium map visualizing the route segments and stops.
        check_no_transfers(graph, src, dst, transit_df, stops_df):
            Checks if a direct transit route exists between two stops (no transfers).
        check_one_transfer(graph, src, dst, transit_df, stops_df):
            Checks if a route with a single transfer exists between two stops.
        dijkstra_transit(src, dst, start_walking_edges, restricted_shapes, heuristic):
            Finds the shortest path in the transit network using a modified Dijkstra's algorithm, supporting walking transfers and restricted shapes.
        - All geographic coordinates are handled in EPSG:3857 for routing and EPSG:4326 for mapping.
        - Transit segments are grouped by shape_id (route/line), and walking segments are included where needed.
        - The service supports alternative route generation by restricting previously used transit shapes.
        - The mapping function provides rich visualization with segment and stop details.
    """

    def __init__(self, graph_walk, graph_transit, stops_df, transit_df, heuristic_enable: bool = True):
        self.graph_walk = graph_walk
        self.graph_transit = graph_transit
        # Metric geopandas dataframes
        self.stops_gdf = gpd.GeoDataFrame(stops_df, geometry='geometry', crs="EPSG:4326").to_crs(epsg=3857)
        self.transit_gdf = gpd.GeoDataFrame(transit_df, geometry='shape_geometry', crs='EPSG:4326').to_crs(epsg=3857)
        self.heuristic = euclidean_heuristic if heuristic_enable else no_heuristic

   
    def route_walking(self, start_point:Point, end_point: Point) -> tuple[LineString, int]:
        """
        Computes the walking route between two geographic points using the walking graph.
            start_point (Point): The starting point as a Shapely Point (in EPSG:3857).
            end_point (Point): The ending point as a Shapely Point (in EPSG:3857).
            tuple[LineString, int]:
                - LineString: The geometry of the walking route as a Shapely LineString (in EPSG:3857).
                - int: The estimated walking time in seconds.
            - The function finds the nearest nodes in the walking graph to the start and end points.
            - If a path exists between these nodes, it computes the shortest path and walking time using the graph's edge lengths.
            - If no path exists, it estimates walking time using direct distance.
            - The route includes segments from the actual start/end points to their nearest graph nodes.
            - Walking speed is assumed to be 3 km/h for unknown paths and 5 km/h for graph paths.
        """

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
    
    def route_transit(self, start_transit_node: str, end_transit_node: str, start_walking_edges: list[tuple[str, int]] = [], restricted_shapes : list[str] = []) -> tuple[list[str,str]]:
        
        #measure time
        import time
        start_time = time.time()
        
        # Run dijkstra algorithm to find optimal transit path
        path, total_cost = self.dijkstra_transit(start_transit_node, end_transit_node, start_walking_edges, restricted_shapes, heuristic=self.heuristic)
        
        end_time = time.time()
        print(f"Transit routing calculation time: {end_time - start_time:.3f} seconds")
        return path

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

    def get_start_walking_edges(self, start: Point) -> list[tuple[str, int]]:

        max_walking_time = self.graph_transit.graph.get('max_walking_time', 5 * 60) # time in seconds, 5 minutes default
        walking_speed_mps = 5 / 3.6 # average walking speed 5 km/h in m/s
        walking_distance_threshold = max_walking_time * walking_speed_mps  

        nearest_stop_idx = self.stops_gdf.geometry.distance(start).idxmin()
        start_transit_node = self.stops_gdf.loc[nearest_stop_idx]['stop_id']
        start_transit_node_pos = self.graph_transit.nodes[start_transit_node]['pos']

        # Route walking from start to nearest transit stop
        walking_distance_start = start.distance(start_transit_node_pos) # walking distance in meters
        time_walking_start = round(walking_distance_start / walking_speed_mps)  # walking time in seconds

        # add the closet stop as default walking edge
        start_walking_edges = [(start_transit_node, time_walking_start)]

        # only search for additional walking edges if within threshold
        if walking_distance_start > walking_distance_threshold:
            return start_walking_edges
        
        # Use spatial index to efficiently find nearby stops
        sindex = self.stops_gdf.sindex

        start_circle_walking = start.buffer(walking_distance_threshold)

        # candidate indices whose geometries intersect the walking reach
        nearby_stops_idx = sindex.query(start_circle_walking, predicate="intersects")

        for nearby_stop_idx in nearby_stops_idx:            
            nearby_stop = self.stops_gdf.iloc[nearby_stop_idx]
            # we dont want to add start walking edge to the already added nearest stop
            if nearby_stop['stop_id'] == start_transit_node:
                continue
            #calculate real distance in meters between the stop and start point
            distance = start.distance(nearby_stop['geometry'])            
            # walking time in seconds
            walking_time = round(distance / walking_speed_mps) 
            start_walking_edges.append((nearby_stop['stop_id'], walking_time))
        
        return start_walking_edges

    def get_end_transit_node(self, end: Point) -> str:
        nearest_stop_idx = self.stops_gdf.geometry.distance(end).idxmin()
        end_transit_node = self.stops_gdf.loc[nearest_stop_idx]['stop_id']
        return end_transit_node


    def route_combined(self, start: Point, end: Point) -> list[tuple[pd.DataFrame, int]]:
       
        start_walking_edges = self.get_start_walking_edges(start)

        end_transit_node = self.get_end_transit_node(end)

        restricted_shapes = []
        alternatives = 3
        routes_list = []

        while alternatives > 0:

            # Route transit from start transit stop to end transit stop
            path_transit = self.route_transit("Real_Start", end_transit_node, start_walking_edges, restricted_shapes)

            path_transit.append(('Real_End', 'walking'))  # Entry to indicate walking at the end

            #from the transit path, build a detailed segments dataframe inclding real walking segments
            route_df = self.get_transit_segments_df(path_transit, start, end)
            
            # calculate total time, segment times + waiting times
            total_time = route_df['segment_time_seconds'].sum() + route_df['frequency'].sum(skipna=True)
            
            routes_list.append((route_df, total_time))
    
            # Get shapes from CURRENT route only
            current_route_shapes = set(route_df[route_df['mode']=='transit']['shape_id'].unique())
            
            #retrieve a shape from current route shapes to restrict in next iteration
            found_new_shape = False
            while current_route_shapes and not found_new_shape:
                shape_to_restrict = current_route_shapes.pop()
                if shape_to_restrict not in restricted_shapes:
                    restricted_shapes.append(shape_to_restrict)
                    found_new_shape = True
            #either already restricted or no more shapes to restrict
            if not found_new_shape:
                break
            
            alternatives -= 1
        
        #sort routes by total time
        routes_list.sort(key=lambda x: x[1])   
      
        return routes_list


    def create_map(self, segments_df):
        """
        Generates an interactive Folium map visualizing route segments and stops.
        Args:
            segments_df (pd.DataFrame): DataFrame containing route segment information. 
                Expected columns include:
                    - 'mode': Mode of transportation (e.g., walking, bus, train).
                    - 'route_color': Hex color code for the route.
                    - 'segment_geometry': Shapely LineString geometry in EPSG:3857.
                    - 'route_type': Type of route (e.g., 0 for train, 1 for macrobus, etc.).
                    - 'route_long_name': Long name of the route.
                    - 'route_short_name': Short name of the route.
                    - 'trip_headsign': Direction or headsign of the trip.
                    - 'segment_time_seconds': Duration of the segment in seconds.
                    - 'stops': List of stop identifiers (optional).
                    - 'stop_names': List of stop names (e.g., 'Origen', 'Destino', or stop names).
                    - 'stop_positions': List of dictionaries with 'lat' and 'lon' keys (EPSG:4326).
        Returns:
            folium.Map: Folium map object with route segments and stop markers styled and annotated.
        Notes:
            - Route segments are drawn with color and width based on route type.
            - Stop markers are styled differently for first/last stops and for origin/destination.
            - Tooltips provide segment and stop information.
            - The map is centered on Guadalajara by default.
        """
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
                tooltip_txt.append(f"Tiempo segmento: {math.ceil(seconds/60)} min")
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

    #Not used currently
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
    

    # Not used currently
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



    def dijkstra_transit(self, src:str, dst:str, start_walking_edges: list[tuple[str, int]] = [], restricted_shapes : list[str] = [], heuristic=euclidean_heuristic) -> tuple[list[tuple[str, str]], float]:
        """
        Finds the shortest path in a transit network from a source node to a destination node using a modified Dijkstra's algorithm with support for walking transfers, restricted transit shapes, and heuristic-based prioritization.
        Args:
            src (str): The source node identifier.
            dst (str): The destination node identifier.
            start_walking_edges (list[tuple[str, int]], optional): List of tuples representing possible starting walking edges from the real origin. Each tuple contains (first_transit_stop, walking_time). Defaults to [].
            restricted_shapes (list[str], optional): List of shape IDs (e.g., transit lines or modes) to exclude from the search. Defaults to [].
            heuristic (callable, optional): Heuristic function to estimate the cost from a node to the destination. Defaults to euclidean_heuristic.
        Returns:
            tuple[list[tuple[str, str]], float]:
                - path: List of tuples (node, shape_id) representing the path from src to dst, including the transit shape used to arrive at each node.
                - total_cost: The accumulated cost of the shortest path. Returns ([], None) if no path is found.
        Notes:
            - The algorithm supports transfer penalties when switching between different transit shapes.
            - If start_walking_edges is provided, the search begins from a virtual "Real_Start" node with walking connections to the transit network.
            - The graph is expected to be a MultiDiGraph with edge attributes 'shape_id', 'weight', and 'frequency'.
            """

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
                heuristic_cost = heuristic(graph.nodes[first_transit_stop]['pos'], graph.nodes[dst]['pos'])
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
                    if shape_id in restricted_shapes:
                        continue
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
                    if next_shape in restricted_shapes:
                        continue
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
