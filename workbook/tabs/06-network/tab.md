# Network
Connections and listeners from netstat (live tables) and netscan (pool scan - also closed and freed connections, lower confidence). Ports 80/443/8080/8443 mean nothing on their own: the rules focus on *who* owns a socket (script hosts, LOLBins, notepad, lsass, processes in staging folders) and on unusual ports, directions and peers.
Direction is inferred (listener match, well-known ports, ephemeral ranges) and can be wrong for RPC/DCOM dynamic ports.
