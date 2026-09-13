# Time-Series API: Python Flask vs Java Spring Boot

This project compares two implementations of a time-series power API:

- `performance/`: Python Flask API with Cassandra access, bulk data insertion, and process memory endpoints.
- `performance_java/`: Java 17 Spring Boot API with Cassandra access and parallel day-to-day power processing.

The project is used to study API behavior, Cassandra-backed time-series queries, memory consumption, and the performance trade-offs between Python and Java.

## Repository Structure

```text
performance/
	app.py                    Flask API and memory endpoints
	app_insert.py             Flask insertion/query variant
	insert_timeseries_data.py Bulk JSON-to-Cassandra loader
	load_data_to_cassandra.py Cassandra startup helper
	monitor_memory.py         Python process memory monitoring
	time_series_data/         Sample HPFC and OP power data
	requirements.txt          Python dependencies

performance_java/
	pom.xml                   Maven build configuration
	src/main/java/            Spring Boot application and Cassandra service
	src/main/resources/       Application configuration and templates
	monitor_memory.sh         Java process monitoring helper
```

Generated environments and build output are intentionally excluded from Git. Create a new Python virtual environment and let Maven recreate `target/` locally.

## Requirements

- Python 3.9 or newer
- Java 17
- Maven 3.8 or newer
- Apache Cassandra running on `127.0.0.1:9042`
- A Cassandra keyspace named `local` with the tables expected by the application

The default Cassandra credentials are `cassandra` / `cassandra`. Change them through environment variables for the Python application. The Java Cassandra connection is currently configured in `performance_java/src/main/java/com/enovos/AppConfig.java`.

## Python Flask API

From the repository root:

```bash
cd performance
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python app.py
```

The Python server uses port `8126` by default. Set `PORT` to change it. Cassandra settings are read from:

```text
CASSANDRA_CONTACT_POINTS   Comma-separated hosts, default: 127.0.0.1
CASSANDRA_KEYSPACE         Default: local
CASSANDRA_USER             Default: cassandra
CASSANDRA_PASS             Default: cassandra
PORT                       Default: 8126
```

Useful endpoints include:

```text
GET  /status
GET  /info/memory
GET  /info/memory/simple
GET  /d2d_new_2/power
POST /series_op_pfc/
```

Example memory request:

```bash
curl http://localhost:8126/info/memory/simple
```

Example day-to-day power request:

```bash
curl -G http://localhost:8126/d2d_new_2/power \
	--data-urlencode "books=DE_PFM,LU_STC" \
	--data-urlencode "as_of_op_old=2025-08-06" \
	--data-urlencode "as_of_op_new=2025-08-15" \
	--data-urlencode "ts_start=2025-10-01T00:00:00+02:00" \
	--data-urlencode "ts_end=2030-01-01T00:00:00+01:00" \
	--data-urlencode "aggr=hour"
```

Load the sample JSON files into Cassandra with:

```bash
python insert_timeseries_data.py
```

The loader reads files from `performance/time_series_data/` and inserts `OP_PWR` and `HPFC_PWR` records into Cassandra.

## Java Spring Boot API

From the repository root:

```bash
cd performance_java
mvn spring-boot:run
```

The Spring Boot server uses port `8080` by default. Its main routes are:

```text
GET /                         Basic application response
GET /cassandra                Cassandra connectivity check
GET /d2d_new_2/power          Day-to-day power processing
```

Example request:

```bash
curl -G http://localhost:8080/d2d_new_2/power \
	--data-urlencode "books=DE_PFM,LU_STC" \
	--data-urlencode "as_of_op_old=2025-08-06" \
	--data-urlencode "as_of_op_new=2025-08-15" \
	--data-urlencode "ts_start=2025-10-01T00:00:00+02:00" \
	--data-urlencode "ts_end=2030-01-01T00:00:00+01:00" \
	--data-urlencode "aggr=hour"
```

Build the Java application without starting it:

```bash
mvn clean package
```

## Memory and Performance Analysis

The repository includes monitoring scripts and implementation-specific profiling code:

- Python exposes RSS and virtual memory through `/info/memory` and `/info/memory/simple`.
- `performance/monitor_memory.py` monitors the Python process.
- `performance_java/monitor_memory.sh` and standard JVM tools such as `jstat` and `jmap` can be used for Java measurements.
- The Java implementation processes books in parallel using a fixed thread pool and `CompletableFuture`.

The recorded Java experiment processed 13 books in approximately 45 seconds in the parallel version versus approximately 48 seconds sequentially. These values depend on the Cassandra dataset, hardware, JVM options, and workload, so they should be treated as an experiment result rather than a universal benchmark.

## Notes

- Both applications expect compatible Cassandra schemas and data.
- Start Cassandra before starting either API.
- Do not commit credentials, virtual environments, Maven output, or local memory-profile logs.

