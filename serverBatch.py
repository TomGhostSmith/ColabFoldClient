from flask import Flask, request, send_file, jsonify, abort
# from flask_cors import CORS, cross_origin
import os
import io
import zipfile
import subprocess
import re
import json
import time
import hashlib
import threading
import shutil

app = Flask(__name__)
# CORS(app, supports_credentials=True)  # Enables CORS for all routes

ALLOWED_IPS = {
    "10.176.62.5",
    "192.168.1.4",
    "192.168.1.3",
    "192.168.1.155",
    "10.138.42.155",
}

queue = []
lock = threading.Lock()
event = threading.Event()

def getSolidID(id)-> str:
    prefix = re.sub(r'[^\w.-]', '_', id)
    h = hashlib.md5(id.encode('utf-8')).hexdigest()[:8]  # first 8 chars
    return f"{prefix}_{h}"

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
    solidID = getSolidID(id)
    newFolder = f"server/output/{solidID}"

    if (os.path.exists(newFolder)):
        return jsonify({}), 200
    

    lock.acquire()
    queue.append((solidID, seq))
    event.set()
    print("event set")
    lock.release()

    return jsonify({}), 202


@app.route("/getResult/<id>", methods=["GET"])
def getResult(id):
    solidID = getSolidID(id)
    
    baseFolder = f"server/cache"
    newFolder = f"server/output/{solidID}"

    if (not os.path.exists(newFolder)):
        # check if ColabFold is done
        if (not os.path.exists(f"{baseFolder}/{solidID}.done.txt")):
            return jsonify({}), 202
        
        storeResult(solidID)

    return zip_files([f"{newFolder}/{f}" for f in os.listdir(newFolder)])

def zip_files(files):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            if not os.path.isfile(path):
                continue

            arcname = os.path.basename(path)

            zf.write(path, arcname=arcname)

    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="results.zip"
    )

def colabFold():
    global queue
    if os.path.exists("server/cache"):
        shutil.rmtree("server/cache")
    os.makedirs("server/cache")
    while True:
        print("colabFold is waiting")
        event.wait()
        print("colabFold received event")

        time.sleep(5)
        lock.acquire()
        queries = queue
        queue = []
        event.clear()
        lock.release()
        
        with open("server/input.fasta", 'wt') as fp:
            for id, seq in queries:
                fp.write(f">{id}\n{seq}\n")

        env = os.environ.copy()

        conda_prefix = env.get("CONDA_PREFIX")
        if not conda_prefix:
            raise RuntimeError("CONDA_PREFIX is not set")

        env["LD_LIBRARY_PATH"] = f"{conda_prefix}/lib:" + env.get("LD_LIBRARY_PATH", "")

        subprocess.run(f"colabfold_batch server/input.fasta server/cache --host-url http://localhost:8081/api", shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for id, _ in queries:
            storeResult(id)

def storeResult(solidID):
    baseFolder = f"server/cache"
    newFolder = f"server/output/{solidID}"

    if (not os.path.exists(newFolder)):
        solidIDprefix = solidID[:-9]
        offset = len(solidID)
        files = [
            f"{solidID}_env",
            f"{solidID}_coverage.png",
            f"{solidID}_pae.png",
            f"{solidID}_plddt.png",
            f"{solidID}_predicted_aligned_error_v1.json",
            f"{solidID}.a3m",
            f"{solidID}.done.txt"
        ]

        
        jsonPattern = re.compile(solidID + r"_scores_rank_[0-9]+_alphafold2_ptm_model_[0-9]+_seed_[0-9]+.json")
        pdbPattern = re.compile(solidID + r"_unrelaxed_rank_[0-9]+_alphafold2_ptm_model_[0-9]+_seed_[0-9]+.pdb")

        for file in os.listdir(baseFolder):
            if jsonPattern.fullmatch(file) or pdbPattern.fullmatch(file):
                files.append(file)

        os.makedirs(newFolder)
        for file in files:
            newFileName = solidIDprefix + file[offset:]
            shutil.move(f"{baseFolder}/{file}", f"{newFolder}/{newFileName}")


if __name__ == "__main__":
    p = subprocess.Popen(["bash", "startup.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    thread = threading.Thread(target=colabFold)
    thread.start()
    app.run(host="0.0.0.0", port=8095)  # do not run multi-thread. The app is not thread-safe
    p.terminate()