cd agent-python
pyinstaller cli.py --name CodeSentinel --onedir \
  --exclude-module magic \
  --exclude-module unstructured \
  --collect-all chromadb \
  --collect-all posthog \
  --collect-all langchain_chroma \
  --collect-all langchain_ollama \
  --collect-all langchain_huggingface \
  --collect-all langchain_core \
  --collect-all sentence_transformers \
  --collect-all tokenizers \
  --collect-all huggingface_hub \
  --clean