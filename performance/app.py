import sys
import weakref
from cassandra.cluster import Session, Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from dateutil import parser
import os

from flask import request, abort, Response, jsonify
import psutil
from flask import Flask

from memory_profiler import profile
import gc
import pandas as pd
from cassandra.query import BatchStatement, BatchType, dict_factory
from cassandra.cluster import ConsistencyLevel, Session, Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from datetime import datetime

HTTP_404_NOT_FOUND = 404
HTTP_500_INTERNAL_SERVER_ERROR = 500
HTTP_200_OK = 200

SERVER_INFO = {
    'port': int(os.getenv('PORT', 8126)),
    'keyspace': os.getenv('CASSANDRA_KEYSPACE', 'local'),
    'dbuser': os.getenv('CASSANDRA_USER', 'cassandra'),
    'dbpass': os.getenv('CASSANDRA_PASS', 'cassandra'),
    'dbpath': ''
}

ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app = Flask(__name__, root_path=ROOT_PATH)

config = {
    "local": {
        "DEBUG": True,
        "CORS_ENABLED": True,
        "CORS_SUPPORTS_CREDENTIALS": True,
        "CORS_ORIGINS": ["http://localhost:3000", "http://localhost:5173"], 
        "CORS_SEND_WILDCARD": False
    }
}
app.config.from_object(config.get("local"))
    
class JsonResponse(Response):
    default_mimetype = 'application/json'


@app.route('/status')
def get_status():
    response = Response(
        response='active',
        status=HTTP_200_OK, mimetype='text')
    return response


@app.route('/info/memory')
def get_memory_info():
    """Get detailed memory usage information for the application"""
    try:
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_percent = process.memory_percent()
        
        # System memory info
        system_memory = psutil.virtual_memory()
        
        memory_data = {
            "process_memory": {
                "rss": memory_info.rss,  # Resident Set Size (actual physical memory)
                "vms": memory_info.vms,  # Virtual Memory Size
                "percent": memory_percent,
                "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
                "vms_mb": round(memory_info.vms / 1024 / 1024, 2)
            },
            "system_memory": {
                "total": system_memory.total,
                "available": system_memory.available,
                "used": system_memory.used,
                "free": system_memory.free,
                "percent": system_memory.percent,
                "total_mb": round(system_memory.total / 1024 / 1024, 2),
                "available_mb": round(system_memory.available / 1024 / 1024, 2),
                "used_mb": round(system_memory.used / 1024 / 1024, 2),
                "free_mb": round(system_memory.free / 1024 / 1024, 2)
            },
            "memory_units": "bytes"
        }
        
        return jsonify(memory_data)
    except Exception as e:
        abort(HTTP_500_INTERNAL_SERVER_ERROR)


@app.route('/series_op_pfc/', methods=['POST'])
def upload_series_op():
    data = request.json

    as_of = parser.parse(data['as_of'])
    book_name = data['name']
    data_insertion_type = data['type']

    df_data = pd.DataFrame(data['data'])

    if data_insertion_type == 'HPFC_PWR':
        insert_pfc_power_data(df_data, book_name, as_of)    

    return 'Data successfully added', HTTP_200_OK

