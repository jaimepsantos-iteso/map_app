import streamlit as st
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import folium
from geopy.geocoders import Nominatim
from shapely.geometry import Point
from pyproj import Transformer


from core.routing import RouteService
from data.graph_loader import GraphLoader
from data.gtfs_loader import GTFSLoader

# --- 1. Page configuration and session state ---

st.set_page_config(
    page_title="Mapa de Rutas GDL",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Session State: persistent app variables ---
if 'route_service' not in st.session_state:
    st.session_state.route_service = None
if 'geolocator' not in st.session_state:
    st.session_state.geolocator = Nominatim(user_agent="map_app_gdl")
if 'last_map' not in st.session_state:
    st.session_state.last_map = None
if 'start_point' not in st.session_state:
    st.session_state.start_point = None
if 'end_point' not in st.session_state:
    st.session_state.end_point = None
if 'selected_target' not in st.session_state:
    st.session_state.selected_target = None
if 'map_center' not in st.session_state:
    st.session_state.map_center = [20.67, -103.35]
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 12

# No pick mode: markers are draggable only

# --- 2. Loading and logic functions ---

@st.cache_resource
def load_services():
    """Load heavy services (graphs, dataframes) and cache them."""
    
    gtfs_loader = GTFSLoader()

    # Load transit and stops data from GTFS files
    transit_df = gtfs_loader.load_transit_dataframe("data/gtfs")
    stops_df = gtfs_loader.load_stops_dataframe("data/gtfs", transit_df)
    
    graph_loader = GraphLoader()

    # Create walking graph limited to the polygon
    graph_walk = graph_loader.create_graph_walk("data/graphs/ZMG_walk.pkl", "data/osm/ZMG_enclosure_2km.geojson")
    
    # Create transit graph from GTFS data and stops with a max walking distance of 300 seconds
    graph_transit = graph_loader.create_graph_transit("data/graphs/ZMG_transit.pkl", stops_df, 300)
    
    return RouteService(graph_walk, graph_transit, stops_df, transit_df)

def geocode_address(address):
    """Convert a text address to coordinates (lat, lon)."""
    try:
        location = st.session_state.geolocator.geocode(address, country_codes="MX")
        
        if location:
            
            transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            x, y = transformer.transform(location.longitude, location.latitude)
            return Point(x, y)
    except Exception as e:
        st.error(f"Geocoding error: {e}")
    return None

# --- 3. App initialization ---

# Show a spinner while heavy data loads the first time
with st.spinner('Cargando grafos y datos de rutas... Por favor, espera.'):
    if st.session_state.route_service is None:
        st.session_state.route_service = load_services()

st.title("🗺️ Planeador de Rutas de Transporte Público - GDL")


# --- 4. User interface (Sidebar and Map) ---

with st.sidebar:
    st.header("Puntos de la Ruta")
    
    # Text inputs for origin and destination
    def _update_from_start_text():
        addr = st.session_state.get("start_address", "")
        sp = geocode_address(addr) if addr else None
        if sp:
            st.session_state.start_point = sp
            # Rerun to refresh markers without clearing the route map
            st.rerun()
    def _update_from_end_text():
        addr = st.session_state.get("end_address", "")
        ep = geocode_address(addr) if addr else None
        if ep:
            st.session_state.end_point = ep
            # Rerun to refresh markers without clearing the route map
            st.rerun()

    start_address = st.text_input("📍 Origen", key="start_address", placeholder="Ej: Catedral de Guadalajara", on_change=_update_from_start_text)
    end_address = st.text_input("🏁 Destino", key="end_address", placeholder="Ej: ITESO", on_change=_update_from_end_text)

    if st.button("Buscar y Calcular Ruta", type="primary"):
        with st.spinner("Buscando direcciones y calculando la mejor ruta..."):
            # Allow either map-picked points or geocoded text
            if start_address:
                sp = geocode_address(start_address)
                if sp:
                    st.session_state.start_point = sp
            if end_address:
                ep = geocode_address(end_address)
                if ep:
                    st.session_state.end_point = ep

            if not st.session_state.start_point or not st.session_state.end_point:
                st.error("Selecciona puntos en el mapa o ingresa direcciones para origen y destino.")
            else:
                # Call routing function that returns a folium map
                df, total_time_list, folium_map, path_transit = st.session_state.route_service.route_combined(
                    st.session_state.start_point,
                    st.session_state.end_point
                )
                st.session_state.last_map = st.session_state.route_service.create_map(df)
                st.session_state.route_df = df
                total_time_min = sum(total_time_list) / 60
                st.success(f"Ruta encontrada. Tiempo total: {total_time_min:.0f} minutos.")
                # After calculating the route, clear selection and disable radio via last_map
                st.session_state.selected_target = None

# --- 5. Map visualization ---

# The map occupies the main page area
st.subheader("Mapa Interactivo")

# Radio + reset button row
col_radio, col_btn = st.columns([3, 1])
with col_radio:
    st.session_state.selected_target = st.radio(
        "Selecciona punto a mover",
        options=["Origen", "Destino"],
        index=(0 if st.session_state.selected_target == "Origen" else 1) if st.session_state.selected_target in ["Origen", "Destino"] else 0,
        horizontal=True,
        help="El clic en el mapa actualizará el punto seleccionado.",
        disabled=bool(st.session_state.last_map)
    )
with col_btn:
    if st.button("Reiniciar selección"):
        # Clear selection and re-enable radio; keep markers and points
        st.session_state.selected_target = None
        # Also clear the route map so selection is enabled again
        st.session_state.last_map = None
        st.rerun()



# If a route map exists, show it as a static HTML (no flicker). Otherwise, show an interactive base map.
if st.session_state.last_map:
    # Apply preserved view to route map if possible and render static HTML
    try:
        st.session_state.last_map.location = st.session_state.map_center or [20.67, -103.35]
        st.session_state.last_map.zoom_start = st.session_state.map_zoom or 12
    except Exception:
        pass
    components.html(st.session_state.last_map._repr_html_(), height=600)
    map_to_show = None
else:
    # Initial base map centered on Guadalajara
    map_to_show = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom)

    # Initialize default markers if not set using placeholders
    if st.session_state.start_point is None:
        default_start = geocode_address("Catedral de Guadalajara")
        if default_start:
            st.session_state.start_point = default_start
    if st.session_state.end_point is None:
        default_end = geocode_address("ITESO")
        if default_end:
            st.session_state.end_point = default_end

