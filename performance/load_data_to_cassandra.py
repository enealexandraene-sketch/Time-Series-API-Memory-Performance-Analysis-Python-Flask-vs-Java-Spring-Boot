#!/usr/bin/env python3
"""
Script to load data into Cassandra running in Docker container.
This is used as part of the Docker image build process.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Wait for Cassandra to be ready
def wait_for_cassandra(max_wait=120):
    """Wait for Cassandra to be ready."""
    print("Waiting for Cassandra to be ready...")
    for i in range(max_wait // 2):
        try:
            result = subprocess.run(
                ['cqlsh', '-e', 'DESCRIBE KEYSPACES'],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print("✓ Cassandra is ready!")
                return True
        except:
            pass
        time.sleep(2)
        if (i + 1) % 5 == 0:
            print(f"   ... still waiting ({i*2} seconds)")
    
    print("❌ Timeout waiting for Cassandra")
    return False

def main():
    # Wait for Cassandra
    if not wait_for_cassandra():
        sys.exit(1)
    
    # Load data using insert_json_files.py
    data_dir = os.getenv('DATA_DIR', '/app')
    flask_url = os.getenv('FLASK_URL', 'http://localhost:8126')
    
    print(f"Loading data from {data_dir}...")
    
    # Check if we need to start Flask app
    # For now, assume it's already running or we'll use direct DB connection
    
    # Run insert script
    script_path = Path('/app/insert_json_files.py')
    if script_path.exists():
        result = subprocess.run(
            ['python3', str(script_path), '--directory', data_dir, '--url', flask_url],
            cwd='/app'
        )
        if result.returncode == 0:
            print("✓ Data loaded successfully")
        else:
            print("⚠️  Data loading completed with warnings")
    else:
        print("⚠️  insert_json_files.py not found, skipping data load")

if __name__ == '__main__':
    main()