def insert_pfc_power_data(df: pd.DataFrame, name: str, as_of: datetime):
    if df.empty:
        abort(HTTP_404_NOT_FOUND, f"No data to insert for this as_of = {as_of} and book = {name}.")
        
    df['time'] = pd.to_datetime(df[['year', 'month', 'day', 'hour']], format="%Y-%m-%d %H").dt.tz_localize(
        LOCAL_TIME_ZONE, ambiguous='infer')
    df['time'] = df['time'].dt.tz_convert('UTC')    

    result = insert_power_pfc_data_cassandra(df, name, as_of)
    if not result:
        abort(HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to insert PFC power data for {name, as_of}.")


@app.route('/info/memory/simple')
def get_simple_memory_info():
    """Get simple memory usage information in MB"""
    try:
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        return jsonify({
            "memory_mb": round(memory_mb, 2),
            "status": "success"
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

# Day-2-Day Power
@app.route("/d2d_new_2/power")
def d2d_power_new_2():
    # Open log file for memory profiling
    # log_file = open("d2d_memory_profile.log", "w")
    data = request.args
    result = get_data_op_power_d2d_new_2(data)
    # log_file.close()
    return JsonResponse(response=result, status=HTTP_200_OK)


THERE_ARE_NO_DATA_FOR_THE_OLD_AS_OF = "There are no data for the old as_of"
THERE_ARE_NO_DATA_FOR_THE_NEW_AS_OF = "There are no data for the new as_of"

LOCAL_TIME_ZONE = 'Europe/Luxembourg'

D2D_POWER_AGGR_PARAMETERS = {
    "hour": "h",
    "day": "D",
    "week": "W-MON",
    "year": "YE",
}

log_file = open("d2d_memory_profile.log", "w")

def aggressive_memory_cleanup(description=""):
    """Perform aggressive memory cleanup."""
    try:
        # Get memory before cleanup
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024
        
        # Force garbage collection multiple times
        total_collected = 0
        for i in range(20):  # Even more iterations
            collected = gc.collect()
            total_collected += collected
            if collected == 0:
                break
        
        
        # Try to force memory return to OS (this is a hint, not guaranteed)
        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            libc.malloc_trim(0)  # This is Linux-specific
        except:
            pass  # Ignore if not available
        
        # Additional cleanup: clear all caches
        try:
            import sys
            # Clear built-in caches (safer than clearing module dicts)
            if hasattr(sys, '_clear_type_cache'):
                sys._clear_type_cache()
            
            # Clear frame cache
            if hasattr(sys, '_clear_frames'):
                sys._clear_frames()

            
        except:
            pass
        
        # Force another garbage collection after cache clearing
        gc.collect()
        
        # Get final memory after all cleanup
        memory_after_cleanup = process.memory_info().rss / 1024 / 1024
        
        memory_freed = memory_before - memory_after_cleanup
        
        if total_collected > 0 or memory_freed > 0:
            print(f"🗑️  {description}: collected {total_collected} objects, freed {memory_freed:.2f} MB, final: {memory_after_cleanup:.2f} MB")
        else:
            print(f"📊 {description}: memory: {memory_after_cleanup:.2f} MB (no objects collected)")
        
        return total_collected, memory_after_cleanup
        
    except Exception as e:
        print(f"Memory cleanup error: {e}")
        return 0, 0

def get_data_op_power_d2d_new_2(data: dict):
    print("🚀 Starting D2D processing with memory monitoring")
    
    # Initial memory check
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024
    print(f"📊 Initial function memory: {initial_memory:.2f} MB")
    
    pfm_list = [string.strip() for string in data.get("books").split(",")]
    if data.get("as_of_op_old") == 'null' or data.get("as_of_op_new") == 'null':
        abort(HTTP_404_NOT_FOUND, f'No data previous for as_of_op_old = {data.get("as_of_op_old")} ')

    as_of_op_old = parser.parse(data.get("as_of_op_old"))
    as_of_op_old = as_of_op_old.strftime('%Y-%m-%d')
    as_of_op_new = parser.parse(data.get("as_of_op_new"))
    as_of_op_new = as_of_op_new.strftime('%Y-%m-%d')
    ts_start = parser.parse(data.get("ts_start"))
    ts_end = parser.parse(data.get("ts_end"))

    for i, book_name in enumerate(pfm_list):
        print(f"Processing book {i+1}/{len(pfm_list)}: {book_name}")
        
        # Memory before processing this book
        pre_memory = process.memory_info().rss / 1024 / 1024
        print(f"📊 Memory before {book_name}: {pre_memory:.2f} MB")
        
        a = None
        b = None
        
        try:
            a = pd.DataFrame(get_op_power_data(
                as_of=as_of_op_old, book_op=book_name, ts_start=ts_start, ts_end=ts_end
            ))
            if a.empty:
                abort(HTTP_404_NOT_FOUND, THERE_ARE_NO_DATA_FOR_THE_OLD_AS_OF)
            
            # Force cleanup after first file
            if a is not None:
                del a
                a = None

            b = pd.DataFrame(get_op_power_data(
                as_of=as_of_op_new, book_op=book_name, ts_start=ts_start, ts_end=ts_end
            ))
            if b.empty:
                abort(HTTP_404_NOT_FOUND, THERE_ARE_NO_DATA_FOR_THE_NEW_AS_OF)
            
            # Force cleanup after first file
            if b is not None:
                del b
                b = None            

            # Memory after reading both files
            loaded_memory = process.memory_info().rss / 1024 / 1024
            print(f"📊 Memory after reading both files: {loaded_memory:.2f} MB")
            
            
        except Exception as e:
            print(f"❌ Error reading book for {book_name}: {e}")
        finally:
            try:
                # Clear and delete lists
                if a is not None:
                    del a
                if b is not None:
                    del b                                
            except Exception as cleanup_error:
                print(f"Cleanup error for {book_name}: {cleanup_error}")
    
    # Final cleanup
    del pfm_list
    aggressive_memory_cleanup("Final cleanup")
    
    final_memory = process.memory_info().rss / 1024 / 1024
    print(f"📊 Final function memory: {final_memory:.2f} MB")
    
    # log_file.flush()
    
    return []

session: Session

def get_op_power_data(as_of, book_op, ts_start, ts_end):
    try:
        execution = session.execute("SELECT time, value, is_peak FROM series_op_power WHERE as_of=%s AND name = %s AND time >= %s AND time < %s", 
        (as_of, book_op, ts_start, ts_end))
        return list(execution)
    except Exception as e:
        return []


@app.route('/series_pfc_power/', methods=['GET'])
def get_pfc_power_data():
    """
    Extract PFC (Power Forward Curve) data from local Cassandra database.
    
    Query parameters:
    - name: book name (required)
    - as_of: timestamp (required)
    - ts_start: start timestamp (optional, for filtering by time)
    - ts_end: end timestamp (optional, for filtering by time)
    
    Returns JSON with PFC data.
    """
    try:
        # Get query parameters
        name = request.args.get('name')
        as_of_str = request.args.get('as_of')
        ts_start_str = request.args.get('ts_start')
        ts_end_str = request.args.get('ts_end')
        
        # Validate required parameters
        if not name or not as_of_str:
            abort(HTTP_404_NOT_FOUND, "Missing required parameters: 'name' and 'as_of' are required")
        
        # Parse as_of timestamp - Cassandra stores as_of as a date type
        try:
            as_of_dt = parser.parse(as_of_str)
            # Extract date part (Cassandra as_of column is date type, not timestamp)
            as_of_date = as_of_dt.date()
        except Exception as e:
            abort(HTTP_404_NOT_FOUND, f"Invalid as_of format: {as_of_str}")
        
        # Build query based on whether time filters are provided
        if ts_start_str and ts_end_str:
            try:
                ts_start = parser.parse(ts_start_str)
                ts_end = parser.parse(ts_end_str)
                # Ensure timezone-aware and convert to UTC
                import pytz
                if ts_start.tzinfo is None:
                    ts_start = pytz.timezone(LOCAL_TIME_ZONE).localize(ts_start)
                if ts_end.tzinfo is None:
                    ts_end = pytz.timezone(LOCAL_TIME_ZONE).localize(ts_end)
                ts_start = ts_start.astimezone(pytz.UTC)
                ts_end = ts_end.astimezone(pytz.UTC)
            except Exception as e:
                abort(HTTP_404_NOT_FOUND, f"Invalid timestamp format: {str(e)}")
            
            query = """SELECT time, value, year, quarter, month, day, hour, week, wk_year, 
                      is_peak, opHxD, pkHxD, opHxW, pkHxW, opHxM, pkHxM, opHxQ, pkHxQ, opHxY, pkHxY 
                      FROM series_pfc_power 
                      WHERE as_of=%s AND name=%s AND time >= %s AND time < %s"""
            execution = session.execute(query, (as_of_date, name, ts_start, ts_end))
        else:
            query = """SELECT time, value, year, quarter, month, day, hour, week, wk_year, 
                      is_peak, opHxD, pkHxD, opHxW, pkHxW, opHxM, pkHxM, opHxQ, pkHxQ, opHxY, pkHxY 
                      FROM series_pfc_power 
                      WHERE as_of=%s AND name=%s"""
            execution = session.execute(query, (as_of_date, name))
        
        # Convert results to list of dictionaries
        data = []
        for row in execution:
            row_dict = {
                'time': row.time.isoformat() if row.time else None,
                'value': float(row.value) if row.value is not None else None,
                'year': int(row.year) if row.year is not None else None,
                'quarter': int(row.quarter) if row.quarter is not None else None,
                'month': int(row.month) if row.month is not None else None,
                'day': int(row.day) if row.day is not None else None,
                'hour': int(row.hour) if row.hour is not None else None,
                'week': int(row.week) if row.week is not None else None,
                'wk_year': int(row.wk_year) if row.wk_year is not None else None,
                'is_peak': bool(row.is_peak) if row.is_peak is not None else None,
            }
            
            # Add optional columns if they exist (Cassandra column names are case-sensitive)
            optional_cols = ['opHxD', 'pkHxD', 'opHxW', 'pkHxW', 'opHxM', 'pkHxM', 'opHxQ', 'pkHxQ', 'opHxY', 'pkHxY']
            for col in optional_cols:
                # Try both original case and lowercase
                col_lower = col.lower()
                if hasattr(row, col):
                    val = getattr(row, col)
                    row_dict[col] = float(val) if val is not None else None
                elif hasattr(row, col_lower):
                    val = getattr(row, col_lower)
                    row_dict[col] = float(val) if val is not None else None
                else:
                    row_dict[col] = None
            
            data.append(row_dict)
        
        # Return JSON response
        response = {
            'name': name,
            'as_of': as_of_str,
            'data': data,
            'count': len(data)
        }
        
        return jsonify(response), HTTP_200_OK
        
    except Exception as e:
        print(e)
        abort(HTTP_500_INTERNAL_SERVER_ERROR, f"Error retrieving PFC power data: {str(e)}")



def insert_power_pfc_data_cassandra(df: pd.DataFrame, name: str, as_of: datetime):
    INSERT_SERIES_QUERY_PFC_POWER = """INSERT INTO series_pfc_power (name, as_of, value, time, year, quarter, month, 
    day, hour, week, wk_year, is_peak, opHxD, pkHxD, opHxW, pkHxW, opHxM, pkHxM, opHxQ, pkHxQ, opHxY, pkHxY) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    insert_power_pfc = session.prepare(INSERT_SERIES_QUERY_PFC_POWER)

    try:
        batch_statement = BatchStatement(
            consistency_level=ConsistencyLevel.LOCAL_QUORUM, batch_type=BatchType.UNLOGGED
        )
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
                    row.opHxD,
                    row.pkHxD,
                    row.opHxW,
                    row.pkHxW,
                    row.opHxM,
                    row.pkHxM,
                    row.opHxQ,
                    row.pkHxQ,
                    row.opHxY,
                    row.pkHxY,
                ),
            )
            if row.Index % 15000 == 0:
                session.execute(batch_statement)
                del batch_statement
                batch_statement = BatchStatement(
                    consistency_level=ConsistencyLevel.LOCAL_QUORUM,
                    batch_type=BatchType.UNLOGGED,
                )
        session.execute(batch_statement)
        del batch_statement
        del df
        return True
    except Exception as e:
        print(e)
        return False

def init_session(username, password):
    global session
    profile = ExecutionProfile(request_timeout=60)

    auth_provider = PlainTextAuthProvider(username=username, password=password)
    
    # Use local Cassandra connection (for development)
    # Get contact points from environment or use default
    contact_points = os.getenv('CASSANDRA_CONTACT_POINTS', '127.0.0.1').split(',')
    cluster = Cluster(contact_points=contact_points,
                        auth_provider=auth_provider,
                        execution_profiles={EXEC_PROFILE_DEFAULT: profile})
        
    
    session = cluster.connect(SERVER_INFO["keyspace"]) 

if __name__ == '__main__':
    # Parse properties file
    if not SERVER_INFO:
        sys.exit()
    init_session(SERVER_INFO["dbuser"], SERVER_INFO["dbpass"])
    app.run(port=SERVER_INFO["port"])
    # log_file.close()