# Add current start/end markers to base map (only when interactive base map is shown)
_to4326 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
if map_to_show and st.session_state.start_point:
    sp = st.session_state.start_point
    lon, lat = _to4326.transform(sp.x, sp.y)
    folium.Marker(location=[lat, lon], tooltip="Origen", icon=folium.Icon(color='green'), draggable=False).add_to(map_to_show)
if map_to_show and st.session_state.end_point:
    ep = st.session_state.end_point
    lon, lat = _to4326.transform(ep.x, ep.y)
    folium.Marker(location=[lat, lon], tooltip="Destino", icon=folium.Icon(color='red'), draggable=False).add_to(map_to_show)


# Use st_folium to render the map interactively and capture clicks
map_events = st_folium(map_to_show, width='100%', height=600) or {} if map_to_show else {}

# Handle map click to set origin/destination
clicked = map_events.get("last_clicked") if map_to_show else None

if clicked and st.session_state.last_map is None:
    _tr = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    dx, dy = _tr.transform(clicked["lng"], clicked["lat"])
    dpt = Point(dx, dy)
    
    # Preserve current zoom/center from this interaction before rerun
    if 'zoom' in map_events and map_events['zoom'] is not None:
        st.session_state.map_zoom = map_events['zoom']
    if 'center' in map_events and map_events['center']:
        st.session_state.map_center = [map_events['center']['lat'], map_events['center']['lng']]
    target = st.session_state.selected_target
    if target == "Origen":
        st.session_state.start_point = dpt
        st.rerun()
    else:#if target == "Destino":
        st.session_state.end_point = dpt
        st.rerun()

# Show route segments DataFrame below the map if available
if st.session_state.get('route_df') is not None and not st.session_state.route_df.empty and st.session_state.last_map is not None:
    st.subheader("Detalles de la Ruta")
    # Display the DataFrame with selected columns for readability
    display_df = st.session_state.route_df[['mode', 'route_long_name', 'route_short_name', 'trip_headsign', 'stops', 'stop_names', 'segment_time_seconds']].copy()
    st.dataframe(display_df, use_container_width=True)

