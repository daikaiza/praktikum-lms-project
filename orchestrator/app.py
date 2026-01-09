from flask import Flask, request, jsonify
from docker import from_env, errors
import shutil
import os
import secrets
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

try:
    client = from_env()
    logging.info("Docker client initialized")
except Exception as e:
    logging.error(f"Docker init failed: {e}")
    client = None

# ================= CONFIG =================
USER_DATA_BASE_PATH = os.environ.get("USER_DATA_PATH", "/app/user_data")
NOTEBOOK_SOURCE_DIR = os.environ.get(
    "NOTEBOOK_SOURCE_DIR",
    "/app/notebooks/"
)
DEFAULT_NOTEBOOK = "praktikum_ml_iris.ipynb"
ACCESSIBLE_HOST = os.environ.get("ACCESSIBLE_HOST", "localhost")
JUPYTER_IMAGE = os.environ.get("JUPYTER_IMAGE")
FLASK_IMAGE = os.environ.get("FLASK_IMAGE")
STREAMLIT_IMAGE = os.environ.get("STREAMLIT_IMAGE")

DEFAULT_MEM_LIMIT = "256m"
DEFAULT_CPU_NANO = int(0.1 * 1e9)

HOST_USER_DATA_PATH = os.environ["HOST_USER_DATA_PATH"]

# ================= HELPERS =================
def get_or_create_token(token_file):
    if os.path.exists(token_file):
        return open(token_file).read().strip()

    token = secrets.token_hex(16)
    with open(token_file, "w") as f:
        f.write(token)
    os.chown(token_file, 1000, 100)
    return token
def ensure_notebook_exists(dest_path, notebook_name):
    src = os.path.join(NOTEBOOK_SOURCE_DIR, notebook_name)

    if os.path.exists(dest_path):
        return

    if not os.path.isfile(src):
        raise FileNotFoundError(f"Notebook source not found: {src}")

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    shutil.copy(src, dest_path)

    try:
        os.chown(dest_path, 1000, 100)
    except Exception:
        pass
def deploy_jupyter_internal(data, safe_group):
    notebook = data.get("notebook", DEFAULT_NOTEBOOK)

    container_name = f"praktikum_{safe_group}"

    group_dir = os.path.join(USER_DATA_BASE_PATH, safe_group)
    work_dir = os.path.join(group_dir, "work")
    host_work_dir = os.path.join(HOST_USER_DATA_PATH, safe_group, "work")

    dest_notebook_path = os.path.join(work_dir, notebook)
    token_file = os.path.join(group_dir, ".jupyter_token")

    os.makedirs(work_dir, exist_ok=True)
    try:
        os.chown(work_dir, 1000, 100)
    except Exception:
        pass

    ensure_notebook_exists(dest_notebook_path, notebook)
    token = get_or_create_token(token_file)

    try:
        client.containers.get(container_name)
        return jsonify(success=True, message="Container already exists")
    except errors.NotFound:
        pass

    container = client.containers.run(
        JUPYTER_IMAGE,
        name=container_name,
        detach=True,
        ports={"8888/tcp": None},
        volumes={
            host_work_dir: {
                "bind": "/home/jovyan/work",
                "mode": "rw",
            }
        },
        command=[
            "start-notebook.sh",
            "--ServerApp.root_dir=/home/jovyan/work",
            f"--ServerApp.token={token}",
        ],
        environment={
            "JUPYTER_ENABLE_LAB": "yes",
            "NB_USER": "jovyan",
            "NB_UID": "1000",
            "CHOWN_HOME": "yes",
        },
        restart_policy={"Name": "no"},
    )

    container.reload()
    port = container.attrs["NetworkSettings"]["Ports"]["8888/tcp"][0]["HostPort"]

    return jsonify(
        success=True,
        url=f"http://{ACCESSIBLE_HOST}:{port}/lab/tree/{notebook}?token={token}",
        host_port=port,
        group=safe_group,
    )
