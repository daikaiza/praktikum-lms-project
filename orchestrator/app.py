from flask import Flask, request, jsonify
from docker import from_env, errors
import os
import secrets
import shutil
import logging

# Basic logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
try:
    client = from_env()
    logging.info("Docker client initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize Docker client: {e}")
    client = None

# --- Configuration ---
USER_DATA_BASE_PATH = os.environ.get("USER_DATA_PATH", "/app/user_data")
SOURCE_NOTEBOOK_PATH = os.environ.get("SOURCE_NOTEBOOK_PATH", "/app/notebooks/praktikum_ml_iris.ipynb")
ACCESSIBLE_HOST = os.environ.get("ACCESSIBLE_HOST", "localhost")
JUPYTER_IMAGE = os.environ.get("JUPYTER_IMAGE", "ml-lab-single-user:latest")
# DEFAULT_MEM_LIMIT = "2g"
# DEFAULT_CPU_NANO = 2 * 10**9 
# DEFAULT_STORAGE_SIZE = "5G" 
# Adjusted for Local Laptop Testing
DEFAULT_MEM_LIMIT = "256m"       # Only 256MB RAM per container
DEFAULT_CPU_NANO = int(0.1 * 10**9)   # Only 10% of a CPU core per container
DEFAULT_STORAGE_SIZE = "1G"      # 1GB Storage limit

# --- Helper Functions ---
def get_or_create_token(token_file_path):
    if os.path.exists(token_file_path):
        with open(token_file_path, "r") as f:
            token = f.read().strip()
            if token:
                logging.info(f"Reusing existing token from {token_file_path}")
                return token
    token = secrets.token_hex(16)
    try:
        os.makedirs(os.path.dirname(token_file_path), exist_ok=True)
        with open(token_file_path, "w") as f:
            f.write(token)
        logging.info(f"Generated new token and saved to {token_file_path}")
        return token
    except IOError as e:
        logging.error(f"Error writing token file {token_file_path}: {e}")
        return None

def ensure_notebook_exists(dest_notebook_path):
    """Copies the source notebook if it doesn't exist in the destination."""
    if not os.path.exists(dest_notebook_path):
        if os.path.exists(SOURCE_NOTEBOOK_PATH):
            try:
                os.makedirs(os.path.dirname(dest_notebook_path), exist_ok=True)
                shutil.copy(SOURCE_NOTEBOOK_PATH, dest_notebook_path)
                logging.info(f"Copied notebook to {dest_notebook_path}")
                
                # --- Set ownership of the notebook file ---
                try:
                    os.chown(dest_notebook_path, 1000, 100) # UID 1000 (jovyan), GID 100 (users)
                    logging.info(f"Set ownership for {dest_notebook_path} to 1000:100")
                except Exception as e:
                     logging.warning(f"Could not chown file {dest_notebook_path}. Error: {e}")

            except Exception as e:
                logging.error(f"Failed to copy notebook from {SOURCE_NOTEBOOK_PATH} to {dest_notebook_path}: {e}")
        else:
            logging.warning(f"Source notebook {SOURCE_NOTEBOOK_PATH} not found. Cannot copy.")


