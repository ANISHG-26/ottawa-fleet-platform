"""Start the real Functions Framework without cloud credentials or resources."""
from pathlib import Path

import functions_framework


def main() -> None:
    source = Path(__file__).resolve().parents[1] / "functions/lab_shutdown/main.py"
    app = functions_framework.create_app(target="main", source=str(source), signature_type="http")
    with app.test_client() as client:
        response = client.post("/", json={"unexpected": "input"})
        if response.status_code != 400:
            raise RuntimeError("Shutdown HTTP entrypoint failed malformed-input startup smoke")
        if response.get_json() != {"error": "body must contain only run_id"}:
            raise RuntimeError("Shutdown HTTP response did not match its validation contract")
    print("Functions Framework startup and HTTP input validation passed")


if __name__ == "__main__":
    main()
