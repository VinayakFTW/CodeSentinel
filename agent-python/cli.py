import os
import sys
from setup import *
from dotenv import load_dotenv,set_key

load_dotenv()


def main():
    print("========================================================")
    print("           Code-Sentinel - Code Review Assistant             ")
    print("========================================================")
    print("Note: Please ensure Ollama is running in the background.\n")
    
    print("Checking Ollama status...")
    if not is_ollama_running():
        print("[Error] Ollama is not responding. Please ensure Ollama is running in the background.")
        sys.exit(1)
    print("[OK] Ollama is running.\n")
    
    app_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(app_dir, ".env")
    
    # Load existing .env if present
    load_dotenv(dotenv_path=env_path)

    while True:
        current_repo = os.environ.get("SOURCE_DIR")
        
        if current_repo:
            print(f"Current repository: {current_repo}")
            repo_path = input("Enter the absolute path to your codebase (Press Enter to keep current, or 'q' to quit): ").strip()
            if not repo_path:
                repo_path = current_repo
        else:
            repo_path = input("Enter the absolute path to your codebase (or 'q' to quit): ").strip()
        
        if repo_path.lower() in ('q', 'quit', 'exit'):
            print("Exiting Code-Sentinel.")
            sys.exit(0)
            
        repo_path = repo_path.strip('"').strip("'")

        if not os.path.exists(repo_path):
            print(f"Error: The path '{repo_path}' does not exist. Please try again.\n")
            continue
            
        # Check if environment is already configured for THIS repo
        is_configured = (
            os.environ.get("SOURCE_DIR") == repo_path and
            os.environ.get("PERSIST_DIRECTORY") and 
            os.environ.get("SYMBOL_DB_PATH") and 
            os.environ.get("DEP_GRAPH_PATH")
        )

        if not is_configured:
            print("Setting up environment variables in .env...")
            if not os.path.exists(env_path):
                open(env_path, 'a').close() # Create if it doesn't exist
                
            set_key(env_path, "SOURCE_DIR", repo_path)
            set_key(env_path, "PERSIST_DIRECTORY", os.path.join(app_dir, "chroma_db"))
            set_key(env_path, "SYMBOL_DB_PATH", os.path.join(app_dir, "symbol_index.db"))
            set_key(env_path, "DEP_GRAPH_PATH", os.path.join(app_dir, "dep_graph.graphml"))
            set_key(env_path, "DOCS_DIR", os.path.join(repo_path, "docs"))
            
            # Reload the updated .env
            load_dotenv(dotenv_path=env_path, override=True)
            
            print("Bootstrapping dependencies...")
            bootstrap_dependencies()
        else:
            print("Environment and dependencies are already set up for this repository.")

        # Check for existing indexes
        vector_dir = os.environ.get("PERSIST_DIRECTORY")
        symbol_db = os.environ.get("SYMBOL_DB_PATH")
        dep_graph = os.environ.get("DEP_GRAPH_PATH")

        needs_ingestion = True
        if os.path.exists(vector_dir) and os.path.exists(symbol_db) and os.path.exists(dep_graph):
            print("\n[INFO] Found existing vector store, dependency graph, and symbol index in the local directory.")
            choice = input("Do you want to re-index the repository? (y/N): ").strip().lower()
            if choice != 'y':
                needs_ingestion = False

        if needs_ingestion:
            print("\nStarting repository ingestion...")
            from ingest.run_ingest import run_ingest
            try:
                run_ingest(repo_path, clean=True)
                print("\nIngestion complete!")
            except Exception as e:
                print(f"\nIngestion failed: {e}")
                print("Returning to repository selection...\n")
                continue
        else:
            print("\nSkipping ingestion. Using existing indexes.")
            
        # Inner loop for the Sentinel CLI
        while True:
            print("\n=======================================")
            print("[1] Start Code-Sentinel CLI")
            print("[2] Change Repository")
            print("[3] Exit Application")
            print("=======================================")
            choice = input("Choice: ").strip()
            
            if choice == "1":
                from main import main as inititate_sentinel
                try:
                    inititate_sentinel()
                except Exception as e:
                    print(f"An error occurred while running the CLI: {e}")
            elif choice == "2":
                print("\nChanging repository...")
                break 
            elif choice == "3":
                print("Exiting Code-Sentinel.")
                sys.exit(0)
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFatal error: {e}")
        input("Press Enter to close...")