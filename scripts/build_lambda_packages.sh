#!/bin/bash

# Exit on error
set -e

echo "Starting Lambda package build..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 could not be found. Please install it."
    exit 1
fi

# Check if pip is installed
if ! command -v pip &> /dev/null; then
    echo "pip could not be found. Please install it."
    exit 1
fi

# Create a temporary directory for packaging
TEMP_DIR=$(mktemp -d)
echo "Created temporary directory: $TEMP_DIR"

# Cleanup function to run on exit
function cleanup {
    echo "Cleaning up temporary files..."
    rm -rf "$TEMP_DIR"
}

# Register the cleanup function to run on exit
trap cleanup EXIT

# Project root directory (assuming script is in scripts/ subdirectory)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Project root directory: $PROJECT_ROOT"

# Define the Lambda functions
LAMBDA_FUNCTIONS=("news_collector" "news_processor" "sns_to_slack")

# Package each Lambda function
for function_name in "${LAMBDA_FUNCTIONS[@]}"; do
    echo "Building $function_name Lambda package..."

    # Create function temp directory
    FUNCTION_DIR="$TEMP_DIR/$function_name"
    mkdir -p "$FUNCTION_DIR"

    # Check if function directory exists
    if [ ! -d "$PROJECT_ROOT/lambda/$function_name" ]; then
        echo "Error: Function directory $PROJECT_ROOT/lambda/$function_name does not exist."
        continue
    fi

    # Copy function code
    cp "$PROJECT_ROOT/lambda/$function_name/lambda_function.py" "$FUNCTION_DIR/"

    # Check if requirements file exists
    if [ -f "$PROJECT_ROOT/lambda/$function_name/requirements.txt" ]; then
        echo "Installing dependencies for $function_name..."
        pip install -r "$PROJECT_ROOT/lambda/$function_name/requirements.txt" -t "$FUNCTION_DIR"
    else
        echo "No requirements.txt found for $function_name. Skipping dependency installation."
    fi

    # Create the zip file
    echo "Creating zip file for $function_name..."
    (cd "$FUNCTION_DIR" && zip -r "$PROJECT_ROOT/${function_name}.zip" .)

    echo "$function_name Lambda function packaged: $PROJECT_ROOT/${function_name}.zip"
done

echo "Lambda packaging complete!"
