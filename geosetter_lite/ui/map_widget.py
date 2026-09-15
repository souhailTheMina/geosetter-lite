"""
Map Widget - Display images on an OpenStreetMap using Leaflet
"""
from typing import List, Tuple, Optional
import json
import base64
from pathlib import Path
from urllib.parse import quote
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineScript, QWebEngineUrlRequestInterceptor, QWebEngineProfile
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, QObject, Signal, Slot
from PIL import Image
import io
from ..core.config import Config
from ..services import kmz_service

# Import Leaflet resources from Qt resource system
import geosetter_lite.resources.resources_rc #noqa: F401


# Constants for Leaflet resources
LEAFLET_RESOURCE_PATH = "qrc:///resources/leaflet/"
LEAFLET_CSS = f"{LEAFLET_RESOURCE_PATH}leaflet.css"
LEAFLET_JS = f"{LEAFLET_RESOURCE_PATH}leaflet.js"
LEAFLET_IMAGES_PATH = f"{LEAFLET_RESOURCE_PATH}images/"
LEAFLET_MARKER_ICON_URL = f"{LEAFLET_IMAGES_PATH}marker-icon.png"
LEAFLET_MARKER_ICON_RETINA_URL = f"{LEAFLET_IMAGES_PATH}marker-icon-2x.png"
LEAFLET_MARKER_SHADOW_URL = f"{LEAFLET_IMAGES_PATH}marker-shadow.png"
LEAFLET_MARKER_ICON_RED_URL = f"{LEAFLET_IMAGES_PATH}marker-icon-2x-red.png"

# User-Agent for OpenStreetMap compliance
# See https://operations.osmfoundation.org/policies/tiles/
OSM_USER_AGENT = b'GeoSetterLite/1.0 (+https://github.com/asaintsever/geosetter-lite)'

# Base layers offered by the map's layer switcher. OpenStreetMap serves no
# satellite imagery, so aerial views come from Esri World Imagery, which needs
# no API key. Attribution is required for both.
LAYER_SATELLITE = 'Satellite'
LAYER_HYBRID = 'Hybrid'
LAYER_STREET = 'Street'
MAP_LAYERS = (LAYER_SATELLITE, LAYER_HYBRID, LAYER_STREET)
DEFAULT_MAP_LAYER = LAYER_HYBRID

ESRI_IMAGERY_URL = ('https://server.arcgisonline.com/ArcGIS/rest/services/'
                    'World_Imagery/MapServer/tile/{z}/{y}/{x}')
ESRI_IMAGERY_ATTRIBUTION = ('Tiles &copy; Esri &mdash; Source: Esri, Maxar, '
                            'Earthstar Geographics, and the GIS User Community')

# Place names and boundaries, drawn over the imagery for the Hybrid layer
ESRI_LABELS_URL = ('https://server.arcgisonline.com/ArcGIS/rest/services/'
                   'Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}')
ESRI_LABELS_ATTRIBUTION = 'Labels &copy; Esri'

OSM_TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
OSM_ATTRIBUTION = ('&copy; <a href="https://www.openstreetmap.org/copyright">'
                   'OpenStreetMap</a> contributors')

MAX_TILE_ZOOM = 19

# Pseudo-overlay in the layer switcher that turns overlay click handling on and
# off. Off by default, so clicks fall through to the map and place the active
# marker even where overlay shapes cover it.
OVERLAY_CLICKS_LAYER_NAME = 'Overlay clicks'

# Where the map opens before any geotagged image is loaded (Riyadh, Saudi Arabia).
# Once images with GPS coordinates are present the map fits to them instead.
DEFAULT_CENTER_LAT = 24.7136
DEFAULT_CENTER_LON = 46.6753
DEFAULT_CENTER_ZOOM = 11

# Leaflet draws the layer-control toggle with images/layers.png, which is not
# among the bundled resources. Supply the icon inline instead of shipping a PNG.
_LAYERS_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="#333333" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<polygon points="12 2 2 7 12 12 22 7 12 2"/>'
    '<polyline points="2 17 12 22 22 17"/>'
    '<polyline points="2 12 12 17 22 12"/>'
    '</svg>'
)
LAYERS_ICON_DATA_URI = "data:image/svg+xml;charset=UTF-8," + quote(_LAYERS_ICON_SVG, safe="")


class OSMUserAgentInterceptor(QWebEngineUrlRequestInterceptor):
    """Intercepts web requests to set User-Agent header for OpenStreetMap compliance"""
    
    def interceptRequest(self, info):
        """Set User-Agent header for OpenStreetMap tile requests"""
        url = info.requestUrl().toString()
        if 'openstreetmap.org' in url:
            info.setHttpHeader(b'User-Agent', OSM_USER_AGENT)


def _wrap_longitude(lon: float) -> float:
    """Wraps longitude to the range [-180, 180] degrees."""
    # Formula: (lon + 180) % 360 - 180
    # For a lon of 190: (190 + 180) % 360 - 180 = 370 % 360 - 180 = 10 - 180 = -170
    # For a lon of -190: (-190 + 180) % 360 - 180 = -10 % 360 - 180 = 350 - 180 = 170
    return (lon + 180) % 360 - 180


