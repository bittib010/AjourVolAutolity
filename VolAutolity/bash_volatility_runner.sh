#!/bin/bash

# Directory of the current script
script_dir="$(dirname "${BASH_SOURCE[0]}")"
source "${script_dir}/adx_vars_bash.sh"
DIRECTORY_TO_WATCH="/mnt/memorydumps"
BASE_OUTPUT_DIRECTORY="/mnt/memorydumps/output"

# Allowed file extensions (add more...)
declare -a allowed_extensions=("dd" "raw" "mem" "vmem" "dump" "dmp")

validate_file() {
    local file_name="$1"
    local extension="${file_name##*.}"
    local os_type="${file_name%%_*}"

    if [[ ! " ${allowed_extensions[@]} " =~ " ${extension} " ]]; then
        echo "File extension not supported for memory analysis: $extension"
        return 1
    fi

    case "$os_type" in
        "win")
            echo "Processing Windows memory dump"
            ;;
        "linux"|"osx")
            echo "Placeholder for future OS support. Skipping file: $file_name"
            return 1
            ;;
        *)
            echo "Unknown OS type in filename. Skipping file: $file_name"
            return 1
            ;;
    esac

    return 0
}

# Function to run Windows commands directly
run_windows_commands() {
    local dump="$1"
    local unique_output_directory="$2"
    local database_name="$3" # TODO: replace dots with _? Especially in need for the registry csv's?
    local log_file="$unique_output_directory/command_log.txt"

    # Define commands
    local commands=(
        # CREATE DATABASE
        "echo 'Creating the database'"
        "az kusto database create --cluster-name $cluster_name --database-name $database_name --resource-group $resource_group_name --read-write-database location=\"$azurerm_location\""

        # CREATE ALL TABLES
        "echo 'Creating all the tables'"
        "az kusto script create --cluster-name $cluster_name --database-name $database_name --name strings-script --resource-group $resource_group_name --script-content \"
        .create tables 
        strings (TreeDepth:int32,String:string,PhysicalAddress:string,Result:string),
        info (TreeDepth:int32, Variable:string, Value:string),
        timeliner (TreeDepth:int32,Plugin:string,Description:string,CreatedDate:string,ModifiedDate:string,AccessedDate:string,ChangedDate:string),
        bigpools (TreeDepth:int32, Allocation:string, Tag:string, PoolType:string, NumberOfBytes:string, Status:string),
        cachedump (TreeDepth:int32, Username:string, Domain:string, Domainname:string, Hash:string),
        callbacks (TreeDepth:int32, Type:string, Callback:string, Module:string, Symbol:string, Detail:string),
        cmdline (TreeDepth:int32, PID:int32, Process:string, Args:string),
        devicetree (TreeDepth:int32, Offset:string, Type:string, DriverName:string, DeviceName:string, DriverNameOfAttDevice:string, DeviceType:string),
        dlllist (TreeDepth:int32, PID:int32, Process:string, Base:string,Size:string, Name:string, Path:string, LoadTime:string, Fileoutput:string),
        driverirp (TreeDepth:int32, Offset:string, DriverName:string, IRP:string, Address:string, Module:string, Symbol:string),
        drivermodule (TreeDepth:int32, Offset:string, KnownException:string, DriverName:string, ServiceKey:string, AlternativeName:string),
        driverscan (TreeDepth:int, Offset:string, Start:string, Size:string, ServiceKey:string, DriverName:string, Name:string),
        dumpfiles (TreeDepth:int32,Cache:string,FileObject:string,FileName:string,Result:string),
        envars (TreeDepth:int32, PID:int32, Process:string, Block:string, Variable:string, Value:string),
        filescan (TreeDepth:int32, Offset:string, Name:string, Size:int32),
        getservicesids (TreeDepth:int32, SID:string, Service:string),
        getsids (TreeDepth:int32, PID:int32, Process:string, SID:string, Name:string),
        handles (TreeDepth:int32, PID:int32, Process:string, Offset:string, HandleValue:string, Type:string, GrantedAccess:string, Name:string),
        hashdump (TreeDepth:int32, User:string, rid:int32, lmhash:string, nthash:string),
        joblinks (TreeDepth:int32,OffsetV:string,Name:string,PID:int32,PPID:int32,Sess:string,JobSess:string,Wow64:string,Total:string,Active:string,Term:string,JobLink:string,Process:string),
        ldrmodules (TreeDepth:int32,Pid:int32,Process:string,Base:string,InLoad:string,InInit:string,InMem:string,MappedPath:string),
        lsadump (TreeDepth:int32,Key:string,Secret:string,Hex:string),
        malfind (TreeDepth:int32,PID:int32,Process:string,StartVPN:string,EndVPN:string,Tag:string,Protection:string,CommitCharge:string,PrivateMemory:string,Fileoutput:string,Notes:string,Hexdump:string,Disasm:string),
        mbrscan (TreeDepth:int32,PotentialMBRatPhysicalOffset:string,DiskSignature:string,BootcodeMD5:string,FullMBRMD5:string,PartitionIndex:string,Bootable:string,PartitionType:string,SectorInSize:string,Disasm:string),
        memmap (TreeDepth:int32,Virtual:string,Physical:string,Size:string,OffsetinFile:string,Fileoutput:string),
        mftscan (TreeDepth:int32,Offset:string,RecordType:string,RecordNumber:string,LinkCount:string,MFTType:string,Permissions:string,AttributeType:string,Created:string,Modified:string,Updated:string,Accessed:string,Filename:string),
        modscan (TreeDepth:int32,Offset:string,Base:string,Size:string,Name:string,Path:string,Fileoutputished:string),
        modules (TreeDepth:int32,Offset:string,Base:string,Size:string,Name:string,Path:string,Fileoutputished:string),
        mutantscan (TreeDepth:int32,Offset:string,Name:string),
        netscan (TreeDepth:int32,Offset:string,Proto:string,LocalAddr:string,LocalPort:string,ForeignAddr:string,ForeignPort:string,State:string,PID:int32,Owner:string,Created:string),
        netstat (TreeDepth:int32,Offset:string,Proto:string,LocalAddr:string,LocalPort:string,ForeignAddr:string,ForeignPort:string,State:string,PID:int32,Owner:string,Created:string),
        poolscanner (TreeDepth:int32,Tag:string,Offset:string,Layer:string,Name:string),
        privileges (TreeDepth:int32,PID:int32,Process:string,Value:string,Privilege:string,Attributes:string,Description:string),
        pslist (TreeDepth:int32, PID:int32, PPID:int32, ImageFileName:string, OffsetV:string, Threads:string, Handles:string, SessionId:string, Wow64:string, CreateTime:string, ExitTime:string, Fileoutput:string),
        psscan (TreeDepth:int32, PID:int32, PPID:int32, ImageFileName:string, OffsetV:string, Threads:string, Handles:string, SessionId:string, Wow64:string, CreateTime:datetime, ExitTime:datetime, Fileoutput:string),
        // pstree (TreeDepth:int32, PID:int32, PPID:int32, ImageFileName:string, OffsetV:string, Threads:string, Handles:string, SessionId:string, Wow64:string, CreateTime:string, ExitTime:string, Audit:string, Cmd:string, Path:string),
        registry (TreeDepth:int32,Certificatepath:string,Certificatesection:string,CertificateID:string,Certificatename:string),
        registry_hivelist (TreeDepth:int32,Offset:string,FileFullPath:string,Fileoutput:string),
        registry_hivescan (TreeDepth:int32,Offset:string),
        registry_printkey (TreeDepth:int32,LastWriteTime:string,HiveOffset:string,Type:string,Key:string,Name:string,Data:string,Volatile:string),
        registry_userassist (TreeDepth:int32,HiveOffset:string,HiveName:string,Path:string,LastWriteTime:string,Type:string,Name:string,ID:string,Count:string,FocusCount:string,TimeFocused:string,LastUpdated:string,RawData:string),
        skeleton_key_check (TreeDepth:int32,PID:int32,Process:string,SkeletonKeyFound:string,rc4HmacInitialize:string,rc4HmacDecrypt:string),
        ssdt (TreeDepth:int32,Index:string,Address:string,Module:string,Symbol:string),
        Statistics (TreeDepth:string,Validpagesall:string,Validpageslarge:string,SwappedPagesall:string,SwappedPageslarge:string,InvalidPagesall:string,InvalidPageslarge:string,OtherInvalidPagesall:string),
        svcscan (TreeDepth:int32,Offset:string,Order:string,PID:int32,Start:string,State:string,Type:string,Name:string,Display:string,Binary:string,BinaryRegistry:string,Dll:string),
        symlinkscan (TreeDepth:int32,Offset:string,CreateTime:string,FromName:string,ToName:string),
        vadinfo (TreeDepth:int32,PID:int32,Process:string,Offset:string,StartVPN:string,EndVPN:string,Tag:string,Protection:string,CommitCharge:string,PrivateMemory:string,Parent:string,File:string,Fileoutput:string),
        vadwalk (TreeDepth:int32,PID:int32,Process:string,Offset:string,Parent:string,Left:string,Right:string,Start:string,End:string,Tag:string),
        vadyarascan (TreeDepth:int32,Offset:string,PID:int32,Rule:string,Component:string,Value:string),
        verinfo (TreeDepth:int32, PID:int32, Process:string, Base:string, Name:string, Major:string, Minor:string, Product:string, Build:string),
        virtmap (TreeDepth:int32,Region:string,Startoffset:string,Endoffset:string)\""

        "echo 'Starting to run Volatility commands. lowercase statistics seems preserved by Kusto'"
        "strings -a -td $dump > $unique_output_directory/strings.txt && strings -a -td -el $dump  > $unique_output_directory/strings.txt && vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.strings.Strings --strings-file $unique_output_directory/strings.txt > $unique_output_directory/strings.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.info > $unique_output_directory/info.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv timeliner > $unique_output_directory/timeliner.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.bigpools > $unique_output_directory/bigpools.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.cachedump > $unique_output_directory/cachedump.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.callbacks.Callbacks > $unique_output_directory/callbacks.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.cmdline.CmdLine > $unique_output_directory/cmdline.csv"
        #"vol.py -f {crashdump} --log $unique_output_directory/Volatility.log -q -r csv windows.crashinfo.Crashinfo > $unique_output_directory/crashinfo.csv"
        #"az kusto script create --cluster-name $cluster_name --database-name $database_name --name crashinfo-script --resource-group $resource_group_name --script-content \".create table crashinfo (NotCreatedYet:string)\""
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.devicetree.DeviceTree > $unique_output_directory/devicetree.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.dlllist.DllList > $unique_output_directory/dlllist.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.driverirp.DriverIrp > $unique_output_directory/driverirp.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.drivermodule.DriverModule > $unique_output_directory/drivermodule.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.driverscan.DriverScan > $unique_output_directory/driverscan.csv"
        "mkdir $unique_output_directory/dumpfiles"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q  -o $unique_output_directory/dumpfiles/ windows.dumpfiles.DumpFiles &"
        # LOGIC TO RUN CLAMAV
        
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.dumpfiles.DumpFiles > $unique_output_directory/dumpfiles.csv"        
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.envars.Envars > $unique_output_directory/envars.csv"        
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.filescan.FileScan > $unique_output_directory/filescan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.getservicesids.GetServiceSIDs > $unique_output_directory/getservicesids.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.getsids.GetSIDs > $unique_output_directory/getsids.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.handles.Handles > $unique_output_directory/handles.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.hashdump.Hashdump > $unique_output_directory/hashdump.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.joblinks.JobLinks > $unique_output_directory/joblinks.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.ldrmodules.LdrModules > $unique_output_directory/ldrmodules.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.lsadump.Lsadump > $unique_output_directory/lsadump.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.malfind.Malfind > $unique_output_directory/malfind.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.mbrscan.MBRScan > $unique_output_directory/mbrscan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.memmap.Memmap > $unique_output_directory/memmap.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.mftscan.MFTScan > $unique_output_directory/mftscan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.modscan.ModScan > $unique_output_directory/modscan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.modules.Modules > $unique_output_directory/modules.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.mutantscan.MutantScan > $unique_output_directory/mutantscan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.netscan.NetScan > $unique_output_directory/netscan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.netstat.NetStat > $unique_output_directory/netstat.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.poolscanner.PoolScanner > $unique_output_directory/poolscanner.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.privileges.Privs > $unique_output_directory/privileges.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.pslist.PsList > $unique_output_directory/pslist.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.psscan.PsScan > $unique_output_directory/psscan.csv"
        #"vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.pstree.PsTree > $unique_output_directory/pstree.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.registry.certificates.Certificates > $unique_output_directory/registry.csv"
        "mkdir $unique_output_directory/regdumps"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv -o $unique_output_directory/regdumps/ windows.registry.hivelist.HiveList &"
        # LOGIC NEEDED
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.registry.hivelist.HiveList > $unique_output_directory/registry_hivelist.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.registry.hivescan.HiveScan > $unique_output_directory/registry_hivescan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.registry.printkey.PrintKey > $unique_output_directory/registry_printkey.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.registry.userassist.UserAssist > $unique_output_directory/registry_userassist.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.sessions.Sessions > $unique_output_directory/sessions.csv"
        #"az kusto script create --cluster-name $cluster_name --database-name $database_name --name sessions-script --resource-group $resource_group_name --script-content \".create table sessions (TreeDepth:int32,SessionID:string,SessionType:string,ProcessID:string,Process:string,UserName:string,CreateTime:string)\""
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.skeleton_key_check.Skeleton_Key_Check > $unique_output_directory/skeleton_key_check.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.ssdt.SSDT > $unique_output_directory/ssdt.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.statistics.Statistics > $unique_output_directory/statistics.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.svcscan.SvcScan > $unique_output_directory/svcscan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.symlinkscan.SymlinkScan > $unique_output_directory/symlinkscan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.vadinfo.VadInfo > $unique_output_directory/vadinfo.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.vadwalk.VadWalk > $unique_output_directory/vadwalk.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.vadyarascan.VadYaraScan > $unique_output_directory/vadyarascan.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.verinfo.VerInfo > $unique_output_directory/verinfo.csv"
        "vol.py -f $dump --log $unique_output_directory/Volatility.log -q -r csv windows.virtmap.VirtMap > $unique_output_directory/virtmap.csv"

        "inotifywait -m \"$unique_output_directory\" -e close_write --format '%w%f' |
            while IFS= read -r new_file; do
                if [[ \"$new_file\" =~ \.csv$ ]]; then
                    echo \"New file detected: $new_file\"
                    # Extract filename without path and extension for table name
                    filename=$(basename -- \"$new_file\")
                    tablename=\"${filename%.*}\"
                    python3 /home/AzVolAutolity/VolAutolity/file_ingestion.py --file_path \"$new_file\" --database \"$database_name\" --table \"$tablename\" --tenant_id \"$TENANT_ID\" --client_id \"$CLIENT_ID\" --client_secret \"$CLIENT_SECRET\" --cluster_ingestion_uri \"$cluster_ingestion_uri\"
                fi
            done"
        )

  # Strings to check in the output that would trigger a rerun
    declare -a rerun_if_contains=("A symbol table requirement was not fulfilled." "Unsatisfied requirement plugins.")

    # Execute each command
    for cmd in "${commands[@]}"; do
        echo "Executing: $cmd" | tee -a "$log_file"

        if [[ $cmd == vol.py* ]]; then
            # Temporary file to hold command output for inspection
            local temp_output="$(mktemp)"
            eval "$cmd" &> "$temp_output"
            cat "$temp_output" >> "$log_file" # Append the output to the log file

            # Check if output contains any of the rerun strings
            for rerun_string in "${rerun_if_contains[@]}"; do
                if grep -q "$rerun_string" "$temp_output"; then
                    echo "Output contains '$rerun_string', rerunning command: $cmd" | tee -a "$log_file"
                    eval "$cmd" &>> "$log_file" # Rerun command and append both stdout and stderr to log
                    break # Break after rerun, assuming only one rerun is needed
                fi
            done

            # Clean up temporary file
            rm "$temp_output"
        else
            # For non-vol.py commands, execute normally
            if ! eval "$cmd" &>> "$log_file"; then
                echo "Command encountered an error, but continuing: $cmd" >> "$log_file"
            fi
        fi
    done
}

# Function to process a new file with all specified Volatility commands
process_new_file() {
    local dump_path="$1"
    local dump_name=$(basename "$dump_path")
    local dump_name_no_ext="${dump_name%.*}"

    if ! validate_file "$dump_name"; then
        return
    fi

    local unique_output_directory="$BASE_OUTPUT_DIRECTORY/$dump_name_no_ext"
    mkdir -p "$unique_output_directory"

    # Run Windows commands
    run_windows_commands "$dump_path" "$unique_output_directory" "$dump_name_no_ext"
}