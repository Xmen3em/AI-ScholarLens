from src.gradio_app import build_demo

if __name__ == "__main__":
    build_demo().launch(server_name="0.0.0.0", server_port=7861)
