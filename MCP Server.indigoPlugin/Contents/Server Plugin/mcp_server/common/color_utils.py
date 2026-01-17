"""
Color utility functions for RGB device control.

Provides conversion utilities for various color formats:
- RGB values (0-255) to Indigo percentages (0-100)
- Hex color codes to RGB percentages
- Named colors (XKCD library + custom aliases) to RGB percentages
- White temperature validation
"""

from typing import Tuple, Optional, Dict
import re
from difflib import get_close_matches


# Try to import matplotlib for XKCD colors
try:
    from matplotlib import colors as mpl_colors
    XKCD_COLORS = mpl_colors.XKCD_COLORS
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    XKCD_COLORS = {}
    MATPLOTLIB_AVAILABLE = False


# Custom color aliases for common home automation use cases
CUSTOM_COLOR_ALIASES = {
    # White variations
    "warm white": "#FFE4B5",  # Moccasin - warm white tone
    "cool white": "#F0F8FF",  # Alice blue - cool white tone
    "soft white": "#FFF8DC",  # Cornsilk - soft white tone
    "daylight": "#FFFAFA",    # Snow - daylight white

    # Basic colors (fallbacks if XKCD not available)
    "red": "#FF0000",
    "green": "#00FF00",
    "blue": "#0000FF",
    "white": "#FFFFFF",
    "yellow": "#FFFF00",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "orange": "#FF8000",
    "purple": "#800080",
    "pink": "#FFC0CB",
    "black": "#000000",
}


