### Required packages

- PyQt5
- PyQtWebEngine
- networkx
- osmnx
- pandas
- geopandas
- folium
- branca
- matplotlib
- mapclassify

Suggested installs:

- Conda (recommended, uses conda-forge):
    - conda install -c conda-forge pyqt pyqtwebengine networkx osmnx pyosmium pandas geopandas folium branca matplotlib mapclassify

- Pip (virtualenv):
    - pip install PyQt5 PyQtWebEngine networkx osmnx pyosmium pandas geopandas folium branca matplotlib mapclassify

Note: use conda-forge for geospatial packages to avoid dependency issues.
PyQtWebEngine


- For downloading the newest version of the OSM of Jalisco
https://geo2day.com/north_america/mexico/jalisco.html

In Anaconda promt:

conda install conda-forge::osmium-tool

osmium extract --polygon=ZMG_enclosure_2km.geojson jalisco.pbf -o zmg.geojson
osmium export zmg.pbf -o zmg.geojson 
