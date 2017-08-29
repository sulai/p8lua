# p8lua - write code in .lua files

This script helps developing cartridges for Pico-8.

The basic concept is: you edit plain .lua files in your favourite external editor, and when ever you save the .lua file, the script will notice the file change and merge the code back into the .p8 file, so you are instantly ready to use ctrl-R in Pico-8 to reload the cartridge and test your code.

# p8lua - can do some pre-processing, if you want

There are some pre-processor commands you can use, for example:

```
-- copies library.lua into your code
--#include library

-- cut out debug code when releasing
--#define debug
--#if debug
print("cpu usage "..stat(1),0,0)
--#end debug

```

See the python script for a more in-depth and up to date documentation.
