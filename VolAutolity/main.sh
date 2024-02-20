#!/bin/bash

# Directory of the current script
script_dir="$(dirname "${BASH_SOURCE[0]}")"
source "${script_dir}/bash_volatility_runner.sh"

# Define the directory to scan and the file to keep track of processed files
DIRECTORY="/mnt/memorydumps"
PROCESSED_FILE="${DIRECTORY}/processed.txt"
LOG_FILE="${DIRECTORY}/processing_log.txt"

# Ensure the processed and log files exist
touch "$PROCESSED_FILE"
touch "$LOG_FILE"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Loop through each .dump and .dmp file in the directory
find "$DIRECTORY" -type f \( -name "*.dump" -o -name "*.dmp" \) | while read file; do
    # Check if the file has already been processed
    if ! grep -qF "$file" "$PROCESSED_FILE"; then
        # If not processed, add it to the list and process it
        echo "$file" >> "$PROCESSED_FILE"
        (
            if process_file "$file"; then
                log_message "Processed: $file"
            else
                log_message "Failed to process: $file"
            fi
        ) & # Runs new files concurrently
    fi
done

# Wait for all background processes to complete
wait
