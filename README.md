# GeoSetter Lite - Image Metadata Viewer and Editor

[![License](https://img.shields.io/badge/license-Apache%202.0-blue?style=for-the-badge)](LICENSE)
[![Fork of](https://img.shields.io/badge/fork%20of-asaintsever%2Fgeosetter--lite-blue?style=for-the-badge)](https://github.com/asaintsever/geosetter-lite)

A comprehensive Python application for viewing and editing EXIF/IPTC/XMP metadata of images in a directory, with advanced geotagging capabilities and reverse geocoding.

> [!IMPORTANT]
> This is a **modified fork** of [asaintsever/geosetter-lite](https://github.com/asaintsever/geosetter-lite),
> the original work of [@asaintsever](https://github.com/asaintsever), used under the Apache License 2.0.
> It is not an official release of that project, and the original author has neither
> reviewed nor endorsed it. Files in this repository have been changed - see
> [Changes from upstream](#changes-from-upstream). The unmodified license text is in
> [`LICENSE`](LICENSE) and covers both the original work and these modifications.

> [!NOTE]
> This application is a tribute to GeoSetter (<https://geosetter.de/en/main-en/>) and is not affiliated with or endorsed by the original GeoSetter project.
>
> This is a light clone, written in Python, focusing on core geotagging features with additional AI-powered functionalities. The triggering reason was the lack of a macOS version of GeoSetter along with the desire to experiment with AI models for photo processing.

## Changes from upstream

Everything below was added or changed in this fork, relative to
[asaintsever/geosetter-lite](https://github.com/asaintsever/geosetter-lite) v1.0.1.

**Map overlays (KMZ/KML)** - new `geosetter_lite/services/kmz_service.py`.
Load KMZ/KML files to draw reference geometry beneath the photo markers, each file
toggleable in the layer switcher, with opt-in click handling so shapes do not
swallow map clicks. Geometry is simplified on load (Ramer-Douglas-Peucker, ~2 m)
and canvas-rendered to stay responsive on large datasets. See
[Map Overlays](#map-overlays-kmzkml).

**Satellite and hybrid basemaps** - the single OpenStreetMap view was replaced by a
layer switcher offering Esri World Imagery satellite, hybrid (imagery plus labels,
the new default) and OSM street views, remembered between sessions.

**Configurable start location** - the map opens at `DEFAULT_CENTER_LAT` /
`DEFAULT_CENTER_LON` / `DEFAULT_CENTER_ZOOM` in `geosetter_lite/ui/map_widget.py`
(Riyadh, Saudi Arabia) until geotagged photos are loaded.

**Parcel folders** - opening a folder named for a parcel in a loaded overlay moves
the map to that parcel. See [Parcel Folders](#parcel-folders).

**GPS updates apply immediately** - "Update GPS" no longer asks for confirmation and
no longer reports success in a modal dialog; the result goes to the status bar
instead. The confirmation can be restored in Settings. See
[GPS Update Confirmation](#gps-update-confirmation).

**Map no longer rebuilds when markers change** - photo markers and the active marker
are now injected into the live map document instead of being embedded in it. This
fixes two problems: writing GPS coordinates rebuilt the whole page, which dropped
tiles, overlays and popup state; and because each marker popup embeds a base64
thumbnail, a few hundred photos pushed the document past the 2 MB `setHtml()` limit,
at which point Qt silently discarded the entire page and the map failed to render.
Thumbnails are also cached by path, mtime and size.

## Features

### Core Features
- **Image List View**: Display all JPEG, PNG, and HEIF/HEIC images from a directory with comprehensive metadata columns
- **Image Viewer**: View selected images in a resizable panel with thumbnail support
- **Interactive Map**: Display all images with GPS coordinates on a satellite, hybrid or street map with visual distinction for selected images
- **Map Overlays**: Load KMZ/KML files to draw reference geometry (polygons, lines and points) beneath your photo markers
- **Active Marker**: Click anywhere on the map to set an active marker for batch GPS updates
- **GPS Coordinate Management**: Update multiple images with GPS coordinates from the active marker, applied immediately without a confirmation prompt
- **Parcel Folders**: Opening a folder named for a parcel in a loaded overlay centres the map on that parcel
- **3-Pane Resizable Layout**: Image list (top-left), image viewer (bottom-left), and map with toolbar (right)
- **Metadata Editor**: Edit EXIF/IPTC/XMP metadata for single or multiple images with namespace display
- **Batch Operations**: Apply metadata changes to multiple images at once
- **Inline Editing**: Edit metadata directly in the table with specialized editors for different field types
- **File Renaming**: Pattern-based batch file renaming with metadata tokens and counters
- **Image Rotation**:
  - Manually rotate images losslessly (90° left/right, 180°) from the "Rotate Photos" dialog.
  - Automatically rotate images for display based on their EXIF orientation tag. This can be enabled in the application settings.

### Advanced Features

- **Reverse Geocoding**: Automatically determine country and city from GPS coordinates using OpenStreetMap Nominatim API
- **Smart Country Picker**: Searchable dropdown with 195+ countries using 3-letter ISO codes (ISO 3166-1 alpha-3)
- **Timezone Management**: Automatic timezone offset calculation with DST support
- **Date/Time Management**: Comprehensive date handling with Taken Date, Created Date, and GPS Date (UTC)
- **Keywords Auto-Update**: Automatically add country code and country name to keywords
- **Metadata Repair**: Fix/repair corrupted metadata with ExifTool's repair function

### AI-Powered Features
- **Photo Similarity Detection**: Find duplicate or similar photos using ResNet-based deep learning
  - Configurable similarity threshold (0.0-1.0)
  - Groups similar photos with similarity scores
  - Batch deletion of similar photos
  - Runs locally with lightweight models
- **Geolocation Prediction**: Predict GPS coordinates for photos without location data
  - Uses CLIP-based vision-language model
  - SQLite database with 1000+ world locations (cities, landmarks, natural features)
  - Location data loaded from `data/world_locations.csv` (easy to update/extend)
  - Provides top 5 location predictions with confidence scores
  - Automatic reverse geocoding for predicted locations
  - Batch GPS coordinate updates
  - Runs entirely offline after initial model download
  - Database auto-initializes on first run from CSV file
  - To rebuild database: delete `locations.db` and restart app
  - To add locations: edit `world_locations.csv` directly

## Screenshots

### Main Window - Image Metadata Viewer
![Main Window](_img/GeoSetterLite-ImageMetadataViewer.png)
*3-pane layout with image list, image viewer, and interactive map*

### Metadata Editor
![Metadata Editor](_img/GeoSetterLite-MetadataEditor.png)
*Edit EXIF/IPTC/XMP metadata with filtering and tag management*

### AI-Powered Photo Similarity Detection
![Photo Similarity](_img/GeoSetterLite-PhotoSimilarity.png)
*Find and manage duplicate or similar photos*

### AI-Powered Geolocation Prediction
![Geolocation Prediction](_img/GeoSetterLite-GeolocPredict.png)
*Predict GPS coordinates for photos without location data*

## Requirements

- Python 3.12.9 or higher
- ExifTool installed on your system
- jpegtran installed on your system

### Installing ExifTool & jpegtran

**macOS:**
```bash
brew install exiftool jpeg-turbo
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install libimage-exiftool-perl
```

See <https://libjpeg-turbo.org/Downloads/YUM> for jpegtran

**Windows:**
Download from [https://exiftool.org](https://exiftool.org) and <https://github.com/libjpeg-turbo/libjpeg-turbo/releases>

## Installation

1. Install dependencies using uv (recommended) or pip:

```bash
# Using uv
uv sync

# Or using pip
pip install -e .
```

### macOS Setup (step by step)

Starting from a fresh Mac, after cloning the repository:

1. Install [Homebrew](https://brew.sh) if it is not already installed, then run the
   `eval ...` lines it prints at the end so `brew` is on your `PATH`:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. Install ExifTool, jpegtran (from `jpeg-turbo`) and uv:

   ```bash
   brew install exiftool jpeg-turbo uv
   ```

3. Install Python and the project dependencies. uv reads `.python-version` and
   downloads Python 3.12.9 itself, so no separate Python install is needed. This
   step takes a while because the AI features pull in PyTorch.

   ```bash
   cd geosetter-lite
   uv sync
   ```

4. Run the application:

   ```bash
   uv run python main.py
   ```

5. Optionally, build a double-clickable app and copy it to Applications:

   ```bash
   make package
   cp -R "dist/GeoSetter Lite.app" /Applications/
   ```

   The app is unsigned, so macOS may block it the first time it is opened. If
   that happens, right-click the app, choose **Open**, then **Open** again.

Notes:

- The first time Photo Similarity or Geolocation Prediction is used, the AI models
  are downloaded, so an internet connection is needed then.
- To update later, run `git pull && uv sync`. If you use the app bundle, also run
  `make package` again and copy the new app over the old one.

## Usage

### Launch with File Dialog

Simply run the application without arguments to open a file picker:

```bash
uv run python main.py
```

### Launch with Command-Line Argument

Provide a path to a folder:

```bash
uv run python main.py /path/to/your/images
```

## User Interface

### Main Window - 3-Pane Layout

The application features a flexible 3-pane layout with resizable borders:

- **Top-Left Panel**: Table showing all images with the following columns:
  - **Filename** (read-only, resizable) - Use File → Rename Photos for batch renaming
  - **Taken Date** (editable) - EXIF:DateTimeOriginal, XMP-exif:DateTimeOriginal
  - **TZ Offset** (editable) - Timezone offset with DST support (e.g., "+05:00")
  - **GPS Coordinates** (display only) - Latitude and Longitude
  - **City** (editable) - IPTC:City, XMP-photoshop:City
  - **Sublocation** (editable) - IPTC:Sub-location, XMP-iptcCore:Location
  - **Headline** (editable) - IPTC:Headline, XMP-photoshop:Headline
  - **Camera Model** (editable) - EXIF:Model
  - **Size** (read-only) - File size in KB/MB
  - **GPS Date** (editable, UTC) - EXIF:GPSDateStamp + GPSTimeStamp
  - **Country** (dropdown picker) - 3-letter ISO code with searchable country list
  - **Keywords** (editable) - Semicolon-separated display, auto-includes country info
  - **Created Date** (editable) - EXIF:CreateDate, XMP-exif:DateTimeDigitized (auto-set from Taken Date)

- **Bottom-Left Panel**: Image viewer showing the first selected image

- **Right Panel**: Interactive map with toolbar displaying:
  - **All Images**: Gray markers for all images with GPS coordinates
  - **Selected Images**: Blue markers for currently selected images
  - **Active Marker**: Red marker set by clicking on the map
  - **Marker Tooltips**: Click markers to see image thumbnails and filenames
  - **Toolbar Icons** (left to right):
    1. **Update GPS** (red pin → images): Update selected images with active marker coordinates
    2. **Set Marker** (image → red pin): Set active marker from selected image GPS coordinates
    3. **Reverse Geocoding** (toggle): Auto-determine country and city from GPS coordinates
    4. **Set Taken Date** (file → calendar): Initialize Taken Date from file creation date
    5. **Set GPS Date** (calendar → GPS): Initialize GPS Date from Taken Date (converted to UTC)
    6. **Repair Metadata** (medical cross): Fix/repair metadata using ExifTool
  - Leaflet-based map with a layer switcher (top right) offering three views:
    - **Satellite**: Esri World Imagery aerial photography
    - **Hybrid**: the same imagery with place names and boundaries drawn on top (default)
    - **Street**: OpenStreetMap tiles
  - The selected view is remembered between sessions
  - Any loaded KMZ/KML overlays appear in the same switcher and can be toggled individually
  - Before any geotagged image is loaded the map opens on Riyadh, Saudi Arabia;
    once images with GPS coordinates are present it fits to them instead
    (change `DEFAULT_CENTER_LAT` / `DEFAULT_CENTER_LON` / `DEFAULT_CENTER_ZOOM`
    in `geosetter_lite/ui/map_widget.py` to start somewhere else)
  - Scale control
  - Automatic zoom and centering based on markers
  - Smart bounds fitting for multiple markers

All three panes can be resized by dragging the borders between them.

### Interactions

**Image List:**
- **Left Click**: Select an image to view it in the bottom-left panel. Selected images are highlighted in blue on the map
- **Multi-Select**: Use Ctrl/Cmd + Click or Shift + Click to select multiple images. The first image will be displayed in the viewer
- **Right Click**: Open context menu with:
  - "Edit Metadata" - Opens full metadata editor dialog (works for single or multiple selections)
  - "Quick Edit (Basic Fields)" - Opens simplified batch editor for common fields (only appears when 2+ images selected)
  - "Remove GPS Coordinates" - After a confirmation, deletes all GPS data (coordinates, altitude, GPS date/time) from the EXIF and XMP metadata of the selected images; other metadata such as City and Country is kept
- **Double-Click Cell**:
  - Filename cell: Opens Edit Metadata dialog
  - other cells: Edit metadata directly in the table (country uses dropdown picker, dates use date picker)
- **Delete/Backspace**: Clear cell values (deletes corresponding metadata tags)
- **Rename Files**: Use File → Rename Photos for pattern-based batch renaming

**Map:**
- **Click on Map**: Set an active marker (red) at the clicked location. Map viewport (center and zoom) is preserved - no auto-fitting occurs
- **Click on Marker**: View popup with image thumbnail and filename
- **Select Image**: Centers map on selected image's marker, preserving current zoom level
- **Deselect All**: Fits map bounds to show all markers

**AI Tools Menu:**
- **Find Similar Photos**: Analyze all loaded images to find similar/duplicate photos
  - Progress dialog shows AI processing status
  - Results dialog displays groups of similar photos with thumbnails
  - Select photos for deletion with checkboxes
  - Batch delete similar photos with confirmation
- **Predict Locations**: Predict GPS coordinates for images without location data
  - Only processes images without GPS coordinates
  - Shows top 5 predictions per image with confidence scores
  - Displays location names via reverse geocoding
  - Select which predictions to apply
  - Batch GPS coordinate updates
- **Settings**: Configure AI feature parameters
  - Similarity threshold slider (0.0-1.0)
  - Model cache directory selection
  - Reset to defaults option

**Panes:**
- **Resize Panes**: Drag the borders between panes to adjust their sizes

### Metadata Editor

The metadata editor allows you to:
- View all EXIF/IPTC/XMP tags from the selected image(s) with namespace prefixes (e.g., XMP-iptcCore, XMP-photoshop)
- Edit existing metadata values
- Delete tags by selecting them and pressing Delete/Backspace or using right-click context menu
- Add new EXIF/IPTC/XMP tags using the "Add New Tag" button
- Apply changes to all selected images

When editing multiple images:
- The editor shows metadata from the first selected image
- Changes are applied to all selected images
- Empty values will not overwrite existing metadata

### Date/Time Management

The application handles multiple date fields with timezone awareness:

- **Taken Date**: When the photo was taken (local time at destination)
- **Created Date**: Auto-set from Taken Date if not present
- **GPS Date**: Always stored and displayed in UTC
- **TZ Offset**: Timezone offset with automatic DST handling

**Timezone Offset Behavior:**
- Select timezone from picker (shows zone ID, offset, and cities)
- Automatically calculates correct offset based on Taken Date (handles DST)
- Updates XMP date tags with timezone offset (e.g., "2024:11:26 10:30:00+05:00")
- Recalculates GPS Date to UTC when offset changes

### Keywords Management

Keywords are automatically managed:
- **Storage Format**: Asterisk-separated (`*`) in IPTC:Keywords and XMP-dc:Subject
- **Display Format**: Semicolon-separated (`;`) in table
- **Auto-Update**: When country is set, country code and country name are automatically added
- **Preservation**: Existing keywords are preserved when adding country information

## Dependencies

- **PySide6**: Qt-based GUI framework (includes QtWebEngineWidgets for map display)
- **Pillow**: Image loading, manipulation, and thumbnail generation
- **requests**: HTTP library for reverse geocoding API calls

**External Requirements:**
- **ExifTool**: Must be installed on your system for reading/writing EXIF/IPTC/XMP metadata
- **jpegtran**: Must be installed for JPEG lossless rotation

**External APIs:**
- **Esri World Imagery**: Satellite tiles for the Satellite/Hybrid views (no API key required)
- **OpenStreetMap**: Street map tiles (no API key required)
- **OpenStreetMap Nominatim**: Free reverse geocoding service (no API key required)

### Map Overlays (KMZ/KML)

Reference geometry can be drawn on the map beneath the photo markers - site
boundaries, networks, parcels and similar.

- **Bundled overlays**: every `.kmz`/`.kml` file in `data/overlays/` is loaded
  automatically the first time the app starts, so a fresh install already shows
  the team's site maps. Each bundled file is added once per user: clearing it is
  remembered, and a file dropped into `data/overlays/` later is picked up on the
  next start. A bundled file identical to one already loaded is not added twice
- **File -> Add Map Overlay (KMZ/KML)...** loads one or more files
- **File -> Clear Map Overlays** removes them all
- Each file appears as a toggle in the map's layer switcher (top right), and both
  the loaded files and their visibility are remembered between sessions
- **Overlay clicks** (a checkbox in the same switcher) controls whether overlay
  shapes respond to clicks:
  - **Off (default)**: clicks pass straight through the shapes to the map, so the
    active marker can be placed anywhere, including on top of a parcel
  - **On**: clicking a shape opens a popup with its name, source folder/layer and
    attributes, and the map does not receive the click
  - The setting is remembered between sessions
- Polygons, lines and points are each drawn in their native form, using the colours
  and line widths defined by the source file's KML styles

Source files are frequently far more detailed than a photo-location map needs, so
geometry is simplified on load (Ramer-Douglas-Peucker, ~2 m tolerance) and drawn on
an HTML canvas. For the sample datasets this removes about 95% of the vertices,
keeping thousands of shapes responsive; adjust `SIMPLIFY_TOLERANCE` in
`geosetter_lite/services/kmz_service.py` to trade detail against speed.

### Parcel Folders

Photo folders are commonly named for the parcel they document. When a folder is
opened, its name is matched against the features of the loaded overlays, and on a
match the map moves to that parcel - useful precisely when the photos have no
coordinates yet and there is nothing else for the map to fit to.

- Placemark names are checked first, then the attribute values parsed out of each
  placemark's description table, since exports differ in where they put the id
- Matching ignores case and surrounding whitespace, and tries the whole folder name
  before its individual words, so the most specific match wins:

  | Folder name | Result |
  | --- | --- |
  | `ANH-139-HF-100004` | matches that parcel |
  | `anh-139-hf-100004` | matches - case is ignored |
  | `ANH-139-HF-100004 - site photos` | matches - extra words are ignored |
  | `Site_ANH-139-HF-100005` | matches - the id is found as a word |
  | `Holiday photos` | no match, map behaves as before |

- A word only counts as a candidate id if it is at least 4 characters **and**
  contains a digit, so a folder called `Site photos` will not latch onto a parcel
  named `SITE`
- A matched parcel takes precedence over fitting the map to the photos, and the
  status bar reports it: `Loaded 47 images - map centred on parcel ANH-139-HF-100004`
- Parcels that are a single point rather than an area are framed at zoom
  `PARCEL_POINT_ZOOM` in `geosetter_lite/ui/map_widget.py`

This only considers overlays already loaded through **File -> Add Map Overlay**; it
does not search the folder for KMZ files.

### GPS Update Confirmation

**Update GPS** writes the active marker's coordinates to the selected photos
straight away, and reports the result in the status bar rather than a dialog.

To be asked to confirm first, enable **Ask for confirmation before updating GPS
coordinates** under Settings -> Map. Since coordinates are written without a prompt,
keep **Create backup files (`_original`)** enabled under Settings -> ExifTool if you
want an undo path.

## Metadata Tags Reference

The application writes to multiple metadata standards for maximum compatibility:

| Category | Field | Metadata Tags | Notes |
|----------|-------|---------------|-------|
| **Location** | Country | `XMP-photoshop:Country`<br>`IPTC:Country-PrimaryLocationName` | Country name |
| **Location** | Country Code | `XMP-iptcCore:CountryCode`<br>`IPTC:Country-PrimaryLocationCode` | 3-letter ISO 3166-1 alpha-3 |
| **Location** | City | `XMP-photoshop:City`<br>`IPTC:City` | City name |
| **Location** | Sublocation | `XMP-iptcCore:Location`<br>`IPTC:Sub-location` | Specific location within city |
| **GPS** | Coordinates | `EXIF:GPSLatitude`<br>`EXIF:GPSLongitude` | Decimal degrees |
| **GPS** | GPS Date/Time | `EXIF:GPSDateStamp`<br>`EXIF:GPSTimeStamp`<br>`XMP-exif:GPSDateTime` | UTC time |
| **GPS** | GPS DateTime (Composite) | `Composite:GPSDateTime` | Read-only, calculated by ExifTool |
| **Date/Time** | Taken Date | `EXIF:DateTimeOriginal`<br>`XMP-exif:DateTimeOriginal` | With timezone offset |
| **Date/Time** | Created Date | `EXIF:CreateDate`<br>`XMP-exif:DateTimeDigitized` | With timezone offset |
| **Date/Time** | Timezone Offset | `EXIF:TimeZoneOffset`<br>`EXIF:OffsetTime`<br>`EXIF:OffsetTimeOriginal`<br>`EXIF:OffsetTimeDigitized` | Decimal hours or "+HH:MM" format |
| **Other** | Headline | `IPTC:Headline`<br>`XMP-photoshop:Headline` | Image headline/title |
| **Other** | Keywords | `IPTC:Keywords`<br>`XMP-dc:Subject` | Asterisk-separated |
| **Other** | Camera Model | `EXIF:Model` | Camera make/model |

## Best Practices

### File Backup
- ExifTool creates backup files with `_original` suffix by default
- Backup files are automatically renamed when you rename the original file
- Original file creation dates are preserved; only modification dates change

### Timezone Handling
- Always set Taken Date first, then set TZ Offset
- TZ Offset automatically handles Daylight Saving Time based on Taken Date
- GPS Date is automatically recalculated to UTC when TZ Offset changes

### Keywords
- Keywords automatically include country code and country name when country is set
- Use semicolons (`;`) when editing keywords in the table
- Keywords are stored with asterisks (`*`) in metadata for compatibility

### Reverse Geocoding
- Enable reverse geocoding before updating GPS coordinates
- Review and edit the suggested country/city before applying
- Uses OpenStreetMap Nominatim API (respects usage policy with proper User-Agent)
- Has 10-second timeout to prevent hanging

### Batch Operations
- Select multiple images to apply changes to all at once
- Use Ctrl/Cmd+Click for non-contiguous selection
- Use Shift+Click for range selection
- **Edit Metadata**: Full metadata editor works with multiple images - changes apply to all selected
- **Quick Edit**: Right-click menu option for batch editing of common fields (TZ Offset, Country, City, Headline) when 2+ images are selected
- Empty values won't overwrite existing metadata

### AI Features
- **First Use**: Models will be downloaded automatically on first use (~1.2GB total)
- **Model Storage**: Models are cached in `~/.cache/geosetter_lite` by default (configurable in settings)
- **Location Database**: 
  - Source data: `data/world_locations.csv` (1000+ locations in CSV format)
  - SQLite database: `~/.cache/geosetter_lite/locations.db` (auto-created from CSV)
  - To add locations: Edit `world_locations.csv` directly (can use Excel, Google Sheets, or text editor)
  - To rebuild database: Delete `locations.db` and restart the app
  - Includes major cities, landmarks, natural features across all continents
  - CSV format: `latitude,longitude,description,country,city,category`
- **Memory Usage**: AI features use less than 4GB of RAM
- **Offline Operation**: After initial download, all AI features work offline
- **Similarity Threshold**: Start with 0.85 (85%) and adjust based on results
  - Higher values (0.90-0.95): Only very similar photos
  - Lower values (0.70-0.80): More groups, less strict matching
- **Geolocation Accuracy**: Predictions work best for photos with:
  - Recognizable landmarks or architecture
  - Distinct geographic features (mountains, coastlines, etc.)
  - Urban scenes with visible signs or buildings
  - May not work well for abstract or indoor photos

## Distribution

### Building packages

Build a distributable package of the application:

```bash
make package
```

This will create the following types of packages in the `dist/` directory:
- Python wheel
- macOS App Bundle *(via PyInstaller)*

The wheel includes:
- All source code from the `geosetter_lite` package
- Data files from the `data/` directory (world_locations.csv)
- Entry point script: `geosetter-lite`

The app bundle includes:
- All Python dependencies (PySide6, PyTorch, etc.)
- Data files (world_locations.csv)
- Self-contained Python runtime

### Installing from Wheel

```bash
# Install the wheel
pip install dist/geosetter_lite-<VERSION>-py3-none-any.whl

# Run the application
geosetter-lite /path/to/images
```

### macOS App Bundle

Run directly: Double-click `dist/GeoSetter Lite.app`

**Customizing the build**: Edit `geosetter_lite.spec` to:
- Include additional data files
- Configure hidden imports
- Adjust bundle settings

**Note**: The app requires ExifTool to be installed separately on the system (refer to the Requirements section).

## License

This project is licensed under the Apache License 2.0.

It is a derivative work of
[asaintsever/geosetter-lite](https://github.com/asaintsever/geosetter-lite), copyright
the original author and contributors, distributed under that same license. The full
license text is unmodified in [`LICENSE`](LICENSE) and applies to both the original
work and the modifications made here, which are listed in
[Changes from upstream](#changes-from-upstream).

### Third-Party Licenses

This project uses the following third-party libraries:

- **PySide6** (LGPL v3): Qt for Python - dynamically linked as a dependency
- **Pillow** (HPND License): Python Imaging Library
- **requests** (Apache 2.0): HTTP library
- **PyYAML** (MIT License): YAML parser and emitter
- **PyTorch** (BSD-style License): Deep learning framework
- **torchvision** (BSD License): Computer vision models and utilities
- **transformers** (Apache 2.0): Hugging Face transformers library
- **Leaflet** (BSD 2-Clause): JavaScript library for interactive maps (v1.9.4, bundled in `geosetter_lite/resources/leaflet/` and served through Qt resources)
- **OpenStreetMap** (ODbL): Street map tiles and data
- **Esri World Imagery**: Satellite tiles, used as a web service under the Esri terms of use (attribution required)
- **Nominatim** (GPL v2): Reverse geocoding service (used as web service, not linked)

The use of PySide6 under LGPL v3 is compatible with Apache 2.0 licensing as long as PySide6 remains dynamically linked (installed as a separate package), which is the case in this project.

## Acknowledgments

- **ExifTool** by Phil Harvey - Comprehensive metadata reading/writing tool
- **OpenStreetMap Contributors** - Street map data and tiles
- **Esri** - World Imagery satellite tiles
- **Nominatim** - Reverse geocoding service
- **Leaflet** - Interactive map library
- **PyTorch** - Deep learning framework
- **Hugging Face** - Pre-trained models (ResNet, CLIP)
- **OpenAI** - CLIP model architecture
# GeoSetterLiteGr
