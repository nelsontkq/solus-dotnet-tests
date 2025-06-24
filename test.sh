#!/bin/bash
set -e
git clean -xfd
major_version=$(dotnet --version | cut -d '.' -f 1)
framework="net$major_version.0"
echo "Testing dotnet build with framework: $framework"

for script in other_tests/*.sh; do
    if [ -x "$script" ]; then
        echo "Running script: $script"
        ./"$script" "$1"
    else
        echo "Skipping non-executable script: $script"
    fi
done

echo "Building solution..."
dotnet build . -p:framework=$framework

echo "Publishing console app as single file..."
dotnet publish console -c Release -r solus.4-x64 --self-contained true -p:PublishSingleFile=true -p:framework=$framework

echo "Uninstalling SDKs to test runtime..."
sudo eopkg remove dotnet-sdk dotnet-$major_version-sdk
result="$(./console/bin/Debug/$framework/console)"
if [ "$result" != "SUCCESS" ]; then
    echo "Console app test failed: expected 'Hello World!', got '$result'"
    exit 1
fi

echo "Testing webapi app..."
for proj in webapi webapiaot; do
    temp_output=$(mktemp)
    trap 'rm -f "$temp_output"' EXIT
    
    ./$proj/bin/Debug/$framework/$proj > "$temp_output" 2>&1 &
    webapi_pid=$!

    timeout 10s bash -c "while ! grep -q 'Now listening on:' '$temp_output'; do sleep 0.1; done"

    result=$(curl -sf http://localhost:5000/TEST)
    kill $webapi_pid 2>/dev/null || true
    rm -f "$temp_output"

    if [ "$result" != "SUCCESS" ]; then
        echo "WebAPI test failed: expected 'SUCCESS', got '$result'"
        exit 1
    fi
done

echo "Testing single file executable after removing dotnet..."
sudo eopkg remove dotnet dotnet-$major_version dotnet-cli || true

# Test the single file executable
single_file_exe="./console/bin/Release/$framework/solus.4-x64/publish/console"
if [ -f "$single_file_exe" ]; then
    result=$("$single_file_exe")
    if [ "$result" != "SUCCESS" ]; then
        echo "Single file test failed: expected 'SUCCESS', got '$result'"
        exit 1
    fi
    echo "Single file test passed: executable runs without dotnet installed"
else
    echo "Single file test failed: executable not found at $single_file_exe"
    exit 1
fi

echo "All tests passed! Dotnet built successfully."
