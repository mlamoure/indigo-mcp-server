"""
Main handler for historical data analysis using LangGraph.
"""

import logging
import time
from typing import Dict, Any, List, Optional

from ...adapters.data_provider import DataProvider
from ..base_handler import BaseToolHandler
from .graph import HistoricalAnalysisGraph
from .state import HistoricalAnalysisState


class HistoricalAnalysisHandler(BaseToolHandler):
    """Handler for historical data analysis with LangGraph workflow."""
    
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
        self.graph = HistoricalAnalysisGraph(self.logger)
    
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
            import os
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
            
            # Create initial state
            initial_state: HistoricalAnalysisState = {
                "query": query,
                "device_names": device_names,
                "time_range_days": time_range_days,
                "raw_data": [],
                "query_success": False,
                "query_error": None,
                "processed_data": [],
                "transform_success": False,
                "transform_error": None,
                "analysis_results": {},
                "analysis_success": False,
                "analysis_error": None,
                "formatted_report": "",
                "summary_stats": {},
                "total_data_points": 0,
                "devices_analyzed": [],
                "analysis_duration_seconds": 0.0
            }
            
            # Execute the LangGraph workflow
            self.info_log("Executing LangGraph workflow")
            final_state = self.graph.execute(initial_state)
            
            # Calculate analysis duration
            analysis_duration = time.time() - start_time
            final_state["analysis_duration_seconds"] = analysis_duration
            
            # Log results
            self._log_analysis_results(final_state)
            
            # Create response
            if final_state["analysis_success"]:
                self.info_log(f"Analysis completed successfully in {analysis_duration:.2f}s")
                
                # Update summary stats with analysis period
                summary_stats = final_state.get("summary_stats", {})
                summary_stats["analysis_period_days"] = time_range_days
                summary_stats["analysis_duration_seconds"] = analysis_duration
                
                return self.create_success_response(
                    data={
                        "report": final_state["formatted_report"],
                        "summary_stats": summary_stats,
                        "analysis_results": final_state["analysis_results"],
                        "devices_analyzed": final_state["devices_analyzed"],
                        "total_data_points": final_state["total_data_points"],
                        "time_range_days": time_range_days,
                        "analysis_duration_seconds": analysis_duration
                    },
                    message=f"Analyzed {final_state['total_data_points']} data points from {len(final_state['devices_analyzed'])} devices"
                )
            else:
                # Collect all errors
                errors = []
                if final_state.get("query_error"):
                    errors.append(f"Query: {final_state['query_error']}")
                if final_state.get("transform_error"):
                    errors.append(f"Transform: {final_state['transform_error']}")
                if final_state.get("analysis_error"):
                    errors.append(f"Analysis: {final_state['analysis_error']}")
                
                error_message = "; ".join(errors) if errors else "Unknown analysis error"
                
                return {
                    "success": False,
                    "error": error_message,
                    "tool": self.tool_name,
                    "report": final_state.get("formatted_report", "Analysis failed"),
                    "summary_stats": final_state.get("summary_stats", {}),
                    "devices_analyzed": final_state.get("devices_analyzed", []),
                    "analysis_duration_seconds": analysis_duration
                }
            
        except Exception as e:
            analysis_duration = time.time() - start_time
            return self.handle_exception(e, f"analyzing historical data (duration: {analysis_duration:.2f}s)")
    
    def _log_analysis_results(self, final_state: HistoricalAnalysisState) -> None:
        """
        Log the results of the analysis.
        
        Args:
            final_state: Final state from the workflow
        """
        try:
            # Log workflow step results
            if final_state.get("query_success"):
                self.info_log(f"Data query: SUCCESS - {final_state['total_data_points']} data points")
            else:
                self.warning_log(f"Data query: FAILED - {final_state.get('query_error', 'Unknown error')}")
            
            if final_state.get("transform_success"):
                processed_count = len(final_state.get("processed_data", []))
                self.info_log(f"Data transform: SUCCESS - {processed_count} processed records")
            else:
                self.warning_log(f"Data transform: FAILED - {final_state.get('transform_error', 'Unknown error')}")
            
            if final_state.get("analysis_success"):
                devices_count = len(final_state.get("devices_analyzed", []))
                self.info_log(f"Data analysis: SUCCESS - {devices_count} devices analyzed")
            else:
                self.warning_log(f"Data analysis: FAILED - {final_state.get('analysis_error', 'Unknown error')}")
            
            # Log summary statistics
            summary = final_state.get("summary_stats", {})
            if summary:
                self.info_log(f"Summary: {summary.get('total_state_changes', 0)} state changes, "
                             f"{summary.get('total_on_time_hours', 0):.1f} hours active")
        
        except Exception as e:
            self.warning_log(f"Failed to log analysis results: {e}")
    
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
            import os
            from ...common.influxdb import InfluxDBClient
            
            if os.environ.get("INFLUXDB_ENABLED", "false").lower() != "true":
                return False
            
            client = InfluxDBClient(logger=self.logger)
            return client.test_connection()
            
        except Exception as e:
            self.debug_log(f"InfluxDB availability check failed: {e}")
            return False