"""
Tests for CPU compatibility checking functionality.
"""

import subprocess
import unittest
from unittest.mock import Mock, patch, MagicMock

# Mock indigo module before importing plugin
import sys
sys.modules['indigo'] = MagicMock()

# Import after mocking indigo
from plugin import Plugin


class MockDict(dict):
    """Mock dictionary that behaves like indigo.Dict"""
    def get(self, key, default=None):
        return super().get(key, default)


class TestCPUCompatibility(unittest.TestCase):
    """Test CPU compatibility checking."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock plugin preferences with all expected keys
        self.plugin_prefs = MockDict({
            'openai_api_key': 'test-key',
            'large_model': 'gpt-5',
            'small_model': 'gpt-5-mini',
            'log_level': 20,
            'enable_langsmith': False,
            'langsmith_endpoint': 'https://api.smith.langchain.com',
            'langsmith_api_key': '',
            'langsmith_project': '',
            'enable_influxdb': False,
            'influx_url': 'http://localhost',
            'influx_port': '8086',
            'influx_login': '',
            'influx_password': '',
            'influx_database': 'indigo',
            'access_mode': 'local_only',
        })

        # Create plugin instance
        self.plugin = Plugin(
            plugin_id='com.test.plugin',
            plugin_display_name='Test Plugin',
            plugin_version='1.0.0',
            plugin_prefs=self.plugin_prefs
        )

    @patch('platform.machine')
    def test_apple_silicon_compatible(self, mock_machine):
        """Test that Apple Silicon (arm64) is always compatible."""
        mock_machine.return_value = 'arm64'

        result = self.plugin.check_cpu_compatibility()

        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('platform.machine')
    def test_x86_with_avx2_compatible(self, mock_machine, mock_run):
        """Test that x86_64 with AVX2 support is compatible."""
        mock_machine.return_value = 'x86_64'

        # Mock subprocess result with AVX2 in output
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'SSE4.2 AVX AVX2 FMA'
        mock_run.return_value = mock_result

        result = self.plugin.check_cpu_compatibility()

        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ['sysctl', '-n', 'machdep.cpu.leaf7_features'],
            capture_output=True,
            text=True,
            timeout=5
        )

    @patch('subprocess.run')
    @patch('platform.machine')
    def test_x86_without_avx2_incompatible(self, mock_machine, mock_run):
        """Test that x86_64 without AVX2 support is incompatible."""
        mock_machine.return_value = 'x86_64'

        # Mock subprocess result without AVX2
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'SSE4.2 AVX'  # No AVX2
        mock_run.return_value = mock_result

        result = self.plugin.check_cpu_compatibility()

        self.assertFalse(result)

    @patch('subprocess.run')
    @patch('platform.machine')
    def test_x86_sysctl_failure_incompatible(self, mock_machine, mock_run):
        """Test that x86_64 with failed sysctl is treated as incompatible."""
        mock_machine.return_value = 'x86_64'

        # Mock subprocess failure
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ''
        mock_run.return_value = mock_result

        result = self.plugin.check_cpu_compatibility()

        self.assertFalse(result)

    @patch('subprocess.run')
    @patch('platform.machine')
    def test_subprocess_timeout_assumes_compatible(self, mock_machine, mock_run):
        """Test that subprocess timeout results in assuming compatible with warning."""
        mock_machine.return_value = 'x86_64'

        # Mock subprocess timeout
        mock_run.side_effect = subprocess.TimeoutExpired('sysctl', 5)

        result = self.plugin.check_cpu_compatibility()

        # Should assume compatible on timeout
        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('platform.machine')
    def test_subprocess_exception_assumes_compatible(self, mock_machine, mock_run):
        """Test that subprocess exception results in assuming compatible with warning."""
        mock_machine.return_value = 'x86_64'

        # Mock subprocess exception
        mock_run.side_effect = Exception('Test error')

        result = self.plugin.check_cpu_compatibility()

        # Should assume compatible on exception
        self.assertTrue(result)

    @patch('platform.machine')
    def test_unknown_architecture_assumes_compatible(self, mock_machine):
        """Test that unknown architecture assumes compatible with warning."""
        mock_machine.return_value = 'unknown_arch'

        result = self.plugin.check_cpu_compatibility()

        # Should assume compatible for unknown architecture
        self.assertTrue(result)

    @patch('subprocess.run')
    @patch('platform.machine')
    def test_error_messages_for_incompatible_cpu(self, mock_machine, mock_run):
        """Test that proper error messages are logged for incompatible CPU."""
        mock_machine.return_value = 'x86_64'

        # Mock subprocess result without AVX2
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'SSE4.2 AVX'
        mock_run.return_value = mock_result

        # Capture log messages
        with patch.object(self.plugin.logger, 'error') as mock_error:
            result = self.plugin.check_cpu_compatibility()

            self.assertFalse(result)

            # Verify error messages were logged
            error_calls = [call[0][0] for call in mock_error.call_args_list]

            # Check for key error messages
            self.assertTrue(any('AVX2 instruction set not supported' in msg for msg in error_calls))
            self.assertTrue(any('2012-2013 Intel Macs' in msg for msg in error_calls))
            self.assertTrue(any('2013 Mac Pro' in msg for msg in error_calls))
            self.assertTrue(any('Apple Silicon Macs' in msg for msg in error_calls))


if __name__ == '__main__':
    unittest.main()
