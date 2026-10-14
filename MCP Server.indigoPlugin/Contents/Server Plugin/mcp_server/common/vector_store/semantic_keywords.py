"""
Semantic keyword generation for Indigo entities to enhance vector search quality.
Generates contextual keywords based on device types, capabilities, and relationships.
Uses hybrid approach: rule-based keywords + LLM-generated contextual keywords.
"""

import hashlib
import json
import logging
import re
from typing import List, Dict, Any, Set, Optional

from pydantic import BaseModel

logger = logging.getLogger("Plugin")


class DeviceKeywords(BaseModel):
    """Keywords for a single device."""
    device_number: int  # 1-based index in the batch
    keywords: List[str]


class BatchKeywordsResponse(BaseModel):
    """Structured response for batch keyword generation."""
    devices: List[DeviceKeywords]

# Global cache for LLM-generated keywords
_llm_keyword_cache = {}

# Shared instructions for both keyword prompts. Keywords used to list nearby
# rooms and unrelated device kinds ("family room / media room" on a basement
# light, "lamp" on ceiling lights), which pulled the wrong devices up for
# exact-name queries (indigo-mcp-server#72), so they are confined to what the
# device itself is and the room it is in.
KEYWORD_GUIDANCE = """For each device, give 5-8 short keywords or phrases a person might type to find it:
- other common names for what the device is or controls, judged from its name, type and model
- the room or area in the device name, plus other common names for that same room or area

Rules:
- Use only the room or area the device name mentions. Never guess at a room, area or feature the name does not mention.
- Never mention a kind of device that the device is not.
- No protocol, network, address or model-number words, and nothing about the device's current state."""


