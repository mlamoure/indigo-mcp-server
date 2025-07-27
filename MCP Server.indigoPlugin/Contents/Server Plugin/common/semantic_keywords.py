"""
Semantic keyword generation for Indigo entities to enhance vector search quality.
Generates contextual keywords based on device types, capabilities, and relationships.
"""

import logging
from typing import List, Dict, Any, Set

logger = logging.getLogger(__name__)


def generate_batch_device_keywords(
    entities: List[Dict[str, Any]], 
    batch_size: int = 10, 
    collection_name: str = "devices"
) -> Dict[str, List[str]]:
    """
    Generate semantic keywords for a batch of entities.
    
    Args:
        entities: List of entity dictionaries
        batch_size: Processing batch size (for future optimization)
        collection_name: Type of entities being processed
        
    Returns:
        Dictionary mapping entity IDs to lists of semantic keywords
    """
    keywords_map = {}
    
    try:
        for entity in entities:
            entity_id = str(entity.get("id", ""))
            if not entity_id:
                continue
                
            keywords = generate_entity_keywords(entity, collection_name)
            keywords_map[entity_id] = keywords
            
    except Exception as e:
        logger.error(f"Error generating batch keywords for {collection_name}: {e}")
        
    return keywords_map


def generate_entity_keywords(entity: Dict[str, Any], entity_type: str) -> List[str]:
    """
    Generate semantic keywords for a single entity.
    
    Args:
        entity: Entity dictionary
        entity_type: Type of entity (devices, variables, actions)
        
    Returns:
        List of semantic keywords
    """
    keywords = set()
    
    try:
        if entity_type == "devices":
            keywords.update(_generate_device_keywords(entity))
        elif entity_type == "variables":
            keywords.update(_generate_variable_keywords(entity))
        elif entity_type == "actions":
            keywords.update(_generate_action_keywords(entity))
            
    except Exception as e:
        logger.error(f"Error generating keywords for {entity_type} {entity.get('id', 'unknown')}: {e}")
        
    return list(keywords)


def _generate_device_keywords(device: Dict[str, Any]) -> Set[str]:
    """Generate semantic keywords for a device."""
    keywords = set()
    
    # Device type keywords
    device_type = device.get("type", "").lower()
    if device_type:
        keywords.add(device_type)
        
        # Add related keywords based on device type
        type_keywords = _get_device_type_keywords(device_type)
        keywords.update(type_keywords)
    
    # Model keywords
    model = device.get("model", "").lower()
    if model:
        keywords.add(model)
        
        # Add manufacturer keywords
        manufacturer_keywords = _get_manufacturer_keywords(model)
        keywords.update(manufacturer_keywords)
    
    # Protocol keywords
    protocol = device.get("protocol", "").lower()
    if protocol:
        keywords.add(protocol)
        keywords.add(f"{protocol}_device")
    
    # State-based keywords
    enabled = device.get("enabled", True)
    keywords.add("enabled" if enabled else "disabled")
    
    # Battery keywords
    if device.get("batteryLevel") is not None:
        keywords.add("battery_powered")
        battery_level = device.get("batteryLevel", 0)
        if battery_level < 20:
            keywords.add("low_battery")
    
    # Energy keywords
    if device.get("energyAccumTotal") is not None:
        keywords.add("energy_meter")
    if device.get("curEnergyLevel") is not None:
        keywords.add("energy_monitoring")
    
    # Temperature keywords
    if device.get("temperatureInput1") is not None or device.get("sensorValue") is not None:
        keywords.add("temperature_sensor")
    
    # Dimmer keywords
    if device.get("brightness") is not None:
        keywords.add("dimmable")
        keywords.add("lighting")
    
    # Location-based keywords from name
    name = device.get("name", "").lower()
    location_keywords = _extract_location_keywords(name)
    keywords.update(location_keywords)
    
    # Function keywords from name
    function_keywords = _extract_function_keywords(name)
    keywords.update(function_keywords)
    
    return keywords


def _generate_variable_keywords(variable: Dict[str, Any]) -> Set[str]:
    """Generate semantic keywords for a variable."""
    keywords = set()
    
    # Value type keywords
    value = variable.get("value", "")
    if isinstance(value, bool):
        keywords.add("boolean")
        keywords.add("true" if value else "false")
    elif isinstance(value, (int, float)):
        keywords.add("numeric")
        if value == 0:
            keywords.add("zero")
    elif isinstance(value, str):
        keywords.add("string")
        if value.lower() in ["on", "off"]:
            keywords.add("switch_state")
        elif value.lower() in ["true", "false"]:
            keywords.add("boolean_string")
    
    # Name-based keywords
    name = variable.get("name", "").lower()
    if "temp" in name:
        keywords.add("temperature")
    if "humidity" in name:
        keywords.add("humidity")
    if "status" in name:
        keywords.add("status")
    if "state" in name:
        keywords.add("state")
    if "mode" in name:
        keywords.add("mode")
    if "level" in name:
        keywords.add("level")
    
    # Location keywords from name
    location_keywords = _extract_location_keywords(name)
    keywords.update(location_keywords)
    
    return keywords