class MapClickHandler(QObject):
    """Handler for map events raised from JavaScript"""
    
    clicked = Signal(float, float)  # latitude, longitude
    layer_changed = Signal(str)     # name of the newly selected base layer
    overlay_toggled = Signal(str, bool)  # overlay name, visible
    
    @Slot(float, float)
    def onMapClick(self, lat: float, lng: float):
        """Handle map click from JavaScript"""
        self.clicked.emit(lat, _wrap_longitude(lng))
    
    @Slot(str)
    def onLayerChange(self, layer_name: str):
        """Handle base layer selection from JavaScript"""
        self.layer_changed.emit(layer_name)
    
    @Slot(str, bool)
    def onOverlayToggle(self, overlay_name: str, visible: bool):
        """Handle an overlay being shown or hidden from JavaScript"""
        self.overlay_toggled.emit(overlay_name, visible)


class MapWidget(QWidget):
    """Widget for displaying a map with image markers"""
    
    # Signal emitted when map is clicked
    map_clicked = Signal(float, float)
    
    def __init__(self, parent=None):
        """Initialize the map widget"""
        super().__init__(parent)
        
        # Store markers with unique IDs: Dict[str, Tuple[float, float, str, bool, Optional[str]]]
        # Key is marker_id, value is (lat, lon, name, is_selected, filepath)
        self.markers: dict = {}  
        self.active_marker: Optional[Tuple[float, float]] = None
        self.click_handler = MapClickHandler()
        self.click_handler.clicked.connect(self._on_map_clicked)
        self.click_handler.layer_changed.connect(self._on_layer_changed)
        self.click_handler.overlay_toggled.connect(self._on_overlay_toggled)
        
        # Selected base layer. The map HTML is regenerated whenever markers or
        # the selection change, so this has to be remembered on the Python side
        # or the user's choice would be lost on the next reload.
        self.current_layer: str = Config.get_app_settings().get(
            'map_layer', DEFAULT_MAP_LAYER)
        if self.current_layer not in MAP_LAYERS:
            self.current_layer = DEFAULT_MAP_LAYER
        
        # KMZ/KML overlays. Parsing is slow enough to be worth doing once, and
        # the serialised form is reused every time the map document is rebuilt.
        self._overlay_cache: Optional[List[str]] = None
        self._overlay_errors: List[str] = []
        self.auto_fit_bounds: bool = True  # Auto-fit on initial load
        self.has_had_markers: bool = False  # Track if markers have been set before
        
        # Track last calculated viewport to reuse when not auto-fitting
        self.last_center_lat: float = DEFAULT_CENTER_LAT
        self.last_center_lon: float = DEFAULT_CENTER_LON
        self.last_zoom: int = DEFAULT_CENTER_ZOOM
        
        # For handling async viewport capture before reload
        self.pending_reload: bool = False
        self.preserve_viewport_completely: bool = False  # Set when map click, don't recenter
        self.skip_viewport_capture: bool = False  # Skip capture when fitting to selected markers
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create web view for displaying the map
        self.web_view = QWebEngineView()
        
        # Set up custom URL request interceptor to set User-Agent for OSM compliance
        self.interceptor = OSMUserAgentInterceptor()
        self.web_view.page().profile().setUrlRequestInterceptor(self.interceptor)
        
        # Set up web channel for JavaScript communication
        self.channel = QWebChannel()
        self.channel.registerObject("clickHandler", self.click_handler)
        self.web_view.page().setWebChannel(self.channel)
        
        # Overlays are pushed in after each load rather than embedded in the
        # document, so they have to be re-applied on every reload
        self.web_view.loadFinished.connect(self._on_map_load_finished)
        
        layout.addWidget(self.web_view)
        
        self.setLayout(layout)
        
        # Load initial map
        self.load_map()
    
    # ------------------------------------------------------------------
    # KMZ/KML overlays
    # ------------------------------------------------------------------
    
    def _on_overlay_toggled(self, overlay_name: str, visible: bool):
        """Remember which overlays the user has switched on"""
        app_settings = Config.get_app_settings()
        
        # Not a real overlay: this one controls whether overlay shapes are
        # clickable at all
        if overlay_name == OVERLAY_CLICKS_LAYER_NAME:
            if app_settings.get('map_overlay_clicks', False) != visible:
                app_settings['map_overlay_clicks'] = visible
                Config.set_app_settings(app_settings)
            return
        
        hidden = list(app_settings.get('map_overlays_hidden', []))
        
        if visible and overlay_name in hidden:
            hidden.remove(overlay_name)
        elif not visible and overlay_name not in hidden:
            hidden.append(overlay_name)
        else:
            return
        
        app_settings['map_overlays_hidden'] = hidden
        Config.set_app_settings(app_settings)
    
    def set_overlay_files(self, paths: List[str]):
        """
        Replace the set of KMZ/KML overlay files and redraw the map.
        
        Args:
            paths: Overlay file paths to display
        """
        app_settings = Config.get_app_settings()
        app_settings['map_overlays'] = list(paths)
        Config.set_app_settings(app_settings)
        
        self._overlay_cache = None  # Force a re-parse on the next draw
        self.reload_map()
    
    def get_overlay_files(self) -> List[str]:
        """Return the configured overlay file paths"""
        return list(Config.get_app_settings().get('map_overlays', []))
    
    def get_overlay_errors(self) -> List[str]:
        """Return messages for overlay files that failed to load"""
        return list(self._overlay_errors)
    
    def reload_map(self):
        """Rebuild the map document from scratch"""
        self.pending_reload = False
        self.skip_viewport_capture = False
        self._do_load_map()
    
    def _on_map_load_finished(self, ok: bool):
        """Draw the KMZ/KML overlays onto a freshly loaded map document"""
        if not ok:
            return
        
        for statement in self._build_overlay_js():
            self.web_view.page().runJavaScript(statement)
    
    def _build_overlay_js(self) -> List[str]:
        """
        Parse the configured overlay files and build the JavaScript that draws
        them. The result is cached, since parsing large KMZ files is slow and
        the map document is rebuilt whenever the marker set changes.
        """
        if self._overlay_cache is not None:
            return self._overlay_cache
        
        self._overlay_errors = []
        paths = self.get_overlay_files()
        if not paths:
            self._overlay_cache = []
            return self._overlay_cache
        
        hidden = set(Config.get_app_settings().get('map_overlays_hidden', []))
        statements = []
        
        for path in paths:
            try:
                overlay = kmz_service.load_overlay(path)
            except Exception as e:
                message = f"{Path(path).name}: {e}"
                print(f"Error loading overlay {path}: {e}")
                self._overlay_errors.append(message)
                continue
            
            if not overlay['features']:
                self._overlay_errors.append(f"{Path(path).name}: no drawable features")
                continue
            
            payload = kmz_service.overlay_to_json(overlay)
            # Stop any "</script>" inside feature text from ending the script
            payload = payload.replace("</", "<\\/")
            visible = 'false' if overlay['name'] in hidden else 'true'
            statements.append(
                f"if (window.gslAddOverlay) {{ window.gslAddOverlay({payload}, {visible}); }}")
        
        self._overlay_cache = statements
        return self._overlay_cache
    
    def _on_layer_changed(self, layer_name: str):
        """Remember the base layer the user picked, across reloads and restarts"""
        if layer_name not in MAP_LAYERS or layer_name == self.current_layer:
            return
        
        self.current_layer = layer_name
        app_settings = Config.get_app_settings()
        app_settings['map_layer'] = layer_name
        Config.set_app_settings(app_settings)
    
    def _on_map_clicked(self, lat: float, lng: float):
        """Handle map click event"""
        self.active_marker = (lat, lng)
        self.auto_fit_bounds = False  # User is interacting, don't auto-fit
        self.map_clicked.emit(lat, lng)
        # Update active marker via JavaScript without reloading map
        self._update_active_marker_js(lat, lng)
    
    def load_map(self):
        """Load the OpenStreetMap with Leaflet"""
        # If not auto-fitting, capture current viewport first to preserve user's zoom/pan
        # Skip capture if we're fitting to selected markers
        if not self.auto_fit_bounds and not self.pending_reload and not self.skip_viewport_capture:
            self.pending_reload = True
            self._capture_viewport_then_reload()
        else:
            self.skip_viewport_capture = False  # Reset flag
            self._do_load_map()
    
    def _do_load_map(self):
        """Actually load the map HTML"""
        self.pending_reload = False
        html = self._generate_map_html()
        self.web_view.setHtml(html)
    
    def _generate_map_html(self) -> str:
        """
        Generate HTML for the map with Leaflet
        
        Returns:
            HTML string with embedded Leaflet map
        """
        # Define icon creation JavaScript (done once)
        icon_definitions = f"""
            // Create custom icons
            var blueIcon = L.icon({{
                iconUrl: '{LEAFLET_MARKER_ICON_URL}',
                iconRetinaUrl: '{LEAFLET_MARKER_ICON_RETINA_URL}',
                shadowUrl: '{LEAFLET_MARKER_SHADOW_URL}',
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                popupAnchor: [1, -34],
                shadowSize: [41, 41],
                className: 'blue-marker'
            }});
            
            var greyIcon = L.icon({{
                iconUrl: '{LEAFLET_MARKER_ICON_URL}',
                iconRetinaUrl: '{LEAFLET_MARKER_ICON_RETINA_URL}',
                shadowUrl: '{LEAFLET_MARKER_SHADOW_URL}',
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                popupAnchor: [1, -34],
                shadowSize: [41, 41],
                className: 'grey-marker'
            }});
        """
        
        # Generate markers JavaScript
        markers_js = icon_definitions
        markers_js += """
            // Store markers in a global object for later reference
            window.imageMarkers = window.imageMarkers || {};
        """
        
        # Add regular image markers
        if self.markers:
            for marker_id, (lat, lon, name, is_selected, filepath) in self.markers.items():
                # Generate popup content with thumbnail
                popup_html = self._generate_popup_html(name, filepath)
                escaped_popup = json.dumps(popup_html)
                
                # Use different icons for selected vs unselected
                icon_var = 'blueIcon' if is_selected else 'greyIcon'
                escaped_id = json.dumps(marker_id)
                markers_js += f"""
                window.imageMarkers[{escaped_id}] = L.marker([{lat}, {lon}], {{icon: {icon_var}}}).addTo(map).bindPopup({escaped_popup});
                """
        
        # Add active marker if set
        if self.active_marker:
            lat, lon = self.active_marker
            markers_js += f"""
            var redIcon = L.icon({{
                iconUrl: '{LEAFLET_MARKER_ICON_RED_URL}',
                shadowUrl: '{LEAFLET_MARKER_SHADOW_URL}',
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                popupAnchor: [1, -34],
                shadowSize: [41, 41]
            }});
            var activeMarker = L.marker([{lat}, {lon}], {{icon: redIcon, draggable: true}}).addTo(map).bindPopup('Active Marker');
            
            // Handle marker drag end event
            activeMarker.on('dragend', function(e) {{
                var latlng = e.target.getLatLng();
                if (clickHandler) {{
                    clickHandler.onMapClick(latlng.lat, latlng.lng);
                }}
            }});
            
            // Store in window for later reference
            window.activeMarker = activeMarker;
            """
        
        # Calculate center and zoom
        all_coords = []
        if self.markers:
            all_coords.extend([(m[0], m[1]) for m in self.markers.values()])
        if self.active_marker:
            all_coords.append(self.active_marker)
        
        # Check if we have selected markers
        selected_coords = [(m[0], m[1]) for m in self.markers.values() if m[3]]  # m[3] is is_selected
        
        # Determine viewport based on auto_fit_bounds setting
        if not self.auto_fit_bounds:
            # User is interacting - preserve zoom and optionally center
            zoom = self.last_zoom
            
            if self.preserve_viewport_completely:
                # Map click - preserve viewport exactly as is
                center_lat = self.last_center_lat
                center_lon = self.last_center_lon
                self.preserve_viewport_completely = False  # Reset flag
            else:
                # Selection change - center on selected markers
                if selected_coords:
                    # Center on selected image(s)
                    if len(selected_coords) == 1:
                        center_lat, center_lon = selected_coords[0]
                    else:
                        # Multiple selected - center on their average
                        lats = [c[0] for c in selected_coords]
                        lons = [c[1] for c in selected_coords]
                        center_lat = sum(lats) / len(lats)
                        center_lon = sum(lons) / len(lons)
                else:
                    # No selection with geolocation - preserve viewport
                    center_lat = self.last_center_lat
                    center_lon = self.last_center_lon
        elif all_coords:
            # Auto-fit mode - calculate new viewport
            if len(all_coords) == 1:
                center_lat, center_lon = all_coords[0]
                zoom = 13
            else:
                lats = [c[0] for c in all_coords]
                lons = [c[1] for c in all_coords]
                center_lat = sum(lats) / len(lats)
                center_lon = sum(lons) / len(lons)
                zoom = 10
            # Store for future use
            self.last_center_lat = center_lat
            self.last_center_lon = center_lon
            self.last_zoom = zoom
        else:
            # No markers - keep where the user was, otherwise open at the default location
            if self.has_had_markers:
                # Use stored viewport
                center_lat = self.last_center_lat
                center_lon = self.last_center_lon
                zoom = self.last_zoom
            else:
                # Default to the configured starting location
                center_lat = DEFAULT_CENTER_LAT
                center_lon = DEFAULT_CENTER_LON
                zoom = DEFAULT_CENTER_ZOOM
                self.last_center_lat = center_lat
                self.last_center_lon = center_lon
                self.last_zoom = zoom
        
        # Generate fit bounds JS if needed
        # Fit bounds when auto_fit is enabled OR when there are selected markers with geolocation
        if self.auto_fit_bounds:
            fit_bounds_js = self._generate_fit_bounds_js()
        elif selected_coords:
            # Even when not auto-fitting, fit to selected markers to ensure they're visible
            fit_bounds_js = self._generate_fit_bounds_js(selected_only=True)
        else:
            # No fit bounds - preserves viewport (e.g., when selecting photos without geolocation)
            fit_bounds_js = ""
        
        # Tile source values referenced by the map template below
        esri_imagery_url = ESRI_IMAGERY_URL
        esri_imagery_attribution = ESRI_IMAGERY_ATTRIBUTION
        esri_labels_url = ESRI_LABELS_URL
        esri_labels_attribution = ESRI_LABELS_ATTRIBUTION
        osm_tile_url = OSM_TILE_URL
        osm_attribution = OSM_ATTRIBUTION
        max_zoom = MAX_TILE_ZOOM
        layer_satellite = LAYER_SATELLITE
        layer_hybrid = LAYER_HYBRID
        layer_street = LAYER_STREET
        current_layer = self.current_layer
        layers_icon = LAYERS_ICON_DATA_URI
        overlay_clicks_name = OVERLAY_CLICKS_LAYER_NAME
        overlay_clicks_enabled = 'true' if Config.get_app_settings().get(
            'map_overlay_clicks', False) else 'false'

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Image Map</title>
            
            <!-- Leaflet CSS -->
            <link rel="stylesheet" href="{LEAFLET_CSS}"/>
            
            <!-- Leaflet JavaScript -->
            <script src="{LEAFLET_JS}"></script>
            
            <!-- Qt WebChannel -->
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                }}
                #map {{
                    width: 100%;
                    height: 100vh;
                }}
                /* Bundled Leaflet resources have no layers.png/layers-2x.png */
                .leaflet-control-layers-toggle,
                .leaflet-retina .leaflet-control-layers-toggle {{
                    background-image: url("{layers_icon}");
                    background-size: 20px 20px;
                    background-position: center;
                    background-repeat: no-repeat;
                    width: 30px;
                    height: 30px;
                }}
                .leaflet-control-compass {{
                    background: white;
                    padding: 5px;
                    border-radius: 4px;
                    box-shadow: 0 1px 5px rgba(0,0,0,0.4);
                }}
                /* Style for grey (unselected) markers */
                .grey-marker {{
                    filter: grayscale(100%) brightness(0.7);
                    opacity: 0.6;
                }}
                /* Style for blue (selected) markers - keep default appearance */
                .blue-marker {{
                    /* Default Leaflet blue marker */
                }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            
            <script>
                var clickHandler;
                
                // Set up Qt WebChannel
                new QWebChannel(qt.webChannelTransport, function(channel) {{
                    clickHandler = channel.objects.clickHandler;
                }});
                
                // Initialize the map (use window.map for global access)
                window.map = L.map('map', {{
                    maxBounds: [[-90, -180], [90, 180]]
                }}).setView([{center_lat}, {center_lon}], {zoom});
                var map = window.map;  // Keep local reference for convenience
                
                // Build the selectable base layers. Each needs its own tile
                // layer instance, since Leaflet adds and removes them as the
                // user switches between views.
                function imageryTiles() {{
                    return L.tileLayer('{esri_imagery_url}', {{
                        attribution: '{esri_imagery_attribution}',
                        maxZoom: {max_zoom}
                    }});
                }}
                
                var baseLayers = {{}};
                baseLayers['{layer_satellite}'] = imageryTiles();
                baseLayers['{layer_hybrid}'] = L.layerGroup([
                    imageryTiles(),
                    L.tileLayer('{esri_labels_url}', {{
                        attribution: '{esri_labels_attribution}',
                        maxZoom: {max_zoom}
                    }})
                ]);
                baseLayers['{layer_street}'] = L.tileLayer('{osm_tile_url}', {{
                    attribution: '{osm_attribution}',
                    maxZoom: {max_zoom}
                }});
                
                // Restore the layer the user last selected
                baseLayers['{current_layer}'].addTo(map);
                
                // ---- KMZ/KML overlays ----------------------------------
                // Thousands of shapes render far faster on canvas than as
                // individual SVG elements.
                window.overlayClicksEnabled = {overlay_clicks_enabled};
                
                // Set while the code adds or removes overlays itself, so those
                // events are not mistaken for the user ticking a checkbox
                window.__gslProgrammaticOverlay = false;
                var overlayRenderer = L.canvas({{padding: 0.3}});
                var overlayLayers = {{}};
                
                function gslEscape(text) {{
                    return String(text === null || text === undefined ? '' : text)
                        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
                }}
                
                // Built on demand: pre-rendering popups for every feature would
                // multiply the size of this document.
                function gslOverlayPopup(feature) {{
                    return function() {{
                        var html = '<div style="max-height:220px;overflow:auto;font-size:12px;">';
                        html += '<div style="font-weight:bold;margin-bottom:2px;">'
                             + gslEscape(feature.n || '(unnamed)') + '</div>';
                        if (feature.f) {{
                            html += '<div style="color:#777;margin-bottom:6px;">'
                                 + gslEscape(feature.f) + '</div>';
                        }}
                        if (feature.a && feature.a.length) {{
                            html += '<table style="border-collapse:collapse;">';
                            for (var i = 0; i < feature.a.length; i++) {{
                                html += '<tr><td style="padding:1px 8px 1px 0;color:#777;'
                                     + 'vertical-align:top;">' + gslEscape(feature.a[i][0])
                                     + '</td><td style="padding:1px 0;">'
                                     + gslEscape(feature.a[i][1]) + '</td></tr>';
                            }}
                            html += '</table>';
                        }}
                        return html + '</div>';
                    }};
                }}
                
                function gslAddOverlay(data, visible) {{
                    window.__gslProgrammaticOverlay = true;
                    try {{
                        gslBuildOverlay(data, visible);
                    }} finally {{
                        window.__gslProgrammaticOverlay = false;
                    }}
                }}
                
                function gslBuildOverlay(data, visible) {{
                    var group = L.layerGroup();
                    
                    for (var i = 0; i < data.features.length; i++) {{
                        var feature = data.features[i];
                        var style = feature.s;
                        var options = {{
                            renderer: overlayRenderer,
                            interactive: window.overlayClicksEnabled,
                            color: style.stroke,
                            weight: style.weight,
                            opacity: style.strokeOpacity,
                            fillColor: style.fill,
                            fillOpacity: style.fillOpacity
                        }};
                        var shape;
                        
                        if (feature.t === 'polygon') {{
                            shape = L.polygon(feature.g, options);
                        }} else if (feature.t === 'line') {{
                            shape = L.polyline(feature.g, options);
                        }} else {{
                            // Points have no meaningful fill in the source style
                            options.radius = 5;
                            options.fillColor = style.stroke;
                            options.fillOpacity = 0.9;
                            shape = L.circleMarker(feature.g, options);
                        }}
                        
                        shape.bindPopup(gslOverlayPopup(feature));
                        
                        // Belt and braces: if the renderer still hit-tests this
                        // shape while clicks are meant to pass through, hand the
                        // position to the map so the active marker still moves.
                        shape.on('click', function(e) {{
                            if (!window.overlayClicksEnabled) {{
                                this.closePopup();
                                if (clickHandler && e.latlng) {{
                                    clickHandler.onMapClick(e.latlng.lat, e.latlng.lng);
                                }}
                            }}
                        }});
                        
                        group.addLayer(shape);
                    }}
                    
                    // Replace rather than stack, so a re-injection cannot
                    // leave duplicate rows in the layer control
                    var previous = overlayLayers[data.name];
                    if (previous) {{
                        map.removeLayer(previous);
                        if (window.layerControl) {{
                            window.layerControl.removeLayer(previous);
                        }}
                    }}
                    
                    overlayLayers[data.name] = group;
                    if (visible) {{
                        group.addTo(map);
                    }}
                    if (window.layerControl) {{
                        window.layerControl.addOverlay(group, data.name);
                    }}
                }}
                window.gslAddOverlay = gslAddOverlay;
                
                // Switch hit-testing on every overlay shape already drawn
                function gslApplyOverlayInteractivity() {{
                    var enabled = window.overlayClicksEnabled;
                    Object.keys(overlayLayers).forEach(function(name) {{
                        overlayLayers[name].eachLayer(function(shape) {{
                            shape.options.interactive = enabled;
                        }});
                    }});
                    // Dismiss anything left open from inspection mode
                    if (!enabled) {{ map.closePopup(); }}
                }}
                window.gslApplyOverlayInteractivity = gslApplyOverlayInteractivity;
                
                // Overlays are injected after load rather than embedded:
                // QWebEnginePage.setHtml() silently refuses documents over 2 MB,
                // and a single KMZ can exceed that on its own.
                window.layerControl = L.control.layers(baseLayers, null, {{
                    position: 'topright',
                    collapsed: true
                }}).addTo(map);
                
                // An empty layer group, used purely so the layer switcher shows
                // a checkbox for overlay click handling alongside the overlays.
                var overlayClicksToggle = L.layerGroup();
                window.layerControl.addOverlay(
                    overlayClicksToggle, '{overlay_clicks_name}');
                if (window.overlayClicksEnabled) {{
                    window.__gslProgrammaticOverlay = true;
                    overlayClicksToggle.addTo(map);
                    window.__gslProgrammaticOverlay = false;
                }}
                
                // Report overlay visibility so it survives the next reload
                map.on('overlayadd', function(e) {{
                    if (window.__gslProgrammaticOverlay) {{ return; }}
                    if (e.name === '{overlay_clicks_name}') {{
                        window.overlayClicksEnabled = true;
                        gslApplyOverlayInteractivity();
                    }}
                    if (clickHandler) {{ clickHandler.onOverlayToggle(e.name, true); }}
                }});
                map.on('overlayremove', function(e) {{
                    if (window.__gslProgrammaticOverlay) {{ return; }}
                    if (e.name === '{overlay_clicks_name}') {{
                        window.overlayClicksEnabled = false;
                        gslApplyOverlayInteractivity();
                    }}
                    if (clickHandler) {{ clickHandler.onOverlayToggle(e.name, false); }}
                }});
                
                // Report layer changes so the choice survives the next reload
                map.on('baselayerchange', function(e) {{
                    if (clickHandler) {{
                        clickHandler.onLayerChange(e.name);
                    }}
                }});
                
                // Add compass/scale control
                L.control.scale({{
                    position: 'bottomright',
                    imperial: false
                }}).addTo(map);
                
                // Handle map clicks
                map.on('click', function(e) {{
                    if (clickHandler) {{
                        clickHandler.onMapClick(e.latlng.lat, e.latlng.lng);
                    }}
                }});
                
                // Add markers
                {markers_js}
                
                // Fit bounds if multiple markers (only on initial load or no selection)
                {fit_bounds_js}
            </script>
        </body>
        </html>
        """
        
        return html
    
    def _update_active_marker_js(self, lat: float, lon: float):
        """Update active marker via JavaScript without reloading map"""
        js = f"""
        (function() {{
            if (!window.map) return;
            
            // Remove existing active marker if any
            if (window.activeMarker) {{
                window.map.removeLayer(window.activeMarker);
            }}
            
            // Create red icon for active marker
            var redIcon = L.icon({{
                iconUrl: '{LEAFLET_MARKER_ICON_RED_URL}',
                shadowUrl: '{LEAFLET_MARKER_SHADOW_URL}',
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                popupAnchor: [1, -34],
                shadowSize: [41, 41]
            }});
            
            // Add new active marker with draggable option
            window.activeMarker = L.marker([{lat}, {lon}], {{icon: redIcon, draggable: true}}).addTo(window.map).bindPopup('Active Marker');
            
            // Handle marker drag end event
            window.activeMarker.on('dragend', function(e) {{
                var latlng = e.target.getLatLng();
                if (clickHandler) {{
                    clickHandler.onMapClick(latlng.lat, latlng.lng);
                }}
            }});
        }})();
        """
        self.web_view.page().runJavaScript(js)
    
    def _capture_viewport_then_reload(self):
        """Capture current map viewport then reload"""
        js = """
        (function() {
            if (window.map) {
                var center = window.map.getCenter();
                var zoom = window.map.getZoom();
                return [center.lat, center.lng, zoom];
            }
            return null;
        })();
        """
        self.web_view.page().runJavaScript(js, self._on_viewport_captured)
    
    def _on_viewport_captured(self, result):
        """Callback when viewport is captured - update and reload"""
        if result and len(result) == 3:
            self.last_center_lat = result[0]
            self.last_center_lon = result[1]
            self.last_zoom = int(result[2])
            self._do_load_map()
        else:
            # Failed to capture viewport - skip reload to preserve current view
            self.pending_reload = False
    
    def _generate_fit_bounds_js(self, selected_only: bool = False) -> str:
        """
        Generate JavaScript to fit map bounds to markers
        
        Args:
            selected_only: If True, only fit to selected markers; otherwise fit to all markers
        """
        coords_to_fit = []
        
        if selected_only:
            # Only include selected markers
            coords_to_fit = [(m[0], m[1]) for m in self.markers.values() if m[3]]  # m[3] is is_selected
        else:
            # Include all markers and active marker
            if self.markers:
                coords_to_fit.extend([(m[0], m[1]) for m in self.markers.values()])
            if self.active_marker:
                coords_to_fit.append(self.active_marker)
        
        if len(coords_to_fit) > 1:
            lats = [c[0] for c in coords_to_fit]
            lons = [c[1] for c in coords_to_fit]
            
            min_lat, max_lat = min(lats), max(lats)
            min_lon, max_lon = min(lons), max(lons)
            
            return f"""
                var bounds = [[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]];
                map.fitBounds(bounds, {{padding: [50, 50]}});
            """
        return ""
    
    def _generate_thumbnail(self, filepath: Optional[str], max_size: int = 150) -> Optional[str]:
        """
        Generate a base64-encoded thumbnail for an image
        
        Args:
            filepath: Path to the image file
            max_size: Maximum width/height for the thumbnail
            
        Returns:
            Base64-encoded image data URL or None if generation fails
        """
        if not filepath:
            return None
        
        try:
            path = Path(filepath)
            if not path.exists():
                return None
            
            # Open and resize image
            with Image.open(path) as img:
                # Convert to RGB if necessary (for PNG with transparency, etc.)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Calculate thumbnail size maintaining aspect ratio
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Save to bytes
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                buffer.seek(0)
                
                # Encode to base64
                img_data = base64.b64encode(buffer.read()).decode('utf-8')
                return f"data:image/jpeg;base64,{img_data}"
        
        except Exception as e:
            print(f"Error generating thumbnail for {filepath}: {e}")
            return None
    
    def _generate_popup_html(self, filename: str, filepath: Optional[str]) -> str:
        """
        Generate HTML content for marker popup with thumbnail
        
        Args:
            filename: Name of the image file
            filepath: Path to the image file
            
        Returns:
            HTML string for the popup
        """
        thumbnail_data = self._generate_thumbnail(filepath)
        
        if thumbnail_data:
            return f"""
                <div style="text-align: center; min-width: 150px;">
                    <img src="{thumbnail_data}" style="max-width: 150px; max-height: 150px; display: block; margin: 0 auto 8px auto; border-radius: 4px;">
                    <div style="font-weight: bold; word-wrap: break-word;">{filename}</div>
                </div>
            """
        else:
            # Fallback to just filename if thumbnail generation fails
            return f"""
                <div style="text-align: center; font-weight: bold;">
                    {filename}
                </div>
            """
    
    def update_markers(self, markers: List[Tuple[float, float, str, bool, Optional[str]]], has_active_selection: bool = False):
        """
        Update map markers - used when the actual marker set changes (add/remove markers)
        
        Args:
            markers: List of tuples (latitude, longitude, name, is_selected, filepath)
            has_active_selection: True if user has selected photos (even without geolocation)
        """
        # Convert markers list to dict with unique IDs based on coordinates and name
        new_markers = {}
        for lat, lon, name, is_selected, filepath in markers:
            lon = _wrap_longitude(lon)
            marker_id = f"{lat}_{lon}_{name}"
            new_markers[marker_id] = (lat, lon, name, is_selected, filepath)
        
        # Check if markers actually changed (not just selection state)
        markers_changed = set(new_markers.keys()) != set(self.markers.keys())
        
        # Update markers dict
        old_markers = self.markers
        self.markers = new_markers
        if new_markers:
            self.has_had_markers = True
        
        # Check if any selected photos have geolocation
        has_geolocated_selection = any(m[3] for m in new_markers.values())  # m[3] is is_selected
        
        # Determine auto-fit behavior after first marker update
        if self.has_had_markers:
            if has_geolocated_selection or has_active_selection:
                # User has selection - preserve viewport
                self.auto_fit_bounds = False
            else:
                # No selection - show all markers
                self.auto_fit_bounds = True
        
        # If only selection state changed (same markers, different selection), update icons only
        if not markers_changed and old_markers:
            self._update_marker_icons()
            return
        
        # Reload map based on selection type
        if has_geolocated_selection:
            # Selected photos have geolocation - fit to them (skip viewport capture)
            self.skip_viewport_capture = True
            self.load_map()
        else:
            # Normal reload (including for selections without geolocation)
            self.load_map()
    
    def _update_marker_icons(self):
        """
        Update marker icons based on selection state without reloading the map.
        This is much faster than reloading the entire map HTML.
        Also adjusts the viewport to show selected markers.
        """
        # Build JavaScript to update all marker icons
        js_updates = []
        selected_coords = []
        
        for marker_id, (lat, lon, name, is_selected, filepath) in self.markers.items():
            escaped_id = json.dumps(marker_id)
            # Determine which icon to use
            icon_class = 'blueIcon' if is_selected else 'greyIcon'
            js_updates.append(f"""
                if (window.imageMarkers && window.imageMarkers[{escaped_id}]) {{
                    var marker = window.imageMarkers[{escaped_id}];
                    // Create the appropriate icon
                    var newIcon = {icon_class};
                    marker.setIcon(newIcon);
                }}
            """)
            
            if is_selected:
                selected_coords.append((lat, lon))
        
        # Calculate viewport adjustment for selected markers
        viewport_js = ""
        if selected_coords:
            # Check if we should preserve the current zoom level
            app_settings = Config.get_app_settings()
            preserve_zoom = app_settings.get('preserve_map_zoom', False)
            
            if len(selected_coords) == 1:
                # Single selected marker - center on it
                lat, lon = selected_coords[0]
                if preserve_zoom:
                    # Preserve current zoom level, just center on marker
                    viewport_js = f"""
                if (window.map) {{
                    window.map.setView([{lat}, {lon}], window.map.getZoom());
                }}
                """
                else:
                    # Use configured zoom level
                    zoom_level = app_settings.get('default_map_zoom', 10)
                    viewport_js = f"""
                if (window.map) {{
                    window.map.setView([{lat}, {lon}], {zoom_level});
                }}
                """
            else:
                # Multiple selected markers - fit bounds to show all
                lats = [c[0] for c in selected_coords]
                lons = [c[1] for c in selected_coords]
                min_lat, max_lat = min(lats), max(lats)
                min_lon, max_lon = min(lons), max(lons)
                viewport_js = f"""
                if (window.map) {{
                    var bounds = [[{min_lat}, {min_lon}], [{max_lat}, {max_lon}]];
                    window.map.fitBounds(bounds, {{padding: [50, 50]}});
                }}
                """
        
        # Execute JavaScript to update all markers and viewport
        if js_updates:
            js = f"""
            (function() {{
                // Define icons if they don't exist
                if (!window.blueIcon) {{
                    window.blueIcon = L.icon({{
                        iconUrl: '{LEAFLET_MARKER_ICON_URL}',
                        iconRetinaUrl: '{LEAFLET_MARKER_ICON_RETINA_URL}',
                        shadowUrl: '{LEAFLET_MARKER_SHADOW_URL}',
                        iconSize: [25, 41],
                        iconAnchor: [12, 41],
                        popupAnchor: [1, -34],
                        shadowSize: [41, 41],
                        className: 'blue-marker'
                    }});
                }}
                if (!window.greyIcon) {{
                    window.greyIcon = L.icon({{
                        iconUrl: '{LEAFLET_MARKER_ICON_URL}',
                        iconRetinaUrl: '{LEAFLET_MARKER_ICON_RETINA_URL}',
                        shadowUrl: '{LEAFLET_MARKER_SHADOW_URL}',
                        iconSize: [25, 41],
                        iconAnchor: [12, 41],
                        popupAnchor: [1, -34],
                        shadowSize: [41, 41],
                        className: 'grey-marker'
                    }});
                }}
                
                {''.join(js_updates)}
                
                {viewport_js}
            }})();
            """
            self.web_view.page().runJavaScript(js)
    
    def clear_markers(self):
        """Clear all markers from the map"""
        self.markers = {}
        self.auto_fit_bounds = True  # Re-enable auto-fit when no selection
        self.has_had_markers = False  # Reset for next load
        self.load_map()
    
    def add_marker(self, latitude: float, longitude: float, name: str = "", is_selected: bool = False, filepath: Optional[str] = None):
        """
        Add a single marker to the map
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            name: Optional name/label for the marker
            is_selected: Whether this marker represents a selected image
            filepath: Optional path to the image file for thumbnail generation
        """
        longitude = _wrap_longitude(longitude)
        marker_id = f"{latitude}_{longitude}_{name}"
        self.markers[marker_id] = (latitude, longitude, name, is_selected, filepath)
        self.load_map()
    
    def set_active_marker(self, latitude: float, longitude: float):
        """
        Set the active marker position
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
        """
        longitude = _wrap_longitude(longitude)
        self.active_marker = (latitude, longitude)
        self._update_active_marker_js(latitude, longitude)
    
    def get_active_marker(self) -> Optional[Tuple[float, float]]:
        """
        Get the active marker coordinates
        
        Returns:
            Tuple of (latitude, longitude) or None if no active marker
        """
        return self.active_marker
    
    def clear_active_marker(self):
        """Clear the active marker"""
        self.active_marker = None
        self.load_map()
    
    def set_center(self, latitude: float, longitude: float, zoom: int = 13):
        """
        Set the map center and zoom level
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            zoom: Zoom level (1-19)
        """
        longitude = _wrap_longitude(longitude)
        js = f"if (window.map) {{ window.map.setView([{latitude}, {longitude}], {zoom}); }}"
        self.web_view.page().runJavaScript(js)

