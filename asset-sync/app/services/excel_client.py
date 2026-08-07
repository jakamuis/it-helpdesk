import pandas as pd
from loguru import logger
import os

class ExcelClient:
    def __init__(self, file_paths=None):
        if file_paths is None:
            # Default paths relative to project root
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
            self.file_paths = [
                os.path.join(base_dir, "docs/Samator Registration Asset 1.0_Final_Remaining.xlsx"),
                os.path.join(base_dir, "docs/Samator Registration Asset 1.0.xlsx")
            ]
        else:
            self.file_paths = file_paths
            
    def load_specs_data(self) -> dict:
        """
        Loads the Excel files and returns a dictionary of specifications
        keyed by the 'Asset / Tag ID'.
        """
        specs_map = {}
        for file_path in self.file_paths:
            if not os.path.exists(file_path):
                logger.warning(f"Excel file not found: {file_path}")
                continue
                
            try:
                df = pd.read_excel(file_path)
                for idx, row in df.iterrows():
                    tag_id = str(row.get("Asset /  Tag  ID", "")).strip()
                    if not tag_id or tag_id == 'nan':
                        continue
                        
                    # Extract specs
                    cpu = str(row.get("Processor", "")).strip()
                    ram = str(row.get("RAM (GB)", "")).strip()
                    storage = str(row.get("Storage", "")).strip()
                    monitor = str(row.get("Monitor", "")).strip()
                    os_val = str(row.get("Operating System", "")).strip()
                    mac = str(row.get("MAC Address", "")).strip()
                    
                    # Clean up 'nan' string from pandas
                    specs_map[tag_id] = {
                        "cpu": cpu if cpu != 'nan' else None,
                        "ram": ram if ram != 'nan' else None,
                        "storage": storage if storage != 'nan' else None,
                        "monitor": monitor if monitor != 'nan' else None,
                        "os": os_val if os_val != 'nan' else None,
                        "mac": mac if mac != 'nan' else None
                    }
                logger.info(f"Loaded {len(specs_map)} specs from Excel files so far.")
            except Exception as e:
                logger.error(f"Failed to read Excel file {file_path}: {e}")
                
        return specs_map
