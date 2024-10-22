# GPT replacement?

#!/bin/bash

# Enable strict error handling and safe variable expansion
set -euo pipefail
IFS=$'\n\t'

# Directory of the current script
script_dir="$(dirname "${BASH_SOURCE[0]}")"
source "${script_dir}/adx_vars_bash.sh"

# Configuration variables
DIRECTORY_TO_WATCH="/mnt/memorydumps"
BASE_OUTPUT_DIRECTORY="/mnt/memorydumps/output"

# Main function to process a new file
process_new_file() {
    local dump_path="$1"
    local dump_name
    dump_name=$(basename "$dump_path")
    local dump_name_no_ext="${dump_name%.*}"
    local os_type
    os_type=$(determine_os "$dump_name")

    if [[ -z "$os_type" ]]; then
        echo "Could not determine OS type for file: $dump_name"
        return
    fi

    local unique_output_directory="$BASE_OUTPUT_DIRECTORY/$dump_name_no_ext"
    mkdir -p "$unique_output_directory"
    run_os_commands "$dump_path" "$unique_output_directory" "$os_type" "$dump_name_no_ext"
}

# Function to determine the OS type based on the filename
determine_os() {
    local file_name="$1"
    case "${file_name%%_*}" in
        win) echo "win" ;;
        linux) echo "linux" ;;
        osx) echo "osx" ;;
        *) echo "" ;;
    esac
}

# Function to run OS-specific commands
run_os_commands() {
    local dump="$1"
    local output_dir="$2"
    local os_type="$3"
    local database_name="$4"
    local log_file="$output_dir/command_log.txt"

    if [[ "$os_type" == "win" ]]; then
        setup_database "$database_name" "$log_file"
        monitor_output_directory "$output_dir" "$database_name" &

        # Create necessary directories
        mkdir -p "$output_dir/dumpfiles" "$output_dir/clamscan_tmp" "$output_dir/regdumps"

        # Run Volatility commands
        run_volatility_commands "$dump" "$output_dir" "$log_file"
    else
        echo "Unsupported OS type: $os_type" | tee -a "$log_file"
        return 1
    fi
}

# Function to set up the database and tables
setup_database() {
    local database_name="$1"
    local log_file="$2"

    echo 'Creating the database' | tee -a "$log_file"
    az kusto database create \
        --cluster-name "$cluster_name" \
        --database-name "$database_name" \
        --resource-group "$resource_group_name" \
        --read-write-database location="$azurerm_location" &>> "$log_file"

    echo 'Creating all the tables' | tee -a "$log_file"
    az kusto script create \
        --cluster-name "$cluster_name" \
        --database-name "$database_name" \
        --name "strings-script" \
        --resource-group "$resource_group_name" \
        --script-content "$(generate_kusto_table_creation_script)" &>> "$log_file"
}

# Function to generate Kusto table creation script
generate_kusto_table_creation_script() {
    cat <<'EOF'
.create tables
strings (TreeDepth:int32, String:string, PhysicalAddress:string, Result:string),
info (TreeDepth:int32, Variable:string, Value:int32),
timeliner (TreeDepth:int32, Plugin:string, Description:string, CreatedDate:string, ModifiedDate:string, AccessedDate:string, ChangedDate:string),
-- Add other table definitions here
EOF
}

