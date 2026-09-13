import sys
import weakref
from cassandra.cluster import Session, Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from dateutil import parser
import os

from flask import request, abort, Response, jsonify
from flask import Flask
from flask_cors import CORS
import pandas as pd
from cassandra.query import BatchStatement, BatchType, dict_factory
from cassandra.cluster import ConsistencyLevel, Session, Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from datetime import datetime

HTTP_404_NOT_FOUND = 404
HTTP_500_INTERNAL_SERVER_ERROR = 500
HTTP_200_OK = 200

ENO_ENV = 'local_dev'

SERVER_INFO = {
    'port': int(os.getenv('PORT', 8126)),
    'keyspace': os.getenv('CASSANDRA_KEYSPACE', 'local'),
    'dbuser': os.getenv('CASSANDRA_USER', 'cassandra'),
    'dbpass': os.getenv('CASSANDRA_PASS', 'cassandra'),
    'dbpath': ''
}

HPFC_MAP = {
    'DE_': 'EEX_DE',
    'LU_': 'EEX_DE',
    'FR_': 'EEX_FR',
    'BE_': 'ICEEDX_BE',
    'TC_': 'EEX_DE',

    'EX_': 'EEX_DE',
    'PV_': 'EEX_DE_PV',
    'WI_': 'EEX_DE_WIND',
}


app = Flask(__name__)

# Initialize CORS
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:3000", "http://localhost:5173"],
        "supports_credentials": True
    }
})