# ================= ROUTES =================
@app.route("/deploy", methods=["POST"])
def deploy():
    if not client:
        return jsonify(success=False, error="Docker unavailable"), 500

    data = request.json or {}
    group = data.get("group")
    tool = data.get("tool", "jupyter")  # default tetap jupyter

    if not group:
        return jsonify(success=False, error="Group required"), 400

    safe_group = "".join(c for c in group if c.isalnum() or c in "-_")

    mem_limit = data.get("mem_limit", "512m")
    cpu_limit = float(data.get("cpu_limit", 0.5))
    nano_cpus = int(cpu_limit * 1e9)

    # =======================
    # JUPYTER
    # =======================
    if tool == "jupyter":
        return deploy_jupyter_internal(data, safe_group)

    # =======================
    # FLASK
    # =======================
    if tool == "flask":
        container_name = f"praktikum_flask_{safe_group}"

        try:
            client.containers.get(container_name)
            return jsonify(success=True, message="Container already running")
        except errors.NotFound:
            pass

        container = client.containers.run(
            FLASK_IMAGE,
            name=container_name,
            detach=True,
            ports={"5000/tcp": None},
            mem_limit=mem_limit,
            nano_cpus=nano_cpus,
            restart_policy={"Name": "no"},
        )

        container.reload()
        port = container.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]

        return jsonify(
            success=True,
            tool="flask",
            url=f"http://{ACCESSIBLE_HOST}:{port}",
            group=safe_group,
            host_port=port,
        )

    # =======================
    # STREAMLIT
    # =======================
    if tool == "streamlit":
        container_name = f"praktikum_streamlit_{safe_group}"

        try:
            client.containers.get(container_name)
            return jsonify(success=True, message="Container already running")
        except errors.NotFound:
            pass

        container = client.containers.run(
            STREAMLIT_IMAGE,
            name=container_name,
            detach=True,
            ports={"8501/tcp": None},
            mem_limit=mem_limit,
            nano_cpus=nano_cpus,
            restart_policy={"Name": "no"},
        )

        container.reload()
        port = container.attrs["NetworkSettings"]["Ports"]["8501/tcp"][0]["HostPort"]

        return jsonify(
            success=True,
            tool="streamlit",
            url=f"http://{ACCESSIBLE_HOST}:{port}",
            group=safe_group,
            host_port=port,
        )

    return jsonify(success=False, error=f"Unknown tool: {tool}"), 400

@app.route("/deploy/flask", methods=["POST"])
def deploy_flask():
    if not client:
        return jsonify(success=False, error="Docker unavailable"), 500

    data = request.json or {}
    group = data.get("group")

    if not group:
        return jsonify(success=False, error="Group required"), 400

    safe_group = "".join(c for c in group if c.isalnum() or c in "-_")
    container_name = f"praktikum_flask_{safe_group}"

    try:
        client.containers.get(container_name)
        return jsonify(success=True, message="Container already running")
    except errors.NotFound:
        pass

    container = client.containers.run(
        FLASK_IMAGE,
        name=container_name,
        detach=True,
        ports={"5000/tcp": None},
        mem_limit=data.get("mem_limit", "512m"),
        nano_cpus=int(float(data.get("cpu_limit", 0.5)) * 1e9),
        restart_policy={"Name": "no"},
    )

    container.reload()
    port = container.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]

    return jsonify(
        success=True,
        tool="flask",
        url=f"http://{ACCESSIBLE_HOST}:{port}",
        group=safe_group,
        host_port=port,
    )


@app.route("/deploy/streamlit", methods=["POST"])
def deploy_streamlit():
    if not client:
        return jsonify(success=False, error="Docker unavailable"), 500

    data = request.json or {}
    group = data.get("group")

    if not group:
        return jsonify(success=False, error="Group required"), 400

    safe_group = "".join(c for c in group if c.isalnum() or c in "-_")
    container_name = f"praktikum_streamlit_{safe_group}"

    try:
        client.containers.get(container_name)
        return jsonify(success=True, message="Container already running")
    except errors.NotFound:
        pass

    container = client.containers.run(
        STREAMLIT_IMAGE,
        name=container_name,
        detach=True,
        ports={"8501/tcp": None},
        mem_limit=data.get("mem_limit", "512m"),
        nano_cpus=int(float(data.get("cpu_limit", 0.5)) * 1e9),
        restart_policy={"Name": "no"},
    )

    container.reload()
    port = container.attrs["NetworkSettings"]["Ports"]["8501/tcp"][0]["HostPort"]

    return jsonify(
        success=True,
        tool="streamlit",
        url=f"http://{ACCESSIBLE_HOST}:{port}",
        group=safe_group,
        host_port=port,
    )

@app.route("/stop", methods=["POST"])
def stop():
    data = request.json or {}
    group = data.get("group")
    if not group:
        return jsonify(success=False, error="Group required"), 400

    name = f"praktikum_{group}"
    try:
        c = client.containers.get(name)
        c.stop()
        c.remove()
        return jsonify(success=True)
    except errors.NotFound:
        return jsonify(success=True)

@app.route("/health")
def health():
    return jsonify(status="healthy", docker=bool(client))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000, debug=True)
