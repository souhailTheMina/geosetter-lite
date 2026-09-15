"""
KMZ/KML overlay service - load vector overlays for display on the map

Reads KMZ (zipped KML) or plain KML files exported from GIS tools such as
ArcGIS, and converts them into a compact structure the map can render.

Source files are often far more detailed than a photo-location map needs: the
geometry is simplified with Ramer-Douglas-Peucker and coordinates are rounded,
which typically removes ~95% of the vertices while staying accurate to a few
metres. That keeps the map responsive, since the map document is regenerated
whenever the photo selection changes.
"""

import json
import math
import re
import zipfile
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

KML_NS = 'http://www.opengis.net/kml/2.2'
NS = {'k': KML_NS}

# Simplification tolerance in degrees (~2.2 m). Detail below this is invisible
# at the zoom levels used for photo geotagging.
SIMPLIFY_TOLERANCE = 0.00002

# Coordinate precision in decimal places (5 dp is a little over 1 m)
COORD_PRECISION = 5

# Cap on attribute rows kept for a feature's popup
MAX_POPUP_ATTRIBUTES = 12

# Styling fallbacks when the KML omits them
DEFAULT_COLOR = '#3388ff'
DEFAULT_WIDTH = 2.0


def _tag(name: str) -> str:
    """Fully qualified KML tag name"""
    return f'{{{KML_NS}}}{name}'


def _kml_color_to_css(kml_color: Optional[str]) -> Tuple[str, float]:
    """
    Convert a KML colour (aabbggrr, alpha first and channels reversed) into a
    CSS colour and an opacity.

    Returns (css_hex, opacity); falls back to the default colour when unset.
    """
    if not kml_color:
        return DEFAULT_COLOR, 1.0

    value = kml_color.strip().lower()
    if len(value) != 8:
        return DEFAULT_COLOR, 1.0

    try:
        alpha = int(value[0:2], 16) / 255.0
        blue = value[2:4]
        green = value[4:6]
        red = value[6:8]
    except ValueError:
        return DEFAULT_COLOR, 1.0

    return f'#{red}{green}{blue}', round(alpha, 3)


def _simplify(points: List[List[float]], tolerance: float) -> List[List[float]]:
    """
    Ramer-Douglas-Peucker simplification.

    Implemented iteratively: some source rings carry thousands of vertices,
    which would overflow the stack in a recursive version.
    """
    if tolerance <= 0 or len(points) < 3:
        return points

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue

        ax, ay = points[start]
        bx, by = points[end]
        dx, dy = bx - ax, by - ay
        segment_length = math.hypot(dx, dy)

        furthest_distance = -1.0
        furthest_index = -1
        for i in range(start + 1, end):
            px, py = points[i]
            if segment_length == 0:
                distance = math.hypot(px - ax, py - ay)
            else:
                distance = abs(dy * px - dx * py + bx * ay - by * ax) / segment_length
            if distance > furthest_distance:
                furthest_distance = distance
                furthest_index = i

        if furthest_distance > tolerance:
            keep[furthest_index] = True
            stack.append((start, furthest_index))
            stack.append((furthest_index, end))

    return [p for p, keep_point in zip(points, keep) if keep_point]


def _parse_coordinates(text: Optional[str], tolerance: float) -> List[List[float]]:
    """
    Parse a KML <coordinates> block into simplified [lat, lon] pairs.

    KML stores lon,lat[,alt]; Leaflet wants lat,lon, and altitude is dropped.
    """
    if not text:
        return []

    points = []
    for token in text.split():
        parts = token.split(',')
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue
        points.append([round(lat, COORD_PRECISION), round(lon, COORD_PRECISION)])

    return _simplify(points, tolerance)


# Matches the <td>key</td><td>value</td> rows of the attribute tables that
# ArcGIS writes into each placemark's description
_TD_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.S | re.I)
_TAG_RE = re.compile(r'<[^>]+>')
_NULL_VALUES = {'', '<null>', 'null', 'none'}


def _parse_description(description: Optional[str]) -> List[List[str]]:
    """
    Pull key/value attribute pairs out of a placemark description.

    The exported descriptions are whole HTML documents, mostly boilerplate; only
    the attribute rows are worth keeping for a popup.
    """
    if not description:
        return []

    cells = []
    for raw in _TD_RE.findall(description):
        text = unescape(_TAG_RE.sub('', raw)).strip()
        cells.append(text)

    attributes = []
    # Cells pair up as key, value; a lone leading title cell is skipped
    start = 1 if len(cells) % 2 else 0
    for i in range(start, len(cells) - 1, 2):
        key, value = cells[i], cells[i + 1]
        if not key or value.strip().lower() in _NULL_VALUES:
            continue
        attributes.append([key, value])
        if len(attributes) >= MAX_POPUP_ATTRIBUTES:
            break

    return attributes


def _collect_styles(root: ET.Element) -> Dict[str, dict]:
    """Read the document's <Style> definitions into a lookup by id"""
    styles: Dict[str, dict] = {}

    for style in root.iter(_tag('Style')):
        style_id = style.get('id')
        if not style_id:
            continue

        line_color = style.find('k:LineStyle/k:color', NS)
        line_width = style.find('k:LineStyle/k:width', NS)
        poly_color = style.find('k:PolyStyle/k:color', NS)
        poly_fill = style.find('k:PolyStyle/k:fill', NS)

        stroke, stroke_opacity = _kml_color_to_css(
            line_color.text if line_color is not None else None)
        fill, fill_opacity = _kml_color_to_css(
            poly_color.text if poly_color is not None else None)

        try:
            width = float(line_width.text) if line_width is not None else DEFAULT_WIDTH
        except (TypeError, ValueError):
            width = DEFAULT_WIDTH

        # An explicit <fill>0</fill> means outline only
        filled = not (poly_fill is not None and (poly_fill.text or '').strip() == '0')

        styles[style_id] = {
            'stroke': stroke,
            'strokeOpacity': stroke_opacity,
            'weight': width,
            'fill': fill,
            'fillOpacity': round(fill_opacity * 0.35, 3) if filled else 0.0,
        }

    return styles


