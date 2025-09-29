# ChessMaster Development Tools

This directory contains development and testing utilities that are not part of the production application.

## Directory Structure

### `/demos/`
Demonstration and example scripts showing how various systems work.
- `demo_multi_channel_system.py` - Demonstrates multi-channel file management (Story 1.2)

### `/testing/`
Quick testing and validation scripts for development.
- `quick_test_bot.py` - Quick bot startup testing script

### `/setup/`
Local development environment setup and configuration helpers.
- `test_local_setup.py` - Local environment testing and validation

### `/validation/`
Story validation and verification scripts.
- `validate_story_1_4.py` - Story 1.4 implementation validation script

## Usage

These tools are intended for:
- Development and debugging
- Local testing and validation
- Demonstrating system capabilities
- Story implementation verification

## Important Notes

- These files are **not deployed** in production
- They may have dependencies not required for the main application
- Some scripts may require additional setup or environment variables
- Use these tools only in development environments

## Running the Tools

Most scripts can be run directly:
```bash
# From project root
python dev-tools/testing/quick_test_bot.py
python dev-tools/setup/test_local_setup.py
python dev-tools/validation/validate_story_1_4.py
python dev-tools/demos/demo_multi_channel_system.py
```

Refer to individual script documentation for specific usage instructions.
