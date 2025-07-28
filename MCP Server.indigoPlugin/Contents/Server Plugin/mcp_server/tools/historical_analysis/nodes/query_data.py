"""
Data querying node for historical analysis.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

from ....common.influxdb import InfluxDBClient, InfluxDBQueryBuilder
from ....common.openai_client.main import perform_completion
from ..state import HistoricalAnalysisState


def query_data_node(state: HistoricalAnalysisState, logger: logging.Logger) -> Dict[str, Any]:
    """
    Query historical data from InfluxDB using LLM to recommend appropriate queries.
    
    Args:
        state: Current graph state
        logger: Logger instance
        
    Returns:
        Updated state with query results
    """
    logger.info(f"[historical_analysis] Querying data for {len(state['device_names'])} devices")
    
    try:
        influx_client = InfluxDBClient(logger=logger)
        query_builder = InfluxDBQueryBuilder(logger=logger)
        
        # Check if InfluxDB is available
        if not influx_client.is_enabled():
            return {
                **state,
                "query_success": False,
                "query_error": "InfluxDB is not enabled or configured",
                "raw_data": []
            }
        
        # Test connection
        if not influx_client.test_connection():
            return {
                **state,
                "query_success": False,
                "query_error": "Cannot connect to InfluxDB",
                "raw_data": []
            }
        
        # Use LLM to determine the best properties to query for each device
        device_queries = _get_llm_recommended_queries(
            state["query"], 
            state["device_names"], 
            state["time_range_days"],
            logger
        )
        
        # Execute queries for each device
        all_data = []
        successful_devices = []
        
        for device_name, properties in device_queries.items():
            logger.debug(f"[historical_analysis] Querying {device_name} for properties: {properties}")
            
            for prop in properties:
                try:
                    query = query_builder.build_device_history_query(
                        device_name=device_name,
                        device_property=prop,
                        time_range_days=state["time_range_days"]
                    )
                    
                    results = influx_client.execute_query(query)
                    
                    # Add metadata to each result
                    for result in results:
                        result["_device_name"] = device_name
                        result["_property"] = prop
                        result["_query_timestamp"] = datetime.now().isoformat()
                    
                    all_data.extend(results)
                    
                    if results and device_name not in successful_devices:
                        successful_devices.append(device_name)
                        
                except Exception as e:
                    logger.warning(f"[historical_analysis] Failed to query {device_name}.{prop}: {e}")
                    continue
        
        logger.info(f"[historical_analysis] Successfully queried {len(successful_devices)} devices, retrieved {len(all_data)} data points")
        
        return {
            **state,
            "raw_data": all_data,
            "query_success": True,
            "query_error": None,
            "devices_analyzed": successful_devices,
            "total_data_points": len(all_data)
        }
        
    except Exception as e:
        error_msg = f"Data querying failed: {str(e)}"
        logger.error(f"[historical_analysis] {error_msg}")
        
        return {
            **state,
            "query_success": False,
            "query_error": error_msg,
            "raw_data": []
        }


def _get_llm_recommended_queries(
    user_query: str, 
    device_names: List[str], 
    time_range_days: int,
    logger: logging.Logger
) -> Dict[str, List[str]]:
    """
    Use LLM to recommend which properties to query for each device.
    
    Args:
        user_query: User's natural language query
        device_names: List of device names
        time_range_days: Time range for analysis
        logger: Logger instance
        
    Returns:
        Dictionary mapping device names to list of properties to query
    """
    try:
        # Common device properties to consider
        common_properties = [
            "onState", "onOffState", "isPoweredOn",  # On/off states
            "brightness", "brightnessLevel",         # Dimmer levels
            "temperature", "temperatureInput1",      # Temperature sensors
            "humidity", "humidityInput1",            # Humidity sensors
            "sensorValue",                           # Generic sensor value
            "energyAccumTotal",                      # Energy monitoring
            "state"                                  # Generic state
        ]
        
        # Build prompt for LLM
        prompt = f"""
Analyze this user query and recommend which InfluxDB properties to query for each device:

User Query: "{user_query}"
Devices: {device_names}
Time Range: {time_range_days} days

Available InfluxDB properties to choose from:
{', '.join(common_properties)}

For each device, recommend 1-3 most relevant properties based on the user's query.
Consider:
- What the user is asking about (energy usage, on/off patterns, temperature trends, etc.)
- Typical device types (lights usually have onState/brightness, sensors have sensorValue, etc.)
- Avoid querying irrelevant properties

Respond with a JSON object mapping device names to arrays of property names:
{{
    "device_name_1": ["property1", "property2"],
    "device_name_2": ["property1"]
}}

Only include properties that are likely to exist and be relevant to the query.
"""
        
        # Get LLM recommendation
        response = perform_completion(
            messages=prompt,
            model="gpt-4o-mini"  # Use smaller model for this task
        )
        
        # Parse the response as JSON
        import json
        try:
            recommendations = json.loads(response)
            
            # Validate and filter recommendations
            filtered_recommendations = {}
            for device_name in device_names:
                if device_name in recommendations:
                    # Keep only valid properties
                    valid_props = [
                        prop for prop in recommendations[device_name] 
                        if prop in common_properties
                    ]
                    if valid_props:
                        filtered_recommendations[device_name] = valid_props
                    else:
                        # Fallback to common properties
                        filtered_recommendations[device_name] = ["onState", "state"]
                else:
                    # Fallback for devices not in recommendations
                    filtered_recommendations[device_name] = ["onState", "state"]
            
            logger.debug(f"[historical_analysis] LLM recommended queries: {filtered_recommendations}")
            return filtered_recommendations
            
        except json.JSONDecodeError:
            logger.warning(f"[historical_analysis] Failed to parse LLM response as JSON: {response}")
            # Fallback to default properties
            return {device: ["onState", "state"] for device in device_names}
        
    except Exception as e:
        logger.warning(f"[historical_analysis] LLM query recommendation failed: {e}")
        # Fallback to default properties for all devices
        return {device: ["onState", "state"] for device in device_names}