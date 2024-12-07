# AjourVolAutolity

## Goal of the project
The goal of this project is
- leveraging power of the cloud, 
- automate the volatility commands,
- speed up the process from acquisition-end to analysis-start,
- utilizing the speed of KQL to find answers quickly on large data sets,
- spend time doing more important stuff than running a bunch of commands on repeat!

This is set up in such a way that allows us to upload as many dumps as we need to. Every Volatility session will be linked with it's dump which will be stored into it's own separate database.

> [!NOTE]  
> This is a work in progress with a lot of additions and improvements already planned. If you want to contribute - please feel free to do so. Suggestions are also very welcome. Currently limited to focus only on Windows.

### Workflow 
The analysor spins up the terraform setup, sends the uploading links/commands to the person acquiring the image(s), who then uploads. The analysor waits until ingestion has been made and starts actively querying the data. Hands-off from upload to querying.

## Parent Child relations
An important part of knowing how to analyse memory dumps is to be aware of known goods. I've created this overview which i tend to analyse and update from time to time. 
```mermaid
mindmap
  Core processes
    system idle process
      Parents None
      Children None
      PID 0
      Occurences 1
      User
        NT AUTHORITY\SYSTEM (S-1-5-18)
    system
      Parents None
      Children
        smss.exe
      PID 4
    userinit.exe
      Parents
        winlogon.exe
      Children
        explorer.exe
        cmd.exe containing \*\\\\netlogon\\\\\*
    RuntimeBroker.exe
      Parents
        svchost.exe
      Children
        InvestigateFurther
    winlogon.exe
      Parents
        smss.exe
      Children
        userinit.exe
        scrnsave.scr
        mpnotify.exe
        dwm.exe
        fontdrvhost.exe
        wlrmdr.exe
        sethc.exe
        LaunchTM.exe
        DisplaySwitch.exe
        AtBroker.exe
        explorer.exe
        Ribbons.scr
        PhotoScreensaver.scr
        Bubbles.scr
        Mystify.scr
    taskhostw.exe
      Parents
        services.exe
      Children
        werfault.exe? 
    gpscript.exe
      Parents
        svchost.exe
      Children
        cmd.exe containing \*\\\\sysvol\\\\\*
    c:\windows\explorer
      Parents
        Could be anything
        explorer.exe
        userinit.exe
        winlogon.exe
      Children
        Programs set to autostart
          RunKey
          StartupFolder
    searchprotocolhost.exe
      Parents
        searchindexer.exe
        dllhost.exe
      Children
        InvestigateFurther
    wmiprvse.exe, wsmprovhost.exe, winrshost.exe
      Parents
        svchost.exe
      Children
        Many. In general legit SCCM related.
    conhost.exe
      Parents
        cmd.exe
        powershell.exe
        Many More
      Children
        InvestigateFurther
    searchindexer.exe
      Parents
        services.exe
      Children
        searchindexer.exe
        searchfilterhost.exe
        wermgr.exe
    taskhostw.exe
      Parents
        svchost.exe
      Children
        DsmUserTask.exe
        WinSat.exe
        WerFault.exe
        InvestigateFurther
    svchost.exe
      Parents
        services.exe
      Children
        Consider blacklist
          Check cmd parent containing \*schedule\*
    lsass.exe
      Parents
        wininit.exe
      Children
        Childrens are rare
        Exclude legit ones like passwordfilters etc
    wininit.exe
      Parents
        smss.exe
      Children
        lsass.exe
        services.exe
        lsm.exe
        LsaIso.exe
        WerFault.exe
    DllHost.exe
      Parents
        svchost.exe
      Children
        InvestigateFurther
    smss.exe
      Parents
        System? Investigate
        smss.exe
      Children
        winlogon.exe
    services.exe
      Parents
        wininit.exe
      Children
        svchost.exe
        3rd party standalone exe
        System Scheduled Tasks
    spoolsv.exe
      Parents
        services.exe
      Children
        splwow64.exe
    csrss.exe
      Parents
        smss.exe
      Children
        InvestigateFurther
```




# Process of setting it up and "How to"
## Requirements
### Roles in Azure
You need "AllDatabasesAdmin" role to be able to read, view and write to the ADX cluster. And to create everything there are a lot of others as well - I have currently been a root tenant owner.

To run scripts on database you need Contributor role on the cluster and Admin role on the database - Pretty much covered.

CloudApplicationAdmin is per now not covered in code.

As root tenant owner you don't need any other permissions/roles as far as my testing goes.

### Install and login
 
Install Terraform: https://developer.hashicorp.com/terraform/install#Windows 

Install Azure CLI: https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows?tabs=winget

