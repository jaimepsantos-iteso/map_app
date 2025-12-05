import streamlit as st
from streamlit_folium import st_folium
import folium
from geopy.geocoders import Nominatim
from shapely.geometry import Point

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

# Session state stores variables across page reloads
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

# --- 2. Loading and logic functions ---

@st.cache_resource
def load_services():
    """Load heavy services (graphs, dataframes) and cache them."""
    graph_loader = GraphLoader()
    gtfs_loader = GTFSLoader()

    graph_walk = graph_loader.create_graph_walk("data/graphs/ZMG_walk.pkl", "data/osm/ZMG_enclosure_2km.geojson")
    transit_df = gtfs_loader.load_transit_dataframe("data/gtfs")
    stops_df = gtfs_loader.load_stops_dataframe("data/gtfs", transit_df)
    graph_transit = graph_loader.create_graph_transit("data/graphs/ZMG_transit.pkl", stops_df, 300)
    
    return RouteService(graph_walk, graph_transit, stops_df, transit_df)

def geocode_address(address):
    """Convert a text address to coordinates (lat, lon)."""
    try:
        location = st.session_state.geolocator.geocode(address, country_codes="MX")
        
        if location:
            from pyproj import Transformer
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
    start_address = st.text_input("📍 Origen", placeholder="Ej: Catedral de Guadalajara")
    end_address = st.text_input("🏁 Destino", placeholder="Ej: ITESO")

    if st.button("Buscar y Calcular Ruta", type="primary"):
        if not start_address or not end_address:
            st.warning("Por favor, introduce tanto el origen como el destino.")
        else:
            with st.spinner("Buscando direcciones y calculando la mejor ruta..."):
                start_coords = geocode_address(start_address)
                end_coords = geocode_address(end_address)

                if start_coords and end_coords:
                    st.session_state.start_point = start_coords
                    st.session_state.end_point = end_coords
                    
                    # Call routing function that returns a folium map
                    total_time_list, folium_map = st.session_state.route_service.route_combined(
                        st.session_state.start_point, 
                        st.session_state.end_point
                    )
                    
                    st.session_state.last_map = folium_map
                    
                    # Show time summary
                    total_time_min = sum(total_time_list) / 60
                    st.success(f"Ruta encontrada. Tiempo total: {total_time_min:.0f} minutos.")
                    
                else:
                    st.error("Could not find coordinates for one or both addresses.")

# --- 5. Map visualization ---

# The map occupies the main page area
st.subheader("Mapa Interactivo")

# If a route map exists, show it. Otherwise, show a base map.
if st.session_state.last_map:
    map_to_show = st.session_state.last_map
else:
    # Initial base map centered on Guadalajara
    map_to_show = folium.Map(location=[20.67, -103.35], zoom_start=12)

# Use st_folium to render the map interactively
st_folium(map_to_show, width='100%', height=600, returned_objects=[])

st.info("To run this app, save as `streamlit_app.py` and run `streamlit run streamlit_app.py` in your terminal.")