def _generate_action_keywords(action: Dict[str, Any]) -> Set[str]:
    """Generate semantic keywords for an action group."""
    keywords = set()
    
    # Name-based action keywords
    name = action.get("name", "").lower()
    
    # Action type keywords
    if any(word in name for word in ["turn", "switch", "toggle"]):
        keywords.add("switching")
    if any(word in name for word in ["dim", "bright", "light"]):
        keywords.add("lighting")
    if any(word in name for word in ["scene", "mood"]):
        keywords.add("scene")
    if any(word in name for word in ["security", "alarm", "lock"]):
        keywords.add("security")
    if any(word in name for word in ["climate", "temp", "heat", "cool"]):
        keywords.add("climate")
    if any(word in name for word in ["schedule", "timer", "delay"]):
        keywords.add("automation")
    if any(word in name for word in ["morning", "evening", "night", "bedtime"]):
        keywords.add("time_based")
    if any(word in name for word in ["all", "house", "whole"]):
        keywords.add("global")
    
    # Location keywords from name
    location_keywords = _extract_location_keywords(name)
    keywords.update(location_keywords)
    
    return keywords


def _get_device_type_keywords(device_type: str) -> Set[str]:
    """Get related keywords for a device type."""
    type_map = {
        "relay": ["switch", "switching", "on_off", "control"],
        "dimmer": ["lighting", "dimmable", "brightness", "level"],
        "sensor": ["monitoring", "detection", "measurement"],
        "thermostat": ["climate", "temperature", "hvac", "heating", "cooling"],
        "sprinkler": ["irrigation", "watering", "garden", "outdoor"],
        "lock": ["security", "access", "door"],
        "camera": ["security", "monitoring", "surveillance", "video"],
        "motion": ["detection", "security", "automation", "trigger"],
        "contact": ["door", "window", "security", "monitoring"],
        "temperature": ["climate", "monitoring", "sensor"],
        "humidity": ["climate", "moisture", "comfort"],
        "light": ["lighting", "illumination", "brightness"],
        "energy": ["power", "consumption", "monitoring", "meter"]
    }
    
    keywords = set()
    for key, values in type_map.items():
        if key in device_type:
            keywords.update(values)
    
    return keywords


def _get_manufacturer_keywords(model: str) -> Set[str]:
    """Get manufacturer/brand keywords from model string."""
    manufacturers = {
        "insteon": ["insteon"],
        "z-wave": ["zwave", "z_wave"],
        "zigbee": ["zigbee"],
        "lutron": ["lutron", "caseta"],
        "philips": ["philips", "hue"],
        "nest": ["nest", "google"],
        "ecobee": ["ecobee"],
        "honeywell": ["honeywell"],
        "schlage": ["schlage"],
        "yale": ["yale"],
        "august": ["august"],
        "ring": ["ring"],
        "arlo": ["arlo"],
        "sonos": ["sonos", "audio"],
        "roku": ["roku", "streaming"],
        "apple": ["apple", "homekit"],
        "amazon": ["amazon", "alexa"],
        "google": ["google", "assistant"]
    }
    
    keywords = set()
    model_lower = model.lower()
    for brand, brand_keywords in manufacturers.items():
        if brand in model_lower:
            keywords.update(brand_keywords)
    
    return keywords


def _extract_location_keywords(name: str) -> Set[str]:
    """Extract location-based keywords from entity name."""
    locations = {
        "living": ["living_room", "family_room", "main"],
        "bedroom": ["bedroom", "bed", "sleep"],
        "kitchen": ["kitchen", "cook"],
        "bathroom": ["bathroom", "bath"],
        "garage": ["garage", "car"],
        "basement": ["basement", "lower"],
        "attic": ["attic", "upper"],
        "office": ["office", "work", "study"],
        "dining": ["dining_room", "eat"],
        "family": ["family_room", "den"],
        "guest": ["guest_room", "spare"],
        "master": ["master_bedroom", "primary"],
        "hallway": ["hallway", "corridor"],
        "entryway": ["entryway", "foyer", "entrance"],
        "patio": ["patio", "deck", "outdoor"],
        "yard": ["yard", "garden", "outdoor"],
        "driveway": ["driveway", "drive"],
        "front": ["front_door", "entrance"],
        "back": ["back_door", "rear"],
        "upstairs": ["upstairs", "upper"],
        "downstairs": ["downstairs", "lower"],
        "closet": ["closet", "storage"]
    }
    
    keywords = set()
    name_lower = name.lower()
    for location, location_keywords in locations.items():
        if location in name_lower:
            keywords.update(location_keywords)
    
    return keywords


def _extract_function_keywords(name: str) -> Set[str]:
    """Extract function-based keywords from entity name."""
    functions = {
        "light": ["lighting", "illumination", "lamp"],
        "switch": ["switching", "control"],
        "fan": ["cooling", "ventilation", "air"],
        "outlet": ["power", "plug"],
        "door": ["access", "entry"],
        "window": ["opening", "view"],
        "lock": ["security", "access"],
        "sensor": ["monitoring", "detection"],
        "camera": ["security", "surveillance"],
        "speaker": ["audio", "sound"],
        "tv": ["entertainment", "media"],
        "heater": ["heating", "warm"],
        "cooler": ["cooling", "cold"],
        "pump": ["water", "circulation"],
        "valve": ["flow", "control"]
    }
    
    keywords = set()
    name_lower = name.lower()
    for function, function_keywords in functions.items():
        if function in name_lower:
            keywords.update(function_keywords)
    
    return keywords