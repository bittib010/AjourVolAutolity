# Files & artefacts
File names cached in memory (filescan: open/cached files only, paths without drive letter), NTFS records (mftscan: names only, plus small resident files and alternate data streams), ClamAV verdicts on files dumped from memory, evidence of execution (Amcache, ShimCache, UserAssist), known malware mutexes, rogue root certificates and YARA hits.
Memory holds a fraction of the file system: use these as leads to collect from disk.
