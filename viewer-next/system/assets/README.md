# Historical reference art for normal monitoring

- `globe-surface.webp` — 4096 × 2048 equirectangular texture for the interactive globe; satellite-derived land, ocean and clouds from NASA/GSFC SVS. Geographic pixels retain the source color; illumination and atmospheric rim are display shading. Not a live observation.

These derivatives are made locally from the cited historical sources. The globe is from NASA/GSFC SVS; nighttime lights use NASA Earth Observatory archival imagery. The inputs are from different periods and are not synchronized or current observations. No internal asset is included and no external runtime requests are required.

- `normal-night-2016.webp` — offline 1800 × 900 derivative of the archived **2016 Black Marble** source linked below (ImageMagick proportional resize, metadata stripped, WebP quality 90, SHA-256 `a8bc75a4acfd61ba1a19da5a701a2f17412f5ad3ac98132cb8edb6555e1c1922`). Its proximity to the daylight texture is a display composite only, not a single capture or current night. Amber is a display grade, not a measurement or an event marker. Normal-monitor globe only. If either texture or WebGL2 is unavailable, the original wireframe placeholder remains.

## Sources and attribution

- Globe: NASA/Goddard Space Flight Center Scientific Visualization Studio, Greg Shirah, [Equirectangular Projected Earth for “LARGEST”](https://svs.gsfc.nasa.gov/3615) ([8192 × 4096 source JPG](https://svs.gsfc.nasa.gov/vis/a000000/a003600/a003615/flat_earth_Largest_still.0330.jpg), SHA-256 `5ea6b68a4412421cae11711ae4fec1a7b1f2dbd7265c0c3004d487a03c43be9a`). Blue Marble Next Generation data courtesy of Reto Stöckli (NASA/GSFC) and NASA Earth Observatory; CPC global satellite cloud composite dated 2007-07-01. NASA SVS describes this as an art-directed historical composition. The atmospheric rim and directional light are presentation only.


- NASA Earth Observatory, [Earth at Night / Black Marble: 2016 Color Flat Maps](https://science.nasa.gov/earth/earth-observatory/earth-at-night/maps/), [download](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/imagerecords/144000/144898/BlackMarble_2016_01deg.jpg), SHA-256 `d87de751a264e4f8ff69c68de5dab9606daee87a6f15ae743c93200743bd7ec1`. [NASA credits](https://science.nasa.gov/earth/earth-observatory/night-light-maps-open-up-new-applications-90008/): Joshua Stevens, using Suomi NPP VIIRS data from Miguel Román, NASA Goddard Space Flight Center.
- [NASA Earth Science re-use and credit guidance](https://science.nasa.gov/earth/faq/), [NASA images/media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/). No NASA marks appear. Source credit does not imply endorsement.


Fixed Sun direction: 2026-06-21 01:00 UTC is a display-only illumination reference, not the timestamp of either texture, the terminal clock, or the monitored world. Decorative color grading, cloud relief and atmosphere carry no measurement. A separate star backdrop and illustrative light arcs are synthetic, not observations, telemetry, live links, or inferred network data.
