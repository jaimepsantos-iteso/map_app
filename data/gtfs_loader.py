
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point
from collections import defaultdict
import os
import pickle

class GTFSLoader:

    def load_transit_dataframe(self, gtfs_folder: str) -> pd.DataFrame:
        """
        Load and merge GTFS transit data from multiple files into a single DataFrame.
        This function reads the following GTFS files from the specified folder:
        - trips.txt: Contains trip information including route and service IDs
        - stop_times.txt: Contains stop sequences and timing information for each trip
        - stops.txt: Contains stop location and details
        - frequencies.txt: Contains headway-based service frequency information
        The function merges these files to create a comprehensive transit dataset with
        all relevant information needed for transit analysis and routing.
        Args:
            gtfs_folder (str): Path to the folder containing GTFS files
        Returns:
            pd.DataFrame: A merged DataFrame (transit_df) containing all relevant
                        transit information from the GTFS files, including trip
                        details, stop times, stop locations, shape geometry,
                        and service frequencies.
        """
        

        
        # if file transit_df.pkl exists only load the file and return otherwise create the whole df
        pkl_path = os.path.join(gtfs_folder, "transit_df.pkl")
        if os.path.exists(pkl_path):
            print(f"Loading transit DataFrame from {pkl_path}")
            transit_df = pd.read_pickle(pkl_path)
            return transit_df

        # If file doesn't exist, create the DataFrame
        print("Creating transit DataFrame from GTFS files")

        # Start with the trips, it contains all the information to be retrieve from the other files, from this one we can filter the information that we want

        ### trips_df = pd.read_csv(f"{gtfs_folder}/trips.txt", dtype=str, low_memory=False)
        
        # Modified trips.txt with Excel to fix some issues regarding some shape allocations
        trips_df = pd.read_excel(f"{gtfs_folder}/trips_fixed.xlsx", dtype=str)
        trips_df = process_trips(trips_df)

        # Based on the stop times get all the sequence of stops per trip and the time between each stop
        stop_times_df = pd.read_csv(f"{gtfs_folder}/stop_times.txt", dtype=str, low_memory=False)
        stop_times_df = process_stops(stop_times_df, stop_times_df, trips_df)

        # To get the average frequency of each trip
        frequencies_df = pd.read_csv(f"{gtfs_folder}/frequencies.txt", dtype=str, low_memory=False)
        frequencies_df = process_frequencies(frequencies_df, trips_df)

        shapes_df = pd.read_csv(f"{gtfs_folder}/shapes.txt", dtype=str, low_memory=False)
        shapes_df = process_shapes(shapes_df, trips_df)

        # Filter used routes and fix colors and route types
        routes_df = pd.read_csv(f"{gtfs_folder}/routes.txt", dtype=str, low_memory=False)
        routes_df = process_routes(routes_df, trips_df)

        # Now merge all the information into transit_df, use trips_df as base
        transit_df = trips_df#[['shape_id', 'route_id', 'trip_id', 'trip_headsign']] -> All columns "copied"
        # Add to the transit_df the geometry of each shape_id
        transit_df = transit_df.merge(shapes_df[['shape_id', 'shape_geometry']], on='shape_id', how='left')
        # Add to the transit_df the information of each route_id
        transit_df = transit_df.merge(routes_df[["route_id", "route_short_name", "route_long_name", "route_type", "route_color"]], on='route_id', how='left')
        # Add to the transit_df the information of stops per trip_id   
        transit_df = transit_df.merge(stop_times_df, on='trip_id', how='left') #stop_ids, stop_headsigns, stop_time_deltas, time_trip, num_stops -> All columns merged
        # Add to the transit_df the information of frequencies per trip_id
        transit_df = transit_df.merge(frequencies_df[["trip_id", "frequency"]], on='trip_id', how='left')

        transit_df.to_pickle(f"{gtfs_folder}/transit_df_py.pkl")

        return transit_df

    def load_stops_dataframe(self, gtfs_folder: str, transit_df: pd.DataFrame) -> pd.DataFrame:
        """
        Load and process the stops.txt GTFS file into a GeoDataFrame.
        This function reads the stops.txt file from the specified GTFS folder,
        processes the stop locations, and converts them into a GeoDataFrame
        with Point geometries for each stop.
        Args:
            gtfs_folder (str): Path to the folder containing GTFS files
        Returns:
            gpd.GeoDataFrame: A GeoDataFrame containing stop information with
                            Point geometries for each stop location.
        """
        
        # if file stops_df.pkl exists only load the file and return otherwise create the whole df
        pkl_path = os.path.join(gtfs_folder, "stops_df.pkl")
        if os.path.exists(pkl_path):
            print(f"Loading stops DataFrame from {pkl_path}")
            stops_df = pd.read_pickle(pkl_path)
            return stops_df
        
        # If file doesn't exist, create the DataFrame
        print("Creating stops DataFrame from GTFS files")
        
        stops_df = pd.read_csv(f"{gtfs_folder}/stops.txt", dtype=str, low_memory=False)

        #filter stops to only those in transit_df["stop_ids"]
        stops_df = stops_df[stops_df['stop_id'].isin(transit_df['stop_ids'].explode().unique())]

        # Adds Point geometries to the stops_df
        stops_df = process_stops_geometry(stops_df)

        # Create adjacency list of stops
        stops_df = process_stops_adjacency(stops_df, transit_df)

        print(f"Saving stops DataFrame to {pkl_path}")
        stops_df.to_pickle(pkl_path)

        return stops_df


