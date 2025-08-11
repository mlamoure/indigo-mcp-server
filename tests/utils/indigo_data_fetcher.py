"""
Utility for fetching real data from Indigo API for testing purposes.
"""

import json
import logging
import os
import urllib3
from typing import Dict, List, Any, Optional
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Disable SSL warnings for local Indigo connections
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger(__name__)


class IndigoDataFetcher:
    """Fetches real data from Indigo API for testing."""
    
    def __init__(self, api_url: str, api_key: str, disable_ssl: bool = True):
        """
        Initialize Indigo data fetcher.
        
        Args:
            api_url: Indigo API URL (e.g., https://localhost:8176)
            api_key: Indigo API key
            disable_ssl: Whether to disable SSL verification
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.verify = not disable_ssl
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })
    
    def fetch_devices(self, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Fetch devices from Indigo.
        
        Args:
            limit: Maximum number of devices to fetch
            
        Returns:
            List of device dictionaries
        """
        try:
            response = self.session.get(f'{self.api_url}/devices.json')
            response.raise_for_status()
            
            devices_data = response.json()
            devices = []
            
            for device_id, device_info in list(devices_data.items())[:limit]:
                # Convert device info to match expected structure
                device = {
                    'id': int(device_id),
                    'name': device_info.get('name', f'Device {device_id}'),
                    'description': device_info.get('description', ''),
                    'model': device_info.get('model', ''),
                    'deviceTypeId': device_info.get('deviceTypeId', ''),
                    'type': device_info.get('type', ''),
                    'address': device_info.get('address', ''),
                    'enabled': device_info.get('enabled', True),
                    'states': device_info.get('states', {}),
                    'protocol': device_info.get('protocol', ''),
                }
                devices.append(device)
            
            logger.info(f"Fetched {len(devices)} devices from Indigo")
            return devices
            
        except Exception as e:
            logger.error(f"Error fetching devices from Indigo: {e}")
            return []
    
    def fetch_variables(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch variables from Indigo.
        
        Args:
            limit: Maximum number of variables to fetch
            
        Returns:
            List of variable dictionaries
        """
        try:
            response = self.session.get(f'{self.api_url}/variables.json')
            response.raise_for_status()
            
            variables_data = response.json()
            variables = []
            
            for var_id, var_info in list(variables_data.items())[:limit]:
                # Convert variable info to match expected structure
                variable = {
                    'id': int(var_id),
                    'name': var_info.get('name', f'Variable {var_id}'),
                    'value': var_info.get('value', ''),
                    'description': var_info.get('description', ''),
                    'folderId': var_info.get('folderId', 1),
                    'readOnly': var_info.get('readOnly', False)
                }
                variables.append(variable)
            
            logger.info(f"Fetched {len(variables)} variables from Indigo")
            return variables
            
        except Exception as e:
            logger.error(f"Error fetching variables from Indigo: {e}")
            return []
    
    def fetch_actions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch action groups from Indigo.
        
        Args:
            limit: Maximum number of action groups to fetch
            
        Returns:
            List of action group dictionaries
        """
        try:
            response = self.session.get(f'{self.api_url}/actionGroups.json')
            response.raise_for_status()
            
            actions_data = response.json()
            actions = []
            
            for action_id, action_info in list(actions_data.items())[:limit]:
                # Convert action info to match expected structure
                action = {
                    'id': int(action_id),
                    'name': action_info.get('name', f'Action Group {action_id}'),
                    'description': action_info.get('description', ''),
                    'folderId': action_info.get('folderId', 1),
                }
                actions.append(action)
            
            logger.info(f"Fetched {len(actions)} action groups from Indigo")
            return actions
            
        except Exception as e:
            logger.error(f"Error fetching action groups from Indigo: {e}")
            return []
    
    def fetch_sample_data(self, device_limit: int = 15, variable_limit: int = 10, 
                         action_limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch sample data for all entity types.
        
        Args:
            device_limit: Maximum number of devices to fetch
            variable_limit: Maximum number of variables to fetch  
            action_limit: Maximum number of action groups to fetch
            
        Returns:
            Dictionary with keys 'devices', 'variables', 'actions'
        """
        return {
            'devices': self.fetch_devices(device_limit),
            'variables': self.fetch_variables(variable_limit),
            'actions': self.fetch_actions(action_limit)
        }
    
    def save_sample_data_to_file(self, filename: str, device_limit: int = 15, 
                               variable_limit: int = 10, action_limit: int = 10) -> bool:
        """
        Fetch and save sample data to a JSON file.
        
        Args:
            filename: Path to save the JSON file
            device_limit: Maximum number of devices to fetch
            variable_limit: Maximum number of variables to fetch
            action_limit: Maximum number of action groups to fetch
            
        Returns:
            True if successful, False otherwise
        """
        try:
            data = self.fetch_sample_data(device_limit, variable_limit, action_limit)
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            logger.info(f"Saved sample data to {filename}")
            logger.info(f"Data summary: {len(data['devices'])} devices, "
                       f"{len(data['variables'])} variables, {len(data['actions'])} actions")
            return True
            
        except Exception as e:
            logger.error(f"Error saving sample data: {e}")
            return False


def create_indigo_fetcher_from_env() -> Optional[IndigoDataFetcher]:
    """
    Create IndigoDataFetcher from environment variables.
    
    Returns:
        IndigoDataFetcher instance or None if credentials not available
    """
    api_url = os.getenv('INDIGO_API_URL')
    api_key = os.getenv('INDIGO_API_KEY') 
    disable_ssl = os.getenv('INDIGO_DISABLE_SSL_VALIDATION', 'false').lower() == 'true'
    
    if not api_url or not api_key:
        logger.warning("Indigo API credentials not found in environment variables")
        return None
    
    return IndigoDataFetcher(api_url, api_key, disable_ssl)


if __name__ == "__main__":
    # Test script to fetch and save sample data
    import sys
    
    fetcher = create_indigo_fetcher_from_env()
    if fetcher:
        output_file = sys.argv[1] if len(sys.argv) > 1 else 'indigo_sample_data.json'
        success = fetcher.save_sample_data_to_file(output_file)
        if success:
            print(f"✅ Sample data saved to {output_file}")
        else:
            print("❌ Failed to save sample data")
    else:
        print("❌ Could not create Indigo fetcher - check environment variables")