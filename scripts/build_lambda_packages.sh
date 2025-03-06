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

echo "Creating Lambda layer..."
# Create Lambda layer directory structure
mkdir -p "$TEMP_DIR/python"

# Install dependencies for the layer
echo "Installing dependencies for Lambda layer..."
pip install feedparser requests beautifulsoup4 boto3 -t "$TEMP_DIR/python"

# Create the layer zip file
echo "Creating layer zip file..."
(cd "$TEMP_DIR" && zip -r "$PROJECT_ROOT/lambda-layer.zip" python)

echo "Lambda layer created: $PROJECT_ROOT/lambda-layer.zip"

# Function to package a Lambda function
package_lambda() {
    local function_name=$1
    local function_dir="$PROJECT_ROOT/lambda/$function_name"
    local output_file="$PROJECT_ROOT/${function_name}.zip"
    
    echo "Packaging $function_name Lambda function..."
    
    # Check if function directory exists
    if [ ! -d "$function_dir" ]; then
        echo "Error: Function directory $function_dir does not exist."
        return 1
    fi
    
    # Create zip file
    (cd "$function_dir" && zip -r "$output_file" .)
    
    echo "$function_name Lambda function packaged: $output_file"
}

# Package the Lambda functions
package_lambda "news_collector"
package_lambda "news_processor"

echo "Lambda packaging complete!"