Login and set subscription:
```powershell
az login # Prompts you interactively via last opened browser and spits out all available subscriptions for your user
az account set --subscription "<INSERT SUBSCRIPTION ID OR NAME>"
```

## Steps to deploy

Set the variable for your initials, path to your public and private SSH-keys in variable.tf (and more as needed).

Navigate to the root directory of the project.

```powershell
terraform init
terraform plan
terraform apply [-auto-approve]
```

Important note to the uploader/investigator: the dump file follows a naming convention: os_anythin.ext. To figure out the best fit for which modules to run I decided to use this approach. An example would be: win_myCompany130224.dd. The available values are: "win", "linux" or "osx". Current set of accepted extensions are limited ("dd" "raw" "mem" "vmem"), but easily extended to whatever Volatility3 accepts.

If you want to make the analysis on a dump you already have, apply the full terraform config with the dump inside ./VolAutolity/sample/ folder. As this operation includes a copy to the memorydumps location that is mointored, nothing more is needed. If you are using upload functionality - you need to trigger the event by copying or moving the file into the same location it was uploaded to as it will trigger some kernel signals that triggers inotifywait. I'm working on a solution to make it run once a blob has been uploaded from elsewhere. Any input or solution is appreciated as all of this is fairly new to me!

Send the investigator the necessary details to sign in to correct location and then upload the dump. The investigator needs to have a registered user in the current tenant to use the az cli uploading functionality (SAS token url is work in progress): Get the list of commands by entering:
```powershell
terraform output setup_and_instructions
```

## Challenges and bugs
Doing too many images at the same times yields poor result in current state as they are running concurrently. Recommend uploading one and one and doing sample-folder for max 2. 

I've stumbled upon a few errors using Azure CLI that was unreproducable but was most often solved by this flow of commands:

```powershell
az ad signed-in-user show
az logout
az login
az ad signed-in-user show
az config set auto-upgrade.enable=yes
```

This setup is not idempotent as we are using provisioners like Ansible to push out our setup. Sometimes you need to run the setup twice to make it work like intended. Sometimes the null_resource takes forever, which I have made successfully run simply by pressing CTRL+C (quitting) and then re-running the apply process.

A bug with errors: "Error: retrieving Subscription <...> stream error: stream ID 3; CANCEL; received from peer" may occur, re-running has been the fix for this and seem to appear randomly for many users when researching the topic.

"Error: remote-exec provisioner error" Sometimes happen. Try a re-run with this error as well. 

# Memory dumps for testing
https://github.com/stuxnet999/MemLabs/tree/master/Lab%200
https://www.osforensics.com/tools/volatility-workbench.html 
https://archive.org/details/Africa-DFIRCTF-2021-WK02 



## Time notes (give or take)
ADX cluster often takes around 15 minutes setting up. 
VM with size Standard_DS1_v2 takes about 16 seconds, but adding the null_resource (installation of apps and more) takes a total of 8 min.

Completes most often within 30 minutes for everything.

## Screenshots
![Available data](image.png)

![PSTree](image-1.png)

![IPs to map](image-2.png)

![Maybe standard passwords are being used](image-3.png)

![Singletons](image-4.png)

And much more on the way...