def _read_kml_bytes(path: Path) -> bytes:
    """Return the KML document from a .kmz archive or a plain .kml file"""
    if path.suffix.lower() == '.kmz':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            # doc.kml is the conventional entry point; fall back to any .kml
            target = 'doc.kml' if 'doc.kml' in names else next(
                (n for n in names if n.lower().endswith('.kml')), None)
            if target is None:
                raise ValueError(f"No KML document inside {path.name}")
            return archive.read(target)

    return path.read_bytes()


def load_overlay(filepath: str, tolerance: float = SIMPLIFY_TOLERANCE) -> dict:
    """
    Load a KMZ/KML file into a compact overlay description.

    Args:
        filepath: Path to a .kmz or .kml file
        tolerance: Simplification tolerance in degrees

    Returns:
        dict with 'name', 'path' and 'features'. Each feature carries its
        geometry type ('polygon', 'line' or 'point'), coordinates, display
        name, source folder and style.

    Raises:
        FileNotFoundError, ValueError or zipfile.BadZipFile if unreadable
    """
    path = Path(filepath).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Overlay file not found: {path}")

    root = ET.fromstring(_read_kml_bytes(path))
    styles = _collect_styles(root)

    features: List[dict] = []

    def placemark_style(placemark: ET.Element) -> dict:
        style_url = placemark.find('k:styleUrl', NS)
        key = (style_url.text or '').lstrip('#') if style_url is not None else ''
        return styles.get(key, {
            'stroke': DEFAULT_COLOR,
            'strokeOpacity': 1.0,
            'weight': DEFAULT_WIDTH,
            'fill': DEFAULT_COLOR,
            'fillOpacity': 0.2,
        })

    def add_placemarks(container: ET.Element, folder_name: str):
        for placemark in container.iter(_tag('Placemark')):
            name_el = placemark.find('k:name', NS)
            name = (name_el.text or '').strip() if name_el is not None else ''
            desc_el = placemark.find('k:description', NS)
            attributes = _parse_description(desc_el.text if desc_el is not None else None)
            style = placemark_style(placemark)

            for polygon in placemark.iter(_tag('Polygon')):
                rings = []
                outer = polygon.find('.//k:outerBoundaryIs//k:coordinates', NS)
                if outer is not None:
                    ring = _parse_coordinates(outer.text, tolerance)
                    if len(ring) >= 3:
                        rings.append(ring)
                for inner in polygon.findall('.//k:innerBoundaryIs//k:coordinates', NS):
                    ring = _parse_coordinates(inner.text, tolerance)
                    if len(ring) >= 3:
                        rings.append(ring)
                if rings:
                    features.append({'t': 'polygon', 'g': rings, 'n': name,
                                     'f': folder_name, 'a': attributes, 's': style})

            for line in placemark.iter(_tag('LineString')):
                coords_el = line.find('k:coordinates', NS)
                points = _parse_coordinates(
                    coords_el.text if coords_el is not None else None, tolerance)
                if len(points) >= 2:
                    features.append({'t': 'line', 'g': points, 'n': name,
                                     'f': folder_name, 'a': attributes, 's': style})

            for point in placemark.iter(_tag('Point')):
                coords_el = point.find('k:coordinates', NS)
                points = _parse_coordinates(
                    coords_el.text if coords_el is not None else None, tolerance)
                if points:
                    features.append({'t': 'point', 'g': points[0], 'n': name,
                                     'f': folder_name, 'a': attributes, 's': style})

    folders = list(root.iter(_tag('Folder')))
    if folders:
        for folder in folders:
            folder_name_el = folder.find('k:name', NS)
            folder_name = (folder_name_el.text or '').strip() if folder_name_el is not None else ''
            add_placemarks(folder, folder_name)
    else:
        # Flat document with no folders
        document = root.find('k:Document', NS)
        add_placemarks(document if document is not None else root, '')

    doc_name_el = root.find('k:Document/k:name', NS)
    doc_name = (doc_name_el.text or '').strip() if doc_name_el is not None else ''
    # "Map" is ArcGIS's generic default; the filename is more recognisable
    if not doc_name or doc_name.lower() == 'map':
        doc_name = path.stem

    return {'name': doc_name, 'path': str(path), 'features': features}


def overlay_bounds(overlay: dict) -> Optional[Tuple[float, float, float, float]]:
    """Return (min_lat, min_lon, max_lat, max_lon) covering an overlay"""
    lats: List[float] = []
    lons: List[float] = []

    for feature in overlay.get('features', []):
        geometry = feature['g']
        if feature['t'] == 'point':
            lats.append(geometry[0])
            lons.append(geometry[1])
        elif feature['t'] == 'line':
            for lat, lon in geometry:
                lats.append(lat)
                lons.append(lon)
        else:
            for ring in geometry:
                for lat, lon in ring:
                    lats.append(lat)
                    lons.append(lon)

    if not lats:
        return None
    return (min(lats), min(lons), max(lats), max(lons))


def overlay_to_json(overlay: dict) -> str:
    """Serialise an overlay for embedding in the map document"""
    return json.dumps(overlay, ensure_ascii=False, separators=(',', ':'))
