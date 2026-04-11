# (IMPORT & CONFIG SAMA SEPERTI PUNYA KAMU — DIPERSINGKAT DI SINI)
from flask import Flask, request, jsonify
from docker import from_env, errors
import shutil, os, secrets, logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.exception(e)
    return jsonify(success=False, error=str(e)), 500

try:
    client = from_env()
except:
    client = None

USER_DATA_BASE_PATH = os.environ.get("USER_DATA_PATH", "/app/user_data")
MODULE_BASE_PATH = os.environ.get("MODULE_BASE_PATH", "/app/modules")

UPLOAD_FOLDERS = {
    "jupyter": os.path.join(MODULE_BASE_PATH, "jupyter"),
    "flask": os.path.join(MODULE_BASE_PATH, "flask"),
    "streamlit": os.path.join(MODULE_BASE_PATH, "streamlit"),
}

JUPYTER_MODULE_DIR = UPLOAD_FOLDERS["jupyter"]
FLASK_MODULE_DIR = UPLOAD_FOLDERS["flask"]
STREAMLIT_MODULE_DIR = UPLOAD_FOLDERS["streamlit"]

ACCESSIBLE_HOST = os.environ.get("ACCESSIBLE_HOST", "localhost")

JUPYTER_IMAGE = os.environ.get("JUPYTER_IMAGE")
FLASK_IMAGE = os.environ.get("FLASK_IMAGE")
STREAMLIT_IMAGE = os.environ.get("STREAMLIT_IMAGE")

HOST_USER_DATA_PATH = os.environ.get("HOST_USER_DATA_PATH", "/tmp/user_data")

DEFAULT_MEM_LIMIT = "256m"

# ================= MODULE DISCOVERY =================
def discover_modules():
    def list_files(path, ext):
        return [f for f in os.listdir(path) if f.endswith(ext)] if os.path.exists(path) else []

    return {
        "jupyter": list_files(JUPYTER_MODULE_DIR, ".ipynb"),
        "flask": list_files(FLASK_MODULE_DIR, ".py"),
        "streamlit": list_files(STREAMLIT_MODULE_DIR, ".py"),
    }

# ================= TOKEN =================
def get_or_create_token(token_file):
    if os.path.exists(token_file):
        return open(token_file).read().strip()

    token = secrets.token_hex(16)
    with open(token_file, "w") as f:
        f.write(token)

    return token

# ================= JUPYTER =================
def deploy_jupyter_internal(data, safe_group):
    module = data.get("module") or data.get("notebook")

    if not module:
        return jsonify(success=False, error="Module required"), 400

    src = os.path.join(JUPYTER_MODULE_DIR, module)
    if not os.path.isfile(src):
        return jsonify(success=False, error="Notebook not found"), 404

    container_name = f"praktikum_{safe_group}"

    group_dir = os.path.join(USER_DATA_BASE_PATH, safe_group)
    work_dir = os.path.join(group_dir, "work")
    host_work = os.path.join(HOST_USER_DATA_PATH, safe_group, "work")

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(host_work, exist_ok=True)

    dest = os.path.join(work_dir, module)
    if not os.path.exists(dest):
        shutil.copy(src, dest)

    token = get_or_create_token(os.path.join(group_dir, ".jupyter_token"))

    try:
        client.containers.get(container_name)
        return jsonify(success=True, message="Already running")
    except:
        pass

    c = client.containers.run(
        JUPYTER_IMAGE,
        name=container_name,
        detach=True,
        ports={"8888/tcp": None},
        volumes={host_work: {"bind": "/home/jovyan/work", "mode": "rw"}},
        command=[
            "start-notebook.sh",
            "--ServerApp.root_dir=/home/jovyan/work",
            f"--ServerApp.token={token}",
        ],
    )

    c.reload()
    port = c.attrs["NetworkSettings"]["Ports"]["8888/tcp"][0]["HostPort"]

    return jsonify(
        success=True,
        tool="jupyter",
        url=f"http://{ACCESSIBLE_HOST}:{port}/lab/tree/{module}?token={token}",
        group=safe_group
    )