def process_stops_geometry(stops_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process the stops DataFrame to include Point geometries for each stop location.
    This function converts the latitude and longitude columns into Point geometries.
    Args:
        stops_df (pd.DataFrame): DataFrame containing stop information
    Returns:
        pd.DataFrame: Processed DataFrame with Point geometries for each stop location
    """
    # Convert latitude and longitude to numeric
    stops_df['stop_lat'] = pd.to_numeric(stops_df['stop_lat'], errors='coerce')
    stops_df['stop_lon'] = pd.to_numeric(stops_df['stop_lon'], errors='coerce')

    # Create Point geometries
    stops_df['geometry'] = [Point(xy) for xy in zip(stops_df['stop_lon'], stops_df['stop_lat'])]
        

    return stops_df

def process_stops_adjacency(stops_df: pd.DataFrame, transit_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process the stops DataFrame to create an adjacency list of stops.
    This function can include any necessary preprocessing steps for stops data.
    Args:
        stops_df (pd.DataFrame): DataFrame containing stop information
        transit_df (pd.DataFrame): DataFrame containing transit information
    Returns:
        pd.DataFrame: Processed DataFrame with adjacency information for stops
    """
    # Use defaultdict to map stop_id to sets
    next_stop_dict = defaultdict(dict)
    routes_dict = defaultdict(set)
    shapes_dict = defaultdict(set)

    for stops_per_trip, stop_time_deltas, shape_id, route_id, frequency in zip(transit_df['stop_ids'], transit_df['stop_time_deltas'], transit_df['shape_id'], transit_df['route_id'], transit_df['frequency']):
        for i in range(len(stops_per_trip)-1):
            stop_id = stops_per_trip[i]
            next_stop_id = stops_per_trip[i+1]
            stop_time_delta = stop_time_deltas[i]
            # if empty key, assign stop_time_delta and shape_id in a list
            if next_stop_id not in next_stop_dict[stop_id]:
                next_stop_dict[stop_id][next_stop_id] = [{'weight': stop_time_delta, 'shape_id': shape_id, 'frequency': frequency}]
            # otherwise append to the list and update with the other ways to reach the next stop            
            else:
                next_stop_dict[stop_id][next_stop_id].append({'weight': stop_time_delta, 'shape_id': shape_id, 'frequency': frequency})
            
            routes_dict[stop_id].add(route_id)
            shapes_dict[stop_id].add(shape_id)

    # add columns from dictionaries
    stops_df['next_stop_id'] = stops_df['stop_id'].map(lambda x: next_stop_dict.get(x, dict()))
    stops_df['routes_by_stop'] = stops_df['stop_id'].map(lambda x: routes_dict.get(x, set()))
    stops_df['shapes_by_stop'] = stops_df['stop_id'].map(lambda x: shapes_dict.get(x, set()))

    return stops_df

def process_trips(trips_df: pd.DataFrame) -> pd.DataFrame:

    """
    Process the trips DataFrame to select one trip per shape_id based on service priority.
    The function assigns a priority to service_ids and selects the trip with the highest
    priority for each shape_id.
    Args:
        trips_df (pd.DataFrame): DataFrame containing trip information
    Returns:
        pd.DataFrame: Processed DataFrame with one trip per shape_id
    """
    # Assign priority to service_id, this due this ones are the more frequent services
    service_priority = {'LD': 1, 'LS': 2, 'LV': 3}
    trips_df['service_prio'] = trips_df['service_id'].map(service_priority).fillna(99).astype(int)

    # Sort by shape_id then priority so the preferred service is first
    tmp = trips_df.sort_values(['shape_id', 'service_prio'])

    # Drop duplicates to keep the chosen trip per shape
    rep = tmp.drop_duplicates(subset='shape_id', keep='first')

    # DataFrame with the assignments
    trips_df = rep[['shape_id', 'route_id', 'trip_id', 'trip_headsign']]

    # Remove route "T14B" since it has problems with its shape
    trips_df = trips_df[trips_df['route_id'] != 'T14B']

    return trips_df

def process_stops(stop_times_df: pd.DataFrame, trips_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process the stops DataFrame  and stop_times DataFrame to include the geometry of the stops.
    This function can include any necessary preprocessing steps for stops data.
    Args:
        stop_times_df (pd.DataFrame): DataFrame containing stop times and sequence of stops per trip
        trips_df (pd.DataFrame): DataFrame containing trip information used to filter valid trips only
    Returns:
        pd.DataFrame: Processed stops DataFrame
    """

    # Filter stop_times to only include trips present in trips_df
    stop_times_df = stop_times_df[stop_times_df['trip_id'].isin(trips_df['trip_id'])]

    # Convert departure times to pandas Timedelta (handles >24:00:00)
    stop_times_df["departure_time"] = pd.to_timedelta(stop_times_df["departure_time"], errors="coerce")
    stop_times_df["stop_sequence"] = pd.to_numeric(stop_times_df["stop_sequence"], errors="coerce")

    # Aggregate stop_times by trip_id to create lists of stop_ids, stop_headsigns, and time deltas between consecutive stops
    def _condense_trip_info(g):
        g = g.copy()
        g = g.sort_values('stop_sequence')
        stops = g['stop_id'].tolist()
        stop_headsigns = g['stop_headsign'].tolist()
        times = g['departure_time']
        deltas = times.diff().iloc[1:].dt.total_seconds().astype(int).tolist()  # list of int seconds (length = len(stops)-1)
        time_trip = int((times.iloc[-1] - times.iloc[0]).total_seconds())  # total trip time in seconds
        return pd.Series({'stop_ids': stops, 'stop_headsigns': stop_headsigns, 'stop_time_deltas': deltas, 'time_trip': time_trip, 'num_stops': len(stops)})

    stop_times_df = stop_times_df.groupby('trip_id').apply(_condense_trip_info).reset_index()
  
    return stop_times_df

def process_frequencies(frequencies_df: pd.DataFrame, trips_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process the frequencies DataFrame to include only relevant trips and aggregate frequencies.
    This function filters frequencies to include only trips present in trips_df and aggregates
    headway_secs to compute average frequency per trip_id.
    Args:
        frequencies_df (pd.DataFrame): DataFrame containing frequency information
        trips_df (pd.DataFrame): DataFrame containing trip information used to filter valid trips only
    Returns:
        pd.DataFrame: Processed frequencies DataFrame
    """
    # Filter frequencies to only include trips present in trips_df
    frequencies_df = frequencies_df[frequencies_df['trip_id'].isin(trips_df['trip_id'])]

    # Convert headway_secs to numeric
    frequencies_df['frequency'] = pd.to_numeric(frequencies_df['headway_secs'], errors='coerce')

    # Combine to have only one entry per trip_id, taking the average headway_secs if multiple entries exist
    frequencies_df = frequencies_df.groupby('trip_id')['frequency'].mean().astype(int).reset_index()

    return frequencies_df

def process_shapes(shapes_df: pd.DataFrame, trips_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process the shapes DataFrame to create LineString geometries for each shape_id.
    This function filters shapes to include only those present in trips_df and constructs
    LineString geometries from the shape points.
    Args:
        shapes_df (pd.DataFrame): DataFrame containing shape information
        trips_df (pd.DataFrame): DataFrame containing trip information used to filter valid shapes only
    Returns:
        pd.DataFrame: Processed shapes DataFrame with LineString geometries
    """
    # Filter shapes to only include those present in trips_df
    shapes_df = shapes_df[shapes_df['shape_id'].isin(trips_df['shape_id'])]

    # Convert shape_pt_lat and shape_pt_lon to numeric
    shapes_df['shape_pt_lat'] = pd.to_numeric(shapes_df['shape_pt_lat'], errors='coerce')
    shapes_df['shape_pt_lon'] = pd.to_numeric(shapes_df['shape_pt_lon'], errors='coerce')
    shapes_df['shape_pt_sequence'] = pd.to_numeric(shapes_df['shape_pt_sequence'], errors='coerce')

    # Aggregate shape points into LineString geometries
    def _create_shape_linestring(g):
        g = g.sort_values('shape_pt_sequence')
        coords = list(zip(g['shape_pt_lon'], g['shape_pt_lat']))  # Note: (lon, lat) for Point
        if len(coords) == 0:
            return None
        elif len(coords) == 1:
            return Point(coords[0])
        else:
            return LineString(coords)

    shapes_geom = shapes_df.groupby('shape_id').apply(_create_shape_linestring).reset_index()
    shapes_geom.columns = ['shape_id', 'shape_geometry']

    return shapes_geom

def process_routes(routes_df: pd.DataFrame, trips_df: pd.DataFrame) -> pd.DataFrame:
    """
    Process the routes DataFrame to include only relevant routes.
    This function filters routes to include only those present in trips_df and modifies route colors and route types.
    Args:
        routes_df (pd.DataFrame): DataFrame containing route information
        trips_df (pd.DataFrame): DataFrame containing trip information used to filter valid routes only
    Returns:
        pd.DataFrame: Processed routes DataFrame
    """
    # Filter routes to only include those present in trips_df
    routes_df = routes_df[routes_df['route_id'].isin(trips_df['route_id'])]

    # Add "#" to the colors of the routes_df
    routes_df['route_color'] = routes_df['route_color'].apply(lambda c: f"#{c}" if pd.notna(c) and not c.startswith('#') else c)

    #to numeric route_type
    routes_df['route_type'] = pd.to_numeric(routes_df['route_type'], errors='coerce')

    # Modify route_type for the Macrobus (Troncales only: MC-L1, MC-L1E, MP-T01, MP-T02, MP-T03)
    routes_df.loc[routes_df['route_short_name'].isin(["MC-L1", "MC-L1E", "MP-T01", "MP-T02", "MP-T03"]), 'route_type'] = 1

    return routes_df