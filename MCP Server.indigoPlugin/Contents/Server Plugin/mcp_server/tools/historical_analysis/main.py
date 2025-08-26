"""
Main handler for historical data analysis.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ...adapters.data_provider import DataProvider
from ..base_handler import BaseToolHandler
from ...common.influxdb import InfluxDBClient, InfluxDBQueryBuilder
from ...common.openai_client.main import _get_client


# Alternative fields to try for device properties
_ALTERNATIVE_FIELDS = [
    "onState", "onOffState", "isPoweredOn",
    "brightness", "brightnessLevel",
    "temperature", "temperatureInput1", 
    "humidity", "humidityInput1",
    "sensorValue", "energyAccumTotal", "state"
]


class HistoricalAnalysisHandler(BaseToolHandler):
    """Handler for historical data analysis using direct InfluxDB queries."""
    
    def __init__(
        self,
        data_provider: DataProvider,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the historical analysis handler.
        
        Args:
            data_provider: Data provider for accessing entity data
            logger: Optional logger instance
        """
        super().__init__(tool_name="historical_analysis", logger=logger)
        self.data_provider = data_provider
    
    def analyze_historical_data(
        self,
        query: str,
        device_names: List[str],
        time_range_days: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze historical data for the specified devices.
        
        Args:
            query: User's natural language query about the data
            device_names: List of device names to analyze
            time_range_days: Number of days to analyze (default: 30)
            
        Returns:
            Dictionary with analysis results
        """
        start_time = time.time()
        
        try:
            self.info_log(f"Starting historical analysis for {len(device_names)} devices over {time_range_days} days")
            self.debug_log(f"Query: '{query}'")
            self.debug_log(f"Devices: {device_names}")
            
            # Validate inputs
            validation_error = self.validate_required_params(
                {"query": query, "device_names": device_names},
                ["query", "device_names"]
            )
            if validation_error:
                return validation_error
            
            if not device_names:
                return self.handle_exception(
                    ValueError("No device names provided"),
                    "validating input parameters"
                )
            
            if time_range_days <= 0 or time_range_days > 365:
                return self.handle_exception(
                    ValueError("Time range must be between 1 and 365 days"),
                    "validating time range"
                )
            
            # Validate device names exist
            validation_result = self._validate_device_names(device_names)
            if not validation_result["all_valid"]:
                return {
                    "success": False,
                    "error": validation_result["error_message"],
                    "tool": self.tool_name,
                    "report": validation_result["detailed_report"],
                    "valid_devices": validation_result["valid_devices"],
                    "invalid_devices": validation_result["invalid_devices"],
                    "suggestions": validation_result["suggestions"],
                    "analysis_duration_seconds": time.time() - start_time
                }
            
            # Check if InfluxDB is available
            if os.environ.get("INFLUXDB_ENABLED", "false").lower() != "true":
                self.warning_log("InfluxDB is not enabled - historical analysis not available")
                return {
                    "success": False,
                    "error": "InfluxDB is not enabled. Please enable InfluxDB in plugin configuration to use historical analysis.",
                    "tool": self.tool_name,
                    "report": "Historical analysis requires InfluxDB to be enabled and configured.",
                    "summary_stats": {},
                    "devices_analyzed": []
                }
            
            # Get historical data for all devices
            all_results = []
            devices_analyzed = []
            
            for device_name in device_names:
                self.debug_log(f"Querying historical data for device: {device_name}")
                
                # Use LLM to intelligently select device properties based on query
                device_results = []
                recommended_properties = self._get_recommended_properties(device_name, query)
                
                if recommended_properties:
                    self.info_log(f"LLM recommended properties for {device_name}: {recommended_properties}")
                    
                    # Try recommended properties in order
                    for device_property in recommended_properties:
                        try:
                            self.debug_log(f"Querying InfluxDB for {device_name}.{device_property}")
                            property_results = self._get_historical_device_data(
                                device_name, device_property, time_range_days
                            )
                            if property_results:
                                device_results.extend(property_results)
                                self.info_log(f"✅ Found {len(property_results)} records for {device_name}.{device_property}")
                                break  # Found data, stop trying other properties
                            else:
                                self.debug_log(f"❌ No data for {device_name}.{device_property}")
                        except Exception as e:
                            self.debug_log(f"❌ Error querying {device_name}.{device_property}: {e}")
                            continue
                
                # Fallback to predefined fields if LLM recommendations didn't work
                if not device_results:
                    self.debug_log(f"LLM recommendations failed, falling back to predefined properties: {_ALTERNATIVE_FIELDS}")
                    for device_property in _ALTERNATIVE_FIELDS:
                        try:
                            self.debug_log(f"Trying fallback property: {device_name}.{device_property}")
                            property_results = self._get_historical_device_data(
                                device_name, device_property, time_range_days
                            )
                            if property_results:
                                device_results.extend(property_results)
                                self.info_log(f"✅ Fallback success: Found {len(property_results)} records for {device_name}.{device_property}")
                                break  # Found data, stop trying other properties
                            else:
                                self.debug_log(f"❌ No fallback data for {device_name}.{device_property}")
                        except Exception as e:
                            self.debug_log(f"❌ Fallback error for {device_name}.{device_property}: {e}")
                            continue
                
                if device_results:
                    all_results.extend(device_results)
                    devices_analyzed.append(device_name)
            
            # Calculate analysis duration
            analysis_duration = time.time() - start_time
            
            # Create summary statistics
            summary_stats = {
                "total_state_changes": len(all_results),
                "devices_with_data": len(devices_analyzed),
                "analysis_period_days": time_range_days,
                "analysis_duration_seconds": analysis_duration
            }
            
            # Format report
            if all_results:
                report_lines = [f"Historical analysis for {len(devices_analyzed)} devices over {time_range_days} days:"]
                report_lines.extend(all_results)
                report = "\n".join(report_lines)
                
                self.info_log(f"Analysis completed successfully in {analysis_duration:.2f}s")
                return self.create_success_response(
                    data={
                        "report": report,
                        "summary_stats": summary_stats,
                        "devices_analyzed": devices_analyzed,
                        "total_data_points": len(all_results),
                        "time_range_days": time_range_days,
                        "analysis_duration_seconds": analysis_duration
                    },
                    message=f"Analyzed {len(all_results)} state changes from {len(devices_analyzed)} devices"
                )
            else:
                self.warning_log("No historical data found for any devices")
                return {
                    "success": False,
                    "error": "No historical data found for the specified devices",
                    "tool": self.tool_name,
                    "report": "No historical data was found for any of the specified devices in the given time range.",
                    "summary_stats": summary_stats,
                    "devices_analyzed": [],
                    "analysis_duration_seconds": analysis_duration
                }
            
        except Exception as e:
            analysis_duration = time.time() - start_time
            return self.handle_exception(e, f"analyzing historical data (duration: {analysis_duration:.2f}s)")
    
    def _get_historical_device_data(
        self, device_name: str, device_property: str, time_range_days: int = 60
    ) -> List[str]:
        """
        Query InfluxDB for historical device data and return formatted results.
        
        Args:
            device_name: The device name to query data for
            device_property: The device property to query data for
            time_range_days: Number of days to look back for historical data
            
        Returns:
            List of formatted messages describing device state changes
        """
        try:
            client = InfluxDBClient(logger=self.logger)
            query_builder = InfluxDBQueryBuilder(logger=self.logger)
            
            if not client.is_enabled() or not client.test_connection():
                return []
            
            # Build and execute query
            query = query_builder.build_device_history_query(
                device_name=device_name,
                device_property=device_property,
                time_range_days=time_range_days
            )
            
            results = client.execute_query(query)
            if not results:
                self.debug_log(f"InfluxDB query returned no results for {device_name}.{device_property}")
                return []
            
            self.debug_log(f"InfluxDB returned {len(results)} raw records for {device_name}.{device_property}")
            
            # Convert to formatted state change messages
            formatted_results = []
            saved_state = None
            from_timestamp = None
            
            for data_record in results:
                record_time_str = data_record.get("time")
                if not record_time_str:
                    continue
                
                timestamp_local = self._convert_to_local_timezone(record_time_str)
                field_value = data_record.get(device_property)
                
                if saved_state is None:
                    from_timestamp = timestamp_local
                    saved_state = field_value
                elif saved_state != field_value and from_timestamp is not None:
                    delta_hours, delta_minutes, delta_seconds = self._get_delta_summary(
                        from_timestamp, timestamp_local
                    )
                    message = (
                        f"{device_name} was {self._format_state_value(saved_state)} for {delta_hours} hours, "
                        f"{delta_minutes} minutes, and {delta_seconds} seconds, "
                        f"from {from_timestamp} to {timestamp_local}"
                    )
                    formatted_results.append(message)
                    self.debug_log(message)
                    from_timestamp = timestamp_local
                    saved_state = field_value
            
            # Handle final state (ongoing until now)
            to_timestamp = datetime.now().astimezone()
            if from_timestamp is not None:
                delta_hours, delta_minutes, delta_seconds = self._get_delta_summary(
                    from_timestamp, to_timestamp
                )
                final_state = self._format_state_value(saved_state)
                message = (
                    f"{device_name} was {final_state} for {delta_hours} hours, "
                    f"{delta_minutes} minutes, and {delta_seconds} seconds, "
                    f"from {from_timestamp} to {to_timestamp}"
                )
                formatted_results.append(message)
            
            return formatted_results
            
        except Exception as e:
            self.debug_log(f"Error querying {device_name}.{device_property}: {e}")
            return []
    
    def _get_delta_summary(self, start_time: datetime, end_time: datetime) -> Tuple[int, int, int]:
        """
        Calculate the difference between two datetime objects.
        
        Args:
            start_time: The start time
            end_time: The end time
            
        Returns:
            Tuple of hours, minutes, and seconds of the time difference
        """
        delta = end_time - start_time
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        seconds = int(round(delta.total_seconds() % 60))
        return hours, minutes, seconds
    
    def _convert_to_local_timezone(self, datetime_str: str) -> datetime:
        """
        Convert an ISO formatted UTC datetime string to a local timezone-aware datetime object.
        
        Args:
            datetime_str: Datetime string in ISO format (ending with 'Z')
            
        Returns:
            Local timezone-aware datetime object
        """
        utc_datetime = datetime.fromisoformat(datetime_str.rstrip("Z")).replace(
            tzinfo=ZoneInfo("UTC")
        )
        local_datetime = utc_datetime.astimezone()
        return local_datetime
    
    def _format_state_value(self, value) -> str:
        """
        Format state value for display.
        
        Args:
            value: Raw state value
            
        Returns:
            Formatted state string
        """
        if value is None:
            return "unknown"
        elif isinstance(value, bool):
            return "on" if value else "off"
        elif isinstance(value, (int, float)):
            if value in [0, 0.0]:
                return "off"
            elif value in [1, 1.0]:
                return "on"
            else:
                return str(value)
        else:
            return str(value)
    
    def get_available_devices(self) -> List[str]:
        """
        Get list of available devices for analysis.
        
        Returns:
            List of device names
        """
        try:
            # Get devices from data provider
            devices = self.data_provider.get_all_devices()
            device_names = [device.get("name", "") for device in devices if device.get("name")]
            
            self.debug_log(f"Found {len(device_names)} available devices")
            return device_names
            
        except Exception as e:
            self.error_log(f"Failed to get available devices: {e}")
            return []
    
    def is_influxdb_available(self) -> bool:
        """
        Check if InfluxDB is available for historical analysis.
        
        Returns:
            True if InfluxDB is enabled and configured
        """
        try:
            if os.environ.get("INFLUXDB_ENABLED", "false").lower() != "true":
                return False
            
            client = InfluxDBClient(logger=self.logger)
            return client.test_connection()
            
        except Exception as e:
            self.debug_log(f"InfluxDB availability check failed: {e}")
            return False
    
    def _get_device_properties(self, device_name: str) -> List[str]:
        """
        Get all available properties for a device.
        
        Args:
            device_name: Name of the device
            
        Returns:
            List of property names for the device
        """
        try:
            # Get device from data provider
            devices = self.data_provider.get_all_devices()
            target_device = None
            
            for device in devices:
                if device.get("name") == device_name:
                    target_device = device
                    break
            
            if not target_device:
                self.debug_log(f"Device '{device_name}' not found")
                return _ALTERNATIVE_FIELDS  # Fallback to predefined fields
            
            # Extract all properties that have values (excluding system/meta properties)
            properties = []
            excluded_props = {
                'id', 'name', 'deviceTypeId', 'pluginId', 'pluginProps', 
                'sharedProps', 'globalProps', 'errorState', 'configured',
                'enabled', 'version', 'protocol', 'address', 'description',
                'model', 'remoteDisplay', 'allowSensorValueChange',
                'allowOnStateChange', 'supportsStatusRequest', 'buttonGroupCount',
                'supportsAllOff', 'supportsAllLightsOnOff', 'folderId', 'subModel',
                'subType', 'lastChanged', 'lastSuccessfulComm', 'ownerProps',
                'energyAccumBaseTime', 'energyAccumTimeDelta'
            }
            
            # First, extract properties from states dictionary (highest priority for historical analysis)
            states_dict = target_device.get('states', {})
            if isinstance(states_dict, dict):
                self.debug_log(f"Found states dictionary with {len(states_dict)} entries")
                for state_key, state_value in states_dict.items():
                    # Skip nested state properties (like state.on, state.off)
                    if '.' not in state_key and self._is_valid_property_value(state_value):
                        properties.append(state_key)
                        self.debug_log(f"Added state property: {state_key} = {state_value}")
            
            # Then, extract top-level properties (lower priority)
            for key, value in target_device.items():
                # Include properties that are likely state/sensor values
                if (key not in excluded_props and 
                    key != 'states' and  # Skip states dict itself
                    value is not None and 
                    not key.startswith('_') and
                    self._is_valid_property_value(value)):
                    # Only add if not already found in states
                    if key not in properties:
                        properties.append(key)
            
            self.debug_log(f"Found {len(properties)} properties for {device_name}: {properties}")
            
            # Always include common fallback properties if not already present
            for prop in _ALTERNATIVE_FIELDS:
                if prop not in properties:
                    properties.append(prop)
            
            return properties
            
        except Exception as e:
            self.debug_log(f"Error getting properties for {device_name}: {e}")
            return _ALTERNATIVE_FIELDS  # Fallback to predefined fields
    
    def _get_recommended_properties(self, device_name: str, user_query: str) -> List[str]:
        """
        Use LLM to recommend device properties to analyze based on user query.
        
        Args:
            device_name: Name of the device
            user_query: User's analysis query
            
        Returns:
            List of 1-3 recommended property names, ordered by relevance
        """
        try:
            # Get all available properties for the device
            available_properties = self._get_device_properties(device_name)
            
            if not available_properties:
                self.debug_log(f"No properties found for device '{device_name}'")
                return []
            
            # Create LLM prompt
            properties_str = ", ".join(available_properties)
            
            system_prompt = """You are an expert in Indigo home automation system analysis. 
Given a user's query about analyzing historical data for a device, recommend the most relevant device properties to query.

Rules:
- Return 1-3 property names that best match the user's query
- Return properties in order of relevance (most relevant first)  
- Only return properties from the provided list
- Properties may come from device states or top-level properties
- For presence/occupancy queries, prioritize: onOffState, displayState, state, pending, presence
- For general queries about "state changes" or "activity", prioritize: onState, onOffState, displayState, state
- For brightness/dimming queries, prioritize: brightness, brightnessLevel  
- For temperature queries, prioritize: temperature, temperatureInput1
- For humidity queries, prioritize: humidity, humidityInput1
- For sensor queries, prioritize: sensorValue, state, displayState
- For energy/power queries, prioritize: energyAccumTotal, realPower, accumEnergyTotal
- For timer/persistence devices, prioritize: onOffState, displayState, state, pending

Return only the property names, separated by commas, no explanations."""

            user_prompt = f"""Device: {device_name}
Available properties: {properties_str}
User query: "{user_query}"

Recommend 1-3 most relevant properties:"""

            # Get OpenAI client
            try:
                client = _get_client()
            except Exception as e:
                self.debug_log(f"OpenAI client not available: {e}, using fallback properties")
                return _ALTERNATIVE_FIELDS[:3]
            
            # Make LLM call
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            # Parse response
            recommendations = response.choices[0].message.content.strip()
            recommended_properties = [prop.strip() for prop in recommendations.split(",")]
            
            # Validate recommendations are in available properties
            valid_properties = []
            for prop in recommended_properties:
                if prop in available_properties:
                    valid_properties.append(prop)
            
            if valid_properties:
                self.debug_log(f"LLM recommended {len(valid_properties)} properties for '{user_query}': {valid_properties}")
                return valid_properties[:3]  # Max 3 properties
            else:
                self.debug_log("LLM recommendations were not valid, using fallback")
                return _ALTERNATIVE_FIELDS[:3]
                
        except Exception as e:
            self.debug_log(f"Error getting LLM recommendations for {device_name}: {e}")
            return _ALTERNATIVE_FIELDS[:3]  # Fallback to first 3 predefined fields
    
    def _validate_device_names(self, device_names: List[str]) -> Dict[str, Any]:
        """
        Validate that all device names exist in the Indigo system.
        
        Args:
            device_names: List of device names to validate
            
        Returns:
            Dictionary with validation results and suggestions
        """
        try:
            # Get all available devices
            all_devices = self.data_provider.get_all_devices()
            existing_device_names = {device.get("name", "") for device in all_devices if device.get("name")}
            
            valid_devices = []
            invalid_devices = []
            suggestions = []
            
            # Check each device name
            for device_name in device_names:
                if device_name in existing_device_names:
                    valid_devices.append(device_name)
                else:
                    invalid_devices.append(device_name)
                    
                    # Find similar device names for suggestions
                    similar_names = self._find_similar_device_names(device_name, existing_device_names)
                    if similar_names:
                        suggestions.append({
                            "invalid_name": device_name,
                            "suggestions": similar_names[:3]  # Top 3 suggestions
                        })
            
            all_valid = len(invalid_devices) == 0
            
            if all_valid:
                return {
                    "all_valid": True,
                    "valid_devices": valid_devices,
                    "invalid_devices": [],
                    "suggestions": [],
                    "error_message": "",
                    "detailed_report": ""
                }
            else:
                # Create detailed error report
                error_lines = [f"Device validation failed. {len(invalid_devices)} of {len(device_names)} devices not found:"]
                
                for invalid_device in invalid_devices:
                    error_lines.append(f"  ❌ '{invalid_device}' - NOT FOUND")
                    
                    # Add suggestions if available
                    device_suggestions = next(
                        (item["suggestions"] for item in suggestions if item["invalid_name"] == invalid_device),
                        []
                    )
                    if device_suggestions:
                        error_lines.append(f"     💡 Did you mean: {', '.join(device_suggestions)}")
                
                if valid_devices:
                    error_lines.append(f"\n✅ Valid devices found: {', '.join(valid_devices)}")
                
                error_lines.extend([
                    "\n📋 To find correct device names, use:",
                    "  • search_entities('your device description')",
                    "  • list_devices() to see all devices",
                    "  • get_devices_by_type('device_type') for specific types"
                ])
                
                detailed_report = "\n".join(error_lines)
                error_message = f"Invalid device names: {', '.join(invalid_devices)}. Use search_entities or list_devices to find correct names."
                
                return {
                    "all_valid": False,
                    "valid_devices": valid_devices,
                    "invalid_devices": invalid_devices,
                    "suggestions": suggestions,
                    "error_message": error_message,
                    "detailed_report": detailed_report
                }
                
        except Exception as e:
            self.error_log(f"Error validating device names: {e}")
            return {
                "all_valid": True,  # Allow processing to continue on validation errors
                "valid_devices": device_names,
                "invalid_devices": [],
                "suggestions": [],
                "error_message": "",
                "detailed_report": ""
            }
    
    def _find_similar_device_names(self, target_name: str, existing_names: set) -> List[str]:
        """
        Find device names similar to the target name using simple string matching.
        
        Args:
            target_name: The device name to find matches for
            existing_names: Set of all existing device names
            
        Returns:
            List of similar device names, sorted by relevance
        """
        try:
            target_lower = target_name.lower()
            target_words = set(target_lower.split())
            
            matches = []
            
            for name in existing_names:
                if not name:
                    continue
                    
                name_lower = name.lower()
                name_words = set(name_lower.split())
                
                # Calculate similarity score
                score = 0
                
                # Exact substring match (highest score)
                if target_lower in name_lower or name_lower in target_lower:
                    score += 100
                
                # Word overlap
                common_words = target_words.intersection(name_words)
                if common_words:
                    word_score = len(common_words) * 10
                    score += word_score
                
                # Character similarity (simple approach)
                if len(target_name) > 2 and len(name) > 2:
                    common_chars = set(target_lower).intersection(set(name_lower))
                    char_score = len(common_chars)
                    score += char_score
                
                if score > 0:
                    matches.append((name, score))
            
            # Sort by score (highest first) and return names only
            matches.sort(key=lambda x: x[1], reverse=True)
            return [match[0] for match in matches[:5]]  # Top 5 matches
            
        except Exception as e:
            self.debug_log(f"Error finding similar device names: {e}")
            return []
    
    def _is_valid_property_value(self, value) -> bool:
        """
        Check if a property value is suitable for historical analysis.
        
        Args:
            value: Property value to check
            
        Returns:
            True if value is suitable for historical tracking
        """
        if value is None:
            return False
        
        # Accept basic data types
        if isinstance(value, (int, float, bool)):
            return True
        
        # Accept strings but filter out very long ones (likely descriptions/configs)
        if isinstance(value, str):
            if len(value) > 100:  # Skip long strings
                return False
            # Skip obvious non-state values
            if value.lower() in {'plugin', 'device', 'none', 'null', ''}:
                return False
            return True
        
        # Reject complex objects
        return False