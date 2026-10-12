from src.gradio_app import build_demo

if __name__ == "__main__":
    build_demo().launch(server_name="127.0.0.1", server_port=7861)
