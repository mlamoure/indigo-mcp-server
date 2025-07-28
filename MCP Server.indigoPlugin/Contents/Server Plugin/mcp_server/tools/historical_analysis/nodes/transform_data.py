"""
Data transformation node for historical analysis.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
import pandas as pd

from ....common.influxdb.time_utils import TimeFormatter
from ..state import HistoricalAnalysisState


def transform_data_node(state: HistoricalAnalysisState, logger: logging.Logger) -> Dict[str, Any]:
    """
    Transform and clean the raw data from InfluxDB.
    
    Args:
        state: Current graph state
        logger: Logger instance
        
    Returns:
        Updated state with transformed data
    """
    logger.info(f"[historical_analysis] Transforming {len(state['raw_data'])} data points")
    
    try:
        raw_data = state["raw_data"]
        
        if not raw_data:
            return {
                **state,
                "processed_data": [],
                "transform_success": True,
                "transform_error": None
            }
        
        time_formatter = TimeFormatter(logger=logger)
        processed_data = []
        
        # Group data by device and property
        device_data = {}
        for record in raw_data:
            device_name = record.get("_device_name", "unknown")
            property_name = record.get("_property", "unknown")
            
            key = f"{device_name}.{property_name}"
            if key not in device_data:
                device_data[key] = []
            device_data[key].append(record)
        
        # Process each device-property combination
        for key, records in device_data.items():
            device_name, property_name = key.split(".", 1)
            
            logger.debug(f"[historical_analysis] Processing {len(records)} records for {key}")
            
            # Sort records by time
            sorted_records = sorted(records, key=lambda x: x.get("time", ""))
            
            # Convert to state duration format (similar to previous implementation)
            state_durations = _convert_to_state_durations(
                sorted_records, 
                device_name, 
                property_name, 
                time_formatter,
                logger
            )
            
            processed_data.extend(state_durations)
        
        logger.info(f"[historical_analysis] Transformed data into {len(processed_data)} state duration records")
        
        return {
            **state,
            "processed_data": processed_data,
            "transform_success": True,
            "transform_error": None
        }
        
    except Exception as e:
        error_msg = f"Data transformation failed: {str(e)}"
        logger.error(f"[historical_analysis] {error_msg}")
        
        return {
            **state,
            "processed_data": [],
            "transform_success": False,
            "transform_error": error_msg
        }


def _convert_to_state_durations(
    records: List[Dict[str, Any]], 
    device_name: str, 
    property_name: str,
    time_formatter: TimeFormatter,
    logger: logging.Logger
) -> List[Dict[str, Any]]:
    """
    Convert time-series records to state duration records.
    
    Args:
        records: Sorted list of time-series records
        device_name: Name of the device
        property_name: Name of the property
        time_formatter: Time formatting utility
        logger: Logger instance
        
    Returns:
        List of state duration records
    """
    if not records:
        return []
    
    durations = []
    current_state = None
    state_start_time = None
    
    try:
        for i, record in enumerate(records):
            timestamp_str = record.get("time", "")
            if not timestamp_str:
                continue
            
            # Get the property value
            state_value = record.get(property_name)
            if state_value is None:
                continue
            
            # Convert timestamp
            timestamp = time_formatter.convert_to_local_timezone(timestamp_str)
            
            # Normalize state value
            normalized_state = _normalize_state_value(state_value)
            
            # If this is the first record or state changed
            if current_state is None:
                current_state = normalized_state
                state_start_time = timestamp
            elif current_state != normalized_state:
                # State changed - record the previous duration
                if state_start_time:
                    hours, minutes, seconds = time_formatter.get_delta_summary(state_start_time, timestamp)
                    
                    duration_record = {
                        "device_name": device_name,
                        "property": property_name,
                        "state": current_state,
                        "start_time": state_start_time.isoformat(),
                        "end_time": timestamp.isoformat(),
                        "duration_hours": hours,
                        "duration_minutes": minutes,
                        "duration_seconds": seconds,
                        "total_duration_seconds": hours * 3600 + minutes * 60 + seconds,
                        "formatted_message": time_formatter.format_device_state_message(
                            device_name, current_state, state_start_time, timestamp
                        )
                    }
                    durations.append(duration_record)
                
                # Start tracking the new state
                current_state = normalized_state
                state_start_time = timestamp
        
        # Handle the final state (ongoing until now)
        if current_state is not None and state_start_time:
            end_time = datetime.now().astimezone()
            hours, minutes, seconds = time_formatter.get_delta_summary(state_start_time, end_time)
            
            final_duration_record = {
                "device_name": device_name,
                "property": property_name,
                "state": current_state,
                "start_time": state_start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_hours": hours,
                "duration_minutes": minutes,
                "duration_seconds": seconds,
                "total_duration_seconds": hours * 3600 + minutes * 60 + seconds,
                "formatted_message": time_formatter.format_device_state_message(
                    device_name, current_state, state_start_time, end_time
                ),
                "is_current_state": True
            }
            durations.append(final_duration_record)
        
        logger.debug(f"[historical_analysis] Converted {len(records)} records to {len(durations)} state durations for {device_name}.{property_name}")
        
    except Exception as e:
        logger.error(f"[historical_analysis] Error converting to state durations: {e}")
    
    return durations


def _normalize_state_value(value: Any) -> str:
    """
    Normalize state values to consistent string representation.
    
    Args:
        value: Raw state value from InfluxDB
        
    Returns:
        Normalized state string
    """
    if value is None:
        return "unknown"
    
    # Handle boolean values
    if isinstance(value, bool):
        return "on" if value else "off"
    
    # Handle numeric values
    if isinstance(value, (int, float)):
        if value == 0 or value == 0.0:
            return "off"
        elif value == 1 or value == 1.0:
            return "on"
        else:
            # For brightness levels, etc.
            return str(value)
    
    # Handle string values
    if isinstance(value, str):
        value_lower = value.lower().strip()
        
        # Common state mappings
        if value_lower in ["true", "1", "on", "active", "enabled"]:
            return "on"
        elif value_lower in ["false", "0", "off", "inactive", "disabled"]:
            return "off"
        else:
            return value_lower
    
    # Default to string representation
    return str(value)