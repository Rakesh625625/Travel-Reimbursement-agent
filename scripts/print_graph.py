import sys
import os

# Add root to python path to import the graph
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.graph import graph

def generate_graph_image():
    print("Generating LangGraph PNG visualization...")
    try:
        # Generates the PNG bytes via Mermaid API
        png_data = graph.get_graph().draw_mermaid_png()
        
        # Save to the root of the project
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out_path = os.path.join(root_dir, "langgraph_architecture.png")
        
        with open(out_path, "wb") as f:
            f.write(png_data)
            
        print(f"Successfully generated {out_path}")
    except Exception as e:
        print(f"Failed to generate PNG: {e}")

if __name__ == "__main__":
    generate_graph_image()
