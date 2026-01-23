import requests
import zipfile
import io
import os
import time

from urllib.parse import quote

serverIP = "http://10.138.42.155:8095"

def submitJob(jobs):
    payload = {"jobs": jobs}
    headers = {"Content-Type": "application/json"}

    response = requests.post(f"{serverIP}/submitJobs", json=payload, headers=headers)
    response.raise_for_status()

def getResult(id):
    output_dir = f"./results_{id}"

    response = requests.get(f"{serverIP}/getResult/{quote(id)}")
    response.raise_for_status()

    os.makedirs(output_dir, exist_ok=True)

    if (response.status_code == 202):  # still in progress
        return False
    else:                              # results returned
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            zf.extractall(output_dir)
        return True

def main():
    id = "sp|P54025|RL41_METJA"
    seq = "MIPIKRSSRRWKKKGRMRWKWYKKRLRRLKRERKRARS"
    submitJob(id, seq)
    while not getResult(id):
        time.sleep(5)
    print("result saved")

if (__name__ == "__main__"):
    main()