#!/usr/bin/env python3
import os
import sys
import uvicorn.main

if __name__ == "__main__":
    port_env = os.getenv("PORT", "8000").strip()
    try:
        int(port_env)
    except ValueError:
        port_env = "8000"

    cleaned_args = []
    for arg in sys.argv[1:]:
        if arg in ("$PORT", "${PORT}", "'$PORT'", '"$PORT"', "\\$PORT"):
            cleaned_args.append(port_env)
        elif arg.startswith("--port=") and ("$PORT" in arg):
            cleaned_args.append(f"--port={port_env}")
        else:
            cleaned_args.append(arg)

    sys.argv = [sys.argv[0]] + cleaned_args
    uvicorn.main.main()
