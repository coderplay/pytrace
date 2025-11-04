# PyTrace

PyTrace is a dynamic tracing tool for Python programs, similar to BTrace in Java or eBPF/DTrace for operating systems. It's designed to safely inject tracing code into a running Python process without modifying or restarting it.

## Features

- **Dynamic Instrumentation**: Attach to running Python processes without restarting
- **Restricted Python Scripts**: Write tracing logic in a restricted Python subset
- **Low Overhead**: Designed for production use with <1% overhead
- **Multi-Platform**: Supports macOS, Linux, and Windows
- **Multi-Client**: Multiple clients can trace the same process concurrently

## Installation

```bash
uv pip install -e .
```

## Usage

```bash
pytrace <pid> <script.py> [args]
```

Example:

```bash
pytrace 12345 trace_script.py
```

## Requirements

- Python 3.12+
- Target process must be Python 3.12+ (for sys.monitoring support)

## License

MIT

