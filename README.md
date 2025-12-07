# map_app
Route planner for Buses in Guadalajara

## 🚌 Overview
An interactive web application for planning public transportation routes in Guadalajara Metropolitan Area (ZMG). The app combines GTFS transit data with OpenStreetMap walking paths to provide optimal multi-modal route recommendations.

## ✨ Features
- **Interactive Route Planning**: Click on the map or enter addresses to set origin and destination
- **Multi-modal Routing**: Combines walking and public transit (buses, BRT, light rail)
- **Alternative Routes**: Displays up to 3 alternative routes sorted by travel time
- **Detailed Instructions**: Step-by-step directions with estimated times and waiting periods
- **Real-time Transit Data**: Uses GTFS data including frequencies, stop times, and route information
- **Dark Mode Support**: UI adapts to your system theme

## 🏗️ Architecture

### Core Components
- **`streamlit_app.py`**: Main UI application with interactive map and route display
- **`core/routing.py`**: Routing algorithms including:
  - Dijkstra's algorithm with A* heuristic for transit routing
  - Multi-start optimization for nearby stops
  - Transfer penalty based on frequency/headway
  - Walking path calculation using OSMnx
- **`data/graph_loader.py`**: Loads and manages walking and transit graphs
- **`data/gtfs_loader.py`**: Processes GTFS transit data

### Key Algorithms
- **Transit Routing**: Modified Dijkstra with shape-aware pathfinding
- **Walking Integration**: 5-minute walking radius for stop accessibility
- **Alternative Routes**: Iterative shape restriction to find diverse paths
- **Spatial Indexing**: R-tree for efficient nearby stop queries

## 📊 Data Sources
- **GTFS Data**: `data/gtfs/` - Transit schedules, routes, stops, and shapes
- **OSM Data**: `data/osm/` - Street network for walking paths
- **Graphs**: Pre-computed NetworkX graphs stored in `data/graphs/`

## 🚀 Installation

### Prerequisites
- Python 3.10+
- Virtual environment (recommended)

### Setup
```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### Required Packages
- `streamlit` - Web application framework
- `streamlit-folium` - Interactive map integration
- `folium` - Map visualization
- `geopandas` - Geospatial data processing
- `osmnx` - OpenStreetMap network analysis
- `networkx` - Graph algorithms
- `shapely` - Geometric operations
- `geopy` - Geocoding services
- `pyproj` - Coordinate transformations
- `pandas` - Data manipulation

## 🎮 Usage

### Running the Application
```bash
streamlit run streamlit_app.py
```

The app will open in your browser at `http://localhost:8501`

### Using the Route Planner
1. **Set Origin and Destination**:
   - Click on the map to place markers, or
   - Enter addresses in the sidebar text inputs
   
2. **Calculate Route**:
   - Click "Buscar y Calcular Ruta" button
   - Wait for route calculation (typically 1-3 seconds)

3. **View Results**:
   - Map displays the complete route with colored lines
   - Alternative routes appear as buttons above the map
   - Detailed instructions show on the right side
   
4. **Switch Routes**:
   - Click "Ruta 1", "Ruta 2", etc. to view alternatives
   - Each button shows the total travel time

## 🗺️ Map Features
- **Green marker**: Origin point
- **Red marker**: Destination point
- **Colored lines**: Transit routes (color matches route branding)
- **Gray lines**: Walking segments
- **Circle markers**: Stops along the route
- **Tooltips**: Hover over stops and routes for details

## 📝 Route Instructions
Each route segment displays:
- **Walking segments**: Origin, destination, estimated time
- **Transit segments**: 
  - Route name and color badge
  - Boarding stop with estimated wait time
  - Direction (headsign)
  - Travel time
  - Alighting stop

## 🔧 Configuration

### Graph Generation
To regenerate the walking graph:
```python
from data.graph_loader import GraphLoader
loader = GraphLoader()
loader.create_graph_walk("data/graphs/ZMG_walk.pkl", "data/osm/ZMG_enclosure_2km.geojson")
```

### Transit Graph
To regenerate the transit graph:
```python
loader.create_graph_transit("data/graphs/ZMG_transit.pkl", stops_df, max_walking_time=300)
```

## 🎯 Algorithm Details

### Route Calculation
1. **Find nearby stops**: Uses spatial indexing to find all stops within 5-minute walk
2. **Multi-start Dijkstra**: Runs pathfinding from all nearby stops simultaneously
3. **Transfer optimization**: Applies frequency-based penalty for transfers
4. **Alternative generation**: Restricts shapes from previous routes to find alternatives
5. **Route ranking**: Sorts by total time (travel + waiting)

### Time Estimation
- Walking speed: 5 km/h on known paths, 3 km/h on direct lines
- Transit time: Based on actual stop_time_deltas from GTFS
- Waiting time: Median frequency (headway) for each route

## 📂 Project Structure
```
map_app/
├── streamlit_app.py          # Main application
├── core/
│   ├── routing.py            # Routing algorithms
│   └── __init__.py
├── data/
│   ├── graph_loader.py       # Graph generation
│   ├── gtfs_loader.py        # GTFS data processing
│   ├── gtfs/                 # GTFS transit data
│   ├── osm/                  # OpenStreetMap data
│   └── graphs/               # Cached graph files
├── gui/                      # (Legacy GUI components)
├── learn/                    # Jupyter notebooks for exploration
└── README.md
```

## 🐛 Troubleshooting

### Common Issues
- **"No route found"**: Origin/destination may be too far from transit stops
- **Slow loading**: First run loads and caches graphs (10-20 seconds)
- **Map not updating**: Click "Reiniciar selección" to reset

### Performance Tips
- Pre-computed graphs are cached in `data/graphs/`
- RouteService is cached with `@st.cache_resource`
- Use EPSG:3857 (meters) for distance calculations

## 📄 License
This project is for academic use as part of Algorithm Design and Analysis coursework at ITESO.

## 👥 Contributors
- Jaime Ignacio Perez De Los Santos
- ITESO - Maestría en Ciencias Computacionales

## 🔗 Related Resources
- [GTFS Specification](https://gtfs.org/)
- [OSMnx Documentation](https://osmnx.readthedocs.io/)
- [Streamlit Documentation](https://docs.streamlit.io/)
