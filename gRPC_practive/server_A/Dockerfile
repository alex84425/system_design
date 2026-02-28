FROM python:3.12-slim

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy project definition first to cache dependencies
COPY pyproject.toml .
# Create empty README for hatchling
RUN touch README.md

# Install dependencies into the system python using uv
RUN uv pip install --system -r pyproject.toml

# Copy the rest of the application
COPY . .

# Generate gRPC code from proto
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. hello.proto

# Expose gRPC port
EXPOSE 50051

# Run the server
CMD ["python", "server.py"]
