#!/bin/bash
set -e

clean() {
    unset COREHOST_TRACE
    unset COREHOST_TRACEFILE
    rm -f /tmp/host_trace.log
}
trap clean EXIT

echo "Testing host fxr with tracing..."
export COREHOST_TRACE=1
export COREHOST_TRACEFILE=/tmp/host_trace.log

dotnet --info > /dev/null 2>&1

if [ ! -f /tmp/host_trace.log ]; then
    echo "Host fxr test failed: trace file not created"
    exit 1
fi

if ! grep -q "Resolved fxr" /tmp/host_trace.log; then
    echo "Host fxr test failed: fxr not resolved according to trace"
    exit 1
fi

echo "Host fxr test passed: fxr loaded successfully"