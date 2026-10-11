# Kernel
Rootkits and "bring your own vulnerable driver" (BYOVD) EDR killers. In Volatility 3 an owner module that cannot be resolved prints as `-`: code that belongs to no loaded module is manually mapped (kdmapper), shellcode, or a hidden driver.
Not covered by these plugins: ObRegisterCallbacks, minifilters, WFP callouts and the win32k shadow SSDT. If almost every row resolves to `-`, suspect a symbol problem rather than a rootkit.
