"""
Semantic search utilities for enhanced vector search capabilities.
Includes semantic keyword generation for better device matching.
"""

import logging
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from hello_indigo_api.agents.common.openai_client import perform_completion
from hello_indigo_api.agents.common.config_manager import config_manager


logger = logging.getLogger("Plugin")


class DeviceKeywords(BaseModel):
    """Response model for device keyword generation."""
    semantic_keywords: List[str] = Field(
        description="5-10 semantic keywords that describe what this device is or does"
    )
    category_keywords: List[str] = Field(
        description="Device category and type keywords (e.g., 'sensor', 'switch', 'automotive')"
    )
    function_keywords: List[str] = Field(
        description="Function and capability keywords (e.g., 'monitoring', 'control', 'measurement')"
    )
    reasoning: str = Field(
        description="Brief explanation of the keyword selection"
    )


class DeviceKeywordItem(BaseModel):
    """Individual device keyword item for batch processing."""
    device_id: str = Field(description="Device ID")
    semantic_keywords: List[str] = Field(
        description="Semantic keywords that describe what this device is or does"
    )
    category_keywords: List[str] = Field(
        description="Device category and type keywords"
    )
    function_keywords: List[str] = Field(
        description="Function and capability keywords"
    )
    
    class Config:
        extra = "forbid"


class BatchDeviceKeywords(BaseModel):
    """Response model for batch device keyword generation."""
    devices: List[DeviceKeywordItem] = Field(
        description="List of devices with their generated keywords"
    )
    
    class Config:
        extra = "forbid"
        schema_extra = {
            "example": {
                "devices": [
                    {
                        "device_id": "device_1",
                        "semantic_keywords": ["lighting", "illumination", "bedroom"],
                        "category_keywords": ["switch", "lighting"],
                        "function_keywords": ["control", "on/off"]
                    }
                ]
            }
        }


