"""
Data analysis node for historical analysis.
"""

import logging
from typing import Dict, Any, List
from collections import defaultdict, Counter
import statistics

from ....common.openai_client.main import perform_completion
from ..state import HistoricalAnalysisState


def analyze_data_node(state: HistoricalAnalysisState, logger: logging.Logger) -> Dict[str, Any]:
    """
    Analyze the processed data and generate insights.
    
    Args:
        state: Current graph state
        logger: Logger instance
        
    Returns:
        Updated state with analysis results
    """
    logger.info(f"[historical_analysis] Analyzing {len(state['processed_data'])} processed records")
    
    try:
        processed_data = state["processed_data"]
        
        if not processed_data:
            return {
                **state,
                "analysis_results": {},
                "analysis_success": True,
                "analysis_error": None,
                "formatted_report": "No data available for analysis.",
                "summary_stats": {}
            }
        
        # Perform statistical analysis
        stats = _calculate_statistics(processed_data, logger)
        
        # Generate patterns and insights
        patterns = _identify_patterns(processed_data, logger)
        
        # Create summary statistics
        summary = _create_summary_stats(processed_data, stats, patterns, logger)
        
        # Generate human-readable report using LLM
        report = _generate_llm_report(
            state["query"], 
            processed_data, 
            stats, 
            patterns, 
            state["time_range_days"],
            logger
        )
        
        analysis_results = {
            "statistics": stats,
            "patterns": patterns,
            "device_summaries": _create_device_summaries(processed_data, logger)
        }
        
        logger.info(f"[historical_analysis] Analysis completed with {len(stats)} statistical measures")
        
        return {
            **state,
            "analysis_results": analysis_results,
            "analysis_success": True,
            "analysis_error": None,
            "formatted_report": report,
            "summary_stats": summary
        }
        
    except Exception as e:
        error_msg = f"Data analysis failed: {str(e)}"
        logger.error(f"[historical_analysis] {error_msg}")
        
        return {
            **state,
            "analysis_results": {},
            "analysis_success": False,
            "analysis_error": error_msg,
            "formatted_report": f"Analysis failed: {error_msg}",
            "summary_stats": {}
        }


def _calculate_statistics(data: List[Dict[str, Any]], logger: logging.Logger) -> Dict[str, Any]:
    """
    Calculate statistical measures from the processed data.
    
    Args:
        data: List of processed data records
        logger: Logger instance
        
    Returns:
        Dictionary of statistical measures
    """
    try:
        # Group by device and state
        device_stats = defaultdict(lambda: defaultdict(list))
        
        for record in data:
            device = record["device_name"]
            state = record["state"]
            duration = record["total_duration_seconds"]
            
            device_stats[device][state].append(duration)
        
        # Calculate statistics for each device and state
        stats = {}
        for device, states in device_stats.items():
            stats[device] = {}
            
            for state, durations in states.items():
                if durations:
                    stats[device][state] = {
                        "count": len(durations),
                        "total_duration_seconds": sum(durations),
                        "average_duration_seconds": statistics.mean(durations),
                        "median_duration_seconds": statistics.median(durations),
                        "min_duration_seconds": min(durations),
                        "max_duration_seconds": max(durations),
                        "total_duration_hours": sum(durations) / 3600
                    }
                    
                    # Add standard deviation if more than one duration
                    if len(durations) > 1:
                        stats[device][state]["std_dev_seconds"] = statistics.stdev(durations)
        
        logger.debug(f"[historical_analysis] Calculated statistics for {len(stats)} devices")
        return stats
        
    except Exception as e:
        logger.error(f"[historical_analysis] Error calculating statistics: {e}")
        return {}


