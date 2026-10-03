"""Exercise the real cleanup image toolchain without Google credentials."""
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.cleanup_execute import install_terraform


def main() -> None:
    subprocess.run(["gcloud", "version"], check=True)
    with tempfile.TemporaryDirectory() as directory:
        binary = install_terraform(Path(directory))
        subprocess.run([str(binary), "version"], check=True)
    subprocess.run([sys.executable, "-m", "scripts.cleanup_execute", "--help"], check=True)


if __name__ == "__main__":
    main()
