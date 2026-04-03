#!/bin/bash

set -e  # Exit on error

echo "🚀 Setting up embedding models for local development..."

# Get the repo root (where the script is executed from)
REPO_ROOT="$(pwd)"

# Create the model cache directory
MODEL_DIR="/tmp/fastembed_cache/ibm-granite/granite-embedding-30m-english"
echo "📁 Creating directory: $MODEL_DIR"
mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

# Download all required model files
echo "⬇️  Downloading model files from HuggingFace..."

echo "  - config.json"
curl -L -o config.json \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/config.json"

echo "  - tokenizer.json"
curl -L -o tokenizer.json \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/tokenizer.json"

echo "  - tokenizer_config.json"
curl -L -o tokenizer_config.json \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/tokenizer_config.json"

echo "  - special_tokens_map.json"
curl -L -o special_tokens_map.json \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/special_tokens_map.json"

echo "  - model.onnx (this may take a while...)"
curl -L -o model.onnx \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/model.onnx"

echo "✅ Model files downloaded successfully!"

# Quantize the model for better performance
echo ""
echo "📦 Installing onnxruntime and onnx via poetry..."
cd "$REPO_ROOT"
poetry run pip install onnxruntime onnx

echo "⚙️  Quantizing model..."
poetry run python - <<EOF
from onnxruntime.quantization import quantize_dynamic, QuantType
print("  Applying dynamic quantization...")
quantize_dynamic(
    "$MODEL_DIR/model.onnx",
    "$MODEL_DIR/model_optimized.onnx",
    weight_type=QuantType.QUInt8,
)
print("  ✅ Quantization complete!")
EOF

echo "🗑️  Removing original unquantized model to save space..."
rm "$MODEL_DIR/model.onnx"
echo "✅ Model quantization complete!"

# Set up environment variable
echo ""
echo "🔧 Setting up environment variables..."
ENV_FILE="$REPO_ROOT/env.conf"

if [ -f "$ENV_FILE" ]; then
    # Check if EMBEDDING_MODEL_PATH already exists (uncommented)
    if grep -q "^EMBEDDING_MODEL_PATH=" "$ENV_FILE"; then
        echo "  ℹ️  EMBEDDING_MODEL_PATH already exists in env.conf"
    # Check if commented placeholder exists
    elif grep -q "^# EMBEDDING_MODEL_PATH=" "$ENV_FILE"; then
        # Replace the commented placeholder line
        sed -i.bak "s|^# EMBEDDING_MODEL_PATH=.*|EMBEDDING_MODEL_PATH=$MODEL_DIR|" "$ENV_FILE"
        rm "$ENV_FILE.bak"
        echo "  ✅ Replaced EMBEDDING_MODEL_PATH placeholder in env.conf"
    else
        echo "EMBEDDING_MODEL_PATH=$MODEL_DIR" >> "$ENV_FILE"
        echo "  ✅ Added EMBEDDING_MODEL_PATH to env.conf"
    fi
else
    echo "  ⚠️  env.conf not found at $ENV_FILE"
    echo "  Please add this to your env.conf manually:"
    echo "  EMBEDDING_MODEL_PATH=$MODEL_DIR"
fi

echo ""
echo "🎉 Setup complete!"
echo ""
echo "📝 Next steps:"
echo "  1. The EMBEDDING_MODEL_PATH has been added to env.conf"
echo "  2. Run your application locally with: poetry run uvicorn src.app.main:app"
echo ""