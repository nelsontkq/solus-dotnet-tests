#!/bin/bash

set -e

if [ $# -eq 0 ]; then
    echo "Usage: $0 <dotnet-version>"
    exit 1
fi

major_version=$(echo "$1" | cut -d'.' -f1)
framework="net$major_version.0"

echo "Testing host fxr with tracing..."

# Enable host tracing and run a simple dotnet command
export COREHOST_TRACE=1
export COREHOST_TRACEFILE=/tmp/host_trace.log

# Run dotnet --info to trigger host resolution
dotnet --info > /dev/null 2>&1

# Check if trace file was created and contains expected host resolution info
if [ ! -f /tmp/host_trace.log ]; then
    echo "Host fxr test failed: trace file not created"
    exit 1
fi

# Check for key indicators of successful host resolution
if ! grep -q "Resolved fxr" /tmp/host_trace.log; then
    echo "Host fxr test failed: fxr not resolved according to trace"
    exit 1
fi

# Clean up
unset COREHOST_TRACE
unset COREHOST_TRACEFILE
rm -f /tmp/host_trace.log

echo "Host fxr test passed: fxr loaded successfully"