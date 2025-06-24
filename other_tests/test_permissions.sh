#!/bin/bash

set -e

if [ $# -eq 0 ]; then
    echo "Usage: $0 <dotnet-version>"
    exit 1
fi

echo "Testing dotnet installation permissions and ownership..."

base_path="/usr/lib64/dotnet"

if [ ! -d "$base_path" ]; then
    echo "Permissions test failed: $base_path directory not found"
    exit 1
fi

# Check that dotnet directory is owned by root
owner=$(stat -c "%U" "$base_path")
if [ "$owner" != "root" ]; then
    echo "Permissions test failed: $base_path not owned by root (owned by: $owner)"
    exit 1
fi

# Check all permissions in one pass
find "$base_path" \( -name "dotnet" -o -name "*.so" -o -name "singlefilehost" -o -name "apphost" \) -type f -exec sh -c '
    for file; do
        perms=$(stat -c "%a" "$file")
        if [ "$perms" != "755" ]; then
            echo "Permissions test failed: $file should be 755, found: $perms"
            exit 1
        fi
    done
' _ {} + || exit 1

# Check directories are 755
find "$base_path" -type d -exec sh -c '
    for dir; do
        perms=$(stat -c "%a" "$dir")
        if [ "$perms" != "755" ]; then
            echo "Permissions test failed: directory $dir should be 755, found: $perms"
            exit 1
        fi
    done
' _ {} + || exit 1

# Check header files are 644
find "$base_path" -name "*.h" -type f -exec sh -c '
    for header; do
        perms=$(stat -c "%a" "$header")
        if [ "$perms" != "644" ]; then
            echo "Permissions test failed: header $header should be 644, found: $perms"
            exit 1
        fi
    done
' _ {} + || exit 1

echo "Permissions test passed: dotnet installation has correct ownership and permissions"