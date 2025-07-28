"""
Integration test suite for all control tools working together.
"""

import pytest
from unittest.mock import Mock, patch
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MCP Server.indigoPlugin', 'Contents', 'Server Plugin'))

from mcp_server.tools.device_control import DeviceControlHandler
from mcp_server.tools.variable_control import VariableControlHandler
from mcp_server.tools.action_control import ActionControlHandler
from tests.mocks.mock_data_provider import MockDataProvider


class TestControlToolsIntegration:
    """Test integration scenarios using multiple control tools together."""
    
    @pytest.fixture
    def handlers(self):
        """Create all control handlers with shared mock data provider."""
        data_provider = MockDataProvider()
        logger = Mock()
        
        return {
            'device': DeviceControlHandler(data_provider, logger),
            'variable': VariableControlHandler(data_provider, logger),
            'action': ActionControlHandler(data_provider, logger),
            'data_provider': data_provider
        }
    
    def test_device_control_sequence(self, handlers):
        """Test a complete device control sequence: turn on, set brightness, turn off."""
        device_id = 12345
        
        # Mock sequential device operations
        handlers['data_provider'].turn_on_device = Mock(return_value={
            "changed": True, "previous": False, "current": True
        })
        handlers['data_provider'].set_device_brightness = Mock(return_value={
            "changed": True, "previous": 0, "current": 75
        })
        handlers['data_provider'].turn_off_device = Mock(return_value={
            "changed": True, "previous": True, "current": False
        })
        
        # Execute sequence
        turn_on_result = handlers['device'].turn_on(device_id)
        brightness_result = handlers['device'].set_brightness(device_id, 75)
        turn_off_result = handlers['device'].turn_off(device_id)
        
        # Assert all operations succeeded
        assert turn_on_result["changed"] is True
        assert turn_on_result["current"] is True
        
        assert brightness_result["changed"] is True
        assert brightness_result["current"] == 75
        
        assert turn_off_result["changed"] is True
        assert turn_off_result["current"] is False
        
        # Verify call sequence
        handlers['data_provider'].turn_on_device.assert_called_once_with(device_id)
        handlers['data_provider'].set_device_brightness.assert_called_once_with(device_id, 75)
        handlers['data_provider'].turn_off_device.assert_called_once_with(device_id)
    
    def test_variable_tracking_device_states(self, handlers):
        """Test updating variables to track device states."""
        device_id = 12345
        state_variable_id = 54321
        brightness_variable_id = 54322
        
        # Mock device operations
        handlers['data_provider'].turn_on_device = Mock(return_value={
            "changed": True, "previous": False, "current": True
        })
        handlers['data_provider'].set_device_brightness = Mock(return_value={
            "changed": True, "previous": 0, "current": 50
        })
        
        # Mock variable updates
        handlers['data_provider'].update_variable = Mock(side_effect=[
            {"previous": "false", "current": "true"},  # State variable
            {"previous": "0", "current": "50"}         # Brightness variable
        ])
        
        # Execute operations
        device_result = handlers['device'].turn_on(device_id)
        state_var_result = handlers['variable'].update(state_variable_id, "true")
        
        brightness_result = handlers['device'].set_brightness(device_id, 50)
        brightness_var_result = handlers['variable'].update(brightness_variable_id, "50")
        
        # Assert all operations succeeded
        assert device_result["current"] is True
        assert state_var_result["current"] == "true"
        assert brightness_result["current"] == 50
        assert brightness_var_result["current"] == "50"
    
    def test_action_group_controlling_multiple_devices(self, handlers):
        """Test action group execution followed by individual device verification."""
        action_group_id = 67890
        device_ids = [12345, 12346, 12347]
        
        # Mock action group execution
        handlers['data_provider'].execute_action_group = Mock(return_value={
            "success": True, "job_id": None
        })
        
        # Mock device state checks after action group execution
        handlers['data_provider'].turn_on_device = Mock(return_value={
            "changed": False, "previous": True, "current": True
        })
        
        # Execute action group
        action_result = handlers['action'].execute(action_group_id)
        assert action_result["success"] is True
        
        # Verify individual devices (simulating checking their states)
        for device_id in device_ids:
            device_result = handlers['device'].turn_on(device_id)  # This should show no change
            assert device_result["changed"] is False
    
    def test_error_handling_across_tools(self, handlers):
        """Test error handling when operations fail across different tools."""
        device_id = 99999  # Non-existent device
        variable_id = 99998  # Non-existent variable
        action_group_id = 99997  # Non-existent action group
        
        # Mock error responses
        handlers['data_provider'].turn_on_device = Mock(return_value={
            "error": f"Device {device_id} not found"
        })
        handlers['data_provider'].update_variable = Mock(return_value={
            "error": f"Variable {variable_id} not found"
        })
        handlers['data_provider'].execute_action_group = Mock(return_value={
            "error": f"Action group {action_group_id} not found",
            "success": False
        })
        
        # Execute operations and verify errors
        device_result = handlers['device'].turn_on(device_id)
        variable_result = handlers['variable'].update(variable_id, "test")
        action_result = handlers['action'].execute(action_group_id)
        
        assert "error" in device_result
        assert "Device" in device_result["error"]
        assert "not found" in device_result["error"]
        
        assert "error" in variable_result
        assert "Variable" in variable_result["error"]
        assert "not found" in variable_result["error"]
        
        assert action_result["success"] is False
        assert "error" in action_result
        assert "Action group" in action_result["error"]
        assert "not found" in action_result["error"]
    
    def test_concurrent_operations_simulation(self, handlers):
        """Test simulated concurrent operations on different entities."""
        # Setup multiple entities
        devices = [12345, 12346]
        variables = [54321, 54322]
        action_groups = [67890, 67891]
        
        # Mock all operations to succeed
        handlers['data_provider'].turn_on_device = Mock(return_value={
            "changed": True, "previous": False, "current": True
        })
        handlers['data_provider'].update_variable = Mock(return_value={
            "previous": "old", "current": "new"
        })
        handlers['data_provider'].execute_action_group = Mock(return_value={
            "success": True, "job_id": None
        })
        
        # Execute operations on all entities
        device_results = [handlers['device'].turn_on(dev_id) for dev_id in devices]
        variable_results = [handlers['variable'].update(var_id, "new") for var_id in variables]
        action_results = [handlers['action'].execute(ag_id) for ag_id in action_groups]
        
        # Verify all operations succeeded
        for result in device_results:
            assert result["changed"] is True
        
        for result in variable_results:
            assert result["current"] == "new"
        
        for result in action_results:
            assert result["success"] is True
        
        # Verify correct number of calls
        assert handlers['data_provider'].turn_on_device.call_count == len(devices)
        assert handlers['data_provider'].update_variable.call_count == len(variables)
        assert handlers['data_provider'].execute_action_group.call_count == len(action_groups)
    
    def test_scene_activation_workflow(self, handlers):
        """Test a complete scene activation workflow."""
        # Scenario: Activate "Movie Night" scene
        scene_action_id = 67890
        
        # Variables to update
        scene_variable_id = 54321
        last_scene_variable_id = 54322
        
        # Devices that should be affected
        living_room_lights = [12345, 12346]
        tv_device_id = 12347
        
        # Mock scene execution
        handlers['data_provider'].execute_action_group = Mock(return_value={
            "success": True, "job_id": None
        })
        
        # Mock variable updates - each call returns different values
        def mock_update_variable(var_id, value):
            if var_id == last_scene_variable_id and str(value) == "Day":
                return {"previous": "Home", "current": "Day"}
            elif var_id == scene_variable_id and str(value) == "Movie Night":
                return {"previous": "Day", "current": "Movie Night"}
            else:
                return {"previous": "unknown", "current": str(value)}
        
        handlers['data_provider'].update_variable = Mock(side_effect=mock_update_variable)
        
        # Mock device verifications (scene would have set these)
        handlers['data_provider'].set_device_brightness = Mock(return_value={
            "changed": True, "previous": 100, "current": 20
        })
        handlers['data_provider'].turn_on_device = Mock(return_value={
            "changed": True, "previous": False, "current": True
        })
        
        # Execute workflow
        # 1. Store previous scene
        prev_scene_result = handlers['variable'].update(last_scene_variable_id, "Day")
        
        # 2. Execute movie night scene
        scene_result = handlers['action'].execute(scene_action_id)
        
        # 3. Update current scene variable
        current_scene_result = handlers['variable'].update(scene_variable_id, "Movie Night")
        
        # 4. Verify devices were set correctly (dim lights, turn on TV)
        for light_id in living_room_lights:
            light_result = handlers['device'].set_brightness(light_id, 20)
            assert light_result["current"] == 20
        
        tv_result = handlers['device'].turn_on(tv_device_id)
        
        # Assert workflow success
        assert prev_scene_result["current"] == "Day"
        assert scene_result["success"] is True
        assert current_scene_result["current"] == "Movie Night"
        assert tv_result["current"] is True
    
    def test_rollback_on_failure_workflow(self, handlers):
        """Test rollback workflow when operations fail."""
        device_id = 12345
        backup_variable_id = 54321
        
        # Mock variable updates with different responses based on value
        call_count = 0
        def mock_update_variable(var_id, value):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call: backup
                return {"previous": "0", "current": "50"}
            elif call_count == 2:  # Second call: rollback
                return {"previous": "50", "current": "0"}
            else:
                return {"previous": str(value), "current": str(value)}
        
        handlers['data_provider'].update_variable = Mock(side_effect=mock_update_variable)
        
        # Mock failed device operation
        handlers['data_provider'].set_device_brightness = Mock(return_value={
            "error": "Device communication failed"
        })
        
        # Execute workflow with failure handling
        # 1. Backup current brightness
        backup_result = handlers['variable'].update(backup_variable_id, "50")
        assert backup_result["current"] == "50"
        
        # 2. Attempt to change brightness (this fails)
        brightness_result = handlers['device'].set_brightness(device_id, 75)
        assert "error" in brightness_result
        
        # 3. Rollback the backup variable (simulating restoration)
        rollback_result = handlers['variable'].update(backup_variable_id, "0")
        assert rollback_result["current"] == "0"
    
    def test_input_validation_across_tools(self, handlers):
        """Test input validation consistency across all tools."""
        # Test invalid IDs across all tools
        invalid_ids = ["string", None, -1, 0.5, [123], {"id": 123}]
        
        for invalid_id in invalid_ids:
            # Device control validation
            device_on_result = handlers['device'].turn_on(invalid_id)
            device_off_result = handlers['device'].turn_off(invalid_id)
            
            # Variable control validation
            variable_result = handlers['variable'].update(invalid_id, "test")
            
            # Action control validation  
            action_result = handlers['action'].execute(invalid_id)
            
            # All should have errors for invalid IDs
            if not isinstance(invalid_id, int):
                assert "error" in device_on_result
                assert "error" in device_off_result
                assert "error" in variable_result
                assert "error" in action_result
                assert action_result["success"] is False
    
    def test_brightness_validation_edge_cases(self, handlers):
        """Test brightness validation edge cases."""
        device_id = 12345
        
        # Test various brightness values
        test_cases = [
            (0, True),      # Valid: minimum
            (1, True),      # Valid: 0-1 range
            (0.5, True),    # Valid: fractional
            (100, True),    # Valid: maximum
            (101, False),   # Invalid: too high
            (-1, False),    # Invalid: negative
            ("50", False),  # Invalid: string
            (None, False),  # Invalid: None
        ]
        
        for brightness, should_succeed in test_cases:
            # Mock appropriate response based on expected outcome
            if should_succeed:
                handlers['data_provider'].set_device_brightness = Mock(return_value={
                    "changed": True, "previous": 0, "current": brightness
                })
            else:
                handlers['data_provider'].set_device_brightness = Mock(return_value={
                    "error": f"Invalid brightness value: {brightness}"
                })
            
            result = handlers['device'].set_brightness(device_id, brightness)
            
            if should_succeed:
                assert "error" not in result
            else:
                assert "error" in result