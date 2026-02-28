import grpc
import sys
import os

# Add current directory to path so the generated files can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import hello_pb2
import hello_pb2_grpc

def run():
    print("Will try to greet world ...")
    # Connect to the server on localhost port 50051
    # If running inside docker and testing from outside, use localhost
    # Make sure to run this script where it can reach the port
    target = os.getenv('GRPC_SERVER_TARGET', 'localhost:50051')
    print(f"Connecting to {target}...")
    
    with grpc.insecure_channel(target) as channel:
        stub = hello_pb2_grpc.GreeterStub(channel)
        response = stub.SayHello(hello_pb2.HelloRequest(name='Practice User'))
    print("Greeter client received: " + response.message)

if __name__ == '__main__':
    run()
