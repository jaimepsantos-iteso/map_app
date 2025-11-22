from PyQt5.QtWebEngineWidgets import QWebEngineView

HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Leaflet Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
</head>
<body style="margin:0">
  <div id="map" style="width:100vw; height:100vh"></div>

  <script>
    var map = L.map('map').setView([20.67, -103.35], 13);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19
    }).addTo(map);

    window.drawRoute = function(coords) {
      if (window.routeLine) {
        map.removeLayer(window.routeLine);
      }
      window.routeLine = L.polyline(coords, {color: 'red', weight: 5}).addTo(map);
      map.fitBounds(window.routeLine.getBounds());
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
