FROM python:3.12-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy project definition first to cache dependencies
COPY server_A/pyproject.toml .
# Create empty README for hatchling
RUN touch README.md

# Install dependencies into the system python using uv
RUN uv pip install --system -r pyproject.toml

# Copy shared proto and server code
COPY proto/ ./proto/
COPY server_A/ .

# Generate gRPC code from shared proto
RUN python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. hello.proto

# Expose gRPC port
EXPOSE 50051

# Run the server
CMD ["python", "server.py"]