# Function to run Volatility commands
run_volatility_commands() {
    local dump="$1"
    local output_dir="$2"
    local log_file="$3"

    echo "Starting to run Volatility commands..." | tee -a "$log_file"

    # Extract strings separately
    echo "Extracting strings..." | tee -a "$log_file"
    strings -a -td "$dump" > "$output_dir/strings.txt"
    strings -a -td -el "$dump" >> "$output_dir/strings.txt"
    vol.py -f "$dump" --log "$output_dir/Volatility.log" -q -r csv windows.strings.Strings \
        --strings-file "$output_dir/strings.txt" > "$output_dir/strings.csv" &

    # Define an array of plugins and their output files
    declare -A plugins=(
        ["windows.info"]="info.csv"
        ["timeliner"]="timeliner.csv"
        ["windows.bigpools"]="bigpools.csv"
        # Add other plugins here
    )

    # Run each plugin
    for plugin in "${!plugins[@]}"; do
        local output_file="${plugins[$plugin]}"
        echo "Executing plugin $plugin..." | tee -a "$log_file"
        vol.py -f "$dump" --log "$output_dir/Volatility.log" -q -r csv $plugin > "$output_dir/$output_file" &
    done

    # Special handling for clamscan
    echo "Running clamscan..." | tee -a "$log_file"
    vol.py -f "$dump" --log "$output_dir/Volatility.log" -q -o "$output_dir/dumpfiles" windows.dumpfiles.DumpFiles
    clamscan "$output_dir/dumpfiles/"* > "$output_dir/clamscan_tmp/clamscan.txt"
    convert_clamscan_output_to_csv "$output_dir/clamscan_tmp/clamscan.txt" "$output_dir/clamscan.csv" &

    # Handle registry hive dumping
    echo "Dumping registry hives..." | tee -a "$log_file"
    vol.py -f "$dump" --log "$output_dir/Volatility.log" -q -r csv -o "$output_dir/regdumps/" \
        windows.registry.hivelist.HiveList --dump &
    vol.py -f "$dump" --log "$output_dir/Volatility.log" -q -r csv windows.registry.hivelist.HiveList \
        > "$output_dir/registry_hivelist.csv"
    printkeys_for_each_hive "$output_dir/registry_hivelist.csv" "$dump" "$output_dir"
}

# Function to monitor the output directory and process new CSV files
monitor_output_directory() {
    local output_dir="$1"
    local database_name="$2"
    local processed_dir="$output_dir/processed"
    mkdir -p "$processed_dir"

    echo "Starting to monitor $output_dir for new CSV files..."
    inotifywait -m "$output_dir" -e close_write --format '%w%f' |
    while read -r new_file; do
        if [[ "$new_file" == *.csv ]]; then
            local filename
            filename=$(basename "$new_file")
            local processed_file="$processed_dir/$filename"

            if [[ ! -f "$processed_file" ]]; then
                echo "New CSV file detected: $new_file"
                local tablename="${filename%.*}"
                python3 /home/AzVolAutolity/VolAutolity/file_ingestion.py \
                    --file_path "$new_file" \
                    --database "$database_name" \
                    --table "$tablename" \
                    --tenant_id "$TENANT_ID" \
                    --client_id "$CLIENT_ID" \
                    --client_secret "$CLIENT_SECRET" \
                    --cluster_ingestion_uri "$cluster_ingestion_uri"
                touch "$processed_file"
            else
                echo "CSV file already processed, skipping: $new_file"
            fi
        fi
    done
}

# Function to convert clamscan output to CSV
convert_clamscan_output_to_csv() {
    local input_file="$1"
    local output_csv="$2"

    [[ -f "$input_file" ]] || { echo "Input file does not exist: $input_file"; exit 1; }

    echo "File,Result" > "$output_csv"
    awk -F':' '/FOUND|OK$/ {gsub(/,/,";",$1); print "\"" $1 "\",\"" $2 "\""}' "$input_file" >> "$output_csv"
    echo "Clamscan results saved to $output_csv"
}

# Function to process registry keys for each hive
printkeys_for_each_hive() {
    local hive_list_file="$1"
    local dump="$2"
    local output_dir="$3"
    declare -A key_counter

    [[ -f "$hive_list_file" ]] || { echo "File $hive_list_file does not exist."; return 1; }

    tail -n +2 "$hive_list_file" | cut -d ',' -f2,3 | while IFS=',' read -r offset file_full_path; do
        local base_name
        base_name=$(basename "${file_full_path//\\//}")
        local filename_key="${base_name%%.*}"
        filename_key="${filename_key:-UnnamedKey}"
        ((key_counter[$filename_key]++))
        [[ "${key_counter[$filename_key]}" -gt 1 ]] && filename_key+="${key_counter[$filename_key]}"

        vol.py -f "$dump" --log "$output_dir/Volatility.log" -q -r csv windows.registry.printkey \
            --offset "$offset" --recurse >> "$output_dir/printkey_${filename_key}.csv"
    done
}

# Main script logic
main() {
    for dump_file in "$DIRECTORY_TO_WATCH"/*; do
        [[ -f "$dump_file" ]] && process_new_file "$dump_file"
    done
}

main "$@"
