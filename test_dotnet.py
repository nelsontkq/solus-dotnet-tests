#!/usr/bin/env python3
import sys
import os
import subprocess
import glob
import re
import tempfile
import time
import requests
from pathlib import Path
from typing import List, Optional, Set, Dict


class DotNetTester:
    def __init__(self, base_dir: str = "/var/lib/solbuild/local"):
        self.base_dir = base_dir
        self.versions = {}
        self._enumerate_packages()

    def run_command(self, cmd, check=True, capture_output=False, shell=False):
        """Run a command and handle errors"""
        if isinstance(cmd, str) and not shell:
            cmd = cmd.split()

        try:
            if capture_output:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, check=check, shell=shell
                )
                return result.stdout.strip()
            else:
                subprocess.run(cmd, check=check, shell=shell)
        except subprocess.CalledProcessError as e:
            if check:
                print(
                    f"Command failed: {' '.join(cmd) if isinstance(cmd, list) else cmd}"
                )
                sys.exit(1)
            return None

    def _enumerate_packages(self):
        """Analyze available packages and group by major version"""
        packages = glob.glob(f"{self.base_dir}/dotnet-*.eopkg")

        for pkg in packages:
            basename = os.path.basename(pkg)

            if "source-built-artifacts" in basename:
                continue

            if basename.startswith("dotnet-shared-"):
                self.versions.setdefault("shared", []).append(pkg)
                continue

            match = re.match(r"dotnet-(?:(\d+)-)?(sdk-)?(\d+)\.\d+", basename)
            if match:
                major_version = match.group(1) or match.group(3).split(".")[0]
                self.versions.setdefault(major_version, []).append(pkg)

    def get_available_versions(self) -> List[str]:
        """Get all available major versions (excluding 'shared')"""
        return [v for v in self.versions.keys() if v != "shared"]

    def install_dotnet(self, versions: List[str]):
        """Install dotnet packages for the specified versions"""
        packages_to_install = []

        if "shared" in self.versions:
            print("Including dotnet-shared packages...")
            packages_to_install.extend(self.versions["shared"])

        for version in versions:
            if version not in self.versions:
                print(f"Warning: No packages found for .NET {version}")
                continue

            print(f"Finding packages for .NET {version}...")
            packages_to_install.extend(self.versions[version])

        if not packages_to_install:
            print("No packages found to install")
            sys.exit(1)

        print(f"\nInstalling {len(packages_to_install)} packages:")
        for pkg in packages_to_install:
            print(f"  - {os.path.basename(pkg)}")

        cmd = ["sudo", "eopkg", "it"] + packages_to_install
        self.run_command(cmd)

    def uninstall_all_dotnet(self):
        """Uninstall all dotnet packages"""
        print("Uninstalling all dotnet packages...")

        packages_to_remove = ["dotnet-shared"]

        for version in self.get_available_versions():
            packages_to_remove.extend(
                [
                    f"dotnet-{version}",
                    f"dotnet-{version}-sdk",
                    "dotnet",
                    "dotnet-sdk",
                ]
            )

        seen = set()
        unique_packages = []
        for pkg in packages_to_remove:
            if pkg not in seen:
                seen.add(pkg)
                unique_packages.append(pkg)

        cmd = ["sudo", "eopkg", "remove"] + unique_packages
        self.run_command(cmd)

    def get_framework_version(self, major_version: str) -> str:
        """Get the framework version string for a major version"""
        return f"net{major_version}.0"

    def run_tests(self, major_version: str):
        """Run dotnet tests for the specified major version"""
        framework = self.get_framework_version(major_version)
        print(f"\nTesting .NET {major_version} with framework: {framework}")

        # Build solution
        print("Building solution...")
        self.run_command(f"dotnet build . -p:framework={framework}")

        # Publish self-contained
        print("Publishing self contained...")
        publish_cmd = [
            "dotnet",
            "publish",
            "console",
            "-c",
            "Release",
            "-r",
            "solus.4-x64",
            "--self-contained",
            "true",
            "-p:PublishSingleFile=true",
            f"-p:framework={framework}",
        ]
        self.run_command(publish_cmd)

        # Test console app
        console_path = f"./console/bin/Debug/{framework}/console"
        result = self.run_command(console_path, capture_output=True)

        if result != "SUCCESS":
            print(f"Console app test failed: expected 'SUCCESS', got '{result}'")
            sys.exit(1)
        print("✓ Console app test passed")

        # Test webapi apps
        print("Testing webapi apps...")
        for proj in ["webapi", "webapiaot"]:
            self._test_webapi(proj, framework)
            print(f"✓ {proj} test passed")

    def _test_webapi(self, project: str, framework: str):
        """Test a web API project"""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_output = temp_file.name

        try:
            webapi_path = f"./{project}/bin/Debug/{framework}/{project}"
            with open(temp_output, "w") as f:
                webapi_process = subprocess.Popen(
                    [webapi_path], stdout=f, stderr=subprocess.STDOUT
                )

            # Wait for the service to start
            timeout = 10
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    with open(temp_output, "r") as f:
                        content = f.read()
                        if "Now listening on:" in content:
                            break
                except:
                    pass
                time.sleep(0.1)
            else:
                print(f"Timeout waiting for {project} to start")
                webapi_process.terminate()
                sys.exit(1)

            # Test the API
            try:
                response = requests.get("http://localhost:5000/TEST", timeout=5)
                result = response.text.strip()
            except requests.RequestException as e:
                print(f"Failed to connect to {project}: {e}")
                webapi_process.terminate()
                sys.exit(1)

            webapi_process.terminate()
            webapi_process.wait()

            if result != "SUCCESS":
                print(f"{project} test failed: expected 'SUCCESS', got '{result}'")
                sys.exit(1)

        finally:
            os.unlink(temp_output)

    def run_other_tests(self, versions: List[str]):
        """Run additional test scripts"""
        print("\n=== Running other tests ===")
        other_tests_dir = Path("other_tests")

        if not other_tests_dir.exists():
            print("No other_tests directory found, skipping...")
            return

        for script_path in other_tests_dir.glob("*.sh"):
            if os.access(script_path, os.X_OK):
                print(f"Running script: {script_path}")
                # Pass all versions as arguments
                self.run_command([str(script_path)] + versions)
            else:
                print(f"Skipping non-executable script: {script_path}")

    def test_single_file_executables(self):
        """Test single file executables after removing dotnet"""
        print("\n=== Testing single file executables ===")

        pattern = "./console/bin/Release/*/solus.4-x64/publish/console"
        executables = glob.glob(pattern)

        if not executables:
            print("No single file executables found to test")
            return

        for exe_path in executables:
            framework_match = re.search(r"net(\d+)\.\d+", exe_path)
            if framework_match:
                major_version = framework_match.group(1)
                print(f"Testing self-contained executable for .NET {major_version}...")

                with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
                    temp_output = temp_file.name

                try:
                    with open(temp_output, "w") as f:
                        result = subprocess.run(
                            [exe_path], stdout=f, stderr=subprocess.STDOUT
                        )

                    if result.returncode != 0:
                        print(
                            f"Self-contained executable for .NET {major_version} failed with exit code {result.returncode}"
                        )
                        sys.exit(1)

                    with open(temp_output, "r") as f:
                        output = f.read().strip()

                    if output != "SUCCESS":
                        print(
                            f".NET {major_version} failed to create self-contained executable"
                        )
                        sys.exit(1)

                    print(
                        f"✓ .NET {major_version} self-contained executable test passed"
                    )

                finally:
                    os.unlink(temp_output)

    def test_version_combinations(self, versions: List[str]):
        """Test various combinations of .NET versions"""
        for version in versions:
            print(f"\n{'='*60}")
            print(f"Testing .NET {version} standalone")
            print("=" * 60)
            self.uninstall_all_dotnet()
            self.install_dotnet([version])
            self.run_tests(version)

        if len(versions) > 1:
            print(f"\n{'='*60}")
            print(f"Testing all versions together: .NET {', '.join(versions)}")
            print("=" * 60)
            self.uninstall_all_dotnet()
            self.install_dotnet(versions)

            for version in versions:
                self.run_tests(version)

        if len(versions) > 2:
            for i in range(len(versions)):
                for j in range(i + 1, len(versions)):
                    pair = [versions[i], versions[j]]
                    print(f"\n{'='*60}")
                    print(f"Testing pair: .NET {pair[0]} and {pair[1]}")
                    print("=" * 60)
                    self.uninstall_all_dotnet()
                    self.install_dotnet(pair)

                    for version in pair:
                        self.run_tests(version)


