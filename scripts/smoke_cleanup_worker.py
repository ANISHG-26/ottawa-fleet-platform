"""Exercise the real cleanup image toolchain without Google credentials."""
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.cleanup_execute import install_terraform


def main() -> None:
    subprocess.run(["gcloud", "version"], check=True)
    # Exercise the exact subnet inventory command used by teardown. Help is
    # local CLI metadata and requires neither credentials nor cloud access.
    subprocess.run(["gcloud", "compute", "networks", "subnets", "list", "--help"],
                   check=True, stdout=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory() as directory:
        binary = install_terraform(Path(directory))
        subprocess.run([str(binary), "version"], check=True)
    subprocess.run([sys.executable, "-m", "scripts.cleanup_execute", "--help"], check=True)


if __name__ == "__main__":
    main()
