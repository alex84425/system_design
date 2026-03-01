"""
Generate gRPC Python stubs from hello.proto.
Run: uv run python generate_proto.py
"""

import os
import subprocess
import sys

client_dir = os.path.dirname(os.path.abspath(__file__))
proto_dir = os.path.join(client_dir, "..", "proto")
proto_file = "hello.proto"

print(f"Generating gRPC stubs from {proto_dir}/{proto_file}...")

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={client_dir}",
        f"--grpc_python_out={client_dir}",
        proto_file,
    ],
    cwd=client_dir,
)

if result.returncode == 0:
    print("Done! Generated: hello_pb2.py, hello_pb2_grpc.py")
else:
    print("Error generating stubs.", file=sys.stderr)
    sys.exit(1)
