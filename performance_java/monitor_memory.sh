#!/bin/bash

# Memory monitoring script for Spring Boot application
PID=$(ps aux | grep "com.enovos.App" | grep -v grep | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "Spring Boot application not found!"
    exit 1
fi

echo "Monitoring Spring Boot Application (PID: $PID)"
echo "Press Ctrl+C to stop"
echo "=========================================="
echo "Time                RSS(MB)    Heap(MB)   OldGen(MB)  YoungGen(MB)  Metaspace(MB)  GC Count"
echo "=========================================="

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Get RSS memory in MB
    RSS_KB=$(ps -p $PID -o rss= 2>/dev/null)
    RSS_MB=$((RSS_KB / 1024))
    
    # Get heap memory details using jstat
    if command -v jstat &> /dev/null; then
        GC_INFO=$(jstat -gc $PID 2>/dev/null | tail -1)
        if [ ! -z "$GC_INFO" ]; then
            # Parse jstat output: S0C S1C S0U S1U EC EU OC OU MC MU CCSC CCSU YGC YGCT FGC FGCT CGC CGCT GCT
            EC=$(echo $GC_INFO | awk '{print $5}' | cut -d. -f1)
            EU=$(echo $GC_INFO | awk '{print $6}' | cut -d. -f1)
            OC=$(echo $GC_INFO | awk '{print $7}' | cut -d. -f1)
            OU=$(echo $GC_INFO | awk '{print $8}' | cut -d. -f1)
            MC=$(echo $GC_INFO | awk '{print $9}' | cut -d. -f1)
            MU=$(echo $GC_INFO | awk '{print $10}' | cut -d. -f1)
            YGC=$(echo $GC_INFO | awk '{print $13}')
            FGC=$(echo $GC_INFO | awk '{print $15}')
            
            # Convert to MB
            EC_MB=$((EC / 1024))
            EU_MB=$((EU / 1024))
            OC_MB=$((OC / 1024))
            OU_MB=$((OU / 1024))
            MC_MB=$((MC / 1024))
            MU_MB=$((MU / 1024))
            
            HEAP_MB=$((EU_MB + OU_MB))
            GC_COUNT=$((YGC + FGC))
            
            printf "%-19s %-10s %-10s %-11s %-13s %-14s %-10s\n" \
                "$TIMESTAMP" \
                "$RSS_MB" \
                "$HEAP_MB" \
                "$OU_MB" \
                "$EU_MB" \
                "$MU_MB" \
                "$GC_COUNT"
        else
            printf "%-19s %-10s %-10s %-11s %-13s %-14s %-10s\n" \
                "$TIMESTAMP" \
                "$RSS_MB" \
                "N/A" \
                "N/A" \
                "N/A" \
                "N/A" \
                "N/A"
        fi
    else
        printf "%-19s %-10s %-10s %-11s %-13s %-14s %-10s\n" \
            "$TIMESTAMP" \
            "$RSS_MB" \
            "N/A" \
            "N/A" \
            "N/A" \
            "N/A" \
            "N/A"
    fi
    
    sleep 5
done

