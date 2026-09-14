"""Run the authentication service."""

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "etl_scripts.src.model_auth.app:app",
        host=os.getenv("CDP_BIND_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