# ================= FLASK =================
def deploy_flask(data, safe_group):
    module = data.get("module")
    src = os.path.join(FLASK_MODULE_DIR, module)

    if not os.path.isfile(src):
        return jsonify(success=False, error="Module not found"), 404

    name = f"praktikum_flask_{safe_group}"

    group_dir = os.path.join(USER_DATA_BASE_PATH, safe_group)
    work_dir = os.path.join(group_dir, "work")
    host_work = os.path.join(HOST_USER_DATA_PATH, safe_group, "work")

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(host_work, exist_ok=True)

    shutil.copy(src, os.path.join(work_dir, module))

    try:
        client.containers.get(name)
        return jsonify(success=True, message="Already running")
    except:
        pass

    c = client.containers.run(
        FLASK_IMAGE,
        name=name,
        detach=True,
        ports={"5000/tcp": None},
        volumes={host_work: {"bind": "/app/work", "mode": "rw"}},
        environment={"FLASK_APP_FILE": f"/app/work/{module}"}
    )

    c.reload()
    port = c.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]

    return jsonify(success=True, tool="flask", url=f"http://{ACCESSIBLE_HOST}:{port}")

# ================= STREAMLIT =================
def deploy_streamlit(data, safe_group):
    module = data.get("module")
    src = os.path.join(STREAMLIT_MODULE_DIR, module)

    if not os.path.isfile(src):
        return jsonify(success=False, error="Module not found"), 404

    name = f"praktikum_streamlit_{safe_group}"

    group_dir = os.path.join(USER_DATA_BASE_PATH, safe_group)
    work_dir = os.path.join(group_dir, "work")
    host_work = os.path.join(HOST_USER_DATA_PATH, safe_group, "work")

    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(host_work, exist_ok=True)

    shutil.copy(src, os.path.join(work_dir, module))

    try:
        client.containers.get(name)
        return jsonify(success=True, message="Already running")
    except:
        pass

    c = client.containers.run(
        STREAMLIT_IMAGE,
        name=name,
        detach=True,
        ports={"8501/tcp": None},
        volumes={host_work: {"bind": "/app/work", "mode": "rw"}},
        environment={"STREAMLIT_APP_FILE": f"/app/work/{module}"}
    )

    c.reload()
    port = c.attrs["NetworkSettings"]["Ports"]["8501/tcp"][0]["HostPort"]

    return jsonify(success=True, tool="streamlit", url=f"http://{ACCESSIBLE_HOST}:{port}")

# ================= DEPLOY =================
@app.route("/deploy", methods=["POST"])
def deploy():
    if not client:
        return jsonify(success=False, error="Docker unavailable"), 500

    raw = request.json or {}

    # BACKWARD COMPAT
    if "module_id" in raw:
        raw = {
            "group": str((raw.get("student_ids") or ["default"])[0]),
            "tool": "jupyter",
            "module": "praktikum_ml_iris.ipynb"
        }

    group = raw.get("group")
    tool = str(raw.get("tool", "jupyter")).lower()

    if not group:
        return jsonify(success=False, error="Group required"), 400

    safe_group = "".join(c for c in group if c.isalnum() or c in "-_")

    if tool == "jupyter":
        return deploy_jupyter_internal(raw, safe_group)
    if tool == "flask":
        return deploy_flask(raw, safe_group)
    if tool == "streamlit":
        return deploy_streamlit(raw, safe_group)

    return jsonify(success=False, error="Unknown tool"), 400

# ================= MODULES =================
@app.route("/modules")
def modules():
    return jsonify(success=True, modules=discover_modules())

# ================= UPLOAD =================
@app.route("/upload", methods=["POST"])
def upload():
    tool = request.form.get("tool")
    file = request.files.get("file")

    if tool not in UPLOAD_FOLDERS:
        return {"success": False, "error": "Invalid tool"}, 400

    path = os.path.join(UPLOAD_FOLDERS[tool], file.filename)
    file.save(path)

    return {"success": True, "filename": file.filename}

# ================= STOP =================
@app.route("/stop", methods=["POST"])
def stop():
    group = (request.json or {}).get("group")
    safe = "".join(c for c in group if c.isalnum() or c in "-_")

    for name in [
        f"praktikum_{safe}",
        f"praktikum_flask_{safe}",
        f"praktikum_streamlit_{safe}",
    ]:
        try:
            c = client.containers.get(name)
            c.stop(); c.remove()
        except:
            pass

    return jsonify(success=True)

@app.route("/health")
def health():
    return jsonify(status="healthy")