# --- API Endpoints ---
@app.route("/deploy", methods=["POST"])
def deploy():
    if not client:
        return jsonify({"success": False, "error": "Docker client not available."}), 500

    data = request.json or {}
    group = data.get("group")
    notebook = data.get("notebook", "praktikum_ml_iris.ipynb") 
    mem_limit = data.get("ram", DEFAULT_MEM_LIMIT)
    
    cpu_cores = float(data.get("cpu", "1"))
    nano_cpus = int(cpu_cores * 10**9)
    
    storage_size = data.get("storage", DEFAULT_STORAGE_SIZE) 

    if not group:
        return jsonify({"success": False, "error": "Group name is required."}), 400

    safe_group_name = "".join(c for c in group if c.isalnum() or c in ('-', '_')).rstrip()
    if not safe_group_name:
        return jsonify({"success": False, "error": "Invalid group name after sanitization."}), 400

    container_name = f"praktikum_{safe_group_name}"
    host_group_dir_internal = os.path.join(USER_DATA_BASE_PATH, safe_group_name) 
    token_file = os.path.join(host_group_dir_internal, ".jupyter_token")
    work_dir = os.path.join(host_group_dir_internal, "work")
    dest_notebook_path = os.path.join(work_dir, notebook)

    logging.info(f"Attempting deployment for group '{safe_group_name}' (Container: {container_name})")

    try:
        # Create directories
        os.makedirs(work_dir, exist_ok=True)
        
        # --- Set ownership ---
        try:
            os.chown(host_group_dir_internal, 1000, 100) # Set ownership to jovyan(1000):users(100) to match on the jupyter container
            os.chown(work_dir, 1000, 100)
            logging.info(f"Set ownership for {work_dir} to 1000:100")
        except Exception as e:
            logging.warning(f"Could not chown directory {work_dir}. This might cause issues. Error: {e}")
        
        ensure_notebook_exists(dest_notebook_path)

    except Exception as e:
        logging.error(f"Error preparing directories/notebook for group {safe_group_name}: {e}")
        return jsonify({"success": False, "error": f"Failed to prepare storage: {e}"}), 500

    token = get_or_create_token(token_file)
    if not token:
         return jsonify({"success": False, "error": "Failed to get or create Jupyter token."}), 500

    try:
        os.chown(token_file, 1000, 100)
    except Exception as e:
        logging.warning(f"Could not chown token file {token_file}. Error: {e}")
    
    container = None
    try:
        container = client.containers.get(container_name)
        logging.info(f"Found existing container '{container_name}' with status: {container.status}")
        if container.status != "running":
            logging.info(f"Starting existing container '{container_name}'...")
            container.start()
            container.reload() 
        else:
             logging.info(f"Container '{container_name}' is already running.")

    except errors.NotFound:
        logging.info(f"Container '{container_name}' not found. Creating new container...")
        try:
            ports_config = {'8888/tcp': None}

            volume_config = {
                 work_dir: {
                     "bind": "/home/jovyan/work",
                     "mode": "rw"
                 }
            }

            storage_options = {"size": storage_size} if storage_size else {}

            container = client.containers.run(
                JUPYTER_IMAGE,
                name=container_name,
                detach=True,
                ports=ports_config,
                volumes=volume_config,
                environment={
                    "JUPYTER_TOKEN": token,
                    "JUPYTER_ENABLE_LAB": "yes",
                    "NB_USER": "jovyan",
                    "NB_UID": "1000",
                    "CHOWN_HOME": "yes",
                    "GRANT_SUDO": "no",
                    "NOTEBOOK_ARGS": f"--NotebookApp.token='{token}' --NotebookApp.notebook_dir='/home/jovyan/work'"
                },
                mem_limit=mem_limit,
                nano_cpus=nano_cpus,
                restart_policy={"Name": "no"}, 
                labels={"creator": "orchestrator", "group": safe_group_name}
            )
            logging.info(f"Successfully created and started container '{container_name}' (ID: {container.short_id})")
            container.reload()

        except errors.APIError as e:
            logging.error(f"Docker API error creating container for group {safe_group_name}: {e}")
            return jsonify({"success": False, "error": f"Docker error: {e}"}), 500
        except Exception as e:
            logging.error(f"Unexpected error creating container for group {safe_group_name}: {e}")
            return jsonify({"success": False, "error": f"Failed to create container: {e}"}), 500

    except Exception as e:
         logging.error(f"Error checking/starting container for group {safe_group_name}: {e}")
         return jsonify({"success": False, "error": f"Failed to ensure container running: {e}"}), 500

    try:
        port_mappings = container.attrs["NetworkSettings"]["Ports"].get("8888/tcp")
        if not port_mappings or not port_mappings[0] or 'HostPort' not in port_mappings[0]:
             logging.error(f"Could not retrieve host port mapping for container {container_name}")
             return jsonify({"success": False, "error": "Failed to get container port mapping."}), 500

        host_port = port_mappings[0]['HostPort']
        logging.info(f"Container '{container_name}' accessible on host port {host_port}")

        access_url = f"http://{ACCESSIBLE_HOST}:{host_port}/lab/tree/{notebook}?token={token}"

        return jsonify({
            "success": True,
            "url": access_url,
            "container_id": container.short_id,
            "group": safe_group_name,
            "host_port": host_port,
            "token": token
        })

    except Exception as e:
        logging.error(f"Error finalizing deployment response for group {safe_group_name}: {e}")
        return jsonify({"success": False, "error": f"Failed to get final container details: {e}"}), 500


@app.route("/stop", methods=["POST"])
def stop():
    if not client:
        return jsonify({"success": False, "error": "Docker client not available."}), 500

    data = request.json or {}
    group = data.get("group")

    if not group:
        return jsonify({"success": False, "error": "Group name is required."}), 400

    safe_group_name = "".join(c for c in group if c.isalnum() or c in ('-', '_')).rstrip()
    if not safe_group_name:
        return jsonify({"success": False, "error": "Invalid group name after sanitization."}), 400

    container_name = f"praktikum_{safe_group_name}"
    logging.info(f"Attempting to stop and remove container '{container_name}'...")

    try:
        container = client.containers.get(container_name)
        if container.status == "running":
            container.stop()
            logging.info(f"Container '{container_name}' stopped successfully.")
        else:
            logging.info(f"Container '{container_name}' was already stopped.")

        container.remove()
        logging.info(f"Container '{container_name}' removed.")
        
        return jsonify({"success": True, "message": f"Container {container_name} stopped and removed"})

    except errors.NotFound:
        logging.warning(f"Container '{container_name}' not found when trying to stop/remove.")
        return jsonify({"success": True, "message": f"Container {container_name} not found, assumed stopped."})
    except errors.APIError as e:
        logging.error(f"Docker API error stopping/removing container {container_name}: {e}")
        return jsonify({"success": False, "error": f"Docker error: {e}"}), 500
    except Exception as e:
        logging.error(f"Unexpected error stopping/removing container {container_name}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "docker_client": bool(client)})

if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", 4000))
    debug_mode = os.environ.get("FLASK_DEBUG", "True").lower() == "true"
    app.run(host=host, port=port, debug=debug_mode)
    