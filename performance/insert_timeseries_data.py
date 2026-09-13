#!/usr/bin/env python3
"""
Script to insert timeseries data from JSON files in time_series_data folder into Cassandra database.
Connects to local Cassandra database using the same configuration as app.py
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd
import pytz

from cassandra.cluster import Cluster, Session, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import BatchStatement, BatchType, ConsistencyLevel

# Configuration (same as app.py)
LOCAL_TIME_ZONE = 'Europe/Luxembourg'
SERVER_INFO = {
    'keyspace': os.getenv('CASSANDRA_KEYSPACE', 'local'),
    'dbuser': os.getenv('CASSANDRA_USER', 'cassandra'),
    'dbpass': os.getenv('CASSANDRA_PASS', 'cassandra'),
    'contact_points': os.getenv('CASSANDRA_CONTACT_POINTS', '127.0.0.1').split(',')
}

# Global session
session: Session = None


def init_session(username, password, keyspace, contact_points):
    """Initialize Cassandra session (same as app.py)"""
    global session
    profile = ExecutionProfile(request_timeout=60)
    auth_provider = PlainTextAuthProvider(username=username, password=password)
    
    cluster = Cluster(
        contact_points=contact_points,
        auth_provider=auth_provider,
        execution_profiles={EXEC_PROFILE_DEFAULT: profile}
    )
    
    session = cluster.connect(keyspace)
    print(f"✓ Connected to Cassandra keyspace: {keyspace}")


def insert_op_power_data(df: pd.DataFrame, name: str, as_of: datetime):
    """Insert OP power data into series_op_power table"""
    INSERT_SERIES_QUERY_OP_POWER = """INSERT INTO series_op_power (name, as_of, value, time, year, quarter, month, 
    day, hour, week, wk_year, is_peak) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    insert_power_op = session.prepare(INSERT_SERIES_QUERY_OP_POWER)
    batch_statement = BatchStatement(
        consistency_level=ConsistencyLevel.LOCAL_QUORUM, 
        batch_type=BatchType.UNLOGGED
    )
    
    try:
        inserted_count = 0
        for row in df.itertuples():
            batch_statement.add(
                insert_power_op,
                (
                    name,
                    as_of,
                    row.value,
                    row.time.to_pydatetime(),
                    row.year,
                    row.quarter,
                    row.month,
                    row.day,
                    row.hour,
                    row.week,
                    row.wk_year,
                    bool(row.is_peak)
                )
            )
            
            # Execute batch every 15000 rows
            if row.Index % 15000 == 0 and row.Index > 0:
                session.execute(batch_statement)
                inserted_count += 15000
                print(f"  ... inserted {inserted_count} rows")
                del batch_statement
                batch_statement = BatchStatement(
                    consistency_level=ConsistencyLevel.LOCAL_QUORUM,
                    batch_type=BatchType.UNLOGGED
                )
        
        # Execute remaining batch
        if len(batch_statement) > 0:
            session.execute(batch_statement)
            inserted_count += len(batch_statement)
        
        del batch_statement
        print(f"  ✓ Inserted {inserted_count} rows into series_op_power")
        return True
        
    except Exception as e:
        print(f"  ❌ Error inserting OP power data: {e}")
        return False