def _identify_patterns(data: List[Dict[str, Any]], logger: logging.Logger) -> Dict[str, Any]:
    """
    Identify patterns in the device behavior.
    
    Args:
        data: List of processed data records
        logger: Logger instance
        
    Returns:
        Dictionary of identified patterns
    """
    try:
        patterns = {
            "most_active_devices": [],
            "longest_on_periods": [],
            "shortest_on_periods": [],
            "state_change_frequency": {},
            "usage_trends": {}
        }
        
        # Analyze device activity
        device_activity = defaultdict(lambda: {"total_on_time": 0, "state_changes": 0, "on_periods": []})
        
        for record in data:
            device = record["device_name"]
            state = record["state"]
            duration = record["total_duration_seconds"]
            
            device_activity[device]["state_changes"] += 1
            
            if state == "on":
                device_activity[device]["total_on_time"] += duration
                device_activity[device]["on_periods"].append(duration)
        
        # Sort devices by activity
        sorted_devices = sorted(
            device_activity.items(),
            key=lambda x: x[1]["total_on_time"],
            reverse=True
        )
        
        patterns["most_active_devices"] = [
            {
                "device": device,
                "total_on_hours": info["total_on_time"] / 3600,
                "state_changes": info["state_changes"]
            }
            for device, info in sorted_devices[:5]  # Top 5
        ]
        
        # Find longest and shortest on periods
        all_on_periods = []
        for device, info in device_activity.items():
            for duration in info["on_periods"]:
                all_on_periods.append({"device": device, "duration_seconds": duration})
        
        if all_on_periods:
            # Sort by duration
            sorted_periods = sorted(all_on_periods, key=lambda x: x["duration_seconds"])
            
            patterns["longest_on_periods"] = [
                {
                    "device": period["device"],
                    "duration_hours": period["duration_seconds"] / 3600
                }
                for period in sorted_periods[-3:]  # Top 3 longest
            ]
            
            patterns["shortest_on_periods"] = [
                {
                    "device": period["device"],
                    "duration_seconds": period["duration_seconds"]
                }
                for period in sorted_periods[:3]  # Top 3 shortest
            ]
        
        # Calculate state change frequency
        patterns["state_change_frequency"] = {
            device: info["state_changes"]
            for device, info in device_activity.items()
        }
        
        logger.debug(f"[historical_analysis] Identified patterns for {len(device_activity)} devices")
        return patterns
        
    except Exception as e:
        logger.error(f"[historical_analysis] Error identifying patterns: {e}")
        return {}


def _create_device_summaries(data: List[Dict[str, Any]], logger: logging.Logger) -> Dict[str, Any]:
    """
    Create summaries for each device.
    
    Args:
        data: List of processed data records
        logger: Logger instance
        
    Returns:
        Dictionary of device summaries
    """
    try:
        summaries = {}
        device_data = defaultdict(list)
        
        # Group data by device
        for record in data:
            device_data[record["device_name"]].append(record)
        
        # Create summary for each device
        for device, records in device_data.items():
            on_records = [r for r in records if r["state"] == "on"]
            off_records = [r for r in records if r["state"] == "off"]
            
            total_on_time = sum(r["total_duration_seconds"] for r in on_records)
            total_off_time = sum(r["total_duration_seconds"] for r in off_records)
            total_time = total_on_time + total_off_time
            
            summaries[device] = {
                "total_records": len(records),
                "on_periods": len(on_records),
                "off_periods": len(off_records),
                "total_on_hours": total_on_time / 3600,
                "total_off_hours": total_off_time / 3600,
                "usage_percentage": (total_on_time / total_time * 100) if total_time > 0 else 0,
                "average_on_duration_minutes": (total_on_time / len(on_records) / 60) if on_records else 0,
                "average_off_duration_minutes": (total_off_time / len(off_records) / 60) if off_records else 0
            }
        
        logger.debug(f"[historical_analysis] Created summaries for {len(summaries)} devices")
        return summaries
        
    except Exception as e:
        logger.error(f"[historical_analysis] Error creating device summaries: {e}")
        return {}


def _create_summary_stats(
    data: List[Dict[str, Any]], 
    stats: Dict[str, Any], 
    patterns: Dict[str, Any], 
    logger: logging.Logger
) -> Dict[str, Any]:
    """
    Create high-level summary statistics.
    
    Args:
        data: Processed data records
        stats: Statistical measures
        patterns: Identified patterns
        logger: Logger instance
        
    Returns:
        Summary statistics dictionary
    """
    try:
        devices_analyzed = len(set(record["device_name"] for record in data))
        total_state_changes = len(data)
        
        # Calculate total usage time
        total_on_time = sum(
            record["total_duration_seconds"] 
            for record in data 
            if record["state"] == "on"
        )
        
        summary = {
            "devices_analyzed": devices_analyzed,
            "total_state_changes": total_state_changes,
            "total_on_time_hours": total_on_time / 3600,
            "most_active_device": patterns["most_active_devices"][0]["device"] if patterns["most_active_devices"] else "None",
            "analysis_period_days": None  # Will be set by the main handler
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"[historical_analysis] Error creating summary stats: {e}")
        return {}


