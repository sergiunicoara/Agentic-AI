from setuptools import setup, find_packages

setup(
    name="agent-observability-sdk",
    version="1.0.0",
    description="SDK for emitting agent observability events to the Agent Observability Dashboard",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "grpcio>=1.68.0",
        "grpcio-tools>=1.68.0",
        "opentelemetry-api>=1.29.0",
        "opentelemetry-sdk>=1.29.0",
    ],
    extras_require={
        "dev": ["pytest", "pytest-asyncio"],
    },
)
