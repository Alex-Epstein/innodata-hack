# Terrain tile sources

All 16 files were downloaded once on 2026-11-14 from the public AWS Open Data registry "Terrain Tiles"
(no key, anonymous HTTPS), Mapzen terrarium encoding, zoom 13, 256x256 PNG, Web Mercator (EPSG:3857).
Decoding: elevation_m = (R*256 + G + B/256) - 32768. The generator reads only these local files.

- Registry: https://registry.opendata.aws/terrain-tiles/
- URL pattern: https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png
- License / attribution: in the contiguous US the underlying data is USGS 3DEP (formerly NED), public domain
  ("Elevation data: U.S. Geological Survey 3D Elevation Program"). The tile set as a whole also blends other
  sources (e.g. ETOPO1 / GMTED / bathymetry); see the Mapzen terrain tiles attribution page
  (https://github.com/tilezen/joerd/blob/master/docs/attribution.md). Water areas (Hudson River) contain blended
  bathymetry artifacts, which is why gen.py rejects crops that are more than 10% water.

| File | z/x/y | URL | bytes |
|---|---|---|---|
| bear_13_2411_3061.png | 13/2411/3061 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2411/3061.png | 120681 |
| bear_13_2411_3062.png | 13/2411/3062 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2411/3062.png | 118932 |
| bear_13_2412_3061.png | 13/2412/3061 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2412/3061.png | 116937 |
| bear_13_2412_3062.png | 13/2412/3062 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2412/3062.png | 120049 |
| breakneck_13_2412_3057.png | 13/2412/3057 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2412/3057.png | 99161 |
| breakneck_13_2412_3058.png | 13/2412/3058 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2412/3058.png | 119728 |
| breakneck_13_2413_3057.png | 13/2413/3057 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2413/3057.png | 116506 |
| breakneck_13_2413_3058.png | 13/2413/3058 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2413/3058.png | 113846 |
| harriman_13_2409_3063.png | 13/2409/3063 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2409/3063.png | 119203 |
| harriman_13_2409_3064.png | 13/2409/3064 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2409/3064.png | 115403 |
| harriman_13_2410_3063.png | 13/2410/3063 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2410/3063.png | 115264 |
| harriman_13_2410_3064.png | 13/2410/3064 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/2410/3064.png | 113379 |
| tam_13_1305_3161.png | 13/1305/3161 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/1305/3161.png | 128600 |
| tam_13_1305_3162.png | 13/1305/3162 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/1305/3162.png | 128260 |
| tam_13_1306_3161.png | 13/1306/3161 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/1306/3161.png | 129770 |
| tam_13_1306_3162.png | 13/1306/3162 | https://s3.amazonaws.com/elevation-tiles-prod/terrarium/13/1306/3162.png | 131783 |

Areas (2x2 tiles each): bear = Bear Mountain NY, breakneck = Breakneck Ridge / Hudson Highlands NY, harriman = Harriman State Park NY, tam = Mount Tamalpais CA. Total 1.9M. SHA-256 in SHA256SUMS.