config = {
    "local": {
        "DEBUG": True,
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

@app.route('/test_routes')
def test_routes():
    """Test route to verify Flask routing is working"""
    routes = [str(rule) for rule in app.url_map.iter_rules()]
    return jsonify({
        "message": "Routes are working",
        "available_routes": routes,
        "total_routes": len(routes)
    }), HTTP_200_OK



@app.route('/series_op_pfc/', methods=['POST'])
def upload_series_op():
    data = request.json

    as_of = parser.parse(data['as_of'])
    book_name = data['name']
    data_insertion_type = data['type']

    df_data = pd.DataFrame(data['data'])

    if data_insertion_type == 'HPFC_PWR':
        insert_pfc_power_data(df_data, book_name, as_of)    
    if data_insertion_type == 'OP_PWR':
        # Convert datetime to string format for insert_op_power_data
        as_of_str = as_of.strftime('%Y-%m-%d') if isinstance(as_of, datetime) else str(as_of)
        print(f"DEBUG: Inserting OP power data for {book_name} with as_of = {as_of_str}")
        insert_op_power_data(df_data, book_name, as_of_str)

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


def insert_op_power_data_simple(df: pd.DataFrame, name: str, as_of: datetime):
    """Simple function to insert OP_PWR data without requiring db_object."""
    if df.empty:
        abort(HTTP_404_NOT_FOUND, f"No data to insert for this as_of = {as_of} and book = {name}.")
        
    df['time'] = pd.to_datetime(df[['year', 'month', 'day', 'hour']], format="%Y-%m-%d %H").dt.tz_localize(
        LOCAL_TIME_ZONE, ambiguous='infer')
    df['time'] = df['time'].dt.tz_convert('UTC')    

    result = insert_op_power_data_cassandra(df, name, as_of)
    if not result:
        abort(HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to insert OP power data for {name, as_of}.")



THERE_ARE_NO_DATA_FOR_THE_OLD_AS_OF = "There are no data for the old as_of"
THERE_ARE_NO_DATA_FOR_THE_NEW_AS_OF = "There are no data for the new as_of"

LOCAL_TIME_ZONE = 'Europe/Luxembourg'


session: Session

def get_op_power_data(as_of, book_op, ts_start, ts_end):
    try:
        execution = session.execute("SELECT time, value, is_peak FROM series_op_power WHERE as_of=%s AND name = %s AND time >= %s AND time < %s", 
        (as_of, book_op, ts_start, ts_end))
        return list(execution)
    except Exception as e:
        return []


@app.route('/series_pfc_power', methods=['GET'])
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
        # Check if session is initialized
        if 'session' not in globals() or session is None:
            print("ERROR: Database session not initialized")
            return jsonify({"error": "Database session not initialized"}), HTTP_500_INTERNAL_SERVER_ERROR
        
        # Get query parameters
        name = request.args.get('name')
        as_of_str = request.args.get('as_of')
        ts_start_str = request.args.get('ts_start')
        ts_end_str = request.args.get('ts_end')
        
        print(f"DEBUG: Received request - name={name}, as_of={as_of_str}, ts_start={ts_start_str}, ts_end={ts_end_str}")
        
        # Validate required parameters
        if not name or not as_of_str:
            print(f"ERROR: Missing required parameters - name={name}, as_of={as_of_str}")
            return jsonify({"error": "Missing required parameters: 'name' and 'as_of' are required"}), HTTP_404_NOT_FOUND
        
        # Parse as_of timestamp - Cassandra stores as_of as a date type
        try:
            as_of_dt = parser.parse(as_of_str)
            # Extract date part (Cassandra as_of column is date type, not timestamp)
            as_of_date = as_of_dt.date()
            print(f"DEBUG: Parsed as_of_date={as_of_date}")
        except Exception as e:
            print(f"ERROR: Failed to parse as_of={as_of_str}, error={str(e)}")
            return jsonify({"error": f"Invalid as_of format: {as_of_str}"}), HTTP_404_NOT_FOUND
        
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
                print(f"DEBUG: Parsed timestamps - ts_start={ts_start}, ts_end={ts_end}")
            except Exception as e:
                print(f"ERROR: Failed to parse timestamps - ts_start={ts_start_str}, ts_end={ts_end_str}, error={str(e)}")
                return jsonify({"error": f"Invalid timestamp format: {str(e)}"}), HTTP_404_NOT_FOUND
            
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
        import traceback
        print(f"ERROR in get_pfc_power_data: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": f"Error retrieving PFC power data: {str(e)}"}), HTTP_500_INTERNAL_SERVER_ERROR



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
        print(f"ERROR in insert_power_pfc_data_cassandra: {str(e)}")
        return False

def get_all_pfc_power_data(as_of: datetime, name: str) -> pd.DataFrame:
    SELECT_ALL_PFC_POWER_FOR_AS_OF_AND_BOOK_NAME = """SELECT time, value, year, quarter, month, day, hour, week, wk_year, 
    is_peak, opHxD, pkHxD, opHxW, pkHxW, opHxM, pkHxM, opHxQ, pkHxQ, opHxY, pkHxY 
    FROM series_pfc_power 
    WHERE as_of=%s AND name=%s"""
    # Extract date part only - Cassandra as_of column is date type, not timestamp
    as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
    execution = session.execute(SELECT_ALL_PFC_POWER_FOR_AS_OF_AND_BOOK_NAME, (as_of_date, name))
    data = []
    for row in execution:
        row_dict = {
            'time': row.time,  # Keep as datetime object from Cassandra
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
        optional_cols = ['opHxD', 'pkHxD', 'opHxW', 'pkHxW', 'opHxM', 'pkHxM', 'opHxQ', 'pkHxQ', 'opHxY', 'pkHxY']
        for col in optional_cols:
            if hasattr(row, col):
                val = getattr(row, col)
                row_dict[col] = float(val) if val is not None else None
            elif hasattr(row, col.lower()):
                val = getattr(row, col.lower())
                row_dict[col] = float(val) if val is not None else None
            else:
                row_dict[col] = None
        data.append(row_dict)
    return pd.DataFrame(data)


def insert_op_power_data(df_op_power: pd.DataFrame, name: str, as_of: str):
    # Convert as_of string to datetime for get_all_pfc_power_data
    as_of_dt = parser.parse(as_of) if isinstance(as_of, str) else as_of
    df_pfc_power = get_all_pfc_power_data(as_of_dt, HPFC_MAP[name[:3]])

    if df_pfc_power.empty:
        abort(HTTP_404_NOT_FOUND, f"Missing PFC data for this as_of = {as_of} and book = {name}.")

    # Prepare PFC data
    df_pfc_power['value'] = 0
    # Only drop columns if they exist (name and as_of are not in the DataFrame from get_all_pfc_power_data)
    cols_to_drop = [col for col in ['name', 'as_of'] if col in df_pfc_power.columns]
    if cols_to_drop:
        df_pfc_power = df_pfc_power.drop(columns=cols_to_drop)
    # Ensure time is timezone-aware (it should already be from Cassandra, but check)
    if df_pfc_power['time'].dt.tz is None:
        df_pfc_power['time'] = df_pfc_power['time'].dt.tz_localize('UTC')
    else:
        df_pfc_power['time'] = df_pfc_power['time'].dt.tz_convert('UTC')
    df_pfc_power = df_pfc_power.set_index('time')

    # Process OP power data
    if df_op_power.empty:
        # If OP data is empty, use PFC structure with value=0
        df = df_pfc_power.copy()
    else:
        # Process OP power data to create time column and merge with PFC
        # clean up this messy fix for an AmbiguousTimeError
        try:
            df_op_power['time'] = (
                pd.to_datetime(df_op_power[['year', 'month', 'day', 'hour']], format="%Y-%m-%d %H")
                .dt.tz_localize(LOCAL_TIME_ZONE, ambiguous="infer")
            )
        except pytz.exceptions.AmbiguousTimeError:
            dst_fwd_month = df_op_power[df_op_power["month"] == 10]
            resulting_df = df_op_power.copy()

            for (year, month), month_df in dst_fwd_month.groupby(["year", "month"]):
                date_times = pd.to_datetime(month_df[["year", "month", "day", "hour"]])
                dst_day = date_times[date_times.dt.weekday == 6].iloc[-1].day

                dst_hour = month_df[
                    (month_df["year"] == year)
                    & (month_df["month"] == month)
                    & (month_df["day"] == dst_day)
                    & (month_df["hour"] == 2)
                    ]

                if len(dst_hour) == 1:
                    # copy is required to get rid of pandas SettingWithCopyWarning
                    dst_hour = dst_hour.copy()
                    dst_hour["load"] = 0
                    dst_hour["volume"] = 0
                    resulting_df = resulting_df.append(dst_hour, ignore_index=True)
                    date_info = dst_hour[["year", "month", "day", "hour"]].to_json(orient="records")
                    error_message = "AmbiguousTimeError: book: " + name + "; " + date_info
                    print(f"ERROR in insert_op_power_data: {error_message}")

            resulting_df.reset_index(drop=True)
            df_op_power = resulting_df.sort_values(by=["year", "month", "day", "hour"])
            df_op_power["time"] = pd.to_datetime(
                df_op_power[["year", "month", "day", "hour"]]
            ).dt.tz_localize(LOCAL_TIME_ZONE, ambiguous="infer")

        df_op_power['time'] = df_op_power['time'].dt.tz_convert('UTC')
        df_op_power = df_op_power.set_index('time')
        df_op_power = df_op_power["value"]  # we get rid of all the extra columns

        # Merge PFC and OP data
        df = pd.merge(df_pfc_power, df_op_power, on='time', how='left')
        df['value'] = df['value_y'].fillna(0)
        df = df.drop(columns=['value_x', 'value_y'])

    df = df.reset_index()  # need to reset the index otherwise it will not be a column

    result = insert_op_power_data_cassandra(df, name, as_of)
    if not result:
        abort(HTTP_500_INTERNAL_SERVER_ERROR, f"Failed to insert OP power data for {name, as_of}.")


def insert_op_power_data_cassandra(df: pd.DataFrame, name: str, as_of: datetime):
    INSERT_SERIES_QUERY_OP_POWER = """INSERT INTO series_op_power (name, as_of, value, time, year, quarter, month, 
    day, hour, week, wk_year, is_peak) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    insert_power_op = session.prepare(INSERT_SERIES_QUERY_OP_POWER)


    batch_statement = BatchStatement(consistency_level=ConsistencyLevel.LOCAL_QUORUM, batch_type=BatchType.UNLOGGED)
    # exclude DE_extSource because it does not have weighted new columns
    try:
        if name != 'DE_extSource':
            for row in df.itertuples():
                batch_statement.add(insert_power_op,
                                    (name, as_of, row.value, row.time.to_pydatetime(), row.year, row.quarter, row.month,
                                    row.day, row.hour, row.week, row.wk_year, bool(row.is_peak)),)
                if row.Index % 15000 == 0:
                    session.execute(batch_statement)
                    del batch_statement
                    batch_statement = BatchStatement(consistency_level=ConsistencyLevel.LOCAL_QUORUM,
                                                    batch_type=BatchType.UNLOGGED)
            session.execute(batch_statement)
            del batch_statement
            del df
            return True
    except Exception as e:
        print(f"ERROR in insert_op_power_data: {str(e)}")
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

# Session will be initialized in __main__ block

if __name__ == '__main__':
    # Parse properties file
    if not SERVER_INFO:
        sys.exit()
    try:
        init_session(SERVER_INFO["dbuser"], SERVER_INFO["dbpass"])
        print(f"Database session initialized successfully. Connected to keyspace: {SERVER_INFO['keyspace']}")
    except Exception as e:
        print(f"ERROR: Failed to initialize database session: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    app.run(port=SERVER_INFO["port"], debug=True)
    # log_file.close()


