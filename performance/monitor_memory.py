#!/usr/bin/env python3
"""
Memory monitoring script for the Python Flask API.
Monitors memory usage via /info/memory and /info/memory/simple endpoints.
"""

import requests
import time
import sys
import argparse
from datetime import datetime
import json

# Default API URL
DEFAULT_API_URL = "http://localhost:8126"
DEFAULT_INTERVAL = 5  # seconds


def get_memory_info(api_url, endpoint="/info/memory"):
    """Fetch memory information from the API."""
    try:
        url = f"{api_url}{endpoint}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error connecting to API at {url}: {e}")
        return None


def format_memory(mb):
    """Format memory value in MB with appropriate unit."""
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.2f} MB"


def print_detailed_memory(data):
    """Print detailed memory information."""
    if not data:
        return
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*70}")
    print(f"Memory Report - {timestamp}")
    print(f"{'='*70}")
    
    # Process memory
    if "process_memory" in data:
        pm = data["process_memory"]
        print(f"\n📊 Process Memory:")
        print(f"  RSS (Resident Set Size): {format_memory(pm.get('rss_mb', 0))} ({pm.get('rss', 0):,} bytes)")
        print(f"  VMS (Virtual Memory Size): {format_memory(pm.get('vms_mb', 0))} ({pm.get('vms', 0):,} bytes)")
        print(f"  Memory Percent: {pm.get('percent', 0):.2f}%")
    
    # System memory
    if "system_memory" in data:
        sm = data["system_memory"]
        print(f"\n💻 System Memory:")
        print(f"  Total: {format_memory(sm.get('total_mb', 0))} ({sm.get('total', 0):,} bytes)")
        print(f"  Used: {format_memory(sm.get('used_mb', 0))} ({sm.get('used', 0):,} bytes)")
        print(f"  Available: {format_memory(sm.get('available_mb', 0))} ({sm.get('available', 0):,} bytes)")
        print(f"  Free: {format_memory(sm.get('free_mb', 0))} ({sm.get('free', 0):,} bytes)")
        print(f"  Usage Percent: {sm.get('percent', 0):.2f}%")
    
    print(f"{'='*70}\n")


def print_simple_memory(data):
    """Print simple memory information."""
    if not data:
        return
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memory_mb = data.get("memory_mb", 0)
    status = data.get("status", "unknown")
    
    print(f"[{timestamp}] Process Memory: {format_memory(memory_mb)} | Status: {status}")


def monitor_continuous(api_url, interval, use_simple=True, log_file=None):
    """Continuously monitor memory at specified intervals."""
    print(f"🔍 Starting continuous memory monitoring...")
    print(f"   API URL: {api_url}")
    print(f"   Interval: {interval} seconds")
    print(f"   Mode: {'Simple' if use_simple else 'Detailed'}")
    print(f"   Press Ctrl+C to stop\n")
    
    iteration = 0
    log_data = []
    
    try:
        while True:
            iteration += 1
            endpoint = "/info/memory/simple" if use_simple else "/info/memory"
            data = get_memory_info(api_url, endpoint)
            
            if data:
                if use_simple:
                    print_simple_memory(data)
                else:
                    print_detailed_memory(data)
                
                # Log to file if specified
                if log_file:
                    log_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "iteration": iteration,
                        "data": data
                    }
                    log_data.append(log_entry)
                    
                    # Write to file periodically
                    if iteration % 10 == 0:
                        with open(log_file, 'w') as f:
                            json.dump(log_data, f, indent=2)
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print(f"\n\n⏹️  Monitoring stopped after {iteration} iterations")
        
        # Save final log
        if log_file and log_data:
            with open(log_file, 'w') as f:
                json.dump(log_data, f, indent=2)
            print(f"📝 Log saved to {log_file}")


def monitor_single(api_url, use_simple=False, output_json=False):
    """Get a single memory snapshot."""
    endpoint = "/info/memory/simple" if use_simple else "/info/memory"
    data = get_memory_info(api_url, endpoint)
    
    if data:
        if output_json:
            print(json.dumps(data, indent=2))
        else:
            if use_simple:
                print_simple_memory(data)
            else:
                print_detailed_memory(data)
        return data
    else:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Monitor memory usage of the Python Flask API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single detailed memory report
  python monitor_memory.py

  # Single simple memory report
  python monitor_memory.py --simple

  # Continuous monitoring (detailed, every 5 seconds)
  python monitor_memory.py --continuous

  # Continuous monitoring (simple, every 2 seconds)
  python monitor_memory.py --continuous --interval 2 --simple

  # Continuous monitoring with logging
  python monitor_memory.py --continuous --log memory_log.json
        """
    )
    
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"API base URL (default: {DEFAULT_API_URL})"
    )
    
    parser.add_argument(
        "--continuous",
        "-c",
        action="store_true",
        help="Run in continuous monitoring mode"
    )
    
    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Interval in seconds for continuous mode (default: {DEFAULT_INTERVAL})"
    )
    
    parser.add_argument(
        "--simple",
        "-s",
        action="store_true",
        help="Use simple memory endpoint (/info/memory/simple)"
    )
    
    parser.add_argument(
        "--log",
        "-l",
        help="Log file path for continuous monitoring (JSON format)"
    )
    
    parser.add_argument(
        "--json",
        "-j",
        action="store_true",
        help="Output in JSON format (for single mode)"
    )
    
    args = parser.parse_args()
    
    # Validate API URL
    if not args.api_url.startswith(("http://", "https://")):
        args.api_url = f"http://{args.api_url}"
    
    # Run monitoring
    if args.continuous:
        monitor_continuous(args.api_url, args.interval, args.simple, args.log)
    else:
        monitor_single(args.api_url, args.simple, args.json)


if __name__ == "__main__":
    main()