class DeviceKeywordGenerator:
    """Generates semantic keywords for device embeddings."""
    
    def __init__(self, config=None):
        # If config is provided and is a dict, use it; otherwise use None for standalone mode
        if config and isinstance(config, dict):
            self.config = config
        else:
            self.config = None  # Will be handled by perform_completion
        self.logger = logging.getLogger("Plugin")
    
    def generate_device_keywords(self, device_name: str, device_description: str = "", 
                                device_model: str = "", device_class: str = "") -> List[str]:
        """
        Generate semantic keywords for a device to enhance its embedding.
        
        Args:
            device_name: The device name
            device_description: Device description (optional)
            device_model: Device model (optional)
            device_class: Device class/type (optional)
            
        Returns:
            List of semantic keywords to include in embedding
        """
        try:
            # Create context for keyword generation
            device_context = {
                "name": device_name,
                "description": device_description,
                "model": device_model,
                "class": device_class
            }
            
            # Filter out empty values
            device_context = {k: v for k, v in device_context.items() if v}
            
            prompt = f"""
Generate semantic keywords for this home automation device to improve vector search matching:

Device Information:
{json.dumps(device_context, indent=2)}

Generate 5-10 keywords in each category:
1. Semantic keywords: What this device IS or relates to (e.g., for "Rivian R1S" → ["electric vehicle", "EV", "automotive", "car"])
2. Category keywords: Device type and classification (e.g., "sensor", "switch", "thermostat", "automotive")  
3. Function keywords: What this device DOES or measures (e.g., "monitoring", "control", "measurement", "charging")

Examples:
- "Bedroom Light Switch" → semantic: ["lighting", "illumination", "bedroom"], category: ["switch", "lighting"], function: ["control", "on/off"]
- "Nest Thermostat" → semantic: ["temperature", "climate", "HVAC", "Nest"], category: ["thermostat", "climate"], function: ["control", "monitoring", "temperature"]
- "Tesla Model Y Charging" → semantic: ["Tesla", "electric vehicle", "EV", "automotive", "battery"], category: ["automotive", "sensor"], function: ["charging", "monitoring", "power"]

Focus on terms that users might naturally use when asking about this device.
"""

            messages = [{"role": "user", "content": prompt}]
            
            response = perform_completion(
                messages=messages,
                response_model=DeviceKeywords,
                model="gpt-4o-mini",
                config=self.config
            )
            
            if not isinstance(response, DeviceKeywords):
                self.logger.warning(f"❌ Invalid response type from keyword generation for {device_name}")
                return self._fallback_keywords(device_name)
            
            # Combine all keywords
            all_keywords = (
                response.semantic_keywords +
                response.category_keywords + 
                response.function_keywords
            )
            
            # Remove duplicates and empty strings
            keywords = [k.strip() for k in all_keywords if k.strip()]
            keywords = list(dict.fromkeys(keywords))  # Remove duplicates
            
            self.logger.debug(
                f"🏷️  Generated {len(keywords)} keywords for '{device_name}': {keywords[:5]}..."
            )
            
            return keywords
            
        except Exception as e:
            self.logger.error(f"❌ Error generating keywords for {device_name}: {e}")
            return self._fallback_keywords(device_name)
    
    def _fallback_keywords(self, device_name: str) -> List[str]:
        """Fallback keyword generation when LLM fails."""
        # Simple keyword extraction from device name
        words = device_name.lower().split()
        return [word for word in words if len(word) > 2]  # Filter short words
    
    def generate_batch_device_keywords(self, devices: List[Dict[str, Any]], batch_size: int = 10, collection_name: str = "devices") -> Dict[str, List[str]]:
        """
        Generate semantic keywords for multiple devices in batches.
        
        Args:
            devices: List of device dictionaries with 'id', 'name', 'description', 'model', 'class'
            batch_size: Number of devices to process per API call (default 10)
            
        Returns:
            Dictionary mapping device IDs to their keyword lists
        """
        results = {}
        total_devices = len(devices)
        
        # Add progress tracking for keyword generation
        total_batches = (total_devices + batch_size - 1) // batch_size
        progress = None
        if total_devices >= 10:
            # Import ProgressTracker
            from hello_indigo_api.lance_database import create_progress_tracker
            progress = create_progress_tracker(f"Keyword Generation ({collection_name})", total_devices)
        
        # Process devices in batches
        for i in range(0, len(devices), batch_size):
            batch = devices[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            try:
                # Create batch context
                device_contexts = []
                for device in batch:
                    context = {
                        "device_id": str(device.get("id", "")),
                        "name": device.get("name", ""),
                        "description": device.get("description", ""),
                        "model": device.get("model", ""),
                        "class": device.get("class", "")
                    }
                    # Filter out empty values except device_id
                    context = {k: v for k, v in context.items() if v or k == "device_id"}
                    device_contexts.append(context)
                
                prompt = f"""
Generate semantic keywords for these home automation devices to improve vector search matching.

For EACH device, generate 5-10 keywords in each category:
1. Semantic keywords: What this device IS or relates to
2. Category keywords: Device type and classification  
3. Function keywords: What this device DOES or measures

Devices to process:
{json.dumps(device_contexts, indent=2)}

Return the keywords for each device in a structured format with the device_id as the key.

Examples:
- "Bedroom Light Switch" → semantic: ["lighting", "illumination", "bedroom"], category: ["switch", "lighting"], function: ["control", "on/off"]
- "Tesla Model Y Charging" → semantic: ["Tesla", "electric vehicle", "EV", "automotive", "battery"], category: ["automotive", "sensor"], function: ["charging", "monitoring", "power"]

Focus on terms that users might naturally use when asking about these devices.
"""

                messages = [{"role": "user", "content": prompt}]
                
                response = perform_completion(
                    messages=messages,
                    response_model=BatchDeviceKeywords,
                    model="gpt-4o-mini",
                    config=self.config
                )
                
                if not isinstance(response, BatchDeviceKeywords):
                    self.logger.warning(f"❌ Invalid batch response type")
                    # Fallback to individual processing
                    for device in batch:
                        device_id = str(device.get("id", ""))
                        results[device_id] = self._fallback_keywords(device.get("name", ""))
                    continue
                
                # Process batch response
                for device_result in response.devices:
                    device_id = str(device_result.device_id)
                    if not device_id:
                        continue
                        
                    # Combine all keywords
                    all_keywords = (
                        device_result.semantic_keywords +
                        device_result.category_keywords +
                        device_result.function_keywords
                    )
                    
                    # Remove duplicates and empty strings
                    keywords = [k.strip() for k in all_keywords if isinstance(k, str) and k.strip()]
                    keywords = list(dict.fromkeys(keywords))  # Remove duplicates
                    
                    results[device_id] = keywords
                
                # Update progress tracking
                if progress:
                    devices_processed = min(i + len(batch), total_devices)
                    progress.update(devices_processed, f"batch {batch_num}/{total_batches} complete")
                else:
                    self.logger.debug(f"🏷️  Batch generated keywords for {len(batch)} devices")
                
            except Exception as e:
                self.logger.error(f"❌ Error in batch keyword generation: {e}")
                # Fallback to individual processing for this batch
                for device in batch:
                    device_id = str(device.get("id", ""))
                    results[device_id] = self._fallback_keywords(device.get("name", ""))
                
                # Update progress even for failed batches
                if progress:
                    devices_processed = min(i + len(batch), total_devices)
                    progress.update(devices_processed, f"batch {batch_num}/{total_batches} (with fallback)")
        
        # Complete progress tracking
        if progress:
            progress.complete(f"generated keywords for {len(results)} devices")
        
        return results


# Convenience functions for easy import
def generate_device_keywords(device_name: str, device_description: str = "", 
                           device_model: str = "", device_class: str = "", 
                           config=None) -> List[str]:
    """Generate semantic keywords for a device."""
    generator = DeviceKeywordGenerator(config)
    return generator.generate_device_keywords(device_name, device_description, device_model, device_class)


def generate_batch_device_keywords(devices: List[Dict[str, Any]], batch_size: int = 10, 
                                 config=None, collection_name: str = "devices") -> Dict[str, List[str]]:
    """Generate semantic keywords for multiple devices in batches."""
    generator = DeviceKeywordGenerator(config)
    return generator.generate_batch_device_keywords(devices, batch_size, collection_name)