def insert_pfc_power_data(df: pd.DataFrame, name: str, as_of: datetime):
    """Insert PFC power data into series_pfc_power table"""
    INSERT_SERIES_QUERY_PFC_POWER = """INSERT INTO series_pfc_power (name, as_of, value, time, year, quarter, month, 
    day, hour, week, wk_year, is_peak, opHxD, pkHxD, opHxW, pkHxW, opHxM, pkHxM, opHxQ, pkHxQ, opHxY, pkHxY) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    insert_power_pfc = session.prepare(INSERT_SERIES_QUERY_PFC_POWER)
    batch_statement = BatchStatement(
        consistency_level=ConsistencyLevel.LOCAL_QUORUM,
        batch_type=BatchType.UNLOGGED
    )
    
    try:
        inserted_count = 0
        for row in df.itertuples():
            batch_statement.add(
                insert_power_pfc,
                (
                    name,
                    as_of,
                    row.value,
                    row.time.to_pydatetime(),
                    row.year,
                    row.quarter,
                    row.month,
                    row.day,
                    row.hour,
                    row.week,
                    row.wk_year,
                    bool(row.is_peak),
                    row.opHxD if hasattr(row, 'opHxD') else None,
                    row.pkHxD if hasattr(row, 'pkHxD') else None,
                    row.opHxW if hasattr(row, 'opHxW') else None,
                    row.pkHxW if hasattr(row, 'pkHxW') else None,
                    row.opHxM if hasattr(row, 'opHxM') else None,
                    row.pkHxM if hasattr(row, 'pkHxM') else None,
                    row.opHxQ if hasattr(row, 'opHxQ') else None,
                    row.pkHxQ if hasattr(row, 'pkHxQ') else None,
                    row.opHxY if hasattr(row, 'opHxY') else None,
                    row.pkHxY if hasattr(row, 'pkHxY') else None,
                )
            )
            
            # Execute batch every 15000 rows
            if row.Index % 15000 == 0 and row.Index > 0:
                session.execute(batch_statement)
                inserted_count += 15000
                print(f"  ... inserted {inserted_count} rows")
                del batch_statement
                batch_statement = BatchStatement(
                    consistency_level=ConsistencyLevel.LOCAL_QUORUM,
                    batch_type=BatchType.UNLOGGED
                )
        
        # Execute remaining batch
        if len(batch_statement) > 0:
            session.execute(batch_statement)
            inserted_count += len(batch_statement)
        
        del batch_statement
        print(f"  ✓ Inserted {inserted_count} rows into series_pfc_power")
        return True
        
    except Exception as e:
        print(f"  ❌ Error inserting PFC power data: {e}")
        return False


def process_json_file(file_path: Path):
    """Process a single JSON file and insert data into Cassandra"""
    print(f"\n📄 Processing: {file_path.name}")
    
    try:
        # Read JSON file
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Extract metadata
        file_type = data.get('type')
        name = data.get('name')
        as_of_str = data.get('as_of')
        data_list = data.get('data', [])
        
        if not file_type or not name or not as_of_str or not data_list:
            print(f"  ❌ Invalid JSON structure. Missing required fields.")
            return False
        
        # Parse as_of date
        as_of = datetime.strptime(as_of_str, '%Y-%m-%d').date()
        
        # Convert to DataFrame
        df = pd.DataFrame(data_list)
        
        if df.empty:
            print(f"  ⚠️  No data to insert")
            return False
        
        print(f"  📊 Data: type={file_type}, name={name}, as_of={as_of}, rows={len(df)}")
        
        # Create time column (same as app.py)
        df['time'] = pd.to_datetime(
            df[['year', 'month', 'day', 'hour']], 
            format="%Y-%m-%d %H"
        ).dt.tz_localize(LOCAL_TIME_ZONE, ambiguous='infer')
        df['time'] = df['time'].dt.tz_convert('UTC')
        
        # Insert based on type
        if file_type == 'OP_PWR':
            return insert_op_power_data(df, name, as_of)
        elif file_type == 'HPFC_PWR':
            return insert_pfc_power_data(df, name, as_of)
        else:
            print(f"  ❌ Unknown type: {file_type}")
            return False
            
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON decode error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error processing file: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function to process all JSON files"""
    # Get script directory and time_series_data folder
    script_dir = Path(__file__).parent
    data_dir = script_dir / 'time_series_data'
    
    if not data_dir.exists():
        print(f"❌ Directory not found: {data_dir}")
        sys.exit(1)
    
    # Find all JSON files
    json_files = list(data_dir.glob('*.json'))
    
    if not json_files:
        print(f"❌ No JSON files found in {data_dir}")
        sys.exit(1)
    
    print(f"🔍 Found {len(json_files)} JSON file(s) in {data_dir}")
    
    # Initialize Cassandra session
    try:
        init_session(
            SERVER_INFO['dbuser'],
            SERVER_INFO['dbpass'],
            SERVER_INFO['keyspace'],
            SERVER_INFO['contact_points']
        )
    except Exception as e:
        print(f"❌ Failed to connect to Cassandra: {e}")
        sys.exit(1)
    
    # Process each file
    success_count = 0
    fail_count = 0
    
    for json_file in sorted(json_files):
        if process_json_file(json_file):
            success_count += 1
        else:
            fail_count += 1
    
    # Summary
    print(f"\n{'='*70}")
    print(f"📊 Summary:")
    print(f"  ✓ Successfully processed: {success_count} file(s)")
    print(f"  ❌ Failed: {fail_count} file(s)")
    print(f"  📁 Total files: {len(json_files)}")
    print(f"{'='*70}\n")
    
    # Close session
    if session:
        session.cluster.shutdown()
        print("✓ Disconnected from Cassandra")


if __name__ == '__main__':
    main()

