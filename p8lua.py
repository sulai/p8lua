
"""

Prerequisites: Linux and pyinotify.
               pyinotify is a python module for linux to detect file changes.
               Get it using the command line: sudo pip install pyinotify

NOTE: before using this script BACKUP your files, or use some version control
      like GIT.

Usage: python lua2p8.py in your carts directory.

Effects: The script will create a .lua file for each of your .p8 cartridges, if not
already present. From then on, it listens to any changes on the .lua files
and re-integrates them into the .p8 files.

Just edit your .lua file and press ctrl+R in
Pico-8, it will load the updated .p8 file. You can edit assets in Pico-8
as well as the external .lua file, everything will sync perfectly as soon as
you hit ctrl+S. However, changes made and saved in the Pico-8 *code editor* will
get overridden in the .p8 file. The code is transferred only one-way (by design).

NOTE: If you want to edit and save your code in Pico-8, disable this script.

Some more sugar:

you can use these commands

--#define debug
--#undefine debug
--#if debug
--#end debug

to cut out parts of your code (eg debugging or testing code).
Of course you can define and use other labels than debug also.
For example: --#define featurexy to cut out a feature
(maybe because it's unfinished, or it takes up too much resources).

There are some special definitions you can add to your program using --#define:

removecomments - Remove comments from the generated .p8 cartridge.
                 Yes you can comment as much as you want
                 in your games now :) however it's nice for others to have
                 those comments, so use it only if you hit the the limit.
                 Removes multi line comments.

removecommentssingle - same as above, but works on single line comments.

plainlua - will convert special pico-8 stuff like += or // into lua.
           you might like this if your IDE/editor only understands plain lua.
           after conversion into .p8, just delete your .lua file, it will be
           re-generated from the .p8 file.
           (never do this without backup or git!!)

Another pre-processor command you might find useful:

--#include lib/collisions

Include lib/collisions.lua, which is a plain copy.


"""


from datetime import datetime, timedelta
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import re
import os

from shutil import copyfile

def re_sub_update_operator(op, lua):
    return re.sub(
            "([\w\.\[\]\/\-\*\+]+)(\s*)\%s=(\s*)([\w\"\']+)"%op,
            r"\1=\1 %s \4"%op, lua)# prettier white space
            #r"\1\2=\3\1\2%s\3\4"%op, lua) -- re-using white space as in original

def re_sub_not_equal(lua):
    return re.sub(
            "([\w\.\[\]\/\-\*\+]+)(\s*)\!\=(\s*)([\w\"\']+)",
            r"\1\2~=\3\4", lua) # re-using white space as in original

def get_if_condition(statement):
    depth=-1
    start=0
    stop=0
    i=0
    for c in statement:
        if c=="(":
            if depth==-1:
                depth=0
                start=i
            depth+=1
        if c==")":
            depth-=1
        if depth==0:
            stop=i
            break
        i+=1
    
    return statement[start+1:stop], statement[stop+1:]

def convert_if(lua):
    result = re.findall("([\n](\s*)(if\s*\(.*\).*)[\n])", lua)
    for r in result:
        if "then" not in r[0]:
            condition, statement = get_if_condition(r[2])
            new_statement = "\n{tab}if {cond} then\n{tab}\t{stat}\n{tab}end\n".format(tab=r[1], cond=condition, stat=statement)
            lua = lua.replace(r[0], new_statement)
    return lua
            
# process lua code for write back to original file
def convert_p8_syntax_to_lua(lua):
    # convert update operators like +=, ...
    lua = re_sub_update_operator("+", lua)
    lua = re_sub_update_operator("-", lua)
    lua = re_sub_update_operator("*", lua)
    lua = re_sub_update_operator("/", lua)
    lua = re_sub_update_operator("%", lua)

    lua = re_sub_not_equal(lua)
    
    # convert if(...) command
    lua = convert_if(lua)
    lua = convert_if(lua) # do this twice since all the replacement makes some miss
    
    # replace // comments
    lua = re.sub("(\s+)//(\s*)", r"\1--\2", lua)
    
    return lua