def rgb_to_percent(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """
    Convert RGB values (0-255) to Indigo percentages (0-100).

    Args:
        r: Red value (0-255)
        g: Green value (0-255)
        b: Blue value (0-255)

    Returns:
        Tuple of (red_percent, green_percent, blue_percent) as floats (0-100)

    Raises:
        ValueError: If any RGB value is out of range
    """
    if not all(0 <= val <= 255 for val in [r, g, b]):
        raise ValueError(f"RGB values must be in range 0-255. Got: ({r}, {g}, {b})")

    red_percent = round((r / 255.0) * 100, 2)
    green_percent = round((g / 255.0) * 100, 2)
    blue_percent = round((b / 255.0) * 100, 2)

    return red_percent, green_percent, blue_percent


def validate_percent(r: float, g: float, b: float) -> Tuple[float, float, float]:
    """
    Validate RGB percentage values (0-100).

    Args:
        r: Red percentage (0-100)
        g: Green percentage (0-100)
        b: Blue percentage (0-100)

    Returns:
        Tuple of validated (red_percent, green_percent, blue_percent)

    Raises:
        ValueError: If any percentage value is out of range
    """
    if not all(0 <= val <= 100 for val in [r, g, b]):
        raise ValueError(f"RGB percentages must be in range 0-100. Got: ({r}, {g}, {b})")

    return round(r, 2), round(g, 2), round(b, 2)


def hex_to_rgb_percent(hex_color: str) -> Tuple[float, float, float]:
    """
    Convert hex color code to RGB percentages (0-100).

    Args:
        hex_color: Hex color code (e.g., "#FF8000" or "FF8000")

    Returns:
        Tuple of (red_percent, green_percent, blue_percent) as floats (0-100)

    Raises:
        ValueError: If hex color is invalid
    """
    # Remove '#' if present
    hex_color = hex_color.lstrip('#')

    # Validate hex format
    if not re.match(r'^[0-9A-Fa-f]{6}$', hex_color):
        raise ValueError(f"Invalid hex color format: {hex_color}. Expected format: #RRGGBB or RRGGBB")

    # Convert hex to RGB (0-255)
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Convert to percentages
    return rgb_to_percent(r, g, b)


def normalize_color_name(name: str) -> str:
    """
    Normalize color name for matching.

    Args:
        name: Color name to normalize

    Returns:
        Normalized color name (lowercase, spaces/underscores removed)
    """
    return name.lower().replace(' ', '').replace('_', '').replace('-', '')


def find_xkcd_color(color_name: str) -> Optional[str]:
    """
    Find XKCD color by name with fuzzy matching.

    Args:
        color_name: Color name to search for

    Returns:
        Hex color code if found, None otherwise
    """
    if not MATPLOTLIB_AVAILABLE:
        return None

    # Normalize input
    normalized_input = normalize_color_name(color_name)

    # Try direct match with 'xkcd:' prefix
    xkcd_key = f"xkcd:{color_name.lower().replace('_', ' ')}"
    if xkcd_key in XKCD_COLORS:
        return XKCD_COLORS[xkcd_key]

    # Try fuzzy matching on normalized names
    xkcd_normalized = {
        normalize_color_name(k.replace('xkcd:', '')): v
        for k, v in XKCD_COLORS.items()
    }

    # Check exact normalized match
    if normalized_input in xkcd_normalized:
        return xkcd_normalized[normalized_input]

    # Try fuzzy matching
    matches = get_close_matches(
        normalized_input,
        xkcd_normalized.keys(),
        n=1,
        cutoff=0.8
    )

    if matches:
        return xkcd_normalized[matches[0]]

    return None


def named_color_to_rgb_percent(color_name: str) -> Tuple[float, float, float]:
    """
    Convert named color to RGB percentages (0-100).

    Supports:
    - 954 XKCD colors (e.g., "sky blue", "burnt orange")
    - Custom aliases (e.g., "warm white", "cool white")
    - Fuzzy matching for XKCD colors

    Args:
        color_name: Color name to convert

    Returns:
        Tuple of (red_percent, green_percent, blue_percent) as floats (0-100)

    Raises:
        ValueError: If color name is not recognized
    """
    # Check custom aliases first
    normalized = color_name.lower()
    if normalized in CUSTOM_COLOR_ALIASES:
        hex_color = CUSTOM_COLOR_ALIASES[normalized]
        return hex_to_rgb_percent(hex_color)

    # Try XKCD colors
    xkcd_hex = find_xkcd_color(color_name)
    if xkcd_hex:
        return hex_to_rgb_percent(xkcd_hex)

    # No match found
    available_hint = "XKCD colors" if MATPLOTLIB_AVAILABLE else "custom aliases"
    raise ValueError(
        f"Color name '{color_name}' not recognized. "
        f"Available: {available_hint}. "
        f"Try colors like: 'sky blue', 'burnt orange', 'warm white', 'cool white'"
    )


def validate_white_temperature(temperature: int) -> int:
    """
    Validate white temperature value (Kelvin).

    Args:
        temperature: Color temperature in Kelvin

    Returns:
        Validated temperature value

    Raises:
        ValueError: If temperature is out of valid range (1200-15000K)
    """
    if not 1200 <= temperature <= 15000:
        raise ValueError(
            f"White temperature must be in range 1200-15000 Kelvin. Got: {temperature}K"
        )

    return temperature


def get_color_suggestions(color_name: str, max_suggestions: int = 5) -> list:
    """
    Get color name suggestions based on partial input.

    Args:
        color_name: Partial or incorrect color name
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of suggested color names
    """
    normalized_input = normalize_color_name(color_name)
    suggestions = []

    # Check custom aliases
    for alias in CUSTOM_COLOR_ALIASES.keys():
        if normalized_input in normalize_color_name(alias):
            suggestions.append(alias)

    # Check XKCD colors
    if MATPLOTLIB_AVAILABLE:
        xkcd_names = [k.replace('xkcd:', '') for k in XKCD_COLORS.keys()]
        matches = get_close_matches(
            color_name.lower(),
            xkcd_names,
            n=max_suggestions,
            cutoff=0.6
        )
        suggestions.extend(matches)

    return suggestions[:max_suggestions]


def get_available_colors() -> Dict[str, int]:
    """
    Get count of available color names by category.

    Returns:
        Dictionary with color counts: {'xkcd': int, 'aliases': int, 'total': int}
    """
    xkcd_count = len(XKCD_COLORS) if MATPLOTLIB_AVAILABLE else 0
    alias_count = len(CUSTOM_COLOR_ALIASES)

    return {
        'xkcd': xkcd_count,
        'aliases': alias_count,
        'total': xkcd_count + alias_count,
        'matplotlib_available': MATPLOTLIB_AVAILABLE
    }