def _calculate_optimal_batch_size(entity_count: int, estimated_tokens_per_entity: int = 85) -> int:
    """
    Calculate optimal batch size based on token limits and entity characteristics.
    
    Args:
        entity_count: Total number of entities to process
        estimated_tokens_per_entity: Estimated tokens per entity (based on observed data)
        
    Returns:
        Optimal batch size for LLM processing
    """
    # GPT-5.4-mini context window: 400,000 tokens
    # Reserve space for response (typical response: ~10 keywords per device * ~2 tokens = ~20 tokens per device)
    max_context_tokens = 400000
    response_reserve = entity_count * 25  # Conservative estimate
    available_tokens = max_context_tokens - response_reserve - 1000  # Extra safety buffer
    
    # Calculate max entities per batch based on token limit
    max_entities_per_batch = available_tokens // estimated_tokens_per_entity
    
    # Practical limits and optimizations
    if entity_count <= 50:
        # For small sets, process all at once
        return min(entity_count, max_entities_per_batch)
    elif entity_count <= 200:
        # For medium sets, use 2-3 batches max
        return min(entity_count // 2, max_entities_per_batch)
    else:
        # For large sets, use optimal batch size but cap at reasonable limits
        optimal_batch_size = min(200, max_entities_per_batch)  # Cap at 200 for API stability
        return max(50, optimal_batch_size)  # Minimum of 50 for efficiency


def generate_batch_device_keywords(
    entities: List[Dict[str, Any]], 
    batch_size: int = None,  # Auto-calculate optimal batch size if not specified
    collection_name: str = "devices",
    progress_callback: Optional[callable] = None
) -> Dict[str, List[str]]:
    """
    Generate semantic keywords for a batch of entities using optimized batch LLM processing.
    
    Args:
        entities: List of entity dictionaries
        batch_size: LLM batch size for processing multiple entities at once
        collection_name: Type of entities being processed
        progress_callback: Optional callback to report progress (called with current index)
        
    Returns:
        Dictionary mapping entity IDs to lists of semantic keywords
    """
    keywords_map = {}
    
    try:
        # Start keyword generation
        
        # Calculate optimal batch size if not specified
        if batch_size is None:
            batch_size = _calculate_optimal_batch_size(len(entities))
        
        # First, generate LLM keywords using parallel or sequential processing
        all_llm_keywords = {}
        if collection_name == "devices":
            from .parallel_keywords import should_use_parallel_keywords, get_optimal_keyword_concurrency, generate_keywords_parallel
            
            total_batches = (len(entities) + batch_size - 1) // batch_size
            # Calculate batches for LLM processing
            
            # Check if parallel processing should be used
            if should_use_parallel_keywords(len(entities)) and total_batches > 1:
                max_concurrent = get_optimal_keyword_concurrency(len(entities), total_batches)
                # Use parallel processing
                
                # Use parallel processing
                all_llm_keywords = generate_keywords_parallel(
                    entities, 
                    batch_size, 
                    collection_name, 
                    progress_callback,
                    max_concurrent
                )
            else:
                # Use sequential processing
                
                # Use sequential processing
                for batch_num, batch_start in enumerate(range(0, len(entities), batch_size), 1):
                    batch_end = min(batch_start + batch_size, len(entities))
                    batch_entities = entities[batch_start:batch_end]
                    
                    # Process batch
                    
                    # Generate LLM keywords for this batch with fallback
                    batch_llm_keywords = _generate_llm_keywords_batch_with_fallback(batch_entities, collection_name, batch_size)
                    all_llm_keywords.update(batch_llm_keywords)
                    
                    # Update progress for this batch with detailed messaging
                    if progress_callback:
                        # Keyword generation takes the first half of progress (0-50%)
                        keyword_progress = int((batch_end / len(entities)) * 50)  # 50% max for keywords
                        progress_callback(keyword_progress, f"Sequential keyword generation - batch {batch_num}/{total_batches}")
                        
                        # Log progress every few batches or every 10%
                        if batch_num % max(1, total_batches // 10) == 0 or batch_num == total_batches:
                            completion_pct = int((batch_end / len(entities)) * 100)
                            logger.info(f"📊 Keyword Generation progress: {completion_pct}% complete ({batch_end}/{len(entities)} entities) - processed {batch_num}/{total_batches} sequential LLM batches")
        else:
            all_llm_keywords = {}
        
        # Now generate rule-based keywords and combine with LLM keywords
        
        for i, entity in enumerate(entities):
            entity_id = str(entity.get("id", ""))
            entity.get("name", f"ID:{entity_id}")
            
            if not entity_id:
                continue
            
            # Generate rule-based keywords (fast)
            keywords = set()
            if collection_name == "devices":
                keywords.update(_generate_device_keywords(entity))
            elif collection_name == "variables":
                keywords.update(_generate_variable_keywords(entity))
            elif collection_name == "actions":
                keywords.update(_generate_action_keywords(entity))
            elif collection_name == "triggers":
                keywords.update(_generate_trigger_keywords(entity))
            elif collection_name == "schedules":
                keywords.update(_generate_schedule_keywords(entity))
            
            # Add cached/batch LLM keywords if available
            if entity_id in all_llm_keywords:
                keywords.update(all_llm_keywords[entity_id])
                pass  # Keywords combined
            else:
                # Fallback to individual LLM generation if not in batch (for edge cases)
                llm_keywords = _generate_llm_keywords(entity, collection_name)
                if llm_keywords:
                    keywords.update(llm_keywords)
                    pass  # Keywords generated
            
            keywords_map[entity_id] = list(keywords)
            
            # Report progress if callback provided
            if progress_callback:
                # Rule-based processing takes the second half of progress (50-100%)
                rule_progress = 50 + int(((i + 1) / len(entities)) * 50)  # 50-100%
                progress_callback(rule_progress, "Combining rule-based + LLM keywords")
                
                # Progress tracking handled by callback, no need for additional logging
        
        # Keyword generation completed
            
    except Exception as e:
        logger.error(f"Error generating batch keywords for {collection_name}: {e}")
        
    return keywords_map


def generate_entity_keywords(entity: Dict[str, Any], entity_type: str) -> List[str]:
    """
    Generate semantic keywords for a single entity using hybrid approach.
    Combines rule-based keywords with LLM-generated contextual keywords.
    
    Args:
        entity: Entity dictionary
        entity_type: Type of entity (devices, variables, actions)
        
    Returns:
        List of semantic keywords
    """
    keywords = set()
    
    try:
        # Generate rule-based keywords (fast, reliable baseline)
        if entity_type == "devices":
            keywords.update(_generate_device_keywords(entity))
        elif entity_type == "variables":
            keywords.update(_generate_variable_keywords(entity))
        elif entity_type == "actions":
            keywords.update(_generate_action_keywords(entity))
        elif entity_type == "triggers":
            keywords.update(_generate_trigger_keywords(entity))
        elif entity_type == "schedules":
            keywords.update(_generate_schedule_keywords(entity))
        
        # Add LLM-generated contextual keywords (enhanced semantic understanding)
        llm_keywords = _generate_llm_keywords(entity, entity_type)
        if llm_keywords:
            keywords.update(llm_keywords)
            
    except Exception as e:
        logger.error(f"Error generating keywords for {entity_type} {entity.get('id', 'unknown')}: {e}")
        
    return list(keywords)


def _generate_device_keywords(device: Dict[str, Any]) -> Set[str]:
    """
    Rule-based keywords for a device: the room/area in its name (with other
    names for that same room), synonyms for what its name says it is, and a
    few stable capabilities.

    Deliberately excluded (they pulled vectors toward hardware and other
    rooms, see indigo-mcp-server#72): model numbers, protocol and address,
    and anything that changes with device state (enabled, battery level).
    """
    keywords = set()
    name = device.get("name", "") or ""

    keywords.update(_extract_location_keywords(name))
    keywords.update(_extract_function_keywords(name))

    if device.get("brightness") is not None:
        keywords.add("dimmable")
    if device.get("energyAccumTotal") is not None or device.get("energyCurLevel") is not None:
        keywords.add("energy monitoring")
    if device.get("batteryLevel") is not None:
        keywords.add("battery powered")

    return keywords


def _generate_variable_keywords(variable: Dict[str, Any]) -> Set[str]:
    """Generate semantic keywords for a variable (from its name only — the value changes)."""
    keywords = set()
    name = _humanize(variable.get("name", "") or "")

    for word, keyword in (
        ("temp", "temperature"),
        ("humidity", "humidity"),
        ("status", "status"),
        ("state", "state"),
        ("mode", "mode"),
        ("level", "level"),
    ):
        if word in name:
            keywords.add(keyword)

    keywords.update(_extract_location_keywords(name))
    return keywords


def _generate_action_keywords(action: Dict[str, Any]) -> Set[str]:
    """Generate semantic keywords for an action group."""
    keywords = set()
    name = _humanize(action.get("name", "") or "")

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
    if any(word in name for word in ["morning", "evening", "night", "bedtime"]):
        keywords.add("time of day")
    if any(word in name for word in ["all", "house", "whole"]):
        keywords.add("whole house")

    keywords.update(_extract_location_keywords(name))
    return keywords


def _generate_trigger_keywords(trigger: Dict[str, Any]) -> Set[str]:
    """Generate semantic keywords for a trigger."""
    keywords = {"trigger", "automation"}

    trigger_type = trigger.get("type", "")
    if trigger_type:
        keywords.add(_humanize(str(trigger_type)))

    name = _humanize(trigger.get("name", "") or "")
    if any(word in name for word in ["motion", "sensor", "door", "window"]):
        keywords.add("sensor driven")
    if any(word in name for word in ["security", "alarm", "lock"]):
        keywords.add("security")
    keywords.update(_extract_location_keywords(name))

    return keywords


def _generate_schedule_keywords(schedule: Dict[str, Any]) -> Set[str]:
    """Generate semantic keywords for a schedule."""
    keywords = {"schedule", "timer", "automation", "time based"}

    for field in ("date_type", "time_type"):
        value = schedule.get(field, "")
        if value:
            keywords.add(_humanize(str(value)))

    keywords.update(_extract_location_keywords(schedule.get("name", "") or ""))
    return keywords


def _humanize(text: str) -> str:
    """'alarm_enabled' / 'isNightTime' -> 'alarm enabled' / 'is night time' (lowercase)."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text or "")
    text = re.sub(r"[_\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


# Rooms and areas -> other common names for the SAME room/area. Never maps
# one room to a different one (a living-room query must not drift to the
# basement media room).
_LOCATION_ALIASES = {
    "living room": ["living room", "family room", "lounge"],
    "family room": ["family room", "living room", "den"],
    "master bedroom": ["master bedroom", "primary bedroom"],
    "primary bedroom": ["primary bedroom", "master bedroom"],
    "guest bedroom": ["guest bedroom", "guest room"],
    "guest room": ["guest room", "guest bedroom"],
    "bedroom": ["bedroom"],
    "kitchen": ["kitchen"],
    "pantry": ["pantry"],
    "dining room": ["dining room"],
    "bathroom": ["bathroom", "bath"],
    "powder room": ["powder room", "half bath"],
    "laundry": ["laundry room"],
    "mudroom": ["mudroom"],
    "office": ["office", "study"],
    "sunroom": ["sunroom", "sun room"],
    "tv room": ["tv room", "media room"],
    "tv area": ["tv area", "tv room", "media room"],
    "media room": ["media room", "tv room"],
    "theater": ["theater", "home theater", "media room"],
    "garage": ["garage"],
    "basement": ["basement", "lower level"],
    "attic": ["attic"],
    "closet": ["closet"],
    "hallway": ["hallway", "hall", "corridor"],
    "foyer": ["foyer", "entryway", "entrance"],
    "entryway": ["entryway", "foyer", "entrance"],
    "front door": ["front door", "entrance", "front porch"],
    "back door": ["back door", "rear entrance"],
    "porch": ["porch"],
    "patio": ["patio"],
    "deck": ["deck"],
    "yard": ["yard"],
    "driveway": ["driveway"],
    "outdoor": ["outdoor", "outside", "exterior"],
    "outside": ["outside", "outdoor", "exterior"],
    "exterior": ["exterior", "outdoor", "outside"],
    "upstairs": ["upstairs"],
    "downstairs": ["downstairs"],
}

# What the device is -> other names for the same kind of thing (one
# direction only where the reverse is wrong: a lamp is a light, but a
# ceiling light is not a lamp).
_FUNCTION_ALIASES = {
    "light": ["light", "lighting"],
    "lights": ["lights", "lighting"],
    "lamp": ["lamp", "light"],
    "sconce": ["sconce", "wall light"],
    "sconces": ["sconces", "wall lights"],
    "fan": ["fan"],
    "outlet": ["outlet", "plug"],
    "plug": ["plug", "outlet"],
    "lock": ["lock"],
    "deadbolt": ["deadbolt", "lock"],
    "camera": ["camera"],
    "speaker": ["speaker"],
    "tv": ["tv", "television"],
    "thermostat": ["thermostat"],
    "heater": ["heater", "heating"],
    "sprinkler": ["sprinkler", "irrigation"],
    "sprinklers": ["sprinklers", "irrigation"],
    "vacuum": ["vacuum"],
    "shade": ["shade", "blind"],
    "shades": ["shades", "blinds"],
}


def keyword_rules_fingerprint() -> str:
    """
    Short hash of everything that shapes generated keywords. The search
    index stores it, so editing the alias tables or the LLM guidance
    rebuilds the index instead of leaving old keywords on unchanged entities.
    """
    rules = json.dumps([KEYWORD_GUIDANCE, _LOCATION_ALIASES, _FUNCTION_ALIASES], sort_keys=True)
    return hashlib.sha256(rules.encode()).hexdigest()[:12]


def _alias_keywords(name: str, aliases: Dict[str, List[str]]) -> Set[str]:
    words = _humanize(name)
    keywords = set()
    for phrase, phrase_aliases in aliases.items():
        if re.search(rf"\b{re.escape(phrase)}\b", words):
            keywords.update(phrase_aliases)
    return keywords


def _extract_location_keywords(name: str) -> Set[str]:
    """Rooms/areas named in the entity name, plus other names for the same room/area."""
    return _alias_keywords(name, _LOCATION_ALIASES)


def _extract_function_keywords(name: str) -> Set[str]:
    """What the entity name says the device is, plus synonyms for that same kind of thing."""
    return _alias_keywords(name, _FUNCTION_ALIASES)


def _generate_llm_keywords_batch_with_fallback(entities: List[Dict[str, Any]], entity_type: str, original_batch_size: int) -> Dict[str, List[str]]:
    """
    Generate LLM keywords with fallback to smaller batch sizes if needed.
    
    Args:
        entities: List of entity dictionaries
        entity_type: Type of entity (devices, variables, actions)
        original_batch_size: Original batch size attempted
        
    Returns:
        Dictionary mapping entity IDs to lists of LLM-generated keywords
    """
    # Try with original batch size first
    result = _generate_llm_keywords_batch(entities, entity_type)
    
    # If we got good results (>50% success), return them
    expected_count = len([e for e in entities if e.get("name") and str(e.get("id", ""))])
    success_rate = len(result) / max(expected_count, 1)
    
    if success_rate >= 0.5:
        logger.debug(f"Batch processing succeeded with {len(result)}/{expected_count} entities")
        return result
    
    # If batch processing failed, try fallback strategies
    
    # Strategy 1: Try smaller batch sizes
    for fallback_size in [10, 5, 3, 1]:
        if fallback_size >= original_batch_size:
            continue
            
        logger.debug(f"Trying fallback batch size: {fallback_size}")
        all_results = {}
        
        for i in range(0, len(entities), fallback_size):
            batch = entities[i:i + fallback_size]
            batch_result = _generate_llm_keywords_batch(batch, entity_type)
            all_results.update(batch_result)
            
            # If this smaller batch also fails, continue but log it
            if len(batch_result) == 0 and len(batch) > 0:
                logger.warning(f"Even small batch of size {fallback_size} failed")
        
        # Check if fallback worked better
        fallback_success_rate = len(all_results) / max(expected_count, 1)
        if fallback_success_rate > success_rate:
            logger.debug(f"Fallback batch size {fallback_size} worked better: {len(all_results)}/{expected_count}")
            return all_results
    
    # If all batch strategies failed, fall back to individual processing
    individual_results = {}
    
    for entity in entities:
        entity_id = str(entity.get("id", ""))
        if entity_id and entity.get("name"):
            try:
                keywords = _generate_llm_keywords(entity, entity_type)
                if keywords:
                    individual_results[entity_id] = keywords
            except Exception as e:
                logger.error(f"Individual LLM processing failed for entity {entity_id}: {e}")
    
    len(individual_results) / max(expected_count, 1)
    # Individual processing completed
    
    return individual_results


def _generate_llm_keywords_batch(entities: List[Dict[str, Any]], entity_type: str) -> Dict[str, List[str]]:
    """
    Generate contextual keywords for multiple entities using batch LLM processing.
    This is much faster than individual API calls for each entity.
    
    Args:
        entities: List of entity dictionaries
        entity_type: Type of entity (devices, variables, actions)
        
    Returns:
        Dictionary mapping entity IDs to lists of LLM-generated keywords
    """
    if entity_type != "devices":
        # Only generate LLM keywords for devices initially
        return {}
    
    if not entities:
        return {}
    
    try:
        # Import here to avoid circular imports
        from ..openai_client.main import get_small_model, low_reasoning_effort, perform_completion
        
        # Prepare batch prompt with multiple devices
        device_descriptions = []
        entity_ids = []
        cache_keys = []
        cached_results = {}

        for entity in entities:
            entity_id = str(entity.get("id", ""))
            if not entity_id:
                continue

            # Check cache first
            cache_key = _create_entity_cache_key(entity)
            if cache_key in _llm_keyword_cache:
                cached_results[entity_id] = _llm_keyword_cache[cache_key]
                continue
            
            name = entity.get("name", "")
            model = entity.get("model", "")
            device_type = entity.get("deviceTypeId", "")
            description = entity.get("description", "")
            
            if not name:  # Skip if no name
                continue
            
            # Add to batch
            device_descriptions.append(f"Device {len(device_descriptions)+1}:\n- Name: {name}\n- Model: {model}\n- Type: {device_type}\n- Description: {description}")
            entity_ids.append(entity_id)
            cache_keys.append(cache_key)
        
        if not device_descriptions:
            if cached_results:
                logger.debug(f"All {len(cached_results)} entities served from LLM keyword cache")
            return cached_results
        
        logger.debug(f"Batch processing {len(device_descriptions)} devices for LLM keywords")
        
        # Create batch prompt for structured response
        batch_prompt = f"""Generate search keywords for these {len(device_descriptions)} home automation devices.

{chr(10).join(device_descriptions)}

{KEYWORD_GUIDANCE}

Return the results as a structured JSON response with device numbers (1-based) and their corresponding keywords."""

        # Call LLM with structured response model
        small_model = get_small_model()
        response = perform_completion(
            messages=batch_prompt,
            model=small_model,
            response_model=BatchKeywordsResponse,
            response_token_reserve=500,  # More tokens for JSON response
            reasoning_effort=low_reasoning_effort(small_model),
        )
        
        if not response:
            logger.warning("Empty batch response from LLM")
            return {}
        
        # Process structured response directly
        logger.debug(f"Received structured response of type: {type(response).__name__}")
        keywords_map = _process_structured_response(response, entity_ids, cache_keys, entities)

        # Merge cached results with newly generated results
        keywords_map.update(cached_results)

        cache_note = f" ({len(cached_results)} from cache)" if cached_results else ""
        logger.debug(f"Batch processed {len(keywords_map)} devices{cache_note}, generated {sum(len(kw) for kw in keywords_map.values())} total keywords")

        return keywords_map
        
    except Exception as e:
        logger.error(f"Error in batch LLM keyword generation: {e}")
        return {}


def _process_structured_response(response, entity_ids: List[str], cache_keys: List[str], entities: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Process structured LLM response into device keywords mapping.
    Handles both parsed BatchKeywordsResponse objects and raw JSON strings.
    
    Args:
        response: Structured response from LLM (BatchKeywordsResponse or JSON string)
        entity_ids: List of entity IDs in order
        cache_keys: List of cache keys in order
        entities: List of entity dictionaries for name lookup
        
    Returns:
        Dictionary mapping entity IDs to keyword lists
    """
    keywords_map = {}
    
    try:
        # Handle different response types from OpenAI API
        parsed_response = None
        
        if isinstance(response, str):
            # OpenAI returned JSON string - parse it into BatchKeywordsResponse
            logger.debug(f"Parsing JSON string response (length: {len(response)})")
            try:
                import json
                json_data = json.loads(response)
                parsed_response = BatchKeywordsResponse(**json_data)
                logger.debug("Successfully parsed JSON string into BatchKeywordsResponse")
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.error(f"❌ Failed to parse JSON response: {e}")
                logger.debug(f"Response content: {response}")
                return {}
        elif hasattr(response, 'devices'):
            # Already a parsed BatchKeywordsResponse object
            parsed_response = response
            logger.debug("Using already parsed BatchKeywordsResponse object")
        else:
            # Unknown response type
            logger.error(f"❌ Unknown response type: {type(response)}")
            logger.debug(f"Response object: {response}")
            return {}
        
        logger.debug(f"Processing structured response with {len(parsed_response.devices)} device entries")
        
        # Map structured response back to entity IDs
        successful_mappings = 0
        
        for device_keywords in parsed_response.devices:
            # Convert 1-based device number to 0-based index
            device_index = device_keywords.device_number - 1
            
            if 0 <= device_index < len(entity_ids):
                entity_id = entity_ids[device_index]
                cache_key = cache_keys[device_index]
                
                # Get entity name for enhanced logging
                entity_name = "Unknown"
                if device_index < len(entities):
                    entity = entities[device_index]
                    entity_name = entity.get("name", f"ID:{entity_id}")
                    # Truncate very long names
                    if len(entity_name) > 30:
                        entity_name = entity_name[:27] + "..."
                
                # Clean and validate keywords
                cleaned_keywords = []
                for keyword in device_keywords.keywords:
                    cleaned = keyword.strip().lower()
                    if cleaned and len(cleaned) > 1:
                        cleaned_keywords.append(cleaned)
                
                if cleaned_keywords:
                    keywords_map[entity_id] = cleaned_keywords
                    # Cache the results
                    _llm_keyword_cache[cache_key] = cleaned_keywords
                    successful_mappings += 1
                    
                    # Enhanced logging with entity name and keywords
                    keyword_preview = ", ".join(cleaned_keywords[:6])  # Show first 6 keywords
                    if len(cleaned_keywords) > 6:
                        keyword_preview += f" (+{len(cleaned_keywords) - 6} more)"
                    
                    logger.debug(f"Mapped device {device_keywords.device_number} \"{entity_name}\" to entity {entity_id}: [{keyword_preview}]")
                else:
                    logger.warning(f"⚠️ No valid keywords for device {device_keywords.device_number} \"{entity_name}\"")
            else:
                logger.warning(f"⚠️ Invalid device number {device_keywords.device_number} (expected 1-{len(entity_ids)})")
        
        logger.debug(f"📊 Successfully mapped {successful_mappings}/{len(entity_ids)} entities from structured response")
        
        return keywords_map
        
    except Exception as e:
        logger.error(f"Error processing structured response: {e}")
        logger.debug(f"Response object: {response}")
        return {}


def _parse_batch_keywords_response(response_text: str, entity_ids: List[str], cache_keys: List[str]) -> Dict[str, List[str]]:
    """
    Parse batch LLM response into individual device keywords with improved resilience.
    
    Args:
        response_text: Raw response text from LLM
        entity_ids: List of entity IDs in order
        cache_keys: List of cache keys in order
        
    Returns:
        Dictionary mapping entity IDs to keyword lists
    """
    keywords_map = {}
    
    try:
        logger.debug(f"Parsing batch response text (length: {len(response_text)})")
        logger.debug(f"Response preview: {response_text[:300]}...")
        
        lines = response_text.strip().split('\n')
        device_responses = []
        
        logger.debug(f"📋 Processing {len(lines)} lines for device responses")
        
        # Extract device responses with multiple parsing strategies
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            logger.debug(f"Line {line_num}: {line[:100]}...")
            
            # Strategy 1: Standard format "Device N: keywords..."
            if line.lower().startswith('device ') and ':' in line:
                keywords_part = line.split(':', 1)[1].strip()
                device_responses.append(keywords_part)
                logger.debug(f"Found device response {len(device_responses)}: {keywords_part[:50]}...")
                continue
            
            # Strategy 2: Alternative formats (numbered lists, bullets, etc.)
            # Handle formats like "1. keywords" or "- keywords" or just "keywords"
            if any(line.startswith(prefix) for prefix in ['1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.', 
                                                           '11.', '12.', '13.', '14.', '15.', '16.', '17.', '18.', '19.', '20.',
                                                           '-', '•', '*']):
                # Remove the prefix and use the rest as keywords
                cleaned_line = line
                for prefix in ['1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.', 
                              '11.', '12.', '13.', '14.', '15.', '16.', '17.', '18.', '19.', '20.',
                              '-', '•', '*']:
                    if cleaned_line.startswith(prefix):
                        cleaned_line = cleaned_line[len(prefix):].strip()
                        break
                
                if cleaned_line and ',' in cleaned_line:  # Only if it looks like a keyword list
                    device_responses.append(cleaned_line)
                    logger.debug(f"Found alternative format response {len(device_responses)}: {cleaned_line[:50]}...")
                    continue
            
            # Strategy 3: If line contains multiple comma-separated words, might be keywords
            if ',' in line and len(line.split(',')) >= 3:  # At least 3 comma-separated items
                device_responses.append(line)
                logger.debug(f"Found comma-separated response {len(device_responses)}: {line[:50]}...")
                continue
        
        logger.debug(f"📊 Extracted {len(device_responses)} device responses from {len(lines)} lines")
        
        # Map responses back to entity IDs
        successful_mappings = 0
        for i, (entity_id, cache_key) in enumerate(zip(entity_ids, cache_keys)):
            if i < len(device_responses):
                keywords_text = device_responses[i]
                logger.debug(f"Parsing keywords for entity {entity_id}: {keywords_text[:100]}...")
                
                # Parse keywords with improved cleaning
                keywords = []
                raw_keywords = keywords_text.split(',')
                logger.debug(f"Raw keyword parts: {len(raw_keywords)}")
                
                for keyword in raw_keywords:
                    cleaned = keyword.strip().lower()
                    # Remove common noise words and artifacts
                    cleaned = cleaned.replace('"', '').replace("'", '').replace('(', '').replace(')', '')
                    cleaned = cleaned.replace('[', '').replace(']', '').replace('{', '').replace('}', '')
                    
                    if cleaned and len(cleaned) > 1 and cleaned not in ['and', 'or', 'the', 'a', 'an']:
                        keywords.append(cleaned)
                
                if keywords:
                    keywords_map[entity_id] = keywords
                    # Cache the results
                    _llm_keyword_cache[cache_key] = keywords
                    successful_mappings += 1
                    logger.debug(f"Parsed {len(keywords)} batch keywords for entity {entity_id}: {', '.join(keywords[:3])}{' (+more)' if len(keywords) > 3 else ''}")
                else:
                    logger.warning(f"⚠️ No valid keywords parsed for entity {entity_id} from: {keywords_text[:100]}...")
            else:
                logger.warning(f"Missing response for entity {entity_id} in batch (index {i}, only {len(device_responses)} responses)")
        
        logger.debug(f"📊 Successfully mapped {successful_mappings}/{len(entity_ids)} entities")
        
        # If we got very few successful mappings, log more details for debugging
        if successful_mappings < len(entity_ids) * 0.5:  # Less than 50% success
            logger.warning(f"Low success rate in batch parsing: {successful_mappings}/{len(entity_ids)}")
            logger.debug(f"Full response text for debugging:\n{response_text}")
        
        return keywords_map
        
    except Exception as e:
        logger.error(f"Error parsing batch keywords response: {e}")
        logger.debug(f"Response text that failed parsing: {response_text[:500]}...")
        return {}


def _generate_llm_keywords(entity: Dict[str, Any], entity_type: str) -> List[str]:
    """
    Generate contextual keywords using LLM for enhanced semantic understanding.
    Uses caching to avoid redundant LLM calls for the same entity.
    
    Args:
        entity: Entity dictionary
        entity_type: Type of entity (devices, variables, actions)
        
    Returns:
        List of LLM-generated keywords, empty list on error
    """
    entity_name = entity.get("name", "unknown")
    
    try:
        # Only generate LLM keywords for devices initially
        if entity_type != "devices":
            return []
        
        # Create cache key from entity static fields
        cache_key = _create_entity_cache_key(entity)
        if cache_key in _llm_keyword_cache:
            pass  # Using cached keywords
            return _llm_keyword_cache[cache_key]
        
        logger.debug(f"🤖 Calling LLM for semantic keywords: {entity_name}")
        
        # Extract relevant info for LLM prompt
        name = entity.get("name", "")
        model = entity.get("model", "")
        device_type = entity.get("deviceTypeId", "")
        description = entity.get("description", "")
        
        if not name:  # Skip if no name
            return []
        
        # Import here to avoid circular imports
        from ..openai_client.main import get_small_model, low_reasoning_effort, perform_completion
        
        # Create prompt for LLM keyword generation
        prompt = f"""Generate search keywords for this home automation device:

Name: {name}
Model: {model}
Type: {device_type}
Description: {description}

{KEYWORD_GUIDANCE}

Return only the keywords as a comma-separated list, no explanations."""

        small_model = get_small_model()
        response = perform_completion(
            messages=prompt,
            model=small_model,
            response_token_reserve=100,
            reasoning_effort=low_reasoning_effort(small_model),
        )
        
        if not response:
            logger.debug(f"Empty response for LLM keywords: '{name}'")
            return []
        
        # Handle different response types from perform_completion
        response_text = ""
        # Use standardized response handling utility
        from ..response_utils import extract_text_content
        
        try:
            response_text = extract_text_content(response, f"llm_keywords[{name}]")
            if not response_text:
                logger.warning(f"Empty response text extracted for '{name}'")
                response_text = ""
        except Exception as e:
            logger.error(f"Error in response extraction for '{name}': {e}")
            response_text = ""
        
        # Parse response into keywords list
        keywords = []
        try:
            for keyword in response_text.split(','):
                try:
                    cleaned = keyword.strip().lower()
                    if cleaned and len(cleaned) > 1:  # Filter very short keywords
                        keywords.append(cleaned)
                except Exception as e:
                    logger.warning(f"Error processing keyword '{keyword}' for '{name}': {e}")
        except Exception as e:
            logger.error(f"Error parsing keywords for '{name}': {e}")
            keywords = []
        
        # Cache the results
        _llm_keyword_cache[cache_key] = keywords
        
        if keywords:
            logger.debug(f"🎯 LLM generated {len(keywords)} keywords for {entity_name}: {', '.join(keywords[:3])}{' (+more)' if len(keywords) > 3 else ''}")
        else:
            logger.debug(f"🤷 LLM generated no keywords for {entity_name}")
        
        return keywords
        
    except Exception as e:
        logger.error(f"Error generating LLM keywords for '{entity_name}': {e}")
        return []



def _create_entity_cache_key(entity: Dict[str, Any]) -> str:
    """
    Create cache key for entity based on static fields that affect keyword generation.
    
    Args:
        entity: Entity dictionary
        
    Returns:
        SHA256 hash string for caching
    """
    # Use fields that affect keyword generation
    key_fields = {
        "name": entity.get("name", ""),
        "model": entity.get("model", ""), 
        "deviceTypeId": entity.get("deviceTypeId", ""),
        "description": entity.get("description", "")
    }
    
    key_str = json.dumps(key_fields, sort_keys=True)
    return hashlib.sha256(key_str.encode()).hexdigest()


def clear_llm_keyword_cache():
    """Clear the LLM keyword cache. Useful for testing or memory management."""
    global _llm_keyword_cache
    _llm_keyword_cache.clear()
    logger.debug("Cleared LLM keyword cache")