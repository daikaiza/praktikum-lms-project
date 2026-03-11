from flask import Flask, request, jsonify
from docker import from_env, errors
import shutil
import os
import secrets
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.exception(e)
    return jsonify(success=False, error=str(e)), 500

try:
    client = from_env()
    logging.info("Docker client initialized")
except Exception as e:
    logging.error(f"Docker init failed: {e}")
    client = None


# ================= CONFIG =================

USER_DATA_BASE_PATH = os.environ.get("USER_DATA_PATH", "/app/user_data")

MODULE_BASE_PATH = os.environ.get(
    "MODULE_BASE_PATH",
    "/app/modules"
)

JUPYTER_MODULE_DIR = os.path.join(MODULE_BASE_PATH, "jupyter")
FLASK_MODULE_DIR = os.path.join(MODULE_BASE_PATH, "flask")
STREAMLIT_MODULE_DIR = os.path.join(MODULE_BASE_PATH, "streamlit")

ACCESSIBLE_HOST = os.environ.get("ACCESSIBLE_HOST", "localhost")

JUPYTER_IMAGE = os.environ.get("JUPYTER_IMAGE")
FLASK_IMAGE = os.environ.get("FLASK_IMAGE")
STREAMLIT_IMAGE = os.environ.get("STREAMLIT_IMAGE")

HOST_USER_DATA_PATH = os.environ["HOST_USER_DATA_PATH"]

DEFAULT_MEM_LIMIT = "256m"
DEFAULT_CPU_NANO = int(0.1 * 1e9)


# ================= AUTO DISCOVERY =================

def discover_modules():

    modules = {
        "jupyter": [],
        "flask": [],
        "streamlit": []
    }

    if os.path.exists(JUPYTER_MODULE_DIR):
        modules["jupyter"] = [
            f for f in os.listdir(JUPYTER_MODULE_DIR)
            if f.endswith(".ipynb")
        ]

    if os.path.exists(FLASK_MODULE_DIR):
        modules["flask"] = [
            f for f in os.listdir(FLASK_MODULE_DIR)
            if f.endswith(".py")
        ]

    if os.path.exists(STREAMLIT_MODULE_DIR):
        modules["streamlit"] = [
            f for f in os.listdir(STREAMLIT_MODULE_DIR)
            if f.endswith(".py")
        ]

    return modules


# ================= HELPERS =================

def get_or_create_token(token_file):

    if os.path.exists(token_file):
        return open(token_file).read().strip()

    token = secrets.token_hex(16)

    with open(token_file, "w") as f:
        f.write(token)

    try:
        os.chown(token_file, 1000, 100)
    except:
        pass

    return token


# ================= JUPYTER DEPLOY =================

def deploy_jupyter_internal(data, safe_group):

    module = data.get("module")

    if not module:
        return jsonify(success=False, error="Module required"), 400

    src_notebook = os.path.join(JUPYTER_MODULE_DIR, module)

    if not os.path.isfile(src_notebook):
        return jsonify(success=False, error="Notebook not found"), 404

    container_name = f"praktikum_{safe_group}"

    group_dir = os.path.join(USER_DATA_BASE_PATH, safe_group)
    work_dir = os.path.join(group_dir, "work")

    host_work_dir = os.path.join(HOST_USER_DATA_PATH, safe_group, "work")

    os.makedirs(work_dir, exist_ok=True)

    dest_notebook = os.path.join(work_dir, module)

    if (not os.path.exists(dest_notebook)) or os.path.getsize(dest_notebook) == 0:
        shutil.copy(src_notebook, dest_notebook)

    token_file = os.path.join(group_dir, ".jupyter_token")
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
                "mode": "rw"
            }
        },
        command=[
            "start-notebook.sh",
            "--ServerApp.root_dir=/home/jovyan/work",
            f"--ServerApp.token={token}",
        ],
        restart_policy={"Name": "no"}
    )

    container.reload()

    port = container.attrs["NetworkSettings"]["Ports"]["8888/tcp"][0]["HostPort"]

    return jsonify(
        success=True,
        tool="jupyter",
        url=f"http://{ACCESSIBLE_HOST}:{port}/lab/tree/{module}?token={token}",
        host_port=port,
        group=safe_group
    )


# ================= DEPLOY ROUTE =================

@app.route("/deploy", methods=["POST"])
def deploy():

    if not client:
        return jsonify(success=False, error="Docker unavailable"), 500

    data = request.json or {}

    group = data.get("group")
    tool = data.get("tool")

    if not group:
        return jsonify(success=False, error="Group required"), 400

    safe_group = "".join(c for c in group if c.isalnum() or c in "-_")

    mem_limit = data.get("mem_limit", DEFAULT_MEM_LIMIT)
    cpu_limit = float(data.get("cpu_limit", 0.5))
    nano_cpus = int(cpu_limit * 1e9)

    # ================= JUPYTER =================

    if tool == "jupyter":
        return deploy_jupyter_internal(data, safe_group)

    # ================= FLASK =================

    if tool == "flask":

        module = data.get("module")

        if not module:
            return jsonify(success=False, error="Module required"), 400

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
            environment={
                "FLASK_APP_FILE": module
            },
            restart_policy={"Name": "no"}
        )

        container.reload()

        port = container.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]

        return jsonify(
            success=True,
            tool="flask",
            url=f"http://{ACCESSIBLE_HOST}:{port}",
            group=safe_group,
            host_port=port
        )

    # ================= STREAMLIT =================

    if tool == "streamlit":

        module = data.get("module")

        if not module:
            return jsonify(success=False, error="Module required"), 400

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
            environment={
                "STREAMLIT_APP_FILE": module
            },
            restart_policy={"Name": "no"}
        )

        container.reload()

        port = container.attrs["NetworkSettings"]["Ports"]["8501/tcp"][0]["HostPort"]

        return jsonify(
            success=True,
            tool="streamlit",
            url=f"http://{ACCESSIBLE_HOST}:{port}",
            group=safe_group,
            host_port=port
        )

    return jsonify(success=False, error="Unknown tool"), 400


# ================= MODULE LIST =================

@app.route("/modules", methods=["GET"])
def list_modules():

    return jsonify(
        success=True,
        modules=discover_modules()
    )


# ================= STOP =================

@app.route("/stop", methods=["POST"])
def stop():

    data = request.json or {}
    group = data.get("group")

    if not group:
        return jsonify(success=False, error="Group required"), 400

    safe_group = "".join(c for c in group if c.isalnum() or c in "-_")

    names = [
        f"praktikum_{safe_group}",
        f"praktikum_flask_{safe_group}",
        f"praktikum_streamlit_{safe_group}",
    ]

    for name in names:
        try:
            c = client.containers.get(name)
            c.stop()
            c.remove()
        except errors.NotFound:
            pass

    return jsonify(success=True)


# ================= HEALTH =================

@app.route("/health")
def health():
    return jsonify(status="healthy", docker=bool(client))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000, debug=True)