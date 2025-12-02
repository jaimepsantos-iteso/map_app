import streamlit as st
from streamlit_folium import st_folium
import folium
from geopy.geocoders import Nominatim
from shapely.geometry import Point

from core.routing import RouteService
from data.graph_loader import GraphLoader
from data.gtfs_loader import GTFSLoader

# --- 1. Configuración de la página y estado de la sesión ---

st.set_page_config(
    page_title="Mapa de Rutas GDL",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# El estado de la sesión se usa para guardar variables entre recargas de la página
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

# --- 2. Funciones de Carga y Lógica ---

@st.cache_resource
def load_services():
    """Carga todos los servicios pesados (grafos, dataframes) y los cachea."""
    graph_loader = GraphLoader()
    gtfs_loader = GTFSLoader()

    graph_walk = graph_loader.create_graph_walk("data/graphs/ZMG_walk.pkl", "data/osm/ZMG_enclosure_2km.geojson")
    transit_df = gtfs_loader.load_transit_dataframe("data/gtfs")
    stops_df = gtfs_loader.load_stops_dataframe("data/gtfs", transit_df)
    graph_transit = graph_loader.create_graph_transit("data/graphs/ZMG_transit.pkl", stops_df, 300)
    
    return RouteService(graph_walk, graph_transit, stops_df, transit_df)

def geocode_address(address):
    """Convierte una dirección de texto a coordenadas (lat, lon)."""
    try:
        location = st.session_state.geolocator.geocode(address, country_codes="MX")
        
        if location:
            from pyproj import Transformer
            transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            x, y = transformer.transform(location.longitude, location.latitude)
            return (x, y)
    except Exception as e:
        st.error(f"Error de geocodificación: {e}")
    return None

# --- 3. Inicialización de la App ---

# Muestra un spinner mientras se cargan los datos pesados la primera vez
with st.spinner('Cargando grafos y datos de rutas... Por favor, espera.'):
    if st.session_state.route_service is None:
        st.session_state.route_service = load_services()

st.title("🗺️ Planeador de Rutas de Transporte Público - GDL")

# --- 4. Interfaz de Usuario (Sidebar y Mapa) ---

with st.sidebar:
    st.header("Puntos de la Ruta")
    
    # Entradas de texto para origen y destino
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
                    st.session_state.start_point = Point(start_coords[1], start_coords[0]) # lon, lat
                    st.session_state.end_point = Point(end_coords[1], end_coords[0]) # lon, lat
                    
                    # Llama a la función de ruteo que devuelve el mapa de folium
                    total_time_list, folium_map = st.session_state.route_service.route_combined(
                        st.session_state.start_point, 
                        st.session_state.end_point
                    )
                    
                    st.session_state.last_map = folium_map
                    
                    # Mostrar resumen del tiempo
                    total_time_min = sum(total_time_list) / 60
                    st.success(f"Ruta encontrada. Tiempo total: {total_time_min:.0f} minutos.")
                    
                else:
                    st.error("No se pudieron encontrar las coordenadas para una o ambas direcciones.")

# --- 5. Visualización del Mapa ---

# El mapa ocupa el área principal de la página
st.subheader("Mapa Interactivo")

# Si hay un mapa de ruta calculado, muéstralo. Si no, muestra un mapa base.
if st.session_state.last_map:
    map_to_show = st.session_state.last_map
else:
    # Mapa inicial centrado en Guadalajara
    map_to_show = folium.Map(location=[20.67, -103.35], zoom_start=12)

# Usamos st_folium para renderizar el mapa y hacerlo interactivo
st_folium(map_to_show, width='100%', height=600, returned_objects=[])

st.info("Para ejecutar esta aplicación, guarda el código como `streamlit_app.py` y corre `streamlit run streamlit_app.py` en tu terminal.")