def main():
    if len(sys.argv) < 2:
        print("Usage: ./test_dotnet.py <version1> [version2] [version3] ...")
        print("Example: ./test_dotnet.py 8 9")
        print("\nThis will test the specified .NET major versions")
        sys.exit(1)

    versions = sys.argv[1:]
    tester = DotNetTester()

    available = tester.get_available_versions()
    print(f"Available .NET versions: {', '.join(sorted(available))}")

    print("\nPackage analysis:")
    for version in sorted(tester.versions.keys()):
        packages = tester.versions[version]
        if version == "shared":
            print(f"  Shared: {len(packages)} package(s)")
        else:
            sdk_count = sum(1 for p in packages if "sdk" in os.path.basename(p).lower())
            runtime_count = len(packages) - sdk_count
            print(
                f"  .NET {version}: {runtime_count} runtime, {sdk_count} SDK package(s)"
            )

    invalid_versions = [v for v in versions if v not in available]
    if invalid_versions:
        print(f"\nError: Version(s) {', '.join(invalid_versions)} not found")
        print(f"Available versions: {', '.join(sorted(available))}")
        sys.exit(1)

    print("\nCleaning git repository...")
    tester.run_command("git clean -xfd")

    tester.test_version_combinations(versions)

    tester.run_other_tests(versions)

    print("\nUninstalling all .NET packages before testing executables...")
    tester.uninstall_all_dotnet()
    tester.test_single_file_executables()

    print(f"\n{'='*60}")
    print(f"✅ All tests passed! .NET {', '.join(versions)} tested successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
