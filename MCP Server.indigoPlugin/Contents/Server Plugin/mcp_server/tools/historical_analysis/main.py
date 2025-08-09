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
                
                # Try different device properties to find data
                device_results = []
                for device_property in _ALTERNATIVE_FIELDS:
                    try:
                        property_results = self._get_historical_device_data(
                            device_name, device_property, time_range_days
                        )
                        if property_results:
                            device_results.extend(property_results)
                            self.debug_log(f"Found {len(property_results)} records for {device_name}.{device_property}")
                            break  # Found data, stop trying other properties
                    except Exception as e:
                        self.debug_log(f"No data for {device_name}.{device_property}: {e}")
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
                return []
            
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
            devices = self.data_provider.get_devices()
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