<details><summary>Resources: </summary>
<ul>
<li>https://github.com/hashicorp/terraform-provider-azurerm/issues/15649</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/create-cluster-database?tabs=azcli </li>
<li>https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-managed-identity</li>
<li>https://azure-training.com/azure-data-science/creating-the-adx-environment/creating-adx-environment-using-cli/</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/create-cluster-database?tabs=azcli#create-an-azure-data-explorer-database</li>
<li>https://learn.microsoft.com/en-us/cli/azure/kusto/database?view=azure-cli-latest#az-kusto-database-update(kusto)</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/python-ingest-data</li>
<li>https://github.com/Azure/azure-kusto-python/blob/master/azure-kusto-ingest/tests/sample.py</li>
<li>https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/managed_service_identity</li>
<li>https://registry.terraform.io/providers/hashicorp/azuread/latest/docs/resources/service_principal_password</li>
<li>https://registry.terraform.io/providers/favoretti/adx/latest/docs</li>
<li>https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/user_assigned_identity</li>
<li>https://pypi.org/project/azure-kusto-ingest/</li>
<li>https://learn.microsoft.com/en-us/dotnet/core/install/linux-scripted-manual#scripted-install</li>
<li>https://www.nuget.org/packages/Microsoft.Azure.Kusto.Tools/#releasenotes-body-tab</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/kusto/tools/kusto-cli</li>
<li>https://thelearningjourneyebooks.com/</li>
<li>https://github.com/vavarachen/volatility_automation</li>
<li>https://linux.die.net/man/1/inotifywait</li>
<li>https://github.com/volatilityfoundation/volatility3/blob/develop/vol.py</li>
<li>https://downloads.volatilityfoundation.org/releases/2.4/CheatSheet_v2.4.pdf</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/kusto/management/data-ingestion/ingest-from-storage</li>
<li>https://github.com/search?q=repo%3AAzure%2Fazure-sdk-for-python%20ingest&type=code</li>
<li>https://github.com/Azure/azure-kusto-python/blob/master/azure-kusto-ingest/tests/sample.py</li>
<li>https://github.com/Azure/azure-kusto-python</li>
<li>https://www.techbrothersit.com/2022/02/how-to-create-single-or-multiple-tables.html</li>
<li>https://ansibledaily.com/execute-detached-process-with-ansible/</li>
<li>https://www.huuhka.net/devops-for-azure-workbooks/</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/geospatial-visualizations</li>
<li>https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-tree-visualizations</li>
<li>https://github.com/Dead-Simple-Scripts/AutoVol-SDF-Memory-Forensics-2/blob/master/autovol_mem2_example.sh</li>
<li>https://github.com/Yara-Rules/rules</li>
<li>https://github.com/k1nd0ne/VolWeb</li>
<li>https://github.com/carlospolop/autoVolatility</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/visualization-timepivot?pivots=azuredataexplorer</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/visualization-linechart?pivots=azuredataexplorer</li>
<li>https://www.cloudsma.com/2021/01/azure-workbooks-icons-thresholds-heatmaps/</li>
<li>https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/visualization-treemap?pivots=azuredataexplorer</li>
<li>https://learn.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-grid-visualizations</li>
<li>https://reversea.me/index.php/writing-a-volatility-3-plugin/</li>
<li>https://hostingjournalist.com/how-to-build-tabs-and-alerts-in-azure-workbooks-azure-portal-series/</li>
<li>https://hostingjournalist.com/how-to-build-tabs-and-alerts-in-azure-workbooks-azure-portal-series/</li>
</ul>
</details>

## Notes on a few decisions
PSTree is not being run, but produced in workbook instead.

Using Terraform as of current version. Basically relates to my own knowledge/limitation (or lack of). Planning on updating to add Bicep, and maybe even running in containers for reducing cost.

Tablenaming convention used is set to be:
- Remove spaces
- Remove Parentheses


# Workbook additions/considerations
- Windows 7 = Taskhost.exe, Windows 8 = Taskhostex.exe, Windows 10 = Taskhostw.exe
- #Get enabled privileges of some processes
    python3 vol.py -f file.dmp windows.privileges.Privs [--pid <pid>]
    #Get all processes with interesting privileges
    python3 vol.py -f file.dmp windows.privileges.Privs | grep "SeImpersonatePrivilege\|SeAssignPrimaryPrivilege\|SeTcbPrivilege\|SeBackupPrivilege\|SeRestorePrivilege\|SeCreateTokenPrivilege\|SeLoadDriverPrivilege\|SeTakeOwnershipPrivilege\|SeDebugPrivilege
    pass
- Similar sounding process names
- Decrypt base 64 strings CompromisedSystemMem.vmem | grep -E '[A-Za-z0-9+/]{4}*([A-Za-z0-9+/]{4}|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2}==)' | grep -vE '^.{1,40}$' |  grep -E '^[A-Za-z0-9+/]+={0,2}$' | base64 -d | less
- Strings of interest list
- Recently changed Registries
- OTX and virustotal lookup

# Modules explanations

## General
### banners.Banners
### configwriter.ConfigWriter
### frameworkinfo.FrameworkInfo
### isfinfo.IsfInfo
### layerwriter.LayerWriter

## Linux
### linux.bash.Bash
### linux.capabilities.Capabilities
### linux.check_afinfo.Check_afinfo
### linux.check_creds.Check_creds
### linux.check_idt.Check_idt
### linux.check_modules.Check_modules
### linux.check_syscall.Check_syscall
### linux.elfs.Elfs
### linux.envars.Envars
### linux.iomem.IOMem
### linux.keyboard_notifiers.Keyboard_notifiers
### linux.kmsg.Kmsg
### linux.library_list.LibraryList
### linux.lsmod.Lsmod
### linux.lsof.Lsof
### linux.malfind.Malfind
### linux.mountinfo.MountInfo
### linux.netfilter.Netfilter
### linux.proc.Maps
### linux.psaux.PsAux
### linux.pslist.PsList
### linux.psscan.PsScan
### linux.pstree.PsTree
### linux.sockstat.Sockstat
### linux.tty_check.tty_check

