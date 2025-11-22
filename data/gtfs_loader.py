import os
from typing import Optional

import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString


def load_routes_geodataframe(gtfs_folder: str, crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """
    Load GTFS `routes.txt`, `trips.txt` and `shapes.txt` and return a GeoDataFrame
    where each route is represented by a LineString geometry built from the
    corresponding shape points.

    Args:
        gtfs_folder: Path to the folder containing GTFS text files (routes.txt,
            trips.txt, shapes.txt).
        crs: Coordinate reference system for the returned GeoDataFrame.

    Returns:
        GeoDataFrame with route fields from `routes.txt` and a `geometry` column
        containing LineString objects where available. Routes without a matching
        shape will have `geometry` set to None.

    Usage example:
        >>> from data.gtfs_loader import load_routes_geodataframe
        >>> gdf = load_routes_geodataframe(r"data/gtfs")
        >>> gdf.plot()
    """

    routes_path = os.path.join(gtfs_folder, "routes.txt")
    trips_path = os.path.join(gtfs_folder, "trips.txt")
    shapes_path = os.path.join(gtfs_folder, "shapes.txt")

    # Read files, handle missing gracefully
    if not os.path.exists(routes_path):
        raise FileNotFoundError(f"routes.txt not found in {gtfs_folder}")

    routes_df = pd.read_csv(routes_path, dtype=str)

    # Load shapes
    if os.path.exists(shapes_path):
        shapes_df = pd.read_csv(shapes_path, dtype={"shape_id": str})
        # Ensure required columns exist
        if not {"shape_pt_lat", "shape_pt_lon"}.issubset(shapes_df.columns):
            raise ValueError("shapes.txt must contain 'shape_pt_lat' and 'shape_pt_lon' columns")
        # Default sequence column name
        seq_col = "shape_pt_sequence" if "shape_pt_sequence" in shapes_df.columns else None

        if seq_col:
            shapes_df = shapes_df.sort_values(["shape_id", seq_col])
        else:
            shapes_df = shapes_df.sort_values(["shape_id"])

        # Build LineString for each shape_id
        shape_geoms = (
            shapes_df.groupby("shape_id").apply(
                lambda df: LineString(list(zip(df["shape_pt_lon"].astype(float), df["shape_pt_lat"].astype(float))))
            )
        )
        # series: index shape_id -> LineString
        shape_point_counts = shapes_df.groupby("shape_id")["shape_pt_lat"].size().to_dict()
    else:
        shape_geoms = pd.Series(dtype=object)
        shape_point_counts = {}

    # Map routes -> shape via trips.txt
    route_shape_map = {}
    if os.path.exists(trips_path):
        trips_df = pd.read_csv(trips_path, dtype=str)
        if "route_id" in trips_df.columns and "shape_id" in trips_df.columns:
            # Collect candidate shapes per route
            candidates = trips_df.groupby("route_id")["shape_id"].unique().to_dict()
            for route_id, shape_ids in candidates.items():
                # choose the shape with the most points (if available)
                best_shape = None
                best_count = -1
                for sid in shape_ids:
                    cnt = shape_point_counts.get(sid, 0)
                    if cnt > best_count:
                        best_count = cnt
                        best_shape = sid
                if best_shape is not None:
                    route_shape_map[route_id] = best_shape

    # Build geometry list matching routes_df rows
    geometries = []
    for _, row in routes_df.iterrows():
        rid = str(row.get("route_id")) if "route_id" in row else None
        geom = None
        if rid in route_shape_map:
            sid = route_shape_map[rid]
            # lookup geometry
            try:
                geom = shape_geoms.loc[sid]
            except Exception:
                geom = None
        geometries.append(geom)

    gdf = gpd.GeoDataFrame(routes_df.copy(), geometry=geometries, crs=crs)

    return gdf
