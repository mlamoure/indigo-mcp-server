"""
LangGraph implementation for historical data analysis.
"""

import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, START, END

from .state import HistoricalAnalysisState
from .nodes import query_data_node, transform_data_node, analyze_data_node


class HistoricalAnalysisGraph:
    """LangGraph for historical data analysis workflow."""
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize the graph.
        
        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph for historical analysis.
        
        Returns:
            Compiled StateGraph
        """
        # Create the graph
        workflow = StateGraph(HistoricalAnalysisState)
        
        # Add nodes
        workflow.add_node("query_data", self._query_data_wrapper)
        workflow.add_node("transform_data", self._transform_data_wrapper)
        workflow.add_node("analyze_data", self._analyze_data_wrapper)
        
        # Add edges
        workflow.add_edge(START, "query_data")
        workflow.add_edge("query_data", "transform_data")
        workflow.add_edge("transform_data", "analyze_data")
        workflow.add_edge("analyze_data", END)
        
        return workflow.compile()
    
    def _query_data_wrapper(self, state: HistoricalAnalysisState) -> Dict[str, Any]:
        """Wrapper for query_data_node with logging."""
        self.logger.debug("[historical_analysis] Executing query_data_node")
        return query_data_node(state, self.logger)
    
    def _transform_data_wrapper(self, state: HistoricalAnalysisState) -> Dict[str, Any]:
        """Wrapper for transform_data_node with logging."""
        self.logger.debug("[historical_analysis] Executing transform_data_node")
        return transform_data_node(state, self.logger)
    
    def _analyze_data_wrapper(self, state: HistoricalAnalysisState) -> Dict[str, Any]:
        """Wrapper for analyze_data_node with logging."""
        self.logger.debug("[historical_analysis] Executing analyze_data_node")
        return analyze_data_node(state, self.logger)
    
    def execute(self, initial_state: HistoricalAnalysisState) -> HistoricalAnalysisState:
        """
        Execute the historical analysis workflow.
        
        Args:
            initial_state: Initial state for the analysis
            
        Returns:
            Final state with analysis results
        """
        try:
            self.logger.info("[historical_analysis] Starting workflow execution")
            
            # Execute the graph
            final_state = self.graph.invoke(initial_state)
            
            self.logger.info("[historical_analysis] Workflow execution completed")
            return final_state
            
        except Exception as e:
            self.logger.error(f"[historical_analysis] Workflow execution failed: {e}")
            
            # Return error state
            return {
                **initial_state,
                "query_success": False,
                "transform_success": False,
                "analysis_success": False,
                "query_error": f"Workflow failed: {str(e)}",
                "transform_error": None,
                "analysis_error": None,
                "formatted_report": f"Analysis failed: {str(e)}",
                "raw_data": [],
                "processed_data": [],
                "analysis_results": {},
                "summary_stats": {}
            }