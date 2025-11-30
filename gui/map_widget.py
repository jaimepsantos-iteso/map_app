from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl
import json

HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Leaflet Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
  <link rel="stylesheet" href="https://unpkg.com/leaflet-control-geocoder/dist/Control.Geocoder.css" />
  <script src="https://unpkg.com/leaflet-control-geocoder/dist/Control.Geocoder.js"></script>
  <script src="https://unpkg.com/@turf/turf@6/turf.min.js"></script>
  <style>
    html, body { height:100%; margin:0; }
    #map { width:100vw; height:100vh; }
    .leaflet-control.geocoder-control input { width: 240px; }
  </style>
</head>
<body>
  <div id="map"></div>

  <script>
    var map = L.map('map').setView([20.67, -103.35], 12);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19
    }).addTo(map);

    // Geocoder control for quick search
    if (L.Control.Geocoder) {
      L.Control.geocoder({ defaultMarkGeocode: false })
        .on('markgeocode', function(e) {
          var center = e.geocode.center;
          map.setView(center, 16);
        })
        .addTo(map);
    }

    // State
    window.boundaryLayer = null;
    window.boundaryGeoJSON = null;
    window.pickMode = 'none'; // 'origin' | 'dest' | 'none'
    window.originMarker = null;
    window.destMarker = null;
    window.routeLayerGroup = L.layerGroup().addTo(map);

    function pointInsideBoundary(latlng) {
      if (!window.boundaryGeoJSON) return true; // allow if no boundary set
      var pt = turf.point([latlng.lng, latlng.lat]);
      var feat = window.boundaryGeoJSON.features ? window.boundaryGeoJSON.features[0] : window.boundaryGeoJSON;
      try {
        return turf.booleanPointInPolygon(pt, feat);
      } catch(e) {
        return true;
      }
    }

    function setMarker(type, latlng) {
      if (!pointInsideBoundary(latlng)) {
        alert('El punto está fuera del polígono');
        return;
      }
      if (type === 'origin') {
        if (window.originMarker) map.removeLayer(window.originMarker);
        window.originMarker = L.marker(latlng, { draggable: true }).addTo(map).bindPopup('Origen');
        window.originMarker.on('dragend', function(ev){
          if (!pointInsideBoundary(ev.target.getLatLng())) {
            alert('Origen fuera del polígono');
            ev.target.setLatLng(latlng);
          }
        });
      } else if (type === 'dest') {
        if (window.destMarker) map.removeLayer(window.destMarker);
        window.destMarker = L.marker(latlng, { draggable: true }).addTo(map).bindPopup('Destino');
        window.destMarker.on('dragend', function(ev){
          if (!pointInsideBoundary(ev.target.getLatLng())) {
            alert('Destino fuera del polígono');
            ev.target.setLatLng(latlng);
          }
        });
      }
    }

    map.on('click', function(e){
      if (window.pickMode === 'origin' || window.pickMode === 'dest') {
        setMarker(window.pickMode, e.latlng);
      }
    });

    // Public API
    window.setPolygon = function(geojson) {
      try {
        if (typeof geojson === 'string') geojson = JSON.parse(geojson);
      } catch(e) {}
      if (window.boundaryLayer) {
        map.removeLayer(window.boundaryLayer);
      }
      window.boundaryGeoJSON = geojson;
      window.boundaryLayer = L.geoJSON(geojson, { style: { color: '#3388ff', weight: 2, fill: false }}).addTo(map);
      try {
        map.fitBounds(window.boundaryLayer.getBounds());
      } catch(e) {}
    }

    window.setPickMode = function(mode) {
      window.pickMode = mode;
    }

    window.setPoint = function(type, lat, lng) {
      setMarker(type, L.latLng(lat, lng));
    }

    window.getPoints = function() {
      var o = window.originMarker ? [window.originMarker.getLatLng().lat, window.originMarker.getLatLng().lng] : null;
      var d = window.destMarker ? [window.destMarker.getLatLng().lat, window.destMarker.getLatLng().lng] : null;
      return { origin: o, dest: d };
    }

    window.searchAndSet = async function(type, query) {
      const url = 'https://nominatim.openstreetmap.org/search?format=json&q=' + encodeURIComponent(query);
      const res = await fetch(url, { headers: { 'Accept-Language': 'es' } });
      const data = await res.json();
      if (!data || !data.length) { alert('No se encontró ubicación'); return; }
      const item = data[0];
      const lat = parseFloat(item.lat), lon = parseFloat(item.lon);
      setMarker(type, L.latLng(lat, lon));
      map.setView([lat, lon], 16);
    }

    window.clearRoute = function(){
      window.routeLayerGroup.clearLayers();
    }

    window.drawRoute = function(coords) {
      window.clearRoute();
      var line = L.polyline(coords, {color: 'red', weight: 5}).addTo(window.routeLayerGroup);
      map.fitBounds(line.getBounds());
    }

    window.drawRouteSegments = function(segments) {
      window.clearRoute();
      var bounds = null;
      segments.forEach(function(seg){
        var color = seg.color || seg.route_color || (seg.mode === 'walk' ? '#666' : '#7b1fa2');
        var weight = seg.weight || seg.width || 4;
        var dash = seg.dashArray || (seg.mode === 'walk' ? '6,6' : null);
        var pl = L.polyline(seg.coords, { color: color, weight: weight, dashArray: dash, opacity: 0.95 }).addTo(window.routeLayerGroup);
        if (!bounds) bounds = pl.getBounds(); else bounds.extend(pl.getBounds());
      });
      if (bounds) map.fitBounds(bounds, { padding: [24,24] });
    }
  </script>
</body>
</html>
"""

class MapWidget(QWebEngineView):
    def __init__(self):
        super().__init__()
        self.setHtml(HTML)

    def draw_route(self, coordinates):
        # coordinates = [ [lat, lon], [lat, lon], ... ]
        js = f"window.drawRoute({coordinates});"
        self.page().runJavaScript(js)

    def set_polygon(self, geojson_obj):
      js_arg = json.dumps(geojson_obj)
      self.page().runJavaScript(f"window.setPolygon({js_arg});")

    def set_pick_mode(self, mode: str):
      self.page().runJavaScript(f"window.setPickMode('{mode}');")

    def set_point(self, which: str, lat: float, lon: float):
      self.page().runJavaScript(f"window.setPoint('{which}', {lat}, {lon});")

    def get_points(self, callback):
      self.page().runJavaScript("window.getPoints();", callback)

    def search_and_set(self, which: str, query: str):
      q = json.dumps(query)
      self.page().runJavaScript(f"window.searchAndSet('{which}', {q});")

    def draw_route_segments(self, segments: list):
      js_arg = json.dumps(segments)
      self.page().runJavaScript(f"window.drawRouteSegments({js_arg});")

    def clear_route(self):
      self.page().runJavaScript("window.clearRoute();")
