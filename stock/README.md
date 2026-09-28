# Local stock library

Drop clips and stills in here, grouped into folders by subject. The `stock`
visual provider indexes filenames and folder names, so descriptive names
matter more than structure:

```
stock/
  city-night/
    _license.json
    city-night-timelapse-traffic.mp4
  server-room/
    _license.json
    server-room-racks-blue.mp4
```

Each folder should carry a `_license.json` so the asset manifest records where
every frame came from:

```json
{
  "license": "Pexels License",
  "source_url": "https://www.pexels.com/video/123456/",
  "photorealistic": true
}
```

**Pexels** and **Pixabay** both permit commercial use with no attribution.
Treat stock as a *base layer* only: the popular clips circulate very widely, so
a video built entirely from them is the reuse that template detection looks
for. The pipeline warns when an asset repeats across jobs.

This directory is gitignored apart from this README.
