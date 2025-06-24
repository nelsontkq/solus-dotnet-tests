#!/bin/bash
set -e

git clean -xfd
install_dotnet() {
    local version=$1
    echo "Installing dotnet $version packages..."
    local base_dir="/var/lib/solbuild/local"
    
    # Always install dotnet-shared first
    sudo eopkg it "$base_dir"/dotnet-shared*.eopkg
    
    if ls "$base_dir"/dotnet-$version-*.eopkg 1> /dev/null 2>&1; then
        sudo eopkg it "$base_dir"/dotnet-$version-*.eopkg
    else
        sudo eopkg it "$base_dir"/dotnet-*.eopkg
    fi
    
    if ls "$base_dir"/dotnet-$version-sdk-*.eopkg 1> /dev/null 2>&1; then
        sudo eopkg it "$base_dir"/dotnet-$version-sdk-*.eopkg
    else
        sudo eopkg it "$base_dir"/dotnet-sdk-*.eopkg
    fi
}

uninstall_all_dotnet() {
    echo "Uninstalling all dotnet packages..."
    sudo eopkg remove dotnet-shared dotnet-8 dotnet-8-sdk dotnet dotnet-sdk 2>/dev/null || true
}

run_tests() {
    local major_version=$1
    local framework="net$major_version.0"

    echo "Testing dotnet build with framework: $framework"

    for script in other_tests/*.sh; do
        if [ -x "$script" ]; then
            echo "Running script: $script"
            ./"$script" "$major_version.0.17"
        else
            echo "Skipping non-executable script: $script"
        fi
    done

    echo "Building solution..."
    dotnet build . -p:framework=$framework

    echo "Publishing console app as single file..."
    dotnet publish console -c Release -r solus.4-x64 --self-contained true -p:PublishSingleFile=true -p:framework=$framework

    result="$(./console/bin/Debug/$framework/console)"
    if [ "$result" != "SUCCESS" ]; then
        echo "Console app test failed: expected 'SUCCESS', got '$result'"
        exit 1
    fi

    echo "Testing webapi app..."
    for proj in webapi webapiaot; do
        temp_output=$(mktemp)
        trap 'rm -f "$temp_output"' EXIT

        ./$proj/bin/Debug/$framework/$proj >"$temp_output" 2>&1 &
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
}

echo "=== Testing dotnet 8 standalone ==="
uninstall_all_dotnet
install_dotnet "8"
run_tests "8"

echo "=== Testing dotnet 9 standalone ==="
uninstall_all_dotnet
install_dotnet "9"
run_tests "9"

echo "=== Testing dotnet 8 and 9 together - testing 8 ==="
uninstall_all_dotnet
install_dotnet "8"
install_dotnet "9"
run_tests "8"

echo "=== Testing dotnet 8 and 9 together - testing 9 ==="
run_tests "9"

echo "Testing single file executable after removing dotnet..."
uninstall_all_dotnet

# Test the single file executables
for major_version in "8" "9"; do
    framework="net$major_version.0"
    single_file_exe="./console/bin/Release/$framework/solus.4-x64/publish/console"

    if [ -f "$single_file_exe" ]; then
        result=$("$single_file_exe")
        if [ "$result" != "SUCCESS" ]; then
            echo "Single file test failed for $major_version: expected 'SUCCESS', got '$result'"
            exit 1
        fi
        echo "Single file test passed for $major_version: executable runs without dotnet installed"
    else
        echo "Single file test failed for $major_version: executable not found at $single_file_exe"
        exit 1
    fi
done

echo "All tests passed! Dotnet 8 and 9 built successfully and work together!"
