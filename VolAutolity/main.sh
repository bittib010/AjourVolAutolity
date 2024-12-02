#!/bin/bash

# Directory of the current script
script_dir="$(dirname "${BASH_SOURCE[0]}")"

# Source the external script
source "${script_dir}/bash_volatility_runner.sh"

# Directory to scan and files to track processed files and logs
DIRECTORY="/mnt/memorydumps"
PROCESSED_FILE="${DIRECTORY}/processed.txt"
LOG_FILE="${DIRECTORY}/processing_log.txt"

# Ensure the processed and log files exist
touch "$PROCESSED_FILE"
touch "$LOG_FILE"

# Log messages with a timestamp
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Process each memory dump file in the directory
find "$DIRECTORY" -type f \( -name "*.dump" -o -name "*.dmp" -o -name "*.raw" -o -name "*.dd" -o -name "*.mem" -o -name "*.vmem" -o -name "*.sys" \) | while read file; do
    # Check if the file has already been processed
    if ! grep -qF "$file" "$PROCESSED_FILE"; then
        # Add to processed list and process the file
        echo "$file" >> "$PROCESSED_FILE"
        (
            if process_new_file "$file"; then
                log_message "Processed: $file"
            else
                log_message "Failed to process: $file"
            fi
        ) & # Run in the background
        sleep 60 # Avoid conflicts or rate limits
    fi
done

# Wait for all background processes to complete
wait
