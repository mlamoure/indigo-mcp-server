"""
State definitions for the historical analysis LangGraph.
"""

from typing import TypedDict, List, Dict, Any, Optional


class HistoricalAnalysisState(TypedDict):
    """State for the historical analysis graph."""
    
    # Input parameters
    query: str  # User's natural language query
    device_names: List[str]  # List of device names to analyze
    time_range_days: int  # Number of days to analyze
    
    # Query results
    raw_data: List[Dict[str, Any]]  # Raw data from InfluxDB
    query_success: bool  # Whether data querying succeeded
    query_error: Optional[str]  # Error message if querying failed
    
    # Transformed data
    processed_data: List[Dict[str, Any]]  # Cleaned and processed data
    transform_success: bool  # Whether data transformation succeeded
    transform_error: Optional[str]  # Error message if transformation failed
    
    # Analysis results
    analysis_results: Dict[str, Any]  # Analysis insights and statistics
    analysis_success: bool  # Whether analysis succeeded
    analysis_error: Optional[str]  # Error message if analysis failed
    
    # Final output
    formatted_report: str  # Human-readable analysis report
    summary_stats: Dict[str, Any]  # Summary statistics
    
    # Metadata
    total_data_points: int  # Number of data points analyzed
    devices_analyzed: List[str]  # Devices that had data
    analysis_duration_seconds: float  # Time taken for analysis