def _generate_llm_report(
    user_query: str,
    data: List[Dict[str, Any]],
    stats: Dict[str, Any],
    patterns: Dict[str, Any],
    time_range_days: int,
    logger: logging.Logger
) -> str:
    """
    Generate a human-readable report using LLM.
    
    Args:
        user_query: Original user query
        data: Processed data
        stats: Statistical measures
        patterns: Identified patterns
        time_range_days: Analysis time range
        logger: Logger instance
        
    Returns:
        Formatted analysis report
    """
    try:
        # Prepare data summary for LLM
        device_count = len(set(record["device_name"] for record in data))
        total_records = len(data)
        
        # Create concise data summary
        data_summary = {
            "devices_analyzed": device_count,
            "total_state_changes": total_records,
            "time_range_days": time_range_days,
            "most_active_devices": patterns.get("most_active_devices", [])[:3],
            "key_statistics": {}
        }
        
        # Add key stats for top devices
        for device_info in patterns.get("most_active_devices", [])[:3]:
            device_name = device_info["device"]
            if device_name in stats:
                data_summary["key_statistics"][device_name] = stats[device_name]
        
        # Build LLM prompt
        prompt = f"""
Based on the historical device data analysis, create a comprehensive but concise report addressing the user's query.

User Query: "{user_query}"

Analysis Summary:
- Time Period: {time_range_days} days
- Devices Analyzed: {device_count}
- Total State Changes: {total_records}

Key Findings:
{_format_data_for_llm(data_summary, stats, patterns)}

Please provide a well-structured report that:
1. Directly addresses the user's question
2. Highlights the most important insights
3. Uses specific numbers and timeframes
4. Is easy to understand for a home automation user
5. Suggests actionable insights if relevant

Keep the report focused and under 500 words.
"""
        
        # Generate report using LLM
        report = perform_completion(
            messages=prompt,
            model="gpt-4o"  # Use larger model for report generation
        )
        
        return report
        
    except Exception as e:
        logger.error(f"[historical_analysis] Error generating LLM report: {e}")
        
        # Fallback to basic report
        return _generate_basic_report(data, stats, patterns, time_range_days)


def _format_data_for_llm(
    data_summary: Dict[str, Any], 
    stats: Dict[str, Any], 
    patterns: Dict[str, Any]
) -> str:
    """Format analysis data for LLM prompt."""
    try:
        formatted = []
        
        # Most active devices
        if patterns.get("most_active_devices"):
            formatted.append("Most Active Devices:")
            for device_info in patterns["most_active_devices"][:3]:
                formatted.append(f"  - {device_info['device']}: {device_info['total_on_hours']:.1f} hours on")
        
        # State change frequency
        if patterns.get("state_change_frequency"):
            formatted.append("\nDevice Activity Levels:")
            sorted_freq = sorted(
                patterns["state_change_frequency"].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for device, changes in sorted_freq[:3]:
                formatted.append(f"  - {device}: {changes} state changes")
        
        return "\n".join(formatted)
        
    except Exception:
        return "Data formatting failed"


def _generate_basic_report(
    data: List[Dict[str, Any]], 
    stats: Dict[str, Any], 
    patterns: Dict[str, Any], 
    time_range_days: int
) -> str:
    """Generate a basic fallback report without LLM."""
    try:
        device_count = len(set(record["device_name"] for record in data))
        total_records = len(data)
        
        report_lines = [
            f"Historical Analysis Report ({time_range_days} days)",
            "=" * 50,
            f"Devices Analyzed: {device_count}",
            f"Total State Changes: {total_records}",
            ""
        ]
        
        # Add most active devices
        if patterns.get("most_active_devices"):
            report_lines.append("Most Active Devices:")
            for device_info in patterns["most_active_devices"][:3]:
                report_lines.append(f"  • {device_info['device']}: {device_info['total_on_hours']:.1f} hours")
            report_lines.append("")
        
        # Add summary note
        report_lines.append("This analysis provides insights into device usage patterns over the specified time period.")
        
        return "\n".join(report_lines)
        
    except Exception:
        return "Unable to generate analysis report due to data processing error."