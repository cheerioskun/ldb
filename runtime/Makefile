LLVM_BUILD ?= $(abspath ../build/llvm)
CXX = $(LLVM_BUILD)/bin/clang++
CC = $(LLVM_BUILD)/bin/clang
GCC = /usr/bin/gcc
AR = /usr/bin/ar

LDB_CFLAGS = -O3 -g -fdebug-default-version=3 -fno-omit-frame-pointer -I./include

all: libshim.so libldb.a

# Shared layout and compiler changes must rebuild every runtime object.
hook.o logger.o monitor.o event.o tag.o shim.o: common.h $(CC)

libldb.a: hook.o logger.o monitor.o event.o tag.o
	$(AR) rcs $@ $^

libshim.so: shim.o event.o
	$(CC) -shared -lpthread -ldl -o $@ $^

shim.o: shim.c
	$(CC) -O1 -g -fdebug-default-version=3 -fno-omit-frame-pointer -fPIC -o $@ -c $<

hook.o: hook.c
	$(CC) $(LDB_CFLAGS) -o $@ -c $<

logger.o: logger.c
	$(CC) $(LDB_CFLAGS) -I./include -o $@ -c $<

monitor.o: monitor.c
	$(CC) $(LDB_CFLAGS) -o $@ -c $<

tag.o: tag.c
	$(CC) $(LDB_CFLAGS) -o $@ -c $<

event.o: event.c
	$(CC) $(LDB_CFLAGS) -fPIC -o $@ -c $<

clean:
	rm -f event.o monitor.o logger.o hook.o shim.o tag.o libshim.so libldb.a
