from flask import Flask, request, send_file, jsonify, abort
# from flask_cors import CORS, cross_origin
import os
import io
import zipfile
import subprocess

app = Flask(__name__)
# CORS(app, supports_credentials=True)  # Enables CORS for all routes

ALLOWED_IPS = {
    "10.176.62.5",
    "192.168.1.4",
    "192.168.1.3",
    "192.168.1.155",
    "10.138.42.155",
}

processes:dict[str, subprocess.Popen] = {}

@app.before_request
def restrict_ip():
    client_ip = request.remote_addr
    if client_ip not in ALLOWED_IPS:
        abort(403)

# @cross_origin(methods=["POST"])
@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()
    if not data or "id" not in data or "seq" not in data:
        return jsonify({"error": "request format error"}), 400

    id = data["id"]
    seq = data["seq"]
    if id in processes:
        return jsonify({"error": "already submitted"}), 400

    with open("server/input.fasta", 'wt') as fp:
        fp.write(">" + id + "\n")
        fp.write(seq)


    env = os.environ.copy()

    conda_prefix = env.get("CONDA_PREFIX")
    if not conda_prefix:
        raise RuntimeError("CONDA_PREFIX is not set")

    env["LD_LIBRARY_PATH"] = f"{conda_prefix}/lib:" + env.get("LD_LIBRARY_PATH", "")

    # subprocess.run("conda run -n ColabFold --no-capture-output colabfold_batch server/input.fasta server/output --host-url http://localhost:8081/api", shell=True)
    p:subprocess.Popen = subprocess.Popen(f"colabfold_batch server/input.fasta server/output_{id} --host-url http://localhost:8081/api", shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    processes[id] = p

    return jsonify({}), 202


@app.route("/getResult/<id>", methods=["GET"])
def getResult(id):
    p = processes.get(id)
    if not p:
        return jsonify({"error": "process already finished"}), 400
    
    if (p.poll() is not None):
        processes.pop(id)
        files = [f"server/output_{id}/{f}" for f in os.listdir(f"server/output_{id}")]

        return zip_files(files)
    else:
        return jsonify({}), 202

def zip_files(files):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            if not os.path.isfile(path):
                continue  # or raise an error

            # Name inside the zip (no full absolute paths!)
            arcname = os.path.basename(path)

            zf.write(path, arcname=arcname)

    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="results.zip"
    )


if __name__ == "__main__":
    p = subprocess.Popen(["bash", "startup.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    app.run(host="0.0.0.0", port=8095)
    p.terminate()