## Mac
### mac.bash.Bash
### mac.check_syscall.Check_syscall
### mac.check_sysctl.Check_sysctl
### mac.check_trap_table.Check_trap_table
### mac.dmesg.Dmesg
### mac.ifconfig.Ifconfig
### mac.kauth_listeners.Kauth_listeners
### mac.kauth_scopes.Kauth_scopes
### mac.kevents.Kevents
### mac.list_files.List_Files
### mac.lsmod.Lsmod
### mac.lsof.Lsof
### mac.malfind.Malfind
### mac.mount.Mount
### mac.netstat.Netstat
### mac.proc_maps.Maps
### mac.psaux.Psaux
### mac.pslist.PsList
### mac.pstree.PsTree
### mac.socket_filters.Socket_filters
### mac.timers.Timers
### mac.trustedbsd.Trustedbsd
### mac.vfsevents.VFSevents

## WHAT?
### timeliner.Timeliner
### vmscan.Vmscan

## Windows
### windows.bigpools.BigPools
Description: The windows.bigpools.BigPools module is used to analyze and extract information about large memory pools in the Windows operating system. Memory pools are areas of memory used by the operating system to manage dynamic memory allocation for various system components and drivers.

**What is a memory pool?**
>A memory pool is a block of memory that is reserved for dynamic memory allocation. In the context of operating systems like Windows, memory pools are used to manage memory more efficiently by pre-allocating a large block of memory and then dividing it into smaller chunks as needed. This approach helps reduce fragmentation and the overhead associated with frequent memory allocation and deallocation. Memory pools are particularly useful for managing memory for system components and drivers that require frequent and dynamic memory allocation. By using memory pools, the operating system can ensure that memory is allocated and freed quickly, which can improve overall system performance and stability.

Usage:

Memory Analysis: This module helps in identifying and analyzing large memory pools, which can be useful for detecting memory leaks, understanding memory usage patterns, and troubleshooting performance issues.
Forensics: In forensic investigations, analyzing big pools can help identify suspicious memory usage by malware or other unauthorized processes.
Example:
```bash
vol -f dump.dd --log ./Volatility.log -r csv windows.bigpools > output.csv
```

### windows.callbacks.Callbacks
### windows.cmdline.CmdLine
### windows.crashinfo.Crashinfo
### windows.devicetree.DeviceTree
### windows.dlllist.DllList
### windows.driverirp.DriverIrp
### windows.drivermodule.DriverModule
### windows.driverscan.DriverScan
### windows.dumpfiles.DumpFiles
### windows.envars.Envars
### windows.filescan.FileScan
### windows.getservicesids.GetServiceSIDs
### windows.getsids.GetSIDs
### windows.handles.Handles
### windows.hollowprocesses.HollowProcesses
### windows.iat.IAT
### windows.info.Info
### windows.joblinks.JobLinks
### windows.kpcrs.KPCRs
### windows.ldrmodules.LdrModules
### windows.malfind.Malfind
### windows.mbrscan.MBRScan
### windows.memmap.Memmap
### windows.modscan.ModScan
### windows.modules.Modules
### windows.mutantscan.MutantScan
### windows.netscan.NetScan
### windows.netstat.NetStat
### windows.pedump.PEDump
### windows.poolscanner.PoolScanner
### windows.privileges.Privs
### windows.processghosting.ProcessGhosting
### windows.pslist.PsList
PSScan - look at unallocated space. Might show processes that WERE running or processes that WERE running but now have been unlinked from the W-Linked list.
It scans the whole image.


```mermaid
mindmap
    Run command
        Singletons
        Boot start time anomaly
        Parent/child relations
```

### windows.psscan.PsScan
### windows.pstree.PsTree
### windows.psxview.PsXView
### windows.registry.certificates.Certificates
### windows.registry.getcellroutine.GetCellRoutine
### windows.registry.hivelist.HiveList
### windows.registry.hivescan.HiveScan
### windows.registry.printkey.PrintKey
### windows.registry.userassist.UserAssist
### windows.sessions.Sessions
### windows.shimcachemem.ShimcacheMem
### windows.skeleton_key_check.Skeleton_Key_Check
### windows.ssdt.SSDT
### windows.statistics.Statistics
### windows.strings.Strings
### windows.suspicious_threads.SuspiciousThreads
### windows.symlinkscan.SymlinkScan
### windows.thrdscan.ThrdScan
### windows.threads.Threads
### windows.timers.Timers
### windows.truecrypt.Passphrase
### windows.unloadedmodules.UnloadedModules
### windows.vadinfo.VadInfo
### windows.vadwalk.VadWalk
### windows.verinfo.VerInfo
### windows.virtmap.VirtMap