# process lua that goes into cartridge    
def process_lua_for_p8(lua):

    # defined and active pre-processor labels
    defined = set()
    active = set()    

    # in the first pass, only consider #include pre-processor commands
    result=""
    for line in lua.splitlines():
        if line.startswith("--#include "):
            lua_fn = line[11:]
            with open(lua_fn+".lua") as luaf:
                lua_include = luaf.read()
                result+=lua_include+"\n"
        else:
            result+=line+"\n"
    lua = result
    
    result=""
    for line in lua.splitlines():

        if line.startswith("--#define "):
            defined.add(line[10:])
            continue
        elif line.startswith("--#undefine "):
            defined.discard(line[12:])
            continue
        elif line.startswith("--#if "):
            active.add(line[6:])
            continue
        elif line.startswith("--#end "):
            active.discard(line[7:])
            continue

        if "removecommentssingle" in defined:
            # full line comment
            if re.match("^\s*--.*$", line):
                continue
            # end of line comment
            line = re.sub("\s*--.*$", "", line) 

        if is_active_code(active,defined):
            result+=line+"\n"
    
    # remove multi line comments
    if "removecomments" in defined:
        result = re.sub("--\[\[.*?\]\]--", "\n", result, flags=re.DOTALL) # multi line comment
    
    # convert .p8 specific stuff to lua code
    if "plainlua" in defined:    
        result = convert_p8_syntax_to_lua(result)    

    return result

def is_active_code(active, defined):
    if len(active)==0:
        return True
    # we are in an active #if section
    # this code is active, if at least one active tag is defined
    for tag in active:
        if tag in defined:
            return True
    

def parse_p8(fn):
    # read .p8
    with open(fn) as p8f:
        p8_content = p8f.read()
        result = re.findall("(.*\n__lua__\n)(.*)(\n__gfx__\n.*)", p8_content,  re.MULTILINE|re.DOTALL)
        tail = '' if len(result[0]) == 2 else result[0][2]
        return {'head': result[0][0], 'lua': result[0][1], 'tail': tail}
        

def on_lua_changed(lua_fn):
    
    p8_fn = lua_fn[:-4]+".p8"
    
    print('*** processing LUA ' + lua_fn, flush=True)
    
    with open(lua_fn) as luaf:
        lua_content = luaf.read()

# writing back to original lua file does trigger the     
#    with open(lua, "wb") as luaf:
#        luaf.write(lua_content)

    # evaluate pre-processors and stuff
    lua_content = process_lua_for_p8(lua_content)    
    
    # insert new code
    result = parse_p8(p8_fn)
    new_p8_content = result['head'] + lua_content + result['tail']

    # create backup
    copyfile(p8_fn, p8_fn+".bak")

    # write out new p8
    with open(p8_fn, "wb") as p8f:
        p8f.write(new_p8_content.encode('utf-8'))
        
    
def create_lua_from_p8():
    # create .lua files from .p8 files if not yet there
    for filename in os.listdir("."):
        if filename.endswith(".p8"):
            lua_fn = filename[:-3] + '.lua'
            if not os.path.isfile(lua_fn):
                print('*** generating .lua file from .p8 file ' + lua_fn, flush=True)
                result = parse_p8(filename)
                # write out new lua file
                with open(lua_fn, "wb") as luaf:
                    luaf.write(result['lua'].encode('utf-8'))

# Handle file events
# timedelta used because events will sometimes be trigged multiple times for some reason
class Identify(FileSystemEventHandler):

    def __init__(self):
        self.last_modified = datetime.now()

    def on_created(self, event):
        super(Identify, self).on_created(event)
        
        if datetime.now() - self.last_modified < timedelta(seconds=1):
            return
        elif not event.is_directory and event.src_path.endswith('.p8'):
            create_lua_from_p8()

    def on_deleted(self, event):
        super(Identify, self).on_deleted(event)

        if datetime.now() - self.last_modified < timedelta(seconds=1):
            return
        elif not event.is_directory and event.src_path.endswith('.lua'):
            create_lua_from_p8()

    def on_modified(self, event):
        super(Identify, self).on_modified(event)

        if datetime.now() - self.last_modified < timedelta(seconds=1):
            return
        elif not event.is_directory and event.src_path.endswith('.lua'):
            on_lua_changed(event.src_path)

    def on_moved(self, event):
        super(Identify, self).on_moved(event)

        if datetime.now() - self.last_modified < timedelta(seconds=1):
            return
        elif not event.is_directory and event.src_path.endswith('.lua'):
            on_lua_changed(event.src_path)

# create lua files for p8 carts, which don't have corresponding lua files yet
create_lua_from_p8()

# Setup file observer to catch changes in cwd
observer = Observer()
observer.schedule(Identify(), '.', recursive=True)
observer.start()
# Loop main thread while the observer thread does its thang
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    observer.stop()